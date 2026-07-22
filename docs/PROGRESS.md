# Progress log

## Status: ✅ COMPLETE — protocol RE'd and Mac control verified live on hardware.

Live test result: connected from the Mac to the Nova (nRF52833, fw 1.0.4, battery 76%),
read device info, triggered Welcome LEDs, and drove a full strobe sequence (steady 10 Hz,
7→14 Hz sweep with breathing intensity, discrete strobes, blank/stop) — all working.
No bonding/encryption barrier once the phone "forgot" the device.

## What we did

1. **Pulled + decompiled** the Android app `com.lumenate.lumenateaa` (jadx). Native
   Kotlin app; flicker waveform generated in `libstrobecontroller-lib.so`.
2. **Captured** a full session HCI snoop log (`captures/btsnoop-last.log`, 9903 ATT
   packets, 4702 strobe frames) and analysed it with tshark.
3. **Cross-verified** decompiled encoders (`D0.w0/s0/v0`, `jb.x`) against the captured
   bytes — our frame encoder reproduces a real captured frame **byte-for-byte**.
4. Wrote **docs/PROTOCOL.md** (full protocol) and **nova/** (Python control lib + demo).

## Confirmed protocol (see docs/PROTOCOL.md)

- Advertises as **"Lumenate Nova"**; Nordic BLE stack; LESC pairing/bonding; MTU 498.
- **Strobe** = stream 12-byte frames `[period_us, on_us, color]` (LE u32) to
  `f2c51a4e-…` (svc `b568de7c-…`) write-without-response. freq 7–14 Hz, duty 1–70%,
  color always 0. ~9 frames/s.
- **Command** `[id,arg]` to `3e25a3bf-…` (svc `47bbfb1e-…`): 0x01 = Welcome LEDs.
- **Offline session** `[mode]` to `2a84aaff-…` (svc `3e8ec328-…`): 0/1/2 = relaxed/explore/sleep.
- **Buttons** notify `[0x01,event]` on `964fbffe-…`: 0/1/2 = power/bright+/bright-.
- **Sensor** notify 3×int16 LE on `12345678-…`. Battery 0x2A19; device info 0x2A24-27.

## How to control from the Mac (verified path)

1. In the Lumenate app, tap **"Forget this Nova"** (Nova settings) so the phone releases it.
   The Nova starts advertising in search mode (LED flashing white).
2. Run the demo (press the Nova power button if it stops advertising before connect):
   - `python3 nova/demo.py scan`
   - `python3 nova/demo.py info`
   - `python3 nova/demo.py welcome`
   - `python3 nova/demo.py ramp`     (or `strobe 10 0.3`, `monitor`)
   - one-shot show: `python3 tools/live_show.py`
3. To use the Nova with the phone again, just re-pair it in the app.

## Open questions

- Does the strobe stream need a keep-alive, or does one frame flash indefinitely? (demo
  re-sends to be safe; confirm live.)
- Exact semantics of the sensor stream (looks like accelerometer). Non-essential.
- The 2 unmapped command-service chars (0x001e–0x001f) — possibly OTA/DFU.
