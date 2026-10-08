# Tasks

One task at a time. Format: ID, task, [where], (spec / plan reference), done when.
Where: L = laptop in mock mode, J = on the Jetson.

Status key: `[x]` done and verified against its "done when". `[ ]` with a "Code:" note means the code
is written and unit-tested where possible, but the "done when" needs the Jetson or a human.

## Phase 0: Foundation (Sunday)

- [x] T01 Scaffold repo, `app/config.py`, sample `config/site.yaml` for 2 plants x 3 floors [L]
      (plan 2, 3). Done when: loader test passes and rejects a malformed file.
- [x] T02 `app/protocol.py` pydantic models for all messages [L] (plan 5).
      Done when: round-trip serialization tests pass.
- [x] T03 Mock perception: random-walk tracks and timed scripted events [L] (plan 7).
      Done when: test shows tracks stay inside floor bounds and events fire.
- [x] T04 FastAPI app: serves `web/`, `/ws` sends `site`, then `state` at 5 Hz [L] (plan 1, 5).
      Done when: integration test receives `site` then `state`.

## Phase 1: 3D twin (Sunday to Monday)

- [x] T05 Scene and twin built from the `site` message [L] (AC1.1, AC1.4).
- [x] T06 Live track markers with interpolation [L] (AC1.2).
- [x] T07 Explode and focus camera animations, driven by clicks and by `ui` messages [L] (AC1.3, AC4.1).
- [x] T08 Event markers and side panel [L] (AC2.2, AC2.3).
- [x] T09 HUD from `metrics` messages [L] (AC6.1, AC6.2).
      Done when (T05-T09): manual check in the browser against each AC, in mock mode.

## Phase 2: Events (Monday)

- [x] T10 Rules engine with debounce [L] (AC2.1, plan 7). Done when: unit tests per rule pass.
- [x] T11 SQLite event store and query function [L] (AC2.4, plan 4). Done when: query tests pass.

## Phase 3: Agent (Tuesday)

- [x] T12 Tools over the store and live state [L] (plan 6). Done when: a test per tool passes.
- [x] T13 Agent loop with `LLM` interface and `MockLLM` [L] (plan 6).
- [x] T14 `text_query` end to end with text box in the UI [L] (AC3.4, AC4.1, AC5.1, AC5.2).
      Done when: integration test "show me plant 2 floor 3" yields `ui` focus and an `answer`.

## Phase 4: Jetson perception (Monday to Tuesday, in parallel with phases 2-3)

- [ ] T15 `scripts/preflight.sh` and `scripts/download_models.py` [J] (plan 10).
      Code: both scripts plus `scripts/safe_install.sh`. `download_models.py --skip-engine` ran on a laptop
      (found and fixed a relative-path bug). Preflight and the TensorRT export have never run.
- [ ] T16 GStreamer ingest for 6 looping videos, OpenCV fallback [J] (plan 7).
      Code: `app/perception/ingest.py`; OpenCV fallback and looping ran on a laptop with two public sample
      videos, shown in the browser camera view. Browser-webcam frames were detected and boxed on a laptop
      (frames posted by a script and by the page with a simulated camera). `webcam:0` ran with a laptop's
      built-in camera, and "Share recording" replaced a file camera's picture and gave it back on stop.
      All six cameras (webcam + five clips) ran together on a laptop CPU at 1 fps with a nano detector.
      The GStreamer hardware path is untested.
- [ ] T17 Detector to TensorRT, batched, plus ByteTrack [J] (NFR1).
      Done when: 6 streams at 10 fps or more, shown in metrics.
      Code: `detector.py`, `tracker.py`, `pipeline.py`. YOLO11s (PyTorch, CPU) + tracker + mapper ran on real
      footage: stable ids at 10 fps offline, 160 ms per frame on a laptop CPU. TensorRT and the 6 x 10 fps
      target need the Jetson.
- [ ] T18 `scripts/calibrate.py` and mapper; calibrate all 6 cameras [J] (plan 7).
      Done when: markers in the twin line up with people in the video.
      Code: `mapper.py` (unit-tested) and `calibrate.py`; site.yaml holds placeholder homographies.

## Phase 5: Voice and vision model (Wednesday)

- [ ] T19 Local VLM backend behind the `LLM` interface; tool-calling test set of 15 questions [J]
      (plan 6, 8). Done when: 13 of 15 pick the right tool.
      Code: `LocalLLM` in `app/agent/llm.py`. Load, chat and image paths ran on CPU with a 256M stand-in
      model, which is far too small to pick tools. The 3B model has never been loaded. Test set: `scripts/eval_tool_calling.py` (MockLLM scores 15/15).
- [ ] T20 `look` tool on the current frame [J] (AC5.3).
      Code: `look` tool passes the live frame to `LocalLLM.look`; ran on a real frame with the stand-in model
      (answer was nonsense, as expected at that size).
- [ ] T21 Push-to-talk capture and `audio_query` [L] (AC3.1).
      Code: `web/src/voice.js`; server side of `audio_query` is tested. Needs one manual microphone test in Chrome.
- [ ] T22 Local speech recognition [J] (AC3.2).
      Code: `LocalASR` in `app/voice/asr.py`. Ran on CPU with whisper-tiny.en through the live app: it got
      one of three test sentences wrong, so keep whisper-small or larger on the Jetson.
- [ ] T23 Sentence-streamed speech synthesis and queued playback [J] (AC3.2, AC3.3).
      Done when: release-to-first-audio under 2.5 s on three consecutive questions.
      Code: `LocalTTS`, per-sentence `audio` messages, queued playback. Piper ran on a laptop (2 s of speech
      in 0.14 s). Release-to-first-audio was 3.8 s on a laptop CPU with a mock LLM; unmeasured on the Jetson.

## Phase 6: Polish (Thursday)

- [ ] T24 `write_report` and report panel [L then J] (AC5.4).
      Laptop part done and tested (tool, panel). Jetson run pending.
- [ ] T25 Helmet check per spec Q2 decision [J] (AC2.1).
      Code: helmet loop in `pipeline.py` + `no_helmet` rule (unit-tested). Accuracy unknown until run with the VLM.
- [ ] T26 Real metrics: fps, voice latency, GPU, memory [J] (AC6.1).
      Code: `app/metrics.py`; fps, latency and memory verified in mock mode, GPU reading needs the Jetson.
- [x] T27 Startup fallback to mocks on model failure [L] (NFR3).
- [x] T28 `scripts/run.sh` cold start and README with architecture diagram [L] (NFR4).

## Added after the freeze (spec v2 to v6, requested by Yash)

- [x] T31 Floor equipment from site.yaml, richer twin [L] (spec 4).
- [x] T32 Camera view of the focused floor [L] (AC1.5). Real frames seen on a laptop CPU.
- [ ] T33 Webcam and recording sources: `browser`, `webcam:<device>`, Share webcam, Share recording [L then J]
      (spec 4). Works on a laptop; not yet tried over the Jetson's HTTPS URL.
- [x] T34 Who is this person: directory, badge feed, `identify_person`, person panel, visit timing [L] (US7).
      Done when: the conversation test passes and the mock scenario on the demo floor ends with a name.

## Friday: freeze

- [ ] T29 Golden path three clean runs on the Jetson (spec 8). No new code after this.
- [ ] T30 Record backup video. Rehearse the 10 + 7 minute slot twice.

## Cut order if behind

T25 helmet, then T24 report, then 6 streams down to 4, then T20 live vision.
Never cut: T07 voice-driven navigation, T23 spoken answers, T26 HUD.

## Human-only work (not for Claude Code)

- Find and download six videos; answer spec open questions Q1-Q4.
- Ask organizers for GPU window and demo slot.
- Click calibration points (T18). Judge whether answers sound right.
- Slides and business case.

## Prompts to use with Claude Code

Start of every session:
> Read CLAUDE.md, specs/spec.md, specs/plan.md and specs/tasks.md. Tell me the next unticked
> task and your approach in five lines. Wait for my OK.

Per task:
> Implement T10 only. Write the tests from its "done when" first, then the code. Run pytest.
> Tick T10 in specs/tasks.md. Do not touch other tasks.

When reality disagrees with the plan:
> T19 shows the model is unreliable at tool calling. Propose a change to specs/plan.md section 6,
> show me the diff, and update the affected tasks. Do not change code yet.

End of day:
> Summarize what is ticked, what is blocked, and what the spec's golden path still lacks.
