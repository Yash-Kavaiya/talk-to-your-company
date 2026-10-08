---
workflow: general-video
flow: automation
storyboard: no
message: "A live 3D twin of your plants that you can talk to, with all AI on one NVIDIA Jetson Thor"
destination: youtube
aspect: 1920x1080
language: en
audience: hackathon judges
---

## Intent

**Ask (Yash, 2026-10-08):** "creat video with proper voice ... nice motion graphics full demo discuss all
the things also mention run on jentor thor live production give me full video i will review it and then push".

One narrated 16:9 film, about three and a half minutes, that covers the whole project: the problem, the
idea, every feature shown on real screen recordings of the running app, the two pipelines under the
hood, the Jetson Thor deployment design, and how the same code runs on a laptop through mocks.
Yash reviews the video before anything is pushed to GitHub.

## Assets

- `capture/raw/overview.mp4`, `capture/raw/story.mp4` — screen recordings made with `capture/record.py`
  (copied to `assets/` by `build.py`). `overview`: simulated site (mock perception). `story`: real video
  detection on a laptop CPU, public sample clips.
- `assets/vo/*.wav` — narration, one file per line of `narration/script.json`.

## Customizations

- Motion-graphic scenes for the problem, the idea, both pipelines, the Jetson Thor design and the mocks.
- No music bed: the narration carries it.

## Notes

- Truth constraint: `specs/tasks.md` shows nothing has run on a Jetson yet (phases 4 to 6 and T29 are
  open). The narration therefore says "built to run live on one NVIDIA Jetson Thor" and labels the
  numbers as design targets. If the app has since run on the Jetson, change the `thor`, `edge`, `mocks`
  and `close` lines in `narration/script.json` and the cards in `build.py`, then regenerate.
- Employees are synthetic; identity comes from a simulated badge feed. Said in narration and on screen.
- Voice input is not demonstrated on screen (questions are typed).
- Voice: local Kokoro (`af_heart`). The ElevenLabs key on this machine lacks text-to-speech permission.
- Look: the app's own control-room palette (near-black #0b1016, one teal accent #4fd1c5, red only for
  events). Montserrat for statements, IBM Plex Mono for labels and data.
