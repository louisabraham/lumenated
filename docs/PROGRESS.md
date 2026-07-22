# Progress log

## Status: protocol RE complete (static + dynamic). Live Mac-control test pending.

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

## Next: live control from the Mac

Needs the physical Nova **connectable from the Mac**. Because it bonds to one central and
is currently bonded to the phone:
1. Ensure it's not connected to the phone app (LED flashing white). Try `python3 nova/demo.py scan`.
2. If it won't connect/pair (still bonded to phone), **factory-reset** the Nova (LED
   alternates blue/white), then retry — CoreBluetooth will Just-Works pair.
3. Validate: `info` → `welcome` → `strobe 10 0.3` → `ramp` → `monitor`.

## Open questions

- Does the strobe stream need a keep-alive, or does one frame flash indefinitely? (demo
  re-sends to be safe; confirm live.)
- Exact semantics of the sensor stream (looks like accelerometer). Non-essential.
- The 2 unmapped command-service chars (0x001e–0x001f) — possibly OTA/DFU.
