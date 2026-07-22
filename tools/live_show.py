#!/usr/bin/env python3
"""Live control demo: catch the Nova, then drive its LEDs so you can SEE it work.

Sequence: connect -> Welcome LEDs -> steady 10Hz -> frequency sweep w/ breathing
intensity -> a couple of discrete steady strobes -> blank/stop.
Keep the Nova awake (press power) if it stops advertising before we connect.
"""
import asyncio
import math
import sys

sys.path.insert(0, "nova")
from bleak import BleakScanner, BleakClient
from nova import Nova


async def catch_connect(secs=60.0):
    loop = asyncio.get_event_loop()
    deadline = loop.time() + secs
    while loop.time() < deadline:
        dev = await BleakScanner.find_device_by_filter(
            lambda d, adv: "lumenate nova" in ((adv.local_name or d.name or "").lower()),
            timeout=6.0,
        )
        if not dev:
            print("… waiting for Nova to advertise (press its power button)")
            continue
        print(f"detected {dev.address}; connecting…")
        cli = BleakClient(dev, timeout=25.0)
        try:
            await cli.connect()
            return cli
        except Exception as e:
            print("  connect failed, retrying:", type(e).__name__)
    return None


async def main():
    cli = await catch_connect(60)
    if not cli:
        print("could not connect")
        return
    nova = Nova(cli)
    try:
        info = await nova.read_info()
        print(f"connected: {info.model} fw={info.firmware} hw={info.hardware} "
              f"serial={info.serial} battery={info.battery}%")

        print(">> Welcome LEDs")
        await nova.welcome_leds()
        await asyncio.sleep(3)

        print(">> steady 10 Hz, 30% for 4s")
        for _ in range(40):
            await nova.set_strobe(10, 0.30)
            await asyncio.sleep(0.1)

        print(">> frequency sweep 7->14 Hz, breathing intensity, ~16s")
        t = 0.0
        while t < 16.0:
            freq = 7.0 + 7.0 * (t / 16.0)
            duty = 0.08 + 0.30 * (0.5 - 0.5 * math.cos(t * math.pi / 2))
            await nova.set_strobe(freq, min(0.7, duty))
            await asyncio.sleep(0.1)
            t += 0.1

        print(">> discrete steady strobes: 6Hz, 10Hz, 13.5Hz (3s each)")
        for hz in (6.0, 10.0, 13.5):
            for _ in range(30):
                await nova.set_strobe(hz, 0.25)
                await asyncio.sleep(0.1)

        print(">> stop (blank)")
        await nova.stop()
        await asyncio.sleep(0.5)
        print("done ✅")
    finally:
        await nova.stop()
        await cli.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
