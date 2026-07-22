#!/usr/bin/env python3
"""Terminal UI for the Lumenate Nova light/sound generator.

Search YouTube Music (ytmusicapi), download audio (yt-dlp), then run a session that
drives the Nova's strobe in one of four modes while the audio plays:

  light      — generated light preset only (no audio)
  music      — generated light preset alongside the downloaded track
  reactive   — light duty follows the track's loudness envelope (flash stays rhythmic)
  isochronic — synthesised isochronic tones phase-locked to the light (no download)

Run:  python3 nova/tui.py        (needs bleak, textual, ytmusicapi, yt-dlp, ffmpeg)

⚠️ Photosensitive-seizure risk: this is a 7–18 Hz stroboscope. See the README.
"""
from __future__ import annotations

import asyncio
import os

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import (Button, DataTable, Footer, Header, Input, Label,
                             ListItem, ListView, Log, ProgressBar, Select, Static)

from . import generator as gen
from . import music
from .core import Nova

MODES = [("light — preset only", "light"),
         ("music — preset + your track", "music"),
         ("reactive — light follows the music", "reactive"),
         ("isochronic — generated tones + light", "isochronic")]
PRESETS = [(p, p) for p in gen.PRESETS]


def _dur_to_minutes(s: str) -> float | None:
    try:
        parts = [int(p) for p in s.split(":")]
    except ValueError:
        return None
    sec = 0
    for p in parts:
        sec = sec * 60 + p
    return sec / 60.0 if sec else None


class NovaTUI(App):
    CSS = """
    #left { width: 55%; }
    #right { width: 45%; padding: 0 1; }
    #results { height: 1fr; }
    #recommended { height: 10; border: round $accent; }
    #log { height: 1fr; border: round $accent; }
    #selected { color: $accent; height: 3; }
    Select, Input, Button { margin: 0 0 1 0; }
    """
    BINDINGS = [("q", "quit", "Quit"), ("s", "stop", "Stop session")]

    def __init__(self):
        super().__init__()
        self.rows: dict = {}          # DataTable row key -> Track
        self.selected: music.Track | None = None
        self.audio_path: str | None = None
        self.session_running = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            with Vertical(id="left"):
                yield Input(placeholder="Search YouTube Music… (Enter)", id="query")
                yield Label("Recommended (Enter to search):")
                yield ListView(*[ListItem(Label(lbl), id=f"rec{i}")
                                 for i, (lbl, _, _) in enumerate(music.RECOMMENDED)],
                               id="recommended")
                yield DataTable(id="results")
            with Vertical(id="right"):
                yield Static("No track selected", id="selected")
                yield Select(MODES, value="reactive", id="mode", allow_blank=False)
                yield Select(PRESETS, value="relax", id="preset", allow_blank=False)
                yield Input(placeholder="minutes (blank = match track / preset default)",
                            id="minutes")
                with Horizontal():
                    yield Button("Run session", variant="success", id="run")
                    yield Button("Stop", variant="error", id="stop")
                yield ProgressBar(total=100, show_eta=False, id="dl")
                yield Log(id="log", highlight=False)
        yield Footer()

    def on_mount(self):
        t = self.query_one("#results", DataTable)
        t.add_columns("Title", "Artist", "Dur")
        t.cursor_type = "row"
        self._log("Search a track (or pick a recommendation), select a result, then Run.")
        self._log("Modes: light / music / reactive / isochronic. Nova must be in pairing mode.")

    # ---------- helpers ----------
    def _log(self, msg: str):
        self.query_one("#log", Log).write_line(msg)

    def _set_progress(self, frac: float, note: str):
        self.query_one("#dl", ProgressBar).update(progress=int(frac * 100))
        if note in ("converting", "done"):
            self._log(f"download: {note}")

    # ---------- search ----------
    @on(Input.Submitted, "#query")
    def _on_query(self, e: Input.Submitted):
        if e.value.strip():
            self.do_search(e.value.strip(), "songs")

    @on(ListView.Selected, "#recommended")
    def _on_rec(self, e: ListView.Selected):
        idx = int(e.item.id.removeprefix("rec"))
        lbl, query, kind = music.RECOMMENDED[idx]
        self.query_one("#query", Input).value = query
        self.do_search(query, kind)

    @work(thread=True, exclusive=True, group="search")
    def do_search(self, query: str, kind: str):
        self.call_from_thread(self._log, f"searching: {query!r} ({kind}) …")
        try:
            tracks = music.search(query, kind=kind, limit=20)
        except Exception as ex:
            self.call_from_thread(self._log, f"search failed: {ex}")
            return
        self.call_from_thread(self._fill_results, tracks)

    def _fill_results(self, tracks):
        t = self.query_one("#results", DataTable)
        t.clear()
        self.rows.clear()
        for tr in tracks:
            key = t.add_row(tr.title[:40], tr.artist[:24], tr.duration)
            self.rows[key] = tr
        self._log(f"{len(tracks)} results.")

    @on(DataTable.RowSelected, "#results")
    def _on_row(self, e: DataTable.RowSelected):
        tr = self.rows.get(e.row_key)
        if tr:
            self.selected = tr
            self.query_one("#selected", Static).update(f"▶ {tr.label}")

    # ---------- run / stop ----------
    @on(Button.Pressed, "#run")
    def _on_run(self, _):
        if self.session_running:
            self._log("a session is already running (press Stop first).")
            return
        mode = self.query_one("#mode", Select).value
        preset = self.query_one("#preset", Select).value
        mins_raw = self.query_one("#minutes", Input).value.strip()
        minutes = float(mins_raw) if mins_raw else None
        if mode in ("music", "reactive") and not self.selected:
            self._log("select a track first (this mode needs audio).")
            return
        self.run_session(mode, preset, minutes)

    @on(Button.Pressed, "#stop")
    def action_stop(self, *_):
        if self.session_running:
            self.workers.cancel_group(self, "session")
            self._log("stopping…")

    @work(thread=True, exclusive=True, group="download")
    def _download_then(self, video_id, mode, preset, minutes):
        try:
            path = music.download(video_id, progress=lambda f, n:
                                  self.call_from_thread(self._set_progress, f, n))
        except Exception as ex:
            self.call_from_thread(self._log, f"download failed: {ex}")
            return
        self.audio_path = path
        self.call_from_thread(self._log, f"downloaded: {os.path.basename(path)}")
        self.call_from_thread(self._start_session_worker, mode, preset, minutes, path)

    def run_session(self, mode, preset, minutes):
        if mode in ("music", "reactive"):
            self._log(f"downloading {self.selected.label} …")
            self._download_then(self.selected.video_id, mode, preset, minutes)
        else:
            self._start_session_worker(mode, preset, minutes, None)

    def _start_session_worker(self, mode, preset, minutes, path):
        self.session(mode, preset, minutes, path)

    @work(exclusive=True, group="session")
    async def session(self, mode, preset, minutes, path):
        self.session_running = True
        # default duration: match track for music modes, else preset default
        if minutes is None and self.selected:
            minutes = _dur_to_minutes(self.selected.duration)
        self._log(f"connecting to Nova… (mode={mode}, preset={preset})")
        try:
            nova = await Nova.connect(timeout=20.0)
        except Exception as ex:
            self._log(f"connect failed: {ex}  (is it in pairing mode / flashing blue?)")
            self.session_running = False
            return
        info = None
        try:
            info = await nova.read_info()
            self._log(f"connected: {info.model} fw {info.firmware} battery {info.battery}%")

            def tick(t, f, d, dur):
                if int(t * 10) % 10 == 0:
                    self.call_from_thread(self._log,
                        f"  t={t:5.1f}/{dur:.0f}s  {f:5.2f} Hz  duty {d*100:4.1f}%")

            segs = gen.PRESETS[preset](minutes) if minutes else gen.PRESETS[preset]()
            if mode == "light":
                await gen.play_segments(nova, segs, on_tick=tick)
            elif mode == "music":
                await gen.play_with_audio(nova, segs, path, on_tick=tick)
            elif mode == "isochronic":
                wav = os.path.join(music.DEFAULT_MUSIC_DIR, f"_iso_{preset}.wav")
                os.makedirs(music.DEFAULT_MUSIC_DIR, exist_ok=True)
                gen.synth_isochronic(segs, wav)
                await gen.play_with_audio(nova, segs, wav, on_tick=tick)
            elif mode == "reactive":
                await gen.play_reactive(nova, path, on_tick=tick)
            self._log("session complete ✅")
        except asyncio.CancelledError:
            self._log("session stopped.")
        except Exception as ex:
            self._log(f"session error: {ex}")
        finally:
            try:
                await nova.stop()
            finally:
                await nova.disconnect()
            self.session_running = False


def main():
    NovaTUI().run()


if __name__ == "__main__":
    main()
