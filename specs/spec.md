# Spec: Talk-to-your-Company

Status: frozen for the hackathon. Changes need a line in the changelog at the bottom.

## 1. Problem

A plant manager with several buildings and floors cannot watch every camera. Safety events
(near-misses, people in restricted zones, missing PPE) go unseen and unreported, and getting a
simple answer ("what is happening on floor 3 right now?") means walking there or calling someone.

## 2. Solution in one sentence

A live 3D twin of the company that you talk to: ask by voice, and the twin flies to the right
floor, shows what the cameras see, and answers out loud, with all AI running on one Jetson Thor.

## 3. Users

- Primary: plant or operations manager (asks questions, wants summaries).
- Secondary: safety officer (reviews events, needs incident reports).
- Demo audience: hackathon judges, scoring innovation 25, technical complexity 20,
  use of Jetson Thor 20, real-world impact 15, demo quality 10, business value 10.

## 4. Site model

- 2 plants (P1, P2), 3 floors each (F1-F3), one camera per floor: 6 streams.
- Cameras are looping recorded videos (mp4) treated as live streams. For the demo, one camera may instead
  be a live webcam: shared from the presenter's browser, or attached to the machine.
- Each floor has a rectangular footprint in metres and optional zones (restricted, walkway, dock).
- Each floor may list fixed equipment (conveyor, rack, machine, pallets, office) as rectangles; the twin
  draws it so floors look like real plant floors.

## 5. User stories and acceptance criteria

### US1 See the company (3D twin)
- AC1.1 On load, both plants render side by side, each with 3 stacked translucent floors.
- AC1.2 People and vehicles appear as moving markers at their mapped floor position,
  updated at least 5 times per second.
- AC1.3 Selecting a plant spreads its floors apart; selecting a floor flies the camera to it.
- AC1.4 Layout is generated from `config/site.yaml`; changing the file changes the scene.
- AC1.5 Focusing a floor shows that floor's live camera view with the tracked objects boxed.

### US2 See events
- AC2.1 The system raises four event types: `near_miss`, `restricted_zone`, `no_helmet`, `crowding`.
- AC2.2 A new event shows a pulsing marker on the right floor within 2 seconds.
- AC2.3 Clicking a marker opens a side panel with snapshot, time, location and a one-line summary.
- AC2.4 Events persist and can be queried by plant, floor, type and time range.

### US3 Ask by voice
- AC3.1 Hold-to-talk button (and space bar) records speech; release sends it.
- AC3.2 The transcript, the answer text and spoken audio are all shown or played.
- AC3.3 Time from release to first spoken audio: target 2.5 s, hard limit 5 s.
- AC3.4 A text box does the same thing without a microphone (fallback and testing).

### US4 Voice drives the twin
- AC4.1 "Show me Plant 2, floor 3" moves the 3D camera there while the agent speaks.
- AC4.2 Answers that mention events highlight those events' markers.

### US5 Questions the agent must answer
- AC5.1 Status: "Give me a status of both plants" (counts of people, vehicles, open events).
- AC5.2 History: "Any safety issues on Plant 1 in the last ten minutes?"
- AC5.3 Live vision: "What is the worker near the conveyor on Plant 2 floor 1 doing?"
  (answered from the current frame by the vision model).
- AC5.4 Report: "Write the incident report for that" produces a structured report in the side panel.
- AC5.5 Unknown or out-of-scope questions get an honest "I can't see that" rather than a guess.

### US7 Know who it was (demo story, synthetic data only)
- AC7.1 An event that involves one person names that person, from a simulated badge feed over a
  synthetic employee directory. Nobody is identified from their face or appearance.
- AC7.2 A person in a restricted zone they are authorised for raises no event.
- AC7.3 "Who is this person?" answers with name, role and shift, and opens a panel with department,
  supervisor, training, authorisation, when they entered the zone, when the alert was raised, when they
  left (or that they are still inside), time in the zone, where they are now and their other incidents.
- AC7.4 Follow-ups work by voice or text: how long, has this happened before, who is the supervisor,
  where is <name> now. The incident report names the person.

### US6 Prove it is edge
- AC6.1 A HUD shows per-stream frames per second, last voice latency, GPU use and memory.
- AC6.2 The HUD states that no audio or video leaves the device.

## 6. Non-functional requirements

- NFR1 At least 10 frames per second of detection per stream with 6 streams (drop to 4 if needed).
- NFR2 Total memory inside the 15 GB limit with headroom of 2 GB.
- NFR3 App survives a model failure: any real backend can fall back to its mock at startup.
- NFR4 Starts from cold with one command and is demo-ready in under 3 minutes.
- NFR5 Works in current Chrome over the team's HTTPS app URL.

## 7. Out of scope

Live physical cameras beyond the one optional demo webcam, robot control, user accounts, multi-language voice, mobile layout,
model training or fine-tuning, cross-camera re-identification, always-listening wake word.

## 8. Acceptance demo (the golden path)

The build is done when this runs end to end three times in a row on the Jetson:

1. Twin loads, 6 streams live, HUD visible.
2. "Give me a status of both plants."
3. "Show me Plant 2, floor 3."
4. "Any safety issues in the last ten minutes?" then click a marker.
5. "What is the worker near the conveyor doing right now?"
6. "Write the incident report."
7. One unscripted question from a judge.

## 9. Open questions

- Q1 Footage: which six public or synthetic warehouse and factory videos? (owner: Yash, due Mon)
- Q2 Helmet detection: PPE-trained detector weights, or vision-model check on person crops?
- Q3 Does GPU memory count against the 15 GB container limit? (ask organizers)
- Q4 Team's assigned GPU window and demo slot.

## Changelog

- v1: initial spec.
- v6: US7, employee identity for events from a simulated badge feed and a synthetic directory, with visit
  timing and history (requested by Yash, 2026-10-04). The no-personal-data rule stands: fictional people
  only, no face recognition.
- v5: any floor's camera can be fed from the browser with a recording (a video file) as well as a webcam,
  so a presenter can show detection on their own footage (requested by Yash, 2026-10-04).
- v4: section 4 and 7, one optional live webcam next to the recorded videos, for the demo
  (requested by Yash, 2026-10-04). Webcam frames are processed on the device like any other camera.
- v3: AC1.5, live camera view of the focused floor (requested by Yash, 2026-10-04).
- v2: section 4, optional fixed equipment per floor in the site model (requested by Yash, 2026-10-04).
