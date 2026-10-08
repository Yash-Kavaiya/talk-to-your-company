---
workflow: general-video
flow: automation
storyboard: no
---

# Brief: Talk-to-your-Company feature demo

**Ask (Yash, 2026-10-04):** "Use hyperframe and deepgram voice and create demo video to all all
features", then "also add real website", "recording and ss".

**Deliverable:** one narrated 16:9 film, 1920x1080, about 90 seconds, that walks through every
feature of the app using real screen recordings of the running website.

**Audience:** hackathon judges (innovation, technical complexity, use of Jetson Thor, impact, demo
quality, business value).

**Voice:** Deepgram text-to-speech (Aura). No music bed: the narration carries it.

**Footage:** recorded from the real app with `capture/record.py`.
- `overview` session: simulated site (mock perception) for the smooth whole-company shots.
- `story` session: real video detection on a laptop CPU for camera view, the restricted-zone story,
  the person panel, the report and a shared recording.

**Truth constraints for the narration**
- Nothing has run on a Jetson yet. Say "built to run on", never "running on". Say the recording is from a laptop.
- Employees are synthetic and identity comes from a simulated badge feed. Say so on screen.
- Voice input is not demonstrated on screen (questions are typed); do not show it as demonstrated.

**Look:** the app's own control-room palette (near-black, one teal accent, red only for events).
Montserrat for statements, IBM Plex Mono for labels and data. Footage sits in a framed screen with
a caption band underneath; punch-ins guide the eye to the panel being discussed.

## Assets
- `assets/overview.mp4`, `assets/story.mp4`: screen recordings. `assets/vo/*.wav`: narration.

## Customizations
- None requested beyond the ask.
