#!/usr/bin/env python3
"""Session generator for the Lumenate Nova.

Builds science-backed light "scores" (segment lists — see docs/GENERATOR_DESIGN.md)
and plays them, with three sound modes:

  A) bring-your-own music        -> play audio + a preset light arc alongside it
  B) generated isochronic tones  -> synth audio phase-locked to the light
  C) audio-reactive              -> modulate strobe duty from the music envelope,
                                    drifting base frequency slowly with musical energy,
                                    while keeping the flash clock rhythmic.

Segment model mirrors Lumenate's own: within each Segment frequency & duty ramp
linearly. All light values stay in the evidence-backed band (see clamp_*).

Deps: numpy + ffmpeg (decode) + afplay/ffplay (playback). BLE via nova.Nova.
"""
from __future__ import annotations

import asyncio
import math
import shutil
import struct
import subprocess
import wave
from dataclasses import dataclass

import numpy as np

from .core import Nova, Segment, sample_session, session_duration

# --- safety / sanity clamps (docs/GENERATOR_DESIGN.md §5) ---
FREQ_MIN, FREQ_MAX = 1.0, 18.0      # never exceed the studied range
DUTY_MIN, DUTY_MAX = 0.0, 0.70      # observed device envelope
DEFAULT_RATE_HZ = 10.0              # frame update rate (app uses ~9-10)


def clamp_freq(f: float) -> float:
    return max(0.0, min(FREQ_MAX, f))


def clamp_duty(d: float) -> float:
    return max(DUTY_MIN, min(DUTY_MAX, d))


# ==========================================================================
# Segment builders
# ==========================================================================
def ramp(t0, t1, f0, f1, d0, d1) -> Segment:
    return Segment(t0, t1, clamp_freq(f0), clamp_freq(f1), clamp_duty(d0), clamp_duty(d1))


def hold(t0, dur, freq, duty) -> Segment:
    return ramp(t0, t0 + dur, freq, freq, duty, duty)


def breathe(t0, dur, freq, d_lo, d_hi, cycle=10.0):
    """Oscillate duty between d_lo and d_hi at `cycle` seconds/breath (freq steady)."""
    segs = []
    t = t0
    end = t0 + dur
    half = cycle / 2.0
    up = True
    while t < end - 1e-6:
        seg_end = min(t + half, end)
        a, b = (d_lo, d_hi) if up else (d_hi, d_lo)
        segs.append(ramp(t, seg_end, freq, freq, a, b))
        t = seg_end
        up = not up
    return segs


# ==========================================================================
# Presets — the 3-part arc (induction -> body -> fade-out)
# ==========================================================================
def preset_relax(minutes: float = 10.0):
    """Relaxed visual exploration: settle to ~10 Hz alpha, breathe intensity, ease out."""
    total = minutes * 60.0
    induction = min(90.0, total * 0.15)
    fade = min(120.0, total * 0.2)
    body = max(0.0, total - induction - fade)
    segs = [ramp(0, induction, 13, 10, 0.05, 0.30)]
    segs += breathe(induction, body, 10.0, 0.15, 0.35, cycle=10.0)
    segs.append(ramp(induction + body, induction + body + fade, 10, 7, 0.30, 0.05))
    return segs


def preset_sleep(minutes: float = 20.0):
    """Wind down from alpha to delta; fade to dark."""
    total = minutes * 60.0
    a = total * 0.15
    b = total * 0.70
    return [
        ramp(0, a, 10, 8, 0.10, 0.20),
        ramp(a, a + b, 8, 3, 0.20, 0.20),
        ramp(a + b, total, 3, 1, 0.20, 0.0),
    ]


def preset_explore(minutes: float = 12.0):
    """Theta<->alpha journey with slow frequency drift and breathing intensity."""
    total = minutes * 60.0
    induction = min(120.0, total * 0.15)
    fade = min(120.0, total * 0.18)
    body = max(0.0, total - induction - fade)
    segs = [ramp(0, induction, 13, 8, 0.05, 0.25)]
    # slow freq drift 8<->11 across the body, with duty breathing
    n = max(2, int(body // 40))
    step = body / n
    for i in range(n):
        f_a = 8 + 3 * (0.5 - 0.5 * math.cos(2 * math.pi * i / n))
        f_b = 8 + 3 * (0.5 - 0.5 * math.cos(2 * math.pi * (i + 1) / n))
        d_a = 0.15 if i % 2 == 0 else 0.35
        d_b = 0.35 if i % 2 == 0 else 0.15
        segs.append(ramp(induction + i * step, induction + (i + 1) * step, f_a, f_b, d_a, d_b))
    segs.append(ramp(induction + body, total, 8, 6, 0.25, 0.05))
    return segs


def preset_energize(minutes: float = 8.0):
    """Higher, alerting band. Keep short (see safety note)."""
    total = minutes * 60.0
    induction = min(60.0, total * 0.15)
    fade = min(60.0, total * 0.15)
    body = max(0.0, total - induction - fade)
    segs = [ramp(0, induction, 10, 14, 0.10, 0.35)]
    segs += breathe(induction, body, 14.0, 0.25, 0.45, cycle=8.0)
    segs.append(ramp(induction + body, total, 14, 10, 0.35, 0.05))
    return segs


PRESETS = {
    "relax": preset_relax,
    "sleep": preset_sleep,
    "explore": preset_explore,
    "energize": preset_energize,
}


def to_dsl(segments) -> str:
    """Serialize segments to the Nova session DSL (see PROTOCOL.md §10)."""
    def expr(a, b):
        if a == 0 and b == 0:
            return "z"
        return f"c({a:g})" if a == b else f"l({a:g},{b:g})"
    parts = [f"s({s.t0:g},{s.t1:g},{expr(s.f0, s.f1)},{expr(s.d0, s.d1)})" for s in segments]
    return ";".join(parts)


# ==========================================================================
# Playback: light-only / with external audio
# ==========================================================================
async def play_segments(nova: Nova, segments, rate_hz=DEFAULT_RATE_HZ,
                        start_clock=None, duration=None, on_tick=None):
    """Stream a segment list to the Nova, time-synced to a wall clock.

    start_clock: loop.time() reference for t=0 (defaults to now). Passing the same
    value used to start audio keeps light and audio aligned.
    """
    loop = asyncio.get_event_loop()
    t0 = start_clock if start_clock is not None else loop.time()
    dur = duration if duration is not None else session_duration(segments)
    dt = 1.0 / rate_hz
    try:
        while True:
            t = loop.time() - t0
            if t > dur:
                break
            f, d = sample_session(segments, t)
            await nova.set_strobe(f, d)
            if on_tick:
                on_tick(t, f, d, dur)
            # keep the cadence steady regardless of write latency
            await asyncio.sleep(max(0.0, (t0 + (int(t / dt) + 1) * dt) - loop.time()))
    finally:
        await nova.stop()


# ==========================================================================
# Audio: envelope analysis (Mode C) + isochronic synth (Mode B)
# ==========================================================================
def _ffmpeg_decode_mono(path: str, sr: int = 22050) -> np.ndarray:
    ff = shutil.which("ffmpeg")
    if not ff:
        raise RuntimeError("ffmpeg not found")
    out = subprocess.run(
        [ff, "-v", "quiet", "-i", path, "-f", "f32le", "-ac", "1", "-ar", str(sr), "-"],
        capture_output=True,
    ).stdout
    return np.frombuffer(out, dtype=np.float32)


@dataclass
class AudioAnalysis:
    rate_hz: float
    duration: float
    fast: np.ndarray   # per-frame loudness 0..1 (reacts to beats)
    slow: np.ndarray   # heavily smoothed 0..1 (musical energy/sections)
    tempo_bpm: float


def analyze(path: str, rate_hz: float = DEFAULT_RATE_HZ, sr: int = 22050) -> AudioAnalysis:
    x = _ffmpeg_decode_mono(path, sr)
    if x.size == 0:
        raise RuntimeError(f"decoded no audio from {path}")
    hop = max(1, int(sr / rate_hz))
    n = x.size // hop
    frames = x[: n * hop].reshape(n, hop)
    rms = np.sqrt(np.mean(frames ** 2, axis=1) + 1e-12)
    # robust normalise 0..1
    lo, hi = np.percentile(rms, 5), np.percentile(rms, 95)
    fast = np.clip((rms - lo) / (hi - lo + 1e-9), 0.0, 1.0)
    # slow envelope: smooth over ~8 s
    win = max(1, int(rate_hz * 8))
    kernel = np.ones(win) / win
    slow = np.convolve(fast, kernel, mode="same")
    slow = np.clip((slow - slow.min()) / (np.ptp(slow) + 1e-9), 0.0, 1.0)
    # crude tempo estimate via onset-envelope autocorrelation (display only)
    onset = np.clip(np.diff(rms, prepend=rms[0]), 0, None)
    tempo = _estimate_tempo(onset, rate_hz)
    return AudioAnalysis(rate_hz, n / rate_hz, fast, slow, tempo)


def _estimate_tempo(onset: np.ndarray, rate_hz: float) -> float:
    if onset.size < rate_hz * 4:
        return 0.0
    o = onset - onset.mean()
    ac = np.correlate(o, o, mode="full")[o.size - 1:]
    # search 60..160 BPM -> lag in frames
    lo = int(rate_hz * 60 / 160)
    hi = int(rate_hz * 60 / 60)
    if hi <= lo or hi >= ac.size:
        return 0.0
    lag = lo + int(np.argmax(ac[lo:hi]))
    return 60.0 * rate_hz / lag if lag else 0.0


def reactive_tracks(a: AudioAnalysis, base_lo=8.0, base_hi=12.0,
                    duty_lo=0.05, duty_hi=0.55):
    """Turn an AudioAnalysis into (freq[], duty[]) arrays, one per frame.

    duty follows the fast envelope (beats -> brighter); frequency drifts slowly with
    musical energy but stays in-band and changes slowly => the flash stays rhythmic.
    """
    freq = base_lo + (base_hi - base_lo) * a.slow
    duty = duty_lo + (duty_hi - duty_lo) * a.fast
    freq = np.clip(freq, FREQ_MIN, FREQ_MAX)
    duty = np.clip(duty, DUTY_MIN, DUTY_MAX)
    return freq, duty


def synth_isochronic(segments, path: str, carrier=200.0, sr=44100,
                     drone=True, rate_hz=DEFAULT_RATE_HZ):
    """Render isochronic tones phase-locked to the light score to a WAV file.

    The carrier is gated on/off at the current strobe frequency & duty (same timeline
    as the light), optionally over a soft sub-drone. Play this WAV while driving the
    light from the same segments for coherent audio-visual entrainment.
    """
    dur = session_duration(segments)
    t = np.arange(int(dur * sr)) / sr
    # per-sample frequency & duty from the score
    fr = np.empty_like(t)
    du = np.empty_like(t)
    idx = 0
    # sample the score at audio rate (vectorised per segment)
    fr[:] = 0.0
    du[:] = 0.0
    for s in segments:
        m = (t >= s.t0) & (t < s.t1)
        if not m.any():
            continue
        frac = (t[m] - s.t0) / max(1e-9, (s.t1 - s.t0))
        fr[m] = s.f0 + (s.f1 - s.f0) * frac
        du[m] = s.d0 + (s.d1 - s.d0) * frac
    # phase of the strobe (integral of frequency) -> gate within each cycle
    phase = np.cumsum(fr) / sr
    cyc = np.mod(phase, 1.0)
    gate = (cyc < np.clip(du, 0, 1)).astype(np.float32)
    # smooth the gate edges a touch to avoid clicks
    env = np.convolve(gate, np.ones(64) / 64, mode="same")
    tone = np.sin(2 * np.pi * carrier * t).astype(np.float32) * env
    mix = 0.6 * tone
    if drone:
        d1 = np.sin(2 * np.pi * (carrier / 2) * t)
        d2 = np.sin(2 * np.pi * (carrier / 2 * 1.5) * t)
        mix += 0.12 * (d1 + d2).astype(np.float32)
    mix /= max(1e-6, np.max(np.abs(mix)))
    pcm = (mix * 0.9 * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return path


# ==========================================================================
# Audio playback helpers
# ==========================================================================
def start_audio(path: str):
    """Start playing an audio file, return the subprocess (afplay on macOS, else ffplay)."""
    if shutil.which("afplay"):
        return subprocess.Popen(["afplay", path])
    ff = shutil.which("ffplay")
    if ff:
        return subprocess.Popen([ff, "-nodisp", "-autoexit", "-loglevel", "quiet", path])
    raise RuntimeError("no audio player (afplay/ffplay) found")


async def play_with_audio(nova: Nova, segments, audio_path: str,
                          rate_hz=DEFAULT_RATE_HZ, on_tick=None):
    """Mode A/B: play audio while streaming a light score, aligned at t=0."""
    loop = asyncio.get_event_loop()
    proc = start_audio(audio_path)
    start = loop.time()
    try:
        await play_segments(nova, segments, rate_hz=rate_hz, start_clock=start,
                            on_tick=on_tick)
    finally:
        if proc.poll() is None:
            proc.terminate()


async def play_reactive(nova: Nova, audio_path: str, base_lo=8.0, base_hi=12.0,
                        duty_lo=0.05, duty_hi=0.55, rate_hz=DEFAULT_RATE_HZ, on_tick=None):
    """Mode C: analyse the track, then modulate the strobe from it while it plays."""
    a = analyze(audio_path, rate_hz=rate_hz)
    freq, duty = reactive_tracks(a, base_lo, base_hi, duty_lo, duty_hi)
    loop = asyncio.get_event_loop()
    proc = start_audio(audio_path)
    start = loop.time()
    dt = 1.0 / rate_hz
    try:
        while True:
            elapsed = loop.time() - start
            i = int(elapsed * rate_hz)
            if i >= freq.size:
                break
            await nova.set_strobe(float(freq[i]), float(duty[i]))
            if on_tick:
                on_tick(elapsed, float(freq[i]), float(duty[i]), a.duration)
            await asyncio.sleep(max(0.0, (start + (i + 1) * dt) - loop.time()))
    finally:
        await nova.stop()
        if proc.poll() is None:
            proc.terminate()
