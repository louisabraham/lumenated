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

## Quickstart (control from the Mac)

```bash
pip install bleak
# In the Lumenate app: Nova settings -> "Forget this Nova" (releases the phone bond).
python3 nova/demo.py scan          # find the Nova
python3 nova/demo.py info          # model/fw/serial/battery
python3 nova/demo.py welcome       # greeting LED animation
python3 nova/demo.py strobe 10 0.3 # steady 10 Hz, 30% duty
python3 nova/demo.py ramp          # 7->14 Hz sweep with breathing intensity
python3 nova/demo.py monitor       # subscribe to buttons/motion sensor/battery
python3 nova/demo.py session       # play a built-in light "score" (DSL)
python3 tools/live_show.py         # scripted end-to-end demo
```

- `docs/PROTOCOL.md` — the full BLE protocol + session content DSL.
- `docs/GENERATOR_DESIGN.md` — science-backed guide for building a light/sound session generator.
- `nova/nova.py` — reusable control library (strobe, commands, motion sensor, DSL session player).

⚠️ **Photosensitivity:** this drives a bright stroboscope at 7–14 Hz — a flicker range that
can trigger seizures in photosensitive people. Don't point it at someone's eyes during testing.

## Status

✅ Protocol reverse-engineered and Mac control verified on hardware. See `docs/PROGRESS.md`.
