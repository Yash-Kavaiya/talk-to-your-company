# Technical plan

Implements `specs/spec.md`. Section numbers are referenced from `specs/tasks.md`.

## 1. Architecture

    videos -> ingest (GStreamer, hw decode) -> detector (YOLO/TensorRT) -> tracker (ByteTrack)
           -> mapper (homography to floor metres) -> rules -> event store (SQLite)
                                   |                             |
                                   v                             v
                         state broadcaster  ---- WebSocket ---- browser (Three.js twin, HUD, voice)
                                                                 ^
    mic audio -> ASR -> agent loop (LLM + tools) -> TTS ---------+

One FastAPI process on `0.0.0.0:8000`. Perception runs in a background thread per stream feeding
one batched detector. The agent loop is async. The browser is the only client.

## 2. Repository layout

    app/main.py              FastAPI app, static files, /ws, broadcast loop
    app/config.py            loads config/site.yaml and env run modes
    app/protocol.py          pydantic models for every WebSocket message
    app/backends.py          builds the four heavy components, falls back to mocks (NFR3)
    app/perception/          base.py ingest.py detector.py tracker.py mapper.py pipeline.py mock.py
    app/events/              rules.py store.py
    app/agent/               llm.py (mock + local) tools.py loop.py prompts.py
    app/voice/               asr.py tts.py (mock + local each)
    app/identity.py          synthetic employee directory, simulated badge feed, zone visit timing
    app/metrics.py           fps, latency, GPU, memory
    web/                     index.html style.css src/{main,scene,twin,fixtures,tracks,events,camera,hud,voice,ws}.js vendor/three
    config/site.yaml employees.yaml
    scripts/                 setup_jetson.sh preflight.sh run.sh safe_install.sh download_models.py
                             get_sample_videos.py calibrate.py eval_tool_calling.py
    tests/
    specs/                   spec.md plan.md tasks.md

## 3. Site config (`config/site.yaml`)

    plants:
      - id: P1
        name: Plant 1
        floors:
          - id: F1
            size_m: [40, 25]
            camera: {id: cam_p1f1, video: /cache/videos/p1f1.mp4, homography: [[..],[..],[..]]}
            zones:
              - {id: z1, type: restricted, polygon: [[0,0],[5,0],[5,5],[0,5]]}
            objects:
              - {id: c1, type: conveyor, rect: [8, 11, 20, 1.6]}   # x, y, width, depth in metres

Global zone key is `P1/F1`. Everything else derives from this file.

## 4. Data model

Track (in memory): `id, zone, cls (person|forklift|vehicle), x, y, vx, vy, bbox, last_seen`.

SQLite table `events`:
`id, ts, plant, floor, camera_id, type, severity (1-3), track_ids (json), x, y, snapshot_path, summary`.

## 5. WebSocket protocol (`/ws`, JSON, field `type` discriminates)

Server to client:
- `site`      full site config, sent on connect
- `state`     `{ts, zones: {"P1/F1": [{id, cls, x, y}]}}` at 5 Hz
- `event`     one event row
- `ui`        `{action: focus|highlight|panel, plant, floor, event_ids, content}`
- `transcript` `{text, final}`
- `answer`    `{text, done}` streamed
- `audio`     `{seq, wav_b64, last}` streamed speech chunks
- `metrics`   `{fps: {cam: n}, voice_latency_ms, gpu_pct, mem_gb}` at 1 Hz

Client to server:
- `audio_query` `{wav_b64}` after push-to-talk release
- `text_query`  `{text}`
- `select_event` `{event_id}`

## 6. Agent

Loop: user text -> LLM with tool schemas -> execute tools -> LLM final answer (max 3 tool rounds)
-> stream sentences to TTS as they complete. Conversation keeps the last 6 turns plus the
last-mentioned event ID so "that" resolves.

Tools:
- `query_events(plant?, floor?, type?, minutes_back=10)` -> list of events
- `live_state(plant?, floor?)` -> counts per zone and open events
- `look(plant, floor, question)` -> vision model answer on the current frame
- `focus_view(plant, floor?)` -> emits `ui` focus
- `show_event(event_id)` -> emits `ui` panel and highlight
- `write_report(event_id)` -> structured report (what, where, when, who, severity, action)

`MockLLM` is a keyword router that calls the same tools. It keeps the UI demoable without a
model and is the fallback required by NFR3.

System prompt rules: answer in two sentences or fewer, always call a tool before stating a fact
about the site, say "I can't see that" when tools return nothing.

## 7. Perception

- Ingest: GStreamer `filesrc ! qtdemux ! h264parse ! nvv4l2decoder ! nvvidconv ! appsink`,
  looping, throttled to real time, 1280x720. Fallback: OpenCV `VideoCapture`.
- Detector: YOLO (small or medium) exported to TensorRT FP16, batch across streams, 10 fps each.
- Tracker: ByteTrack per stream.
- Mapper: foot point (bottom-centre of bbox) through the camera homography to floor metres.
  `scripts/calibrate.py` lets you click 4 image points and type their floor coordinates.
- Mock: random-walk tracks per zone plus scripted events on a timer.

Rules (pure functions over tracks, unit-tested):
- `near_miss`: person and forklift within 2 m and closing speed above 0.5 m/s
- `restricted_zone`: person inside a restricted polygon for more than 2 s
- `crowding`: more than N people within a 3 m radius
- `no_helmet`: see spec Q2; start with vision-model check on a person crop every few seconds
- Debounce: same type and same tracks cannot re-fire within 30 s.

## 8. Models and memory budget (verify every choice on day 1)

| Component | Candidate | Budget |
|---|---|---|
| Vision-language model (agent + `look`) | 3B-class VLM with tool calling, half precision | 6 GB |
| Speech recognition | Whisper small | 1.5 GB |
| Detector | YOLO TensorRT FP16 | 1 GB |
| Speech synthesis | Piper (CPU) | 0.3 GB |
| App, frames, buffers | | 2 GB |
| Headroom | | 2 GB+ |

One VLM serves both text reasoning and vision to stay in budget. Test its tool calling first;
if unreliable, fall back to JSON-constrained prompts parsed by us.
All weights go to `/cache/models`. Load everything through the pre-installed NVIDIA PyTorch.

## 9. Frontend

- `scene.js`: renderer, lights, orbit controls, camera tween helper.
- `twin.js`: builds plants and floors from the `site` message; explode and focus animations.
- `tracks.js`: instanced meshes per class, positions lerped between `state` messages.
- `events.js`: pulsing markers, click picking, side panel.
- `voice.js`: push-to-talk via MediaRecorder, queued audio playback, voice orb.
- `wave.js`: waveform in the voice bar; follows the microphone or answer audio level, flat when idle.
- `hud.js`: metrics and the "nothing leaves the device" line.
- Geometry is boxes and planes generated in code. Dark theme, one accent colour, red for events.

## 10. Testing

- Unit: config loader, protocol models, rules, event store, each tool.
- Integration (mock mode): WebSocket connect receives `site` then `state`; `text_query`
  "show me plant 2 floor 3" yields a `ui` focus message; golden-path questions each yield an `answer`.
- Jetson: `scripts/preflight.sh` checks CUDA available, GStreamer hardware plugins, disk in
  `/cache`, port 8000 free, models present.
- Manual: golden path from spec section 8, three clean runs.

## 11. Risks

- Shared GPU slows everything: keep detector at 10 fps, pre-warm models, record a backup video.
- Dependency replaces torch: dry-run check before every install (CLAUDE.md).
- Small VLM weak at tool calling: MockLLM router as fallback for navigation intents.
- Microphone blocked in the browser: text box (AC3.4).

## 12. As built (v2 amendments)

Decisions taken while building. Each one refines a section above; where they differ, this section wins.

Protocol (section 5)
- `answer` carries one sentence per message; `done` is true on the last one. `audio` chunk `seq` n is that sentence spoken.
- `transcript` is sent for typed questions too, so the browser renders both paths the same way.
- On connect the server sends `site`, the current `state`, then one `event` per event of the last 10 minutes.
- `ui` `panel` has `content = {kind: "event", event}` or `{kind: "report", report, event}`.
- `GET /api/camera/{plant}/{floor}` returns the floor's current camera frame with every track boxed
  (JPEG; in mock mode the synthetic top-down SVG). `camera.js` polls it about 4 times a second for the
  focused floor only, so one stream is encoded at a time and nothing new is published besides port 8000.
- `GET /api/health` returns the run modes actually in use (`mock`, `real`/`local`, or `mock (fallback)`).
- Snapshots are files in `DATA_DIR/snapshots`, served at `/snapshots/`; `snapshot_path` holds that URL path.
- The browser records with MediaRecorder, then converts to 16 kHz mono 16-bit WAV before sending `audio_query`.

Agent (section 6)
- An event is "open" for 10 minutes after it was raised (there is no acknowledge step in scope).
- Tool calling uses the JSON-constrained fallback from section 8 from the start: tool schemas go into the
  system prompt and the model answers `<tool_call>{"name", "arguments"}</tool_call>`, parsed by us.
  This does not depend on the model's chat template. T19 still decides whether it is reliable enough.
- The system prompt ends with `Current view:` and `Last event id:` so "that" and "there" resolve for any LLM.
  The view follows `focus_view`, `look`, `show_event` and marker clicks.
- `query_events` emits `ui highlight` itself and `look` emits `ui focus`, so AC4.1 and AC4.2 hold whatever
  the model says.
- `write_report` is filled from the event row, not generated, so a report can never contain invented facts.
- The final answer is generated whole and then split into sentences for speech; it is not token-streamed.
  If T23 misses the 2.5 s target, streaming the generation is the first thing to add.

Perception (section 7)
- The rules engine runs in the broadcast loop on the tracks of whichever backend is active.
- Mock: tracks walk between waypoints; every 30 s a scripted scenario steers them (into a restricted zone,
  towards a forklift, into a group, or takes a helmet off) and the real rules raise the event.
  Mock snapshots are SVG top-down views labelled as synthetic.
- Tracker: ByteTrack-style two-stage IoU association in pure Python, without a Kalman filter.
- `restricted_zone` fires once per stay in the zone; `no_helmet` once per person until the helmet is back.
  Debounce suppresses a rule on a floor when it fired within 30 s for any of the same tracks.
- `no_helmet` (spec Q2): the vision model is asked yes/no about one unchecked person crop every 3 s,
  and skipped when the model is busy answering the user.
- COCO weights have no forklift class: `truck` is mapped to forklift, `car`, `bus`, `motorcycle` to vehicle.
  Weights with a real `forklift` class work unchanged (`DETECTOR_WEIGHTS`).
- Speech recognition and the VLM both load through `transformers`, so the Jetson needs one extra
  framework on top of the pre-installed PyTorch. Models: `VLM_MODEL` (default Qwen2.5-VL-3B-Instruct),
  `ASR_MODEL` (default whisper-small), `PIPER_VOICE`.

Frontend (section 9)
- Selecting a plant spreads its floors as a staircase (each floor up and back), not straight up, so the
  camera can look down on any floor without the floors above hiding it.
- `fixtures.js` draws each floor's `objects` (conveyor with moving parcels, rack, machine, pallets, office)
  as instanced boxes; floors also get a 5 m grid, see-through walls, and zone outlines with names.
  People, forklifts and trucks are built from a few parts each instead of one primitive.
- Mock people and vehicles route around equipment footprints (scenarios may still cut across).
- A navigation list (overview, plants, floors) is generated from the `site` message next to click picking.

Identity (spec US7)
- `config/employees.yaml`: synthetic directory (id, name, role, department, shift, supervisor, home floor,
  authorised zones, certifications). `EMPLOYEES` overrides the path.
- `app/identity.py`: `BadgeFeed` stands in for an access-control system. It gives each tracked person on a
  floor one of that floor's employees and keeps the badge when the tracker loses and re-finds someone
  nearby. It is the single place to replace with a real badge or location system.
- The hub names the person in the event summary and stores `person_id` on the event (new nullable column;
  older databases are migrated on open). Authorised people in a restricted zone raise no event.
- `People.visits` keeps, in memory, when the person entered the zone and when they left, per event.
- Tool `identify_person(event_id?, name?)`: employee details, visit timing, current location, incidents in
  the last 24 hours. It emits a `ui` panel with `content.kind = "person"`. `write_report` names the person.
- The system prompt forbids naming anyone from appearance; only this tool can name a person.
- `demo_restricted_floor` in site.yaml tells mock perception where to stage its restricted-zone scenario.
  Plant 1 F2's restricted zone sits where the worker in that camera's sample clip stops, so real
  perception raises the same alert every loop of the video.
- With real footage the badge is attached to whoever the tracker sees on that floor: it shows the flow,
  it does not know who is really in the video.

Camera sources (section 7)
- `camera.video` in site.yaml is one of: an mp4 file (a relative name is looked up in `VIDEOS_DIR`, default
  `/cache/videos`), `browser` (frames come from a browser's webcam), or `webcam:<device>` (a camera on the
  machine itself, e.g. `webcam:0`). `ingest.py` has one class per kind with the same `latest()` interface.
- Browser webcam: `camera.js` captures 1280x720 JPEG frames and sends them one at a time with
  `POST /api/camera/{plant}/{floor}/frame`. A frame older than 2 s counts as no picture, so the floor
  empties when sharing stops. This works where a USB camera is not visible inside the container, and it
  needs HTTPS or localhost, like the microphone.
- "Share recording" plays a chosen video file in the browser (looped, never uploaded as a file) and sends
  its frames the same way. Every camera accepts shared frames, whatever its own source: while they are
  fresh they replace the camera's picture, and when sharing stops the camera returns to its own source.
- In mock mode shared frames are shown in the camera view but nothing is detected.
- `scripts/get_sample_videos.py` downloads public sample clips for every file camera.
- `scripts/setup_jetson.sh` is the one-time setup: packages (dry-run checked, torch/numpy versions compared
  before and after), models, TensorRT export, videos, preflight.

Checking the real backends without a Jetson
- `DEVICE=cpu` lets `LocalLLM` and `LocalASR` load in float32 on a CPU. It exists only to exercise the
  real code paths on a laptop with small models; the Jetson keeps the default `cuda`.

Paths
- `DATA_DIR` (events database, snapshots) defaults to `./data` on a laptop; `scripts/run.sh` sets `/cache/ttyc`.
