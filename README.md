# lumenated

Independent, unofficial reverse-engineering of the BLE protocol of the **Lumenate Nova**
light/sound mask — a documented protocol, a Python control library, and a science-backed
light/sound *session generator*, so you can drive a Nova you own from your own computer.

Not affiliated with, authorized, or endorsed by Lumenate. See **[License & legal](#license--legal)**.

> ⚠️ **Photosensitivity / seizure risk.** This drives a bright stroboscope in the 7–18 Hz
> range, which overlaps the band that can trigger seizures in people with photosensitive
> epilepsy. Do not use if you (or anyone exposed) are photosensitive, pregnant, or under 18
> without medical advice; never shine it into someone's eyes as a "test"; keep an instant
> stop reachable. Use at your own risk — no warranty (see LICENSE).

## Layout

- `tools/` — RE and control scripts
  - `scan.py` — BLE advertisement scanner
  - `pull_apk.sh` — pull the Lumenate APK from a USB-connected Android phone
  - `decompile.sh` — decompile the APK with jadx and grep for BLE bits
  - `snoop_start.sh` / `snoop_pull.sh` — capture & retrieve the Bluetooth HCI snoop log
  - `enumerate.py` — connect to the Nova and dump all GATT services/characteristics
- `apk/` — pulled APK + decompiled sources (gitignored; large)
- `captures/` — HCI snoop logs and analysis (gitignored)
- `docs/PROTOCOL.md` — the protocol documentation
- `lumenated/` — the installable Python package (control library, generator, interactive player)

## Method

1. **Static**: decompile the app → find service/char UUIDs, scan name filter, command encoders.
2. **Dynamic**: enable Android "Bluetooth HCI snoop log", exercise each app feature,
   pull `btsnoop_hci.log`, read GATT writes/notifications in Wireshark/tshark.
3. **Confirm**: connect from the Mac with bleak, replay/adapt commands, build the demo.

## Install

```bash
pip install lumenated                 # once published to PyPI
# or, from a clone of this repo:
pip install -e .                      # core (bleak + numpy): control + generator + player
pip install -e ".[music]"             # + music search/download (ytmusicapi, yt-dlp)
```

> **yt-dlp + endpoint security:** yt-dlp bundles `cookies.py` (a browser-cookie extractor)
> that some EDRs (e.g. SentinelOne) quarantine, which breaks a normal `pip install`. If that
> happens, install yt-dlp with `python3 tools/install_ytdlp_stub.py` — it installs a build
> with a **benign, no-browser-access** cookies module (public downloads still work), so nothing
> flagged is written. On a managed device, prefer an IT-approved exclusion.

## Quickstart (control from the Mac)

```bash
# In the Lumenate app: Nova settings -> "Forget this Nova", then power it to flashing blue (pairing).
lumenated scan            # find the Nova
lumenated info            # model / fw / serial / battery
lumenated welcome         # greeting LED animation
lumenated strobe 10 0.3   # steady 10 Hz, 30% duty
lumenated ramp            # 7->14 Hz sweep with breathing intensity
lumenated monitor         # subscribe to buttons / motion sensor / battery
lumenated session         # play a built-in light "score" (DSL)
```

### Session generator (light + sound)

```bash
lumenated generate relax 10             # generated 10-min 'relax' light arc
lumenated generate explore 12 song.mp3  # preset light alongside your music
lumenated reactive song.mp3             # light reacts to a music file (duty <- envelope)
lumenated iso explore 8                 # generated isochronic tones + matched light
# presets: relax | sleep | explore | energize
```

### Interactive player (recommended)

```bash
lumenated-play
```

A minimal, keyboard-only wizard — one decision at a time. Navigate menus with **↑↓ / j k**,
**→ or Enter** to go forward, **← to go back**, 1-9 to jump. Flow:

1. **Sound** — search a track · a suggested track · generated tones · none
2. **Light** — *reactive* (tracks the music) vs a designed *journey* — asked only when there's a track
3. **Journey** — which light preset (skipped for reactive; there the music drives the light)
4. **Connect the Nova** — the last step, with pairing instructions + a retry loop

Then **press the Nova's power button to start**; **power or space pauses/resumes** (light and
audio freeze together); **q / esc / Ctrl-C quits** — just like the app.

- `lumenated/core.py` — control library (strobe, commands, motion sensor, DSL session player).
- `lumenated/generator.py` — presets, audio-reactive mode, isochronic synth.
- `lumenated/music.py` — YouTube-Music search/download; `lumenated/wizard.py` — the player.
- `docs/PROTOCOL.md` — the full BLE protocol + session content DSL.
- `docs/GENERATOR_DESIGN.md` — science-backed guide for the light/sound generator.

The reverse-engineering `tools/` require a decompiled APK and BLE captures; **those are not
included** in this repo (see License & legal) — regenerate them from your own device/app.

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

## License & legal

The original work in this repository — the Python code (`lumenated/`, `tools/`) and the documentation
(`docs/`, this README) — is released under the **MIT License** (see [LICENSE](LICENSE)).

- **Independent & unofficial.** This is interoperability reverse-engineering of a device the
  author owns, done for personal use and research. It is **not** affiliated with, authorized by,
  or endorsed by Lumenate. "Lumenate" and "Nova" are trademarks of their respective owner, used
  here only for identification (nominative fair use).
- **No Lumenate code, firmware, or assets are included or distributed.** The decompiled app, the
  APK, and the Bluetooth captures used during analysis are deliberately **not** committed (they're
  in `.gitignore`). Regenerate them from your own device and app copy with the scripts in `tools/`.
- **Facts vs. expression.** The protocol details documented here (UUIDs, byte layouts, value
  encodings) are factual interoperability information and are not themselves copyrightable; the
  MIT license covers only this repo's original code and prose.
- **No warranty.** Provided "as is". You are responsible for safe and lawful use — including the
  photosensitive-seizure risk described above and not attempting firmware modification (the DFU
  path is documented but untested and can brick the device).
