# Lumenate Nova — BLE protocol

Reverse-engineered from the Android app `com.lumenate.lumenateaa` (jadx) and a full
session HCI snoop capture. Confirmed values are marked ✅; inferences are marked ⓘ.

## 1. Hardware & overview

- Wearable stroboscopic **light mask, 4 LEDs**. SoC = **Nordic nRF52833** (read live from
  the Model Number char) ✅; manufacturer **"Oxalis Design"** (Manufacturer Name char);
  Nordic `no.nordicsemi.android.ble` client stack + Nordic-style DFU + blue/white status LED.
  Test unit: firmware `1.0.4`, hardware `1.0`.
- Advertises as local name **`Lumenate Nova`** ✅. The app scans with a `ScanFilter`
  on a service UUID ⓘ; filtering by name works too.
- **The flicker waveform is generated on the phone**, not the device. A native library
  (`libstrobecontroller-lib.so`, `StrobeManager.doStrobe(...)`) computes brightness/timing
  and the app streams compact "strobe frames" to the device ~9×/s ✅. The device runs the
  requested flicker autonomously between frames.
- Also supports **offline/standalone sessions** (device plays a stored program with no phone)
  and **on-device buttons** (power + brightness) that notify the phone.

## 2. Connection & security

- Transport: BLE / GATT. Negotiated **ATT MTU = 498** ✅.
- The device issues an SMP **Security Request** and the app performs **LE Secure Connections
  pairing + bonding** at connect time ✅ (14 SMP PDUs observed). Pairing looked like
  Just-Works (no passkey UI on the mask) ⓘ.
- The device **bonds to one central at a time** (status LED: flashing white = looking for its
  last device, solid blue = connected). It will not accept a new host while it is still bound to
  the phone.
- **Confirmed live:** after tapping **"Forget this Nova"** in the app (which drops the
  phone-side association), the Nova accepts a fresh connection from the Mac and **all custom
  characteristics are readable/writable with no bonding/encryption barrier** ✅ — GATT reads and
  strobe writes succeed immediately. So the custom services do *not* require encryption; the
  bonding was only for the device's auto-reconnect to its remembered phone. (After this, you'll
  need to re-pair the Nova with your phone in the app to use it there again.)

## 3. GATT table (verified live from the device ✅)

Full table read from the connected Nova. **Address by UUID** (handles vary by firmware).
`WWR` = Write-Without-Response.

### Command service — `47bbfb1e-670e-4f81-bfb3-78daffc9a783`
| Char UUID | Props | Role |
|---|---|---|
| `964fbffe-6940-4371-8d48-fe43b07ed00b` | notify, read | **Remote/button events** — `[0x01, event]` |
| `3e25a3bf-bfe1-4c71-97c5-5bdb73fac89e` | WWR | **Command** — e.g. Welcome-LEDs |
| `2b35ef1f-11a6-4089-8cd5-843c5d0c9c55` | notify, WWR, read | extra command channel ⓘ (unmapped) |

### Offline-session service — `3e8ec328-a4b8-4273-a380-47d219f64e9b`
| Char UUID | Props | Role |
|---|---|---|
| `2a84aaff-6738-4629-894c-346357b89a0c` | notify, WWR, read | **Offline session mode** — 1 byte |
| `51bfc219-feab-4227-8b93-8af8cc5306d4` | read | **Offline session header** — 16 bytes |

### Strobe service — `b568de7c-b6c6-42cb-8303-fcc9cb25007c`
| Char UUID | Props | Role |
|---|---|---|
| `f2c51a4e-2a46-4bef-b18f-cb00c716cfa6` | WWR | **Strobe frames** (the core) |
| `12345678-9abc-4def-8012-3456789abcde` | notify, read | **Motion sensor** stream — 3×int16 LE ✅ |
| `abcdef01-2345-6789-abcd-ef0123456789` | WWR | **Motion sample-rate config** — 1 byte ✅ |

### Firmware-update service — `8d53dc1d-1db7-4cd3-868b-8a527460aa84` ⓘ
| Char UUID | Props | Role |
|---|---|---|
| `da2e7828-fbce-4e01-ae9e-261174997c48` | notify, WWR | buttonless-DFU entry / OTA (see §11). Not used in normal operation. |

### Standard
| Service | Char | Role |
|---|---|---|
| Battery `0x180F` | `0x2A19` | Battery level % (read/notify) ✅ |
| | `0x2BED` | (extra, read/notify/indicate) ⓘ |
| Device Info `0x180A` | `0x2A24` | Model number → `nrf52833` ✅ |
| | `0x2A29` | Manufacturer name → `Oxalis Design` ✅ |
| | `0x2A25` | Serial number → used as the device id ✅ |
| | `0x2A26` | Firmware revision → `1.0.4` ✅ |
| | `0x2A27` | Hardware revision → `1.0` ✅ |

## 4. Strobe frames (the core protocol) ✅

Write little-endian `uint32` arrays to the strobe char `f2c51a4e-…` with
**Write-Without-Response**. The app dedupes identical consecutive frames and streams updates
at ~9 Hz as the brightness envelope changes; the device keeps flashing at the last frame's
parameters until a new frame arrives.

Two layouts, chosen by the encoder (`D0.w0`):

**Symmetric (both eyes identical) — 12 bytes = 3 × uint32:**
```
[ period_us , on_us , color ]
```
This is what real guided sessions use (100% of the 4702 captured frames were symmetric).

**Asymmetric (per-eye, with an optional 2nd pulse) — 40 bytes = 10 × uint32:**
```
[ periodL , onL , periodL2 , onL2 , colorL ,
  periodR , onR , periodR2 , onR2 , colorR ]
```

Field encoding (from `jb.x` + `D0.w0`):
- `period_us = round(1e6 / frequency_Hz)`  — flash period in microseconds
- `on_us     = round(period_us * duty)`    — on-time (LED lit) in microseconds; `duty` ∈ (0,1]
- `color     = round(colorValue * 1e6)`    — **observed always 0** ✅ (white-light mask; field
  present but unused in captured sessions). Treat as `0`.
- All values clamped to `[0, 2^32-1]`. `frequency ≤ 0` or non-finite ⇒ the whole 4-tuple is
  zeroed (a blank/off frame).
- **Stop / blank:** write `[0, 0, 0]` (all zero) — the app does this on pause/stop.
- The `2nd pulse` (asymmetric only) is derived from a phase-offset input, letting one eye emit
  two pulses per cycle. Not needed for basic control.

Observed session envelope ✅: **frequency 7–14 Hz**, **duty 1%–70%**, stream rate 9.2 frames/s.

**Worked example** (real captured frame `5a 21 01 00 | 78 0e 00 00 | 00 00 00 00`):
- period = `0x0001215a` = 74074 µs → **13.5 Hz**
- on = `0x00000e78` = 3704 µs → duty = 3704/74074 = **5.0%**
- color = 0

## 5. Command characteristic ✅

Write to `3e25a3bf-…` (command service). Format: `[commandId, arg]`.
Known command id (enum `defpackage.c`):
- `0x01` = **Welcome LEDs** (greeting/identify animation). Captured write: `01 00`.

## 6. Offline / standalone sessions ✅

Write 1 byte to `2a84aaff-…` (offline service) to start a stored on-device session
(mode enum `defpackage.h`):
- `0x00` RELAXED, `0x01` EXPLORE, `0x02` SLEEP, `0xFF` NOT_SET.

The header char `51bfc219-…` reports 16 bytes (`NovaOfflineSessionHeader`, all uint32 LE):
```
[ magic , version , sessionCount , activeSessionIndex ]
```
Live read ✅: `magic=0x4F464C4E` ("NLFO"), `version=1`, `sessionCount=0`, `activeSessionIndex=255`
(no offline session stored on the test unit). The mode char `2a84aaff-…` read back `0xFF`
(NOT_SET) when idle.

## 7. Remote / button events ✅

Notifications on `964fbffe-…` (command service) with format `[0x01, event]`
(enum `EnumC4278k2`):
- `0x00` POWER, `0x01` BRIGHTNESS_UP, `0x02` BRIGHTNESS_DOWN.

Brightness is adjusted device-side via these buttons; it is **not** carried in the strobe
frame (`color` stays 0), so master brightness lives in the device firmware ⓘ.

## 8. Motion sensor ✅

The app calls this **"motion detection"** (`G1.j()` logs *"Setting motion detection enabled"*).
To turn it on:
1. Write a **1-byte sample rate** to `abcdef01-…` (strobe service). Observed value `0x0a` (=10).
   Writing `0x00` turns streaming off.
2. Subscribe to notifications on `12345678-…` (strobe service).

Each notification is 6 bytes = **3 × signed int16 LE** `(x, y, z)` — a 3-axis **accelerometer**
(confirmed live: values swing sharply with motion; at rest |(x,y,z)| ≈ 4096 = 1 g ⇒ **±8 g scale,
~4096 LSB/g**). Used to detect head movement during a session. The rate byte written to
`abcdef01-…` is the **sample rate in Hz** (verified: rate 20 → ~19.4 samples/s).

## 9. Group sessions

Up to 5 Novas can run in sync from one phone. Mechanically this is just the same per-device
strobe stream sent to multiple connections with a shared clock (`StrobeManager.syncMe(long)`
provides the time base) ⓘ.

## 10. Session content format (light "score" DSL) ✅

A guided session's light track is authored as a compact **text DSL** (found in the app's
session catalogue and parsed by `ib/c.java` into `ib/a`,`ib/b`). This is the *source* the phone
turns into the strobe frames of §4 — useful if you want to author your own sessions.

A session has **one or two** `;`-separated segment lists — the second (optional) is the
**right eye**; if omitted, both eyes use the first (symmetric). Each segment:

```
s(startSec, endSec, freqExpr, dutyExpr [, constantOnExpr, phaseShiftExpr])
```

Value expressions (each yields a start,end pair that is linearly interpolated across the segment):
- `c(x)`  — constant `x`
- `l(a,b)` — linear ramp `a → b`
- `z`     — zero (off)

`freqExpr` is in **Hz**, `dutyExpr` is a **0–1 fraction**. `constantOn`/`phaseShift` are optional
(default 0); `phaseShift` drives the per-eye second pulse (the 40-byte asymmetric frame in §4).

Example (real, from the app — a "Breathe" session, left eye):
```
s(0,13.6,z,z);                          # 0–13.6s: dark
s(13.6,16,l(13.5,6.5),c(0.01));         # ramp 13.5→6.5 Hz, 1% duty
s(16,25,c(6.5),c(0.01));                # hold 6.5 Hz, 1% duty
s(32,34,l(6.5,7.67),l(0.01,0.11));      # ramp freq & intensity up together
...                                     # (breathing cycles of ramps up/down)
```

Playback model: iterate time; within the active segment, linearly interpolate freq & duty, then
emit a §4 frame (`period=1e6/freq`, `on=period*duty`). See `nova.session` in `nova/nova.py`.

## 11. Firmware update (OTA) ⓘ

Not fully exercised (bricking risk), but the mechanism is clear from the app:
- The app calls Firebase Cloud Functions **`checkForHeadsetFirmwareUpdate`** (with hardware +
  firmware version) and **`generateHeadsetFirmwareUpdateURL`** to get a signed firmware download
  URL (`common/V1.java`). `libsigner.so` handles signing/verification.
- Update is then pushed over BLE via the **`8d53dc1d-…` / `da2e7828-…`** service (a Nordic-style
  buttonless-DFU entry that reboots the nRF52833 into its Secure DFU bootloader). **Do not poke
  this blindly** — a bad DFU can brick the device.

## Reserved / unused characteristics

Present in firmware but **not driven by this app version** (safe to ignore for control). Live
values read from the test unit ✅: `2b35ef1f-…` (command svc) = `0x2b`; `0x2BED` (battery svc) =
`00 00 00`. Both are static — nothing dynamic hides there.

## 12. Reproduce the analysis

- `tools/pull_apk.sh` + `tools/decompile.sh` — static analysis (jadx).
- `tools/snoop_start.sh` / `tools/snoop_pull.sh` / `tools/analyze_snoop.py` — live capture.
- `tools/connect_test.py`, `tools/probe.py`, `tools/live_show.py` — live device work.
- Key decompiled classes: `services/LumenateSessionService` (strobe→BLE bridge),
  `common/G1` (Nova manager + UUID table + motion detection), `common/D0` (per-device GATT,
  encoders `w0`/`s0`/`v0`/`t0`), `strobe/StrobeManager` (native waveform),
  `ib/{a,b,c}` (session DSL parser), `defpackage/{c,h}` (enums), `common/V1` (firmware update).
