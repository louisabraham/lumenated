#!/usr/bin/env python3
"""Command-line control for a Lumenate Nova.

Examples (installed as the `lumenated` console script):
    lumenated scan                 # find advertising Novas
    lumenated info                 # connect, print device info
    lumenated welcome              # trigger the greeting LED animation
    lumenated strobe 10 0.3        # steady 10 Hz, 30% duty (Ctrl-C to stop)
    lumenated ramp                 # sweep frequency/intensity for ~20s
    lumenated monitor              # subscribe to buttons/sensor/battery
    lumenated session              # play a built-in DSL session
    lumenated session my.txt       # play a session DSL from a file
    lumenated generate relax 10    # play a generated 10-min 'relax' preset
    lumenated generate relax 10 song.mp3   # preset light + your audio
    lumenated reactive song.mp3    # light reacts to a music file
    lumenated iso explore 8        # generated isochronic tones + matched light
    lumenated offline 0            # start a standalone RELAXED session

Presets: relax, sleep, explore, energize.  Add --device <addr> to target a specific Nova.
(Also runnable as `python3 -m lumenated`.)
"""
import asyncio
import math
import sys

from .core import Nova, decode_strobe_frame, strobe_frame

# A short original demo session in the Nova DSL (see docs/PROTOCOL.md §10):
# fade in, hold at a calm theta ~6.5 Hz, breathe up toward ~12 Hz, settle, fade out.
DEMO_SESSION = (
    "s(0,3,z,z);"
    "s(3,6,l(4,6.5),l(0.02,0.15));"
    "s(6,16,c(6.5),c(0.15));"
    "s(16,20,l(6.5,12),l(0.15,0.45));"
    "s(20,24,l(12,6.5),l(0.45,0.15));"
    "s(24,34,c(6.5),c(0.15));"
    "s(34,38,l(6.5,0),l(0.15,0));"
)


async def cmd_scan():
    print("scanning 10s for 'Lumenate Nova' ...")
    devs = await Nova.discover(timeout=10.0)
    if not devs:
        print("none found. Power on the Nova and disconnect it from the phone app "
              "(LED flashing white).")
        return
    for dev, adv in devs:
        print(f"  {dev.address}  rssi={adv.rssi}  name={adv.local_name or dev.name!r}")
        if adv.service_uuids:
            print(f"    services: {adv.service_uuids}")


async def cmd_info(addr):
    async with await Nova.connect(addr) as nova:
        info = await nova.read_info()
        print(f"  model:    {info.model}")
        print(f"  serial:   {info.serial}")
        print(f"  firmware: {info.firmware}")
        print(f"  hardware: {info.hardware}")
        print(f"  battery:  {info.battery}%")


async def cmd_welcome(addr):
    async with await Nova.connect(addr) as nova:
        print("triggering Welcome LEDs ...")
        await nova.welcome_leds()
        await asyncio.sleep(3.0)


async def cmd_strobe(addr, freq, duty):
    async with await Nova.connect(addr) as nova:
        print(f"steady strobe: {decode_strobe_frame(strobe_frame(freq, duty))}")
        print("Ctrl-C to stop.")
        await nova.set_strobe(freq, duty)
        try:
            # Re-send at 4 Hz in case the device expects a keep-alive stream.
            while True:
                await nova.set_strobe(freq, duty)
                await asyncio.sleep(0.25)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass


async def cmd_ramp(addr):
    """Sweep 7->14 Hz while breathing the duty cycle, ~20s."""
    async with await Nova.connect(addr) as nova:
        print("ramping (7-14 Hz, breathing intensity) ~20s. Ctrl-C to stop.")
        t = 0.0
        try:
            while t < 20.0:
                freq = 7.0 + 7.0 * (t / 20.0)
                duty = 0.10 + 0.25 * (0.5 - 0.5 * math.cos(t * math.pi))  # breathe 0.10..0.35
                await nova.set_strobe(freq, duty)
                await asyncio.sleep(0.1)  # 10 Hz stream, matches the app
                t += 0.1
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass


async def cmd_monitor(addr):
    async with await Nova.connect(addr) as nova:
        print("subscribing to buttons / sensor / battery. Ctrl-C to stop.")
        await nova.subscribe_remote(lambda e: print(f"  [button] {e}"))
        await nova.subscribe_battery(lambda b: print(f"  [battery] {b}%"))
        n = [0]
        def on_sensor(xyz):
            n[0] += 1
            if n[0] % 10 == 0:  # throttle print
                print(f"  [sensor] {xyz}")
        await nova.subscribe_sensor(on_sensor)
        try:
            await asyncio.Event().wait()
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass


async def cmd_session(addr, path):
    dsl = DEMO_SESSION
    if path:
        with open(path) as f:
            dsl = f.read().strip()
    async with await Nova.connect(addr) as nova:
        print("playing session (Ctrl-C to stop)…")
        def tick(t, freq, duty):
            if int(t * 10) % 10 == 0:
                print(f"  t={t:5.1f}s  {freq:5.2f} Hz  duty {duty*100:4.1f}%")
        try:
            await nova.play_session(dsl, rate_hz=10, on_tick=tick)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
    print("done")


def _mk_tick():
    def tick(t, freq, duty, dur):
        if int(t * 10) % 10 == 0:
            bar = "#" * int(duty * 20)
            print(f"  t={t:6.1f}/{dur:.0f}s  {freq:5.2f} Hz  duty {duty*100:4.1f}% {bar}")
    return tick


async def cmd_generate(addr, preset, minutes, audio):
    from . import generator as gen
    if preset not in gen.PRESETS:
        print("presets:", ", ".join(gen.PRESETS)); return
    segs = gen.PRESETS[preset](minutes) if minutes else gen.PRESETS[preset]()
    async with await Nova.connect(addr) as nova:
        print(f"generating '{preset}' ({gen.session_duration(segs):.0f}s)"
              + (f" + audio {audio}" if audio else "") + "  (Ctrl-C to stop)")
        try:
            if audio:
                await gen.play_with_audio(nova, segs, audio, on_tick=_mk_tick())
            else:
                await gen.play_segments(nova, segs, on_tick=_mk_tick())
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
    print("done")


async def cmd_reactive(addr, audio):
    from . import generator as gen
    async with await Nova.connect(addr) as nova:
        print(f"audio-reactive light from {audio}  (Ctrl-C to stop)")
        try:
            await gen.play_reactive(nova, audio, on_tick=_mk_tick())
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
    print("done")


async def cmd_iso(addr, preset, minutes):
    from . import generator as gen
    import tempfile, os
    if preset not in gen.PRESETS:
        print("presets:", ", ".join(gen.PRESETS)); return
    segs = gen.PRESETS[preset](minutes) if minutes else gen.PRESETS[preset]()
    wav = os.path.join(tempfile.gettempdir(), f"nova_iso_{preset}.wav")
    print(f"synthesising phase-locked isochronic audio -> {wav}")
    gen.synth_isochronic(segs, wav)
    async with await Nova.connect(addr) as nova:
        print(f"playing '{preset}' with generated tones  (Ctrl-C to stop)")
        try:
            await gen.play_with_audio(nova, segs, wav, on_tick=_mk_tick())
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
    print("done")


async def cmd_offline(addr, mode):
    async with await Nova.connect(addr) as nova:
        try:
            print("offline header:", await nova.read_offline_header())
        except Exception as e:
            print("header read failed:", e)
        print(f"starting offline session mode={mode} ...")
        await nova.start_offline_session(mode)
        await asyncio.sleep(2.0)


def _is_float(s):
    try:
        float(s); return True
    except (TypeError, ValueError):
        return False


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    cmd = args[0]
    rest = args[1:]

    # explicit device selector (works for every command)
    addr = None
    if "--device" in rest:
        i = rest.index("--device")
        addr = rest[i + 1]
        del rest[i:i + 2]
    # legacy: a trailing CoreBluetooth-UUID / MAC address for the simple commands
    elif rest and (":" in rest[-1] or len(rest[-1]) >= 30) and not _is_float(rest[-1]):
        if cmd in {"info", "welcome", "strobe", "ramp", "monitor", "offline"}:
            addr = rest[-1]
            rest = rest[:-1]

    if cmd == "scan":
        asyncio.run(cmd_scan())
    elif cmd == "info":
        asyncio.run(cmd_info(addr))
    elif cmd == "welcome":
        asyncio.run(cmd_welcome(addr))
    elif cmd == "strobe":
        freq = float(rest[0]) if rest else 10.0
        duty = float(rest[1]) if len(rest) > 1 else 0.3
        asyncio.run(cmd_strobe(addr, freq, duty))
    elif cmd == "ramp":
        asyncio.run(cmd_ramp(addr))
    elif cmd == "monitor":
        asyncio.run(cmd_monitor(addr))
    elif cmd == "session":
        path = rest[0] if rest else None
        asyncio.run(cmd_session(addr, path))
    elif cmd == "generate":
        preset = rest[0] if rest else "relax"
        minutes = None
        audio = None
        for a in rest[1:]:
            if _is_float(a):
                minutes = float(a)
            else:
                audio = a
        asyncio.run(cmd_generate(addr, preset, minutes, audio))
    elif cmd == "reactive":
        if not rest:
            print("usage: reactive <audiofile>"); return
        asyncio.run(cmd_reactive(addr, rest[0]))
    elif cmd == "iso":
        preset = rest[0] if rest else "relax"
        minutes = float(rest[1]) if len(rest) > 1 and _is_float(rest[1]) else None
        asyncio.run(cmd_iso(addr, preset, minutes))
    elif cmd == "offline":
        mode = int(rest[0]) if rest else 0
        asyncio.run(cmd_offline(addr, mode))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
