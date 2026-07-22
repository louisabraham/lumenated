# Progress log

## Known facts (from public sources + recon)

- Nova = wearable light mask, **4 independently-controlled LEDs**, stroboscopic sequences.
- Controls: play/pause + intensity from both the app and the device buttons.
- **Group session**: up to 5 Novas synced to one phone.
- Status LEDs: flashing white = searching for last device; solid blue = connected;
  alternating blue/white = needs factory reset.
- **OTA firmware update** via app (Settings > Lumenate Nova > Update Nova) → almost
  certainly Nordic Secure DFU ⇒ **nRF52-class hardware**.
- No public reverse-engineering of the protocol exists (checked 2026-07).

## Hypotheses to confirm

- Custom control service (possibly Nordic-UART-style: one write char + one notify char),
  plus a Nordic DFU service (0000fe59 / 8ec9xxxx).
- Session = either streamed brightness frames, or a pattern id + parameters the device
  plays locally. The 1–2 min "warm up" hints the app may stream/schedule frames.

## Environment

- Mac: Python 3.14 + bleak installed; jadx installed; tshark installed; adb installed.
- nRF52840 MDK: NOT currently seen on USB (would be a sniffer fallback anyway).
- Android phone: not yet connected via adb.

## Next steps

1. [blocked: phone] Pull APK, decompile, extract UUIDs + command encoders.
2. [blocked: phone] HCI snoop log while exercising each app feature.
3. Enumerate Nova GATT from Mac (needs Nova in connectable/unbonded state).
4. Write protocol doc + Python control demo.
