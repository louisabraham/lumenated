# Light + Sound Generator — Science & Design Guide

Evidence-backed design notes for building a light/sound "session generator" for the Nova,
based on the flicker-entrainment literature and audio-visual-entrainment (AVE) practice.
Maps directly onto the Nova frame stream (`[period, on, color]`) documented in `PROTOCOL.md`
and the session DSL / `Nova.play_session` in `../nova/nova.py`.

## TL;DR design decisions
- **Core visual band: 7–18 Hz, sweet spot ~10 Hz.** 10 Hz rhythmic flicker reliably produces the
  strongest geometric-pattern/"trip" experience; 3 Hz is weak. Default **duty ≈ 0.3** (30% on-time).
- **Keep the flicker rhythmic.** Jittered/arrhythmic flicker at the same frequency *strongly*
  reduces the visual effects — periodicity itself drives the phenomenon. Modulate *intensity*
  freely with the music, but keep the *timing* regular.
- **Intensity = duty cycle** on the Nova (frames carry period/on-time; `color`/brightness is 0 and
  master brightness is a device-side button). "Brighter moments" → higher duty (cap ~0.6–0.7).
- **Sound: prefer isochronic/monaural tones over binaural** for entrainment you can phase-lock to
  the light (works on speakers). Best subjective results come from **light + music together**.
- **For music-driven light, modulate a rhythmic base flicker with the audio envelope** rather than
  hard-syncing flashes to transients (preserves rhythmicity while feeling reactive).
- **Safety is non-negotiable:** the effect band (8–18 Hz) overlaps the photosensitive-epilepsy
  danger zone (worst 15–25 Hz). Screening + warning + instant-stop + conservative first-run.

## 1. Why it works (mechanism)
Periodic light drives **neural entrainment**: cortical oscillations phase-align to the flicker
(a steady-state visual response), strongest in visual cortex, persisting a few cycles after the
stimulus stops ([bioRxiv AV study](https://www.biorxiv.org/content/10.1101/2023.10.25.563865v1.full);
[40 Hz microstates](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8710722/)). Flicker in the alpha
band elicits **Klüver form constants** (grids, spirals, tunnels) behind closed eyes — the basis of
Gysin's 1959 **Dreamachine** (8–13 Hz, eyes closed)
([flicker-hallucination history](https://karger.com/ene/article/62/5/316/124200/);
[Dreamachine](https://en.wikipedia.org/wiki/Dreamachine)) and of **Lumenate** (1–20 Hz)
([altered-states review](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8248711/)).

## 2. Frequency → experience map (for presets)
From the Sussex frequency/rhythmicity study (3/8/10/18 Hz, duty 0.3)
([PLOS One / PMC10089352](https://pmc.ncbi.nlm.nih.gov/articles/PMC10089352/)) plus AVE practice
([Mind Alive](https://mindalive.com/pages/audio-visual-entrainment-ave),
[Mind Machines](https://www.mindmachines.com/how-to-create-custom-brainwave-entrainment-sessions/)):

| Band | Hz | Subjective use | Notes |
|---|---|---|---|
| Delta | 0.5–4 | sleep, deep rest | ~no visuals (3 Hz weak); long sessions OK |
| Theta | 4–8 | deep meditation, hypnagogia, creativity, emotional release | dreamy imagery toward 7–8 Hz |
| **Alpha** | **8–13** | **relaxed awareness, richest visuals** | **10 Hz = peak geometric patterns** |
| Beta | 15–20 | focus, alertness | strong visuals at 18 Hz but activating; **PSE-risk peak** |
| Gamma | 40 | energize/cognition | 40 Hz light+sound (MIT GENUS) — research; keep short ([Picower review](https://picower.mit.edu/news/review-evidence-expanding-40hz-gamma-stimulation-promotes-brain-health)) |

## 3. Light generator design
Per-moment params: **frequency (Hz)**, **duty (0.01–0.7)**, optional **per-eye phase offset** (Nova
supports L/R + a 2nd pulse for shimmer/wave effects). Session = **timed segments with linear ramps**
— exactly Lumenate's own content model (per-eye DSL `s(start,end,freqExpr,dutyExpr)` with `c(x)`
constant, `l(a,b)` ramp, `z` off; see `PROTOCOL.md` §10).

**Session arc (adopt the AVE 3-part structure):**
1. **Induction/fade-in (~2–3 min):** start near where the brain is (~12–13 Hz, low duty ~0.05) and
   ramp toward target — never start abruptly at full intensity.
2. **Body (~10–15 min):** hold/oscillate around the target band; gently "breathe" duty
   (e.g. 0.1↔0.35) and slowly drift frequency. Effects appear in 5–15 min.
3. **Fade-out (~2–3 min):** ramp frequency and duty down before stopping. Sleep recipe: 12→2 Hz.

**Two concrete presets (Nova-ready, freq/duty over time):**
- *Relax/visual explore (10-min):* `0–90s: 13→10 Hz, duty 0.05→0.30` · `90s–8min: 10 Hz, duty
  breathe 0.15↔0.35 @ ~0.1 Hz` · `8–10min: 10→7 Hz, duty 0.30→0.05`.
- *Sleep (20-min):* `0–3min: 10→8 Hz` · `3–17min: 8→3 Hz slow ramp, duty 0.2` · `17–20min:
  3→1 Hz, duty→0`.

## 4. Sound design — three modes
**Mode A — Bring your own music (recommended default).** Light + music is **synergistic**: adding
music to 10 Hz flicker raised pattern/motion ratings and emotional arousal vs flicker alone
([Frontiers/PMC10901288](https://pmc.ncbi.nlm.nih.gov/articles/PMC10901288/)). Suggested artists
(slow, spacious, warm): Jon Hopkins *Music for Psychedelic Therapy*, Brian Eno *Ambient 1/4*, Stars
of the Lid, Nils Frahm, Hania Rani, Max Richter *Sleep*, Hammock, Ólafur Arnalds; for theta energy,
steady frame-drum (~4–7 Hz pulse). Ready-made: Spotify/Apple "Ambient Focus", "Deep Meditation",
SomaFM "Drone Zone".

**Mode B — Generated entrainment audio.** Synthesize alongside the light:
- **Isochronic tones** (carrier ~100–250 Hz gated on/off at the target Hz) — audio analog of the
  flash; **phase-lock it to the light pulses**. Works on speakers.
- **Monaural beats** for a smoother texture without headphones.
- **Binaural beats** only if headphones are guaranteed; evidence is mixed
  ([review](https://www.scielo.org.mx/scielo.php?script=sci_arttext&pid=S1665-50442021000600238)).
- Layer over a soft **drone/pink-noise pad**; keep entrainment tones barely audible under it.

**Mode C — Light generated from music (audio-reactive).** Map audio features → light **while
preserving flicker rhythmicity** (don't jitter the flash to every transient — that kills the visuals):
- **Loudness/RMS envelope → duty** (0.03–0.6): louder = more light. Main reactive channel.
- **Tempo/section → base flicker frequency**, snapped into 7–14 Hz and held rhythmic between
  changes; cross-fade freq on section boundaries, not every beat.
- **Bass → slow duty swells; highs → subtle per-eye phase shimmer.**
- **Beat onsets → gentle momentary duty boosts**, not hard resets of the pulse clock.
Fast flicker feels incongruous with slow music — match light dynamics to the track's pacing.

## 5. Safety (must-have in any generator)
The effective band (8–18 Hz) sits inside the photosensitive-epilepsy trigger zone; ~96% of
photosensitive people react at 15–20 Hz, and 3–30 Hz is broadly risky
([Epilepsy Action](https://www.epilepsy.org.uk/info/seizure-triggers/photosensitive-epilepsy);
[Int'l PSE guidelines](https://pmc.ncbi.nlm.nih.gov/articles/PMC11872230/)). Requirements: up-front
**PSE/pregnancy/<18 screening + warning**; a **low-intensity first-session default** and conservative
ramps; **instant stop** always reachable; **avoid saturated red and red↔blue alternation** (Nova is
white — good); eyes-closed lowers but doesn't remove risk; hydrate, sit/recline, expect possible
emotional release; keep beta/gamma segments **<30 min**
([Mind Machines safety](https://www.mindmachines.com/brainwave-entrainment-safety-what-you-need-to-know/)).

---

**Bottom line:** a segment-based engine (freq + duty ramps, per-eye phase) centered on **rhythmic
8–12 Hz, duty ~0.3**, with a **3-part session arc**; sound via **bring-your-own music (best) or
phase-locked isochronic tones**; and an **audio-reactive mode that modulates duty/segment-pacing
from the music envelope while keeping the flash clock rhythmic** — all of which maps cleanly onto
the Nova `[period, on, color]` frame stream.
