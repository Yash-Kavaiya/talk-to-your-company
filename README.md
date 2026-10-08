# Talk-to-your-Company

A live 3D twin of a company (2 plants x 3 floors) that you talk to. Ask by voice or text; the twin
flies to the right floor, shows what the cameras see and answers out loud. Detection, the language
and vision model, speech recognition and speech synthesis all run on one NVIDIA Jetson Thor.
No audio or video leaves the device.

Specs: [`specs/spec.md`](specs/spec.md) (what), [`specs/plan.md`](specs/plan.md) (how),
[`specs/tasks.md`](specs/tasks.md) (order and status).

## Architecture

```
 6 looping videos                                                      browser (Chrome)
       |                                                        +--------------------------+
       v                                                        |  Three.js twin           |
  ingest (GStreamer hw decode, OpenCV fallback)                 |  tracks, event markers   |
       |  latest frame per stream                               |  side panel, HUD         |
       v                                                        |  push-to-talk, text box  |
  detector (YOLO, TensorRT FP16, one batch for all streams)     +------------^-------------+
       v                                                                     |
  tracker (ByteTrack-style, per stream)                                      |  /ws  JSON
       v                                                                     |
  mapper (homography: pixels -> floor metres)                                |
       |  tracks                                                             |
       v                                                                     |
  +-----------------------------  FastAPI on 0.0.0.0:8000  ------------------+-------------+
  |  broadcast loop, 5 Hz:  state -> rules -> event store (SQLite) -> event, metrics       |
  |                                                                                        |
  |  query:  audio -> ASR (Whisper) -> agent loop (VLM + tools) -> sentences -> TTS (Piper)|
  |          tools: query_events  live_state  look  focus_view  show_event  write_report   |
  +----------------------------------------------------------------------------------------+
```

Every heavy component has a mock, chosen by environment variable, so the whole app runs on a laptop:

| Variable | Values | Mock behaviour |
|---|---|---|
| `PERCEPTION` | `mock` / `real` | Simulated people and vehicles; scripted scenarios raise real rule events |
| `LLM` | `mock` / `local` | Keyword router that calls the same tools |
| `ASR` | `mock` / `local` | Returns a fixed question (`MOCK_ASR_TEXT`) |
| `TTS` | `mock` / `local` | A short chime per sentence |

If a real backend fails to load, the app logs it and starts with that backend's mock (NFR3).
`GET /api/health` shows what is actually running.

## Run on a laptop (all mock, no GPU)

    pip install --user -r requirements.txt
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

Open http://localhost:8000. Try: "Give me a status of both plants", "Show me Plant 2, floor 3",
"Any safety issues in the last ten minutes?", click a red marker, "Write the incident report".

    pytest -q

Focus a floor (click it, use the list, or ask) to see its live camera view bottom right. In mock mode
that view is a synthetic top-down drawing; with real perception it is the video with detection boxes.

### Real backends on a laptop (CPU, optional)

Useful to check the real code paths before Jetson time. It is slow and only sensible with one or two
cameras and small models:

    scripts/safe_install.sh ultralytics
    scripts/safe_install.sh piper-tts
    VLM_MODEL=HuggingFaceTB/SmolVLM-256M-Instruct ASR_MODEL=openai/whisper-tiny.en \
      python scripts/download_models.py --models-dir data/models --skip-engine
    python scripts/get_sample_videos.py --videos-dir data/demo-videos
    # copy config/site.yaml to data/site.demo.yaml; set a camera to `webcam:0` to use the laptop's camera.
    # All six cameras run at about 1 fps on a CPU with DETECTOR_WEIGHTS=data/models/yolo11n.pt.
    SITE_CONFIG=data/site.demo.yaml VIDEOS_DIR=data/demo-videos PERCEPTION=real ASR=local TTS=local LLM=mock DEVICE=cpu \
      MODELS_DIR=data/models ASR_MODEL=openai/whisper-tiny.en \
      python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

Keep `LLM=mock` here: a model small enough for a laptop CPU cannot choose tools.

## Demo story: someone enters a restricted area

Plant 1, floor F2 has a restricted zone. In the sample clip for that camera a worker walks in and stops
there, so the alert comes back on every loop of the video (in mock mode a simulated person does the same).

1. A red marker appears on Plant 1 F2: "Arjun Mehta (E1006) has been inside restricted zone z2 ..."
2. Click the marker, or ask "Any safety issues on Plant 1?"
3. "Who is this person?" answers with name, role and shift, and opens a panel with department, supervisor,
   training, whether they are authorised, when they entered, when the alert was raised, when they left and
   how long they stayed, where they are now, and their other incidents today.
4. Follow up: "How long were they in there?", "Has this person done this before?",
   "Who is the supervisor?", "Where is Arjun Mehta now?"
5. "Write the incident report" produces a report that names the person.

The people are fictional (`config/employees.yaml`) and the identity comes from a simulated badge feed, not
from face recognition: the system attaches a badge to whoever it tracks on that floor. To use real
staff you would replace `BadgeFeed` in `app/identity.py` with your access-control system. An employee who
is authorised for a zone (the maintenance technician of each floor) raises no alert there.

## Camera sources: recorded mp4 files and a live webcam

Each camera in `config/site.yaml` has a `video:` that is one of:

| Value | Meaning |
|---|---|
| `p1f2.mp4` | A recorded video, looped. Relative names are looked up in `VIDEOS_DIR` (default `/cache/videos`). |
| `browser` | Whoever opens the app can share their webcam into this camera (Plant 1, floor F1 by default). |
| `webcam:0` | A camera attached to the machine that runs the app (`webcam:/dev/video0` also works). |

    python3 scripts/get_sample_videos.py --videos-dir /cache/videos    # public sample clips, one per file camera

**Share from the browser.** Focus any floor and use the buttons in its camera view:

- **Share webcam** sends your webcam into that floor's camera (allow the camera when asked).
- **Share recording** lets you pick a video file; it plays in a loop and its frames go to that camera.

While you share, your picture replaces that camera's own source; **Stop sharing** gives it back.
To use the webcam on the default site: focus Plant 1, F1 and press **Share webcam**. With real perception you are detected, boxed in the camera view and appear as a marker in the
twin. The browser only allows this over HTTPS or on localhost. Frames are processed in memory, but an
event raised on that floor stores a snapshot in `DATA_DIR/snapshots`; delete that folder after a demo
with real people in view.

## Deploy on the Jetson Thor

1. Copy the repo to `/workspace` on the Jetson, without the local `data/` folder. For example, on the
   laptop: `tar --exclude=data --exclude=__pycache__ -czf ttyc.tar.gz talk-to-your-company`, upload it,
   then on the Jetson: `cd /workspace && tar -xzf ttyc.tar.gz && cd talk-to-your-company`.
2. One-time setup (the only step that uses the network; several GB into `/cache`):

       scripts/setup_jetson.sh

   It installs the Python packages one at a time through `safe_install.sh` (which refuses anything that
   would touch `torch`, `torchvision` or `numpy`, and the script stops if their versions changed),
   downloads the models, exports the detector to TensorRT, fetches the sample videos and runs preflight.
3. Calibrate each camera so markers land where people stand:

       python3 scripts/calibrate.py cam_p1f2 --save-frame /cache/p1f2.jpg   # then --points, per camera

Every start:

    scripts/preflight.sh && scripts/run.sh

`run.sh` sets all four modes to real, keeps data in `/cache/ttyc`, and sets the Hugging Face and
Ultralytics offline flags so nothing is fetched at runtime.

Checks to run on the Jetson, in this order (see `specs/tasks.md`, phases 4 to 6):

    LLM=local python3 scripts/eval_tool_calling.py     # T19: 13 of 15 right tools

Then the golden path from `specs/spec.md` section 8, three clean runs.

## Configuration

- `config/employees.yaml` is the synthetic employee directory (`EMPLOYEES` overrides the path).
- `config/site.yaml` is the only place that knows plants, floors, cameras, zones and equipment. Change it and
  the twin, the rules and the agent follow.
- `SITE_CONFIG`, `DATA_DIR`, `MODELS_DIR` override paths. `DEVICE=cpu` loads the real models without a GPU. `VLM_MODEL`, `ASR_MODEL`, `PIPER_VOICE`,
  `DETECTOR_WEIGHTS` override models.

## Layout

    app/         FastAPI app, perception, events, agent, voice, metrics
    web/         index.html, style.css, src/*.js (plain ES modules), vendor/three (r170, MIT)
    config/      site.yaml
    scripts/     setup_jetson.sh preflight.sh run.sh safe_install.sh download_models.py
                 get_sample_videos.py calibrate.py eval_tool_calling.py
    tests/       pytest, mock mode only
    specs/       spec.md plan.md tasks.md
