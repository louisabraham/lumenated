#!/usr/bin/env python3
"""YouTube Music search + audio download for the Nova session generator.

Thin, UI-agnostic wrappers over ytmusicapi (search) and yt-dlp (download-to-mp3).
Downloads are converted to mp3 so macOS `afplay` can play them and `generator.analyze`
(ffmpeg) can read them.

Note: yt-dlp here is expected to be installed with a benign cookies stub (see
tools/install_ytdlp_stub.py) — no browser-cookie access is used or needed.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

# Where downloads land. Override with $LUMENATED_MUSIC_DIR; defaults to ./music in the CWD.
DEFAULT_MUSIC_DIR = os.environ.get(
    "LUMENATED_MUSIC_DIR", os.path.join(os.getcwd(), "music"))

# Curated starting points (see docs/GENERATOR_DESIGN.md §4): slow, spacious, emotionally
# warm — pairs well with meditative flicker. (label, search-query) — searched as playable tracks.
RECOMMENDED = [
    ("Jon Hopkins — Music for Psychedelic Therapy", "Jon Hopkins Music for Psychedelic Therapy"),
    ("Brian Eno — Music for Airports", "Brian Eno Music for Airports"),
    ("Stars of the Lid — Refinement of the Decline", "Stars of the Lid Refinement of the Decline"),
    ("Nils Frahm — Spaces", "Nils Frahm Spaces"),
    ("Hania Rani — Esja", "Hania Rani Esja"),
    ("Max Richter — Sleep", "Max Richter Sleep"),
    ("Hammock — Departure Songs", "Hammock Departure Songs"),
    ("Ólafur Arnalds — Island Songs", "Olafur Arnalds Island Songs"),
    ("Ambient / drone (meditation)", "ambient drone deep meditation"),
    ("Theta frame-drum (~7 Hz feel)", "shamanic drumming theta meditation"),
]


@dataclass
class Track:
    video_id: str
    title: str
    artist: str
    duration: str = ""
    kind: str = "song"

    @property
    def label(self) -> str:
        d = f"  [{self.duration}]" if self.duration else ""
        return f"{self.title} — {self.artist}{d}"


def search(query: str, kind: str = "songs", limit: int = 15) -> list[Track]:
    from ytmusicapi import YTMusic
    yt = YTMusic()
    out = []
    for r in yt.search(query, filter=kind, limit=limit):
        vid = r.get("videoId")
        if not vid:
            continue
        artist = ", ".join(a["name"] for a in r.get("artists", []) if a.get("name"))
        out.append(Track(vid, r.get("title", "?"), artist or r.get("author", ""),
                         r.get("duration", "") or "", r.get("resultType", kind)))
    return out


def search_playable(query: str, limit: int = 20) -> list[Track]:
    """Search for individually-playable tracks (songs, then videos as fallback).

    Avoids the albums/playlists filters, whose results have no videoId and can't be
    downloaded directly.
    """
    out = search(query, kind="songs", limit=limit)
    if len(out) < 5:
        seen = {t.video_id for t in out}
        for t in search(query, kind="videos", limit=limit):
            if t.video_id not in seen:
                out.append(t)
                seen.add(t.video_id)
    return out[:limit]


def download(video_id: str, outdir: str = DEFAULT_MUSIC_DIR, progress=None) -> str:
    """Download a track's audio as mp3. `progress` is called with (fraction, note)."""
    import yt_dlp

    os.makedirs(outdir, exist_ok=True)

    def hook(d):
        if not progress:
            return
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            frac = (d.get("downloaded_bytes", 0) / total) if total else 0.0
            progress(min(0.98, frac), "downloading")
        elif d["status"] == "finished":
            progress(0.99, "converting")

    opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(outdir, "%(title).80s [%(id)s].%(ext)s"),
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3",
                            "preferredquality": "192"}],
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "progress_hooks": [hook],
    }
    url = f"https://music.youtube.com/watch?v={video_id}"
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    # resolve final mp3 path
    reqs = info.get("requested_downloads") or []
    if reqs and reqs[0].get("filepath"):
        path = os.path.splitext(reqs[0]["filepath"])[0] + ".mp3"
        if os.path.exists(path):
            if progress:
                progress(1.0, "done")
            return path
    with yt_dlp.YoutubeDL(opts) as ydl:
        base = os.path.splitext(ydl.prepare_filename(info))[0] + ".mp3"
    if progress:
        progress(1.0, "done")
    return base
