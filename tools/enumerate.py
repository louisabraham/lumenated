#!/usr/bin/env python3
"""Connect to a BLE device and dump its full GATT table.

Reads every readable characteristic, lists descriptors, and (optionally)
subscribes to all notify/indicate characteristics for a few seconds to see
what the device pushes.

Usage:
    python3 tools/enumerate.py <address-or-name-substring> [notify-seconds]

On macOS <address> is the CoreBluetooth UUID printed by scan.py (not a MAC).
A name substring also works (we scan first to resolve it).
"""
import asyncio
import sys
from bleak import BleakScanner, BleakClient


async def resolve(target: str):
    print(f"scanning to resolve {target!r} ...")
    dev = await BleakScanner.find_device_by_address(target, timeout=10.0)
    if dev:
        return dev
    # try by name substring
    devs = await BleakScanner.discover(timeout=10.0)
    for d in devs:
        if target.lower() in (d.name or "").lower():
            return d
    return None


def known(uuid: str) -> str:
    # a few common ones for readability
    table = {
        "00002a00": "Device Name",
        "00002a19": "Battery Level",
        "00002a24": "Model Number",
        "00002a25": "Serial Number",
        "00002a26": "Firmware Rev",
        "00002a27": "Hardware Rev",
        "00002a28": "Software Rev",
        "00002a29": "Manufacturer",
    }
    return table.get(uuid[:8], "")


async def main(target: str, notify_secs: float):
    dev = await resolve(target)
    if not dev:
        print("device not found. Is it powered on and advertising (app disconnected)?")
        return
    print(f"connecting to {dev.address} ({dev.name}) ...")
    async with BleakClient(dev) as client:
        print("connected:", client.is_connected)
        notif_chars = []
        for svc in client.services:
            print(f"\n[service] {svc.uuid}  {svc.description}")
            for ch in svc.characteristics:
                props = ",".join(ch.properties)
                label = known(ch.uuid)
                line = f"  [char] {ch.uuid}  ({props})  handle={ch.handle}"
                if label:
                    line += f"  <{label}>"
                print(line)
                if "read" in ch.properties:
                    try:
                        val = await client.read_gatt_char(ch)
                        txt = ""
                        try:
                            t = val.decode("utf-8")
                            if t.isprintable():
                                txt = f"  ascii={t!r}"
                        except Exception:
                            pass
                        print(f"        value: {val.hex()}{txt}")
                    except Exception as e:
                        print(f"        read failed: {e}")
                for d in ch.descriptors:
                    print(f"        [desc] {d.uuid} handle={d.handle}")
                if "notify" in ch.properties or "indicate" in ch.properties:
                    notif_chars.append(ch)

        if notify_secs > 0 and notif_chars:
            print(f"\nsubscribing to {len(notif_chars)} notify/indicate chars for {notify_secs}s ...")

            def make_cb(uuid):
                def cb(_, data: bytearray):
                    print(f"  NOTIFY {uuid}: {data.hex()}")
                return cb

            for ch in notif_chars:
                try:
                    await client.start_notify(ch, make_cb(ch.uuid))
                except Exception as e:
                    print(f"  subscribe {ch.uuid} failed: {e}")
            await asyncio.sleep(notify_secs)
            for ch in notif_chars:
                try:
                    await client.stop_notify(ch)
                except Exception:
                    pass


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    tgt = sys.argv[1]
    secs = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    asyncio.run(main(tgt, secs))
