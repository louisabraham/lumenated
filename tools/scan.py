#!/usr/bin/env python3
"""Scan for BLE devices and dump advertisement data.

Usage:
    python3 tools/scan.py [seconds] [name-filter]

Examples:
    python3 tools/scan.py 8
    python3 tools/scan.py 12 lumen
"""
import asyncio
import sys
from bleak import BleakScanner


async def main(duration: float, name_filter: str | None):
    seen = {}

    def cb(device, adv):
        seen[device.address] = (device, adv)

    scanner = BleakScanner(detection_callback=cb)
    await scanner.start()
    await asyncio.sleep(duration)
    await scanner.stop()

    rows = sorted(seen.values(), key=lambda t: (t[1].rssi or -999), reverse=True)
    for device, adv in rows:
        name = adv.local_name or device.name or ""
        if name_filter and name_filter.lower() not in (name or "").lower():
            # also let UUID / manufacturer matches through
            hay = (name or "") + " " + " ".join(adv.service_uuids)
            if name_filter.lower() not in hay.lower():
                continue
        print(f"\n{device.address}  rssi={adv.rssi}  name={name!r}")
        if adv.service_uuids:
            print(f"  service_uuids: {adv.service_uuids}")
        if adv.manufacturer_data:
            for cid, data in adv.manufacturer_data.items():
                print(f"  manufacturer 0x{cid:04x}: {data.hex()}")
        if adv.service_data:
            for u, data in adv.service_data.items():
                print(f"  service_data {u}: {data.hex()}")

    if not seen:
        print("No BLE devices found. Is Bluetooth on / permission granted to the terminal?")


if __name__ == "__main__":
    dur = float(sys.argv[1]) if len(sys.argv) > 1 else 8.0
    filt = sys.argv[2] if len(sys.argv) > 2 else None
    asyncio.run(main(dur, filt))
