#!/usr/bin/env python3
"""Aggressively catch the Nova's advertising window and connect.

Continuously scans; the instant a 'Lumenate Nova' advertisement appears it fires a
connect (CoreBluetooth will hold the pending connection). Loops for `--secs`.
Keep the Nova awake (press its power button) while this runs.
"""
import asyncio
import sys

sys.path.insert(0, "nova")
from bleak import BleakScanner, BleakClient


async def main(secs: float):
    loop = asyncio.get_event_loop()
    deadline = loop.time() + secs
    attempt = 0
    while loop.time() < deadline:
        dev = await BleakScanner.find_device_by_filter(
            lambda d, adv: "lumenate nova" in ((adv.local_name or d.name or "").lower()),
            timeout=6.0,
        )
        if not dev:
            print("… not advertising, waiting (press the Nova button)")
            continue
        attempt += 1
        print(f"[{attempt}] detected {dev.address}; connecting…")
        cli = BleakClient(dev, timeout=25.0)
        try:
            await cli.connect()
            print("  ✅ CONNECTED — is_connected:", cli.is_connected)
            print("  services:")
            for s in cli.services:
                print("   ", s.uuid)
                for c in s.characteristics:
                    print("      ", c.uuid, list(c.properties))
            # try reading model to prove GATT access works (needs encryption if required)
            try:
                m = await cli.read_gatt_char("00002a24-0000-1000-8000-00805f9b34fb")
                print("  model number:", m.decode(errors="replace"))
                print("  🎉 GATT read succeeded — no bonding barrier!")
            except Exception as e:
                print("  ⚠️ GATT read failed (likely needs bonding):", type(e).__name__, e)
            await cli.disconnect()
            return
        except Exception as e:
            print("  connect failed:", type(e).__name__, e)
    print("gave up after", secs, "s")


if __name__ == "__main__":
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 60.0
    asyncio.run(main(secs))
