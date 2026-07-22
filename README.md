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

## Device buttons & LED states

The Nova has a **power** button and **+ / −** (brightness) buttons at the top, with a status
LED. Meanings below are ✅ from the Lumenate app's own help text / support docs, or ⓘ inferred
(undocumented).

**Power button**
- **Hold ~4 s (from off)** → powers on into connection mode. ✅
- **Hold power + `+` together** → save/play a preset 10-minute offline light sequence (a
  standalone on-device session). ✅
- **`+` / `−`** → brightness up/down (these emit the `BRIGHTNESS_UP`/`DOWN` remote events). ✅

**Status LED**
- **Flashing blue** = *pairing mode* — no remembered device, open to a new connection. ✅
  (App: "Hold the power button until you see a flashing blue light. This indicates that Nova is
  in pairing mode.")
- **Flashing white** = it *has* a remembered device and is searching for that one specifically. ✅
- **Solid blue** = connected/paired to a device. ✅
- **Alternating blue/white** = fault; needs a reset. ✅
- **No light on power-on** = flat battery — charge ≥10 min, then retry. ✅
- **Brief solid green (short press while on)** = ⓘ *undocumented* — not in Lumenate's docs or the
  app. Most likely a battery/charge "OK / powered & ready" acknowledgement (green = healthy
  charge), consistent with how single-button devices flash green on a tap. Not confirmed.

**Getting "flashing blue" (open pairing) vs "flashing white":** the colour on power-on depends on
whether the Nova still remembers a device. If it flashes **white**, it is still bonded to a
previous phone and hunting for it. To force **flashing blue** (open pairing so a *new* host — e.g.
this Mac — can connect), the device must forget its bond:
- The app's **"Forget this Nova"** clears only the *phone side*, so the Nova may still boot to
  white. A **device-side factory reset** is what clears the on-device bond and returns it to
  flashing blue. Lumenate documents the *alternating blue/white* state as "needs a reset" but does
  **not** publish the exact button combo (ⓘ likely a long power hold, or holding power + both
  brightness buttons). Try a long power hold first; if unsure, contact Lumenate support.

Sources: [Lumenate — trouble connecting your Nova](https://support.lumenate.co/en/articles/12918154-i-m-struggling-to-connect-my-nova-what-might-be-going-wrong),
[Lumenate Nova support collection](https://support.lumenate.co/en/collections/14181536-lumenate-nova),
and the decompiled app's in-app help strings.

## Status

✅ Protocol reverse-engineered and Mac control verified on hardware. See `docs/PROGRESS.md`.
