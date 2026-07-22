#!/usr/bin/env python3
"""Demo CLI for controlling a Lumenate Nova from the Mac.

Examples:
    python3 nova/demo.py scan                 # find advertising Novas
    python3 nova/demo.py info                 # connect, print device info
    python3 nova/demo.py welcome              # trigger the greeting LED animation
    python3 nova/demo.py strobe 10 0.3        # steady 10 Hz, 30% duty (Ctrl-C to stop)
    python3 nova/demo.py ramp                 # sweep frequency/intensity for ~20s
    python3 nova/demo.py monitor              # subscribe to buttons/sensor/battery
    python3 nova/demo.py offline 0            # start a standalone RELAXED session

Add an address as the last arg to target a specific device (from `scan`):
    python3 nova/demo.py strobe 10 0.3 <ADDRESS>

Requires: pip install bleak
"""
import asyncio
import math
import sys

from nova import Nova, decode_strobe_frame, strobe_frame


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


async def cmd_offline(addr, mode):
    async with await Nova.connect(addr) as nova:
        try:
            print("offline header:", await nova.read_offline_header())
        except Exception as e:
            print("header read failed:", e)
        print(f"starting offline session mode={mode} ...")
        await nova.start_offline_session(mode)
        await asyncio.sleep(2.0)


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    cmd = args[0]

    # optional trailing address
    addr = None
    rest = args[1:]
    if rest and ":" in rest[-1] or (rest and len(rest[-1]) >= 30):
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
    elif cmd == "offline":
        mode = int(rest[0]) if rest else 0
        asyncio.run(cmd_offline(addr, mode))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
