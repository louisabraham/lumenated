# openlumenate

Reverse-engineering the BLE protocol of the **Lumenate Nova** light/sound device,
to control it from a Mac (and document the protocol) independently of the official
Android/iOS app.

Scope: interoperability with a device I own, for personal use.

## Layout

- `tools/` — RE and control scripts
  - `scan.py` — BLE advertisement scanner
  - `pull_apk.sh` — pull the Lumenate APK from a USB-connected Android phone
  - `decompile.sh` — decompile the APK with jadx and grep for BLE bits
  - `snoop_start.sh` / `snoop_pull.sh` — capture & retrieve the Bluetooth HCI snoop log
  - `enumerate.py` — connect to the Nova and dump all GATT services/characteristics
- `apk/` — pulled APK + decompiled sources (gitignored; large)
- `captures/` — HCI snoop logs and analysis (gitignored)
- `docs/PROTOCOL.md` — the protocol documentation (the deliverable)
- `nova/` — the Python control library + demo (the other deliverable)

## Method

1. **Static**: decompile the app → find service/char UUIDs, scan name filter, command encoders.
2. **Dynamic**: enable Android "Bluetooth HCI snoop log", exercise each app feature,
   pull `btsnoop_hci.log`, read GATT writes/notifications in Wireshark/tshark.
3. **Confirm**: connect from the Mac with bleak, replay/adapt commands, build the demo.

## Status

See `docs/PROGRESS.md`.
