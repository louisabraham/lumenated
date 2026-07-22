#!/usr/bin/env python3
"""Close remaining unknowns live: read reserved chars + confirm the motion sensor.

Enables motion detection (writes the sample-rate byte to abcdef01, subscribes to the
12345678 sensor char) and prints the 3xint16 stream. Move/tilt the Nova while it runs
to confirm it tracks orientation/acceleration.
"""
import asyncio
import struct
import sys

sys.path.insert(0, "nova")
from bleak import BleakScanner, BleakClient

STROBE_RATE_CFG = "abcdef01-2345-6789-abcd-ef0123456789"  # t0 "streaming data rate"
SENSOR = "12345678-9abc-4def-8012-3456789abcde"           # motion sensor notify
CMD_EXTRA = "2b35ef1f-11a6-4089-8cd5-843c5d0c9c55"        # reserved (readable)
BATT_EXTRA = "00002bed-0000-1000-8000-00805f9b34fb"       # reserved (readable)
OFFLINE_HEADER = "51bfc219-feab-4227-8b93-8af8cc5306d4"
OFFLINE_MODE = "2a84aaff-6738-4629-894c-346357b89a0c"
MANUF = "00002a29-0000-1000-8000-00805f9b34fb"


async def catch():
    loop = asyncio.get_event_loop()
    end = loop.time() + 60
    while loop.time() < end:
        dev = await BleakScanner.find_device_by_filter(
            lambda d, adv: "lumenate nova" in ((adv.local_name or d.name or "").lower()),
            timeout=6.0)
        if not dev:
            print("… press the Nova power button (waiting to advertise)"); continue
        cli = BleakClient(dev, timeout=25.0)
        try:
            await cli.connect(); return cli
        except Exception as e:
            print("retry:", type(e).__name__)
    return None


async def main():
    cli = await catch()
    if not cli:
        print("no connection"); return
    try:
        async def rd(u):
            try:
                return (await cli.read_gatt_char(u))
            except Exception as e:
                return f"<err {type(e).__name__}>".encode()

        print("== reserved / reference characteristic values ==")
        print("  manufacturer     :", (await rd(MANUF)).decode(errors="replace"))
        print("  cmd extra 2b35ef1f:", (await rd(CMD_EXTRA)).hex())
        print("  batt extra 0x2bed :", (await rd(BATT_EXTRA)).hex())
        h = await rd(OFFLINE_HEADER)
        if len(h) >= 16:
            m, v, c, a = struct.unpack("<IIII", h[:16])
            print(f"  offline header    : magic={m:#x} version={v} sessionCount={c} activeIndex={a}")
        print("  offline mode      :", (await rd(OFFLINE_MODE)).hex())

        print("\n== enabling motion detection; MOVE/TILT the Nova now (~20s) ==")
        got = [0]
        def on_sensor(_, data):
            got[0] += 1
            if got[0] <= 40 or got[0] % 10 == 0:
                x, y, z = struct.unpack("<hhh", bytes(data[:6]))
                mag = (x*x + y*y + z*z) ** 0.5
                print(f"  sample {got[0]:4d}: x={x:6d} y={y:6d} z={z:6d} |v|={mag:8.0f}")
        await cli.start_notify(SENSOR, on_sensor)
        for rate in (0x0a, 0x14):  # try the app's rate, then a faster one
            try:
                await cli.write_gatt_char(STROBE_RATE_CFG, bytes([rate]), response=False)
                print(f"  (wrote sample-rate {rate} to abcdef01)")
            except Exception as e:
                print("  rate write failed:", type(e).__name__)
        await asyncio.sleep(20)
        await cli.stop_notify(SENSOR)
        print(f"\n  total sensor samples: {got[0]}")
    finally:
        try:
            await cli.write_gatt_char(STROBE_RATE_CFG, bytes([0]), response=False)
        except Exception:
            pass
        await cli.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
