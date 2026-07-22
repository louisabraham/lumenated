#!/usr/bin/env python3
"""Keyboard-driven terminal UI for the Lumenate Nova light/sound generator.

A single list you navigate with the arrow keys (or j/k). Search YouTube Music,
pick a track, and it downloads + runs a session on the Nova. No mouse needed.

Keys:  / search   ↑↓/jk move   enter select/run   m mode   p preset   d duration
       s stop   r recommended   q quit

Run:  lumenated-tui         (needs the [tui] extra: textual, ytmusicapi, yt-dlp, ffmpeg)

⚠️ Photosensitive-seizure risk: this is a 7–18 Hz stroboscope. See the README.
"""
from __future__ import annotations

import asyncio
import os

from textual import on, work
from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Input, Log, OptionList, Static
from textual.widgets.option_list import Option

from . import generator as gen
from . import music
from .core import Nova

MODES = ["reactive", "music", "light", "isochronic"]
MODE_HELP = {
    "reactive": "light follows the music envelope",
    "music": "generated light preset + your track",
    "light": "generated light preset only (no audio)",
    "isochronic": "generated tones phase-locked to light (no download)",
}
PRESETS = list(gen.PRESETS)
DURATIONS = [None, 5, 10, 20]  # None = auto (match track / preset default)


def _dur_to_minutes(s: str):
    try:
        sec = 0
        for p in s.split(":"):
            sec = sec * 60 + int(p)
        return sec / 60.0 or None
    except (ValueError, AttributeError):
        return None


class NovaTUI(App):
    CSS = """
    Screen { background: $surface; }
    #status { padding: 0 1; height: 1; color: $accent; }
    #hint   { padding: 0 1; height: 1; color: $text-muted; }
    #search { margin: 0 1; display: none; }
    #search.on { display: block; }
    #list { height: 1fr; padding: 0 1; }
    #log { height: 6; margin: 0 1; padding: 0 1; background: $panel; color: $text-muted; }
    """
    BINDINGS = [
        ("slash", "search", "search"),
        ("m", "mode", "mode"),
        ("p", "preset", "preset"),
        ("d", "duration", "duration"),
        ("r", "recommended", "recommended"),
        ("s", "stop", "stop"),
        ("j", "down", ""),
        ("k", "up", ""),
        ("escape", "escape", ""),
        ("q", "quit", "quit"),
    ]

    def __init__(self):
        super().__init__()
        self.view = "recommended"
        self.tracks: list[music.Track] = []
        self.mode = "reactive"
        self.preset = "relax"
        self.minutes = None
        self.session_running = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static(id="status")
        yield Input(placeholder="type to search YouTube Music, Enter to run…", id="search")
        yield OptionList(id="list")
        yield Static(id="hint")
        yield Log(id="log", highlight=False)
        yield Footer()

    def on_mount(self):
        self._refresh_status()
        self.action_recommended()
        self.query_one("#list", OptionList).focus()
        self._log("Pick a recommendation (Enter) or press / to search. m=mode p=preset d=duration.")

    # ---------- status / log ----------
    def _refresh_status(self):
        dur = "auto" if self.minutes is None else f"{self.minutes} min"
        self.query_one("#status", Static).update(
            f" mode: [b]{self.mode}[/]   preset: [b]{self.preset}[/]   length: [b]{dur}[/]"
            f"{'   ● running' if self.session_running else ''}")
        self.query_one("#hint", Static).update(f" {self.mode}: {MODE_HELP[self.mode]}")

    def _log(self, msg: str):
        self.query_one("#log", Log).write_line(msg)

    def _set_progress(self, frac, note):
        if note in ("converting", "done") or int(frac * 100) % 20 == 0:
            self._log(f"download {int(frac*100):3d}%  {note}")

    # ---------- list population ----------
    def _show_recommended(self):
        self.view = "recommended"
        ol = self.query_one("#list", OptionList)
        ol.clear_options()
        ol.add_options([Option(f"★ {lbl}", id=f"rec:{i}")
                        for i, (lbl, _) in enumerate(music.RECOMMENDED)])
        ol.highlighted = 0

    def _show_results(self, tracks):
        self.view = "results"
        self.tracks = tracks
        ol = self.query_one("#list", OptionList)
        ol.clear_options()
        if not tracks:
            ol.add_option(Option("(no results — press / to search again)", id="none"))
        else:
            for i, t in enumerate(tracks):
                dur = f"  [{t.duration}]" if t.duration else ""
                ol.add_option(Option(f"{t.title[:46]}  ·  {t.artist[:26]}{dur}", id=f"trk:{i}"))
            ol.highlighted = 0
        ol.focus()

    # ---------- actions ----------
    def action_recommended(self):
        self._show_recommended()
        self.query_one("#list", OptionList).focus()

    def action_search(self):
        s = self.query_one("#search", Input)
        s.add_class("on")
        s.focus()

    def action_escape(self):
        s = self.query_one("#search", Input)
        if s.has_class("on"):
            s.remove_class("on")
        self.query_one("#list", OptionList).focus()

    def action_mode(self):
        self.mode = MODES[(MODES.index(self.mode) + 1) % len(MODES)]
        self._refresh_status()

    def action_preset(self):
        self.preset = PRESETS[(PRESETS.index(self.preset) + 1) % len(PRESETS)]
        self._refresh_status()

    def action_duration(self):
        self.minutes = DURATIONS[(DURATIONS.index(self.minutes) + 1) % len(DURATIONS)]
        self._refresh_status()

    def action_down(self):
        self.query_one("#list", OptionList).action_cursor_down()

    def action_up(self):
        self.query_one("#list", OptionList).action_cursor_up()

    def action_stop(self):
        if self.session_running:
            self.workers.cancel_group(self, "session")
            self._log("stopping…")

    # ---------- events ----------
    @on(Input.Submitted, "#search")
    def _submit(self, e: Input.Submitted):
        q = e.value.strip()
        self.query_one("#search", Input).remove_class("on")
        if q:
            self.do_search(q)

    @on(OptionList.OptionSelected, "#list")
    def _selected(self, e: OptionList.OptionSelected):
        oid = e.option.id or ""
        if oid.startswith("rec:"):
            _, q = music.RECOMMENDED[int(oid[4:])]
            self.query_one("#search", Input).value = q
            self.do_search(q)
        elif oid.startswith("trk:"):
            if self.session_running:
                self._log("a session is running — press s to stop first.")
                return
            self.run_session(self.tracks[int(oid[4:])])

    # ---------- search worker ----------
    @work(thread=True, exclusive=True, group="search")
    def do_search(self, query):
        self.call_from_thread(self._log, f"searching: {query!r} …")
        try:
            tracks = music.search_playable(query, limit=25)
        except Exception as ex:
            self.call_from_thread(self._log, f"search failed: {ex}")
            return
        self.call_from_thread(self._show_results, tracks)
        self.call_from_thread(self._log, f"{len(tracks)} tracks — ↑↓ then Enter to run ({self.mode}).")

    # ---------- run ----------
    def run_session(self, track):
        if self.mode in ("light", "isochronic"):
            self.session(None, track)
        else:
            self._log(f"downloading: {track.label} …")
            self._download_then(track)

    @work(thread=True, exclusive=True, group="download")
    def _download_then(self, track):
        try:
            path = music.download(track.video_id,
                                  progress=lambda f, n: self.call_from_thread(self._set_progress, f, n))
        except Exception as ex:
            self.call_from_thread(self._log, f"download failed: {ex}")
            return
        self.call_from_thread(self._log, f"downloaded: {os.path.basename(path)}")
        self.call_from_thread(self.session, path, track)

    @work(exclusive=True, group="session")
    async def session(self, path, track):
        self.session_running = True
        self._refresh_status()
        minutes = self.minutes
        if minutes is None and track:
            minutes = _dur_to_minutes(track.duration)
        self._log(f"connecting to Nova… (mode={self.mode}, preset={self.preset})")
        try:
            nova = await Nova.connect(timeout=20.0)
        except Exception as ex:
            self._log(f"connect failed: {ex} — is it flashing blue (pairing mode)?")
            self.session_running = False
            self._refresh_status()
            return
        try:
            info = await nova.read_info()
            self._log(f"connected: {info.model} fw {info.firmware} battery {info.battery}%")

            def tick(t, f, d, dur):
                if int(t * 10) % 10 == 0:
                    self.call_from_thread(self._log, f"  t={t:5.1f}/{dur:.0f}s  {f:5.2f} Hz  {d*100:4.1f}%")

            segs = gen.PRESETS[self.preset](minutes) if minutes else gen.PRESETS[self.preset]()
            if self.mode == "light":
                await gen.play_segments(nova, segs, on_tick=tick)
            elif self.mode == "music":
                await gen.play_with_audio(nova, segs, path, on_tick=tick)
            elif self.mode == "isochronic":
                wav = os.path.join(music.DEFAULT_MUSIC_DIR, f"_iso_{self.preset}.wav")
                os.makedirs(music.DEFAULT_MUSIC_DIR, exist_ok=True)
                gen.synth_isochronic(segs, wav)
                await gen.play_with_audio(nova, segs, wav, on_tick=tick)
            else:  # reactive
                await gen.play_reactive(nova, path, on_tick=tick)
            self._log("session complete ✅")
        except asyncio.CancelledError:
            self._log("stopped.")
        except Exception as ex:
            self._log(f"session error: {ex}")
        finally:
            try:
                await nova.stop()
            finally:
                await nova.disconnect()
            self.session_running = False
            self._refresh_status()


def main():
    NovaTUI().run()


if __name__ == "__main__":
    main()
