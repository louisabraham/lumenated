#!/usr/bin/env python3
"""Minimal interactive session setup for the Lumenate Nova.

A short sequential prompt — one decision at a time:
  1. Mode  (only audio modes then ask you to choose music)
  2. Preset
  3. Length
  4. Connect the Nova (last step; with pairing instructions + retry)
  5. Press the Nova's power button to start — and again to stop — as in the app.

No full-screen UI, no mouse.

Run:  lumenated-play        (music modes need the [music] extra: ytmusicapi + yt-dlp + ffmpeg)

⚠️ Photosensitive-seizure risk: this is a 7–18 Hz stroboscope. See the README.
"""
from __future__ import annotations

import asyncio
import os
import sys

from . import generator as gen
from .core import Nova

# ---- minimal styling: one accent, dim for secondary; plain when not a TTY / NO_COLOR ----
_COLOR = sys.stdout.isatty() and "NO_COLOR" not in os.environ


def _c(s, code):
    return f"\033[{code}m{s}\033[0m" if _COLOR else s


def bold(s): return _c(s, "1")
def dim(s): return _c(s, "2")
def accent(s): return _c(s, "36")       # cyan
def ok(s): return _c(s, "32")           # green


MODES = [
    ("reactive", "light follows the music's loudness"),
    ("music", "generated light preset alongside your track"),
    ("light", "generated light preset only — no audio"),
    ("isochronic", "generated tones phase-locked to the light — no download"),
]
PRESET_DESC = {
    "relax": "settle to ~10 Hz alpha, breathe, ease out",
    "sleep": "wind down from alpha to delta, fade to dark",
    "explore": "theta↔alpha journey with slow drift",
    "energize": "higher, alerting band (keep it short)",
}


class Abort(Exception):
    pass


def _read(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        raise Abort()


def choose(title: str, options, default: int = 0) -> int:
    """Numbered single-choice. options = [(name, description)]. Returns the index."""
    print(f"\n{bold(title)}")
    for i, (name, desc) in enumerate(options):
        marker = accent("›") if i == default else " "
        num = accent(f"{i + 1}")
        print(f"  {marker} {num}  {name:<11} {dim(desc)}")
    while True:
        raw = _read(f"  choose {dim(f'[{default + 1}]')} ")
        if not raw:
            return default
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw) - 1
        print(dim("  enter a number from the list"))


def ask(prompt: str, default: str | None = None) -> str:
    suffix = dim(f" [{default}]") if default else ""
    val = _read(f"{prompt}{suffix} ")
    return val or (default or "")


# --------------------------------------------------------------------------
# Music selection (only for modes that use audio)
# --------------------------------------------------------------------------
def pick_track():
    from . import music
    while True:
        q = ask("\n" + bold("Music") + " — search YouTube Music" + dim(" (blank = suggestions)"))
        if not q:
            idx = choose("Suggestions", [(lbl, "") for lbl, _ in music.RECOMMENDED])
            q = music.RECOMMENDED[idx][1]
        print(dim(f"  searching {q!r} …"))
        try:
            tracks = music.search_playable(q, limit=10)
        except Exception as ex:
            print(dim(f"  search failed: {ex}"))
            continue
        if not tracks:
            print(dim("  no results — try another search"))
            continue
        opts = [(f"{t.title[:44]}", f"{t.artist[:22]}  {t.duration}") for t in tracks]
        opts.append(("search again", ""))
        idx = choose("Results", opts)
        if idx == len(tracks):
            continue
        return tracks[idx]


def download(track):
    from . import music

    def prog(frac, note):
        sys.stdout.write(f"\r  downloading {int(frac * 100):3d}%  {dim(note)}      ")
        sys.stdout.flush()
        if note == "done":
            print()
    print(dim(f"  fetching “{track.title}” …"))
    return music.download(track.video_id, progress=prog)


# --------------------------------------------------------------------------
# Pairing (the final step) + power-button start
# --------------------------------------------------------------------------
async def connect_with_retry():
    print("\n" + bold("Connect your Nova"))
    print(dim("  1. In the Lumenate app: Settings → your Nova → “Forget this Nova”."))
    print(dim("  2. Hold the Nova's power button until it flashes blue (pairing mode)."))
    while True:
        print(dim("  scanning for a Nova in pairing mode …"))
        try:
            return await Nova.connect(timeout=20.0)
        except Exception as ex:
            print(f"  {dim('no Nova found —')} {dim(str(ex).splitlines()[0][:60])}")
            ans = (await asyncio.to_thread(input, f"  {accent('[Enter]')} retry   {accent('[q]')} cancel: ")).strip().lower()
            if ans == "q":
                return None


async def wait_to_start(nova) -> bool:
    """Wait for a Nova power-button press (or Enter). Returns False if aborted."""
    start = asyncio.Event()

    def on_remote(ev):
        if ev == "POWER":
            start.set()

    try:
        await nova.subscribe_remote(on_remote)
    except Exception:
        pass  # fall back to Enter-only
    print("\n  " + ok("connected.") + dim("  press the Nova's power button to start"
                                          " (or Enter here) — Ctrl-C to cancel."))
    enter = asyncio.create_task(asyncio.to_thread(sys.stdin.readline))
    power = asyncio.create_task(start.wait())
    try:
        await asyncio.wait({enter, power}, return_when=asyncio.FIRST_COMPLETED)
    except (KeyboardInterrupt, asyncio.CancelledError):
        return False
    finally:
        for t in (enter, power):
            if not t.done():
                t.cancel()
    return True


async def _play(mode, preset, minutes, path, nova, tick):
    segs = gen.PRESETS[preset](minutes) if minutes else gen.PRESETS[preset]()
    if mode == "light":
        await gen.play_segments(nova, segs, on_tick=tick)
    elif mode == "music":
        await gen.play_with_audio(nova, segs, path, on_tick=tick)
    elif mode == "isochronic":
        from . import music
        wav = os.path.join(music.DEFAULT_MUSIC_DIR, f"_iso_{preset}.wav")
        os.makedirs(music.DEFAULT_MUSIC_DIR, exist_ok=True)
        gen.synth_isochronic(segs, wav)
        await gen.play_with_audio(nova, segs, wav, on_tick=tick)
    else:  # reactive
        await gen.play_reactive(nova, path, on_tick=tick)


async def connect_and_run(mode, preset, minutes, path):
    nova = await connect_with_retry()
    if nova is None:
        print(dim("  cancelled."))
        return
    try:
        info = await nova.read_info()
        print(f"  {info.model}  fw {info.firmware}  battery {info.battery}%")
        if not await wait_to_start(nova):
            print("\n  " + dim("cancelled."))
            return
        print(dim("  running — press the power button again (or Ctrl-C) to stop.\n"))

        # a second power press stops the session
        stop = asyncio.Event()
        await nova.subscribe_remote(lambda ev: stop.set() if ev == "POWER" else None)

        def tick(t, f, d, dur):
            sys.stdout.write(
                f"\r  {ok('●')} {f:5.2f} Hz   duty {d * 100:4.1f}%   "
                f"{dim(f't {t:5.1f}/{dur:.0f}s')}   ")
            sys.stdout.flush()

        play = asyncio.create_task(_play(mode, preset, minutes, path, nova, tick))
        stopper = asyncio.create_task(stop.wait())
        await asyncio.wait({play, stopper}, return_when=asyncio.FIRST_COMPLETED)
        if not play.done():
            play.cancel()
        stopper.cancel()
        await asyncio.gather(play, return_exceptions=True)
        print("\n  " + (dim("stopped.") if stop.is_set() else ok("done ✅")))
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n  " + dim("stopped."))
    finally:
        try:
            await nova.stop()
        finally:
            await nova.disconnect()


def main():
    print(bold("lumenated") + dim(" · session setup"))
    try:
        mode = MODES[choose("Mode", MODES)][0]

        track = path = None
        if mode in ("reactive", "music"):
            track = pick_track()

        preset = list(gen.PRESETS)[
            choose("Preset", [(p, PRESET_DESC[p]) for p in gen.PRESETS])]

        mr = ask("\n" + bold("Length") + " in minutes" + dim(" (blank = match track / preset)"))
        minutes = float(mr) if mr else None

        bits = [accent(mode), accent(preset), f"{minutes:g} min" if minutes else "auto"]
        if track:
            bits.append(f"“{track.title}”")
        print("\n  " + dim("→ ") + "  ·  ".join(bits))

        # prepare audio before pairing so the session can start the instant you press the button
        if track:
            path = download(track)

        asyncio.run(connect_and_run(mode, preset, minutes, path))
    except Abort:
        print("\n" + dim("cancelled."))


if __name__ == "__main__":
    main()
