#!/usr/bin/env python3
"""Minimal interactive session setup for the Lumenate Nova.

A short sequential prompt — one decision at a time:
  1. Mode  (only audio modes then ask you to choose music)
  2. Preset
  3. Length
  4. Connect the Nova (last step; with pairing instructions + retry)
  5. Press the Nova's power button to start; power or space to pause/resume;
     q / esc / Ctrl-C to quit — as in the app.

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


def _interactive() -> bool:
    return _COLOR and sys.stdin.isatty() and sys.stdout.isatty()


def _getkey() -> str:
    """Read one keypress: 'up'/'down'/'esc', or the literal character."""
    import select
    import termios
    import tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = os.read(fd, 1).decode(errors="ignore")
        if ch == "\x1b":  # escape sequence (arrows) or a lone Esc
            if select.select([fd], [], [], 0.05)[0]:
                rest = os.read(fd, 2).decode(errors="ignore")
                return {"[A": "up", "[B": "down"}.get(rest, "esc")
            return "esc"
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def choose(title: str, options, default: int = 0) -> int:
    """Single-choice menu. options = [(name, description)]. Returns the index.

    Interactive (TTY): arrow keys / j / k to move, Enter to select, 1-9 to jump, q/Esc
    to cancel. Non-TTY: falls back to a plain numbered prompt.
    """
    width = max((len(n) for n, _ in options), default=0)

    if not _interactive():
        print(f"\n{bold(title)}")
        for i, (name, desc) in enumerate(options):
            print(f"    {i + 1}  {name.ljust(width)}  {dim(desc)}")
        while True:
            raw = _read(f"  choose {dim(f'[{default + 1}]')} ")
            if not raw:
                return default
            if raw.isdigit() and 1 <= int(raw) <= len(options):
                return int(raw) - 1
            print(dim("  enter a number from the list"))

    print(f"\n{bold(title)}   "
          f"{dim(f'↑↓ move · enter select · 1-{min(9, len(options))} jump · q cancel')}")
    sel = default

    def render(first: bool):
        if not first:
            sys.stdout.write(f"\x1b[{len(options)}A")  # cursor up N rows
        for i, (name, desc) in enumerate(options):
            cur = i == sel
            mark = accent(">") if cur else " "
            num = accent(str(i + 1)) if cur else dim(str(i + 1))
            label = bold(name) if cur else name
            pad = " " * (width - len(name))
            sys.stdout.write(f"\r\x1b[2K  {mark} {num}  {label}{pad}  {dim(desc)}\n")
        sys.stdout.flush()

    sys.stdout.write("\x1b[?25l")  # hide cursor
    try:
        render(True)
        while True:
            k = _getkey()
            if k in ("up", "k"):
                sel = (sel - 1) % len(options); render(False)
            elif k in ("down", "j"):
                sel = (sel + 1) % len(options); render(False)
            elif k in ("\r", "\n"):
                return sel
            elif k.isdigit() and 1 <= int(k) <= len(options):
                return int(k) - 1
            elif k == "\x03":  # Ctrl-C
                raise KeyboardInterrupt
            elif k in ("q", "esc"):
                raise Abort()
    finally:
        sys.stdout.write("\x1b[?25h")  # show cursor
        sys.stdout.flush()


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


async def _keepalive(nova):
    """Blank frames every 2 s so the Nova doesn't drop an idle link before we start."""
    try:
        while True:
            await nova.set_strobe(0, 0)   # all-zero = LEDs off
            await asyncio.sleep(2.0)
    except (asyncio.CancelledError, Exception):
        pass


async def _play(mode, preset, minutes, path, nova, tick, control):
    segs = gen.PRESETS[preset](minutes) if minutes else gen.PRESETS[preset]()
    if mode == "light":
        await gen.play_segments(nova, segs, on_tick=tick, control=control)
    elif mode == "music":
        await gen.play_with_audio(nova, segs, path, on_tick=tick, control=control)
    elif mode == "isochronic":
        from . import music
        wav = os.path.join(music.DEFAULT_MUSIC_DIR, f"_iso_{preset}.wav")
        os.makedirs(music.DEFAULT_MUSIC_DIR, exist_ok=True)
        gen.synth_isochronic(segs, wav)
        await gen.play_with_audio(nova, segs, wav, on_tick=tick, control=control)
    else:  # reactive
        await gen.play_reactive(nova, path, on_tick=tick, control=control)


def _key_listener(loop, on_space, on_quit, stop_flag):
    """Daemon thread: read single keys in raw mode; space→pause, q/esc/Ctrl-C→quit."""
    import select
    import termios
    import tty
    fd = sys.stdin.fileno()
    try:
        old = termios.tcgetattr(fd)
    except Exception:
        return
    try:
        tty.setraw(fd)
        while not stop_flag.is_set():
            if not select.select([fd], [], [], 0.1)[0]:
                continue
            ch = os.read(fd, 1).decode(errors="ignore")
            if ch == " ":
                loop.call_soon_threadsafe(on_space)
            elif ch == "\x1b":  # esc — but distinguish from arrow escape sequences
                if select.select([fd], [], [], 0.02)[0]:
                    os.read(fd, 2)  # swallow an arrow/other sequence
                else:
                    loop.call_soon_threadsafe(on_quit)
            elif ch in ("q", "\x03"):
                loop.call_soon_threadsafe(on_quit)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


async def connect_and_run(mode, preset, minutes, path):
    import threading
    nova = await connect_with_retry()
    if nova is None:
        print(dim("  cancelled."))
        return

    control = gen.PlayControl()
    start_evt = asyncio.Event()
    started = {"v": False}

    def announce():
        if control.paused:
            sys.stdout.write("\r\x1b[2K  " + dim("⏸ paused — space/power resume · q/esc quit"))
            sys.stdout.flush()

    def toggle():
        control.toggle()
        announce()

    def on_remote(ev):           # one subscription: first POWER starts, then pauses/resumes
        if ev != "POWER":
            return
        if not started["v"]:
            start_evt.set()
        else:
            toggle()

    try:
        try:
            info = await nova.read_info()
            print(f"  {ok('connected')}  {info.model}  fw {info.firmware}  battery {info.battery}%")
        except Exception:
            print("  " + ok("connected"))

        button = True
        try:
            await nova.subscribe_remote(on_remote)
        except Exception:
            button = False

        ka = asyncio.create_task(_keepalive(nova))  # hold the link while we wait
        try:
            if button:
                print("\n  press the Nova's " + accent("power button")
                      + " to start" + dim("   (Ctrl-C to cancel)"))
                await start_evt.wait()
            else:
                await asyncio.to_thread(input, "\n  press Enter to start… ")
        finally:
            ka.cancel()
            await asyncio.gather(ka, return_exceptions=True)
        started["v"] = True
        print(dim("  running — power / space pause · q / esc / Ctrl-C quit\n"))

        loop = asyncio.get_event_loop()
        stop_flag = threading.Event()
        listener = None
        if _interactive():
            listener = threading.Thread(
                target=_key_listener,
                args=(loop, toggle, control.stop, stop_flag), daemon=True)
            listener.start()

        def tick(t, f, d, dur):
            if control.paused:
                return
            sys.stdout.write(
                f"\r\x1b[2K  {ok('●')} {f:5.2f} Hz   duty {d * 100:4.1f}%   "
                f"{dim(f't {t:5.1f}/{dur:.0f}s')}")
            sys.stdout.flush()

        try:
            await _play(mode, preset, minutes, path, nova, tick, control)
        finally:
            stop_flag.set()
            if listener is not None:
                listener.join(timeout=0.5)
        print("\n  " + (dim("stopped.") if control.stopped.is_set() else ok("done ✅")))
    except (KeyboardInterrupt, asyncio.CancelledError):
        control.stop()
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

        # Preset & length only matter for the generated light arc (light/music/isochronic).
        # In reactive mode the music's envelope drives the light, so we skip both.
        if mode == "reactive":
            preset, minutes = "relax", None  # unused by reactive
        else:
            preset = list(gen.PRESETS)[
                choose("Preset", [(p, PRESET_DESC[p]) for p in gen.PRESETS])]
            mr = ask("\n" + bold("Length") + " in minutes"
                     + dim(" (blank = match track / preset)"))
            minutes = float(mr) if mr else None

        bits = [accent(mode)]
        if mode != "reactive":
            bits += [accent(preset), f"{minutes:g} min" if minutes else "auto"]
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
