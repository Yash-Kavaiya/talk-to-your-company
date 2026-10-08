// Section "Architecture in detail": the technical deep dive, called from build.js.
// Same facts as ../beamer/architecture.tex and docs/architecture.md; change all three together.
module.exports = function architecture({ pres, content, lead, bullets, chip, colors, THEME, W, M, TOP }) {
  const { INK, SOFT, BLACK, GREEN, LIME, MUTED, CARD } = colors;
  const FULL = W - 2 * M;
  const header = (t) => ({ text: t, options: { bold: true, color: BLACK, fill: { color: GREEN }, fontSize: 13 } });
  const cell = (t, kind) => ({ text: t, options: { color: kind === "key" ? INK : SOFT, bold: kind === "key", fontFace: kind === "code" ? "Consolas" : undefined, fill: { color: CARD }, fontSize: 13 } });
  const code = (t) => ({ text: t, options: { color: INK, fontFace: "Consolas", fill: { color: CARD }, fontSize: 13 } });
  const table = (s, rows, colW, name, rowH = 0.5, y = TOP + 0.05) => s.addTable(rows, {
    x: M, y, w: colW.reduce((a, b) => a + b, 0), colW, rowH, border: { type: "solid", color: THEME.colors.dk1, pt: 1.5 },
    valign: "middle", margin: [0.04, 0.12, 0.04, 0.12], objectName: name });
  const note = (s, text, y, name = "Note") => s.addText(text, { x: M, y, w: FULL, h: 0.5, fontSize: 14, italic: true, color: MUTED, valign: "top", margin: 0, isTextBox: true, objectName: name });
  const cards = (s, items, y, h, cols = items.length) => {
    const gap = 0.3, w = (FULL - gap * (cols - 1)) / cols;
    items.forEach(([head, body, mono], i) => {
      const x = M + (i % cols) * (w + gap), cy = y + Math.floor(i / cols) * (h + gap);
      s.addShape(pres.ShapeType.roundRect, { x, y: cy, w, h, rectRadius: 0.1, fill: { color: CARD }, line: { color: CARD, width: 0 }, objectName: `Card ${i + 1}` });
      s.addText(head, { x: x + 0.3, y: cy + 0.22, w: w - 0.6, h: 0.45, fontSize: 19, bold: true, color: GREEN, fontFace: mono ? "Consolas" : undefined, margin: 0, isTextBox: true, objectName: `Card ${i + 1} head` });
      s.addText(body, { x: x + 0.3, y: cy + 0.75, w: w - 0.6, h: h - 0.95, fontSize: 14, color: SOFT, valign: "top", margin: 0, isTextBox: true, objectName: `Card ${i + 1} body` });
    });
  };
  const steps = (s, items, y) => {
    const w = FULL / items.length;
    s.addShape(pres.ShapeType.line, { x: M + w / 2, y: y + 0.23, w: FULL - w, h: 0, line: { color: MUTED, width: 1.25 }, objectName: "Step line" });
    items.forEach((text, i) => {
      chip(s, i + 1, M + i * w + w / 2 - 0.23, y);
      s.addText(text, { x: M + i * w + 0.08, y: y + 0.6, w: w - 0.16, h: 0.8, fontSize: 13, color: INK, align: "center", valign: "top", margin: 0, isTextBox: true, objectName: `Step ${i + 1}` });
    });
  };

  {
    const s = content("One process runs three loops at once",
      "One FastAPI process. Perception in threads, a 5 Hz broadcast loop, and an async agent loop per question.");
    cards(s, [
      ["Perception threads", "One thread per stream decodes video. The latest frame of every stream goes to the detector in one batch, then to the tracker and the mapper."],
      ["Broadcast loop, 5 Hz", "Reads the latest tracks, runs the rules, attaches identity, stores events and sends state to the browser. Metrics go out once a second."],
      ["Agent loop, per question", "Asynchronous. Speech to text, up to three rounds of tool calls, the final answer, then speech sentence by sentence."],
    ], TOP + 0.05, 2.6);
    lead(s, "One FastAPI process on 0.0.0.0:8000. The browser is the only client, and that is the only port.", M, TOP + 3.0, FULL, 0.9);
    note(s, "Python 3, FastAPI, pydantic models for every message that crosses a boundary. Plain ES modules and Three.js in the browser.", TOP + 4.0);
  }
  {
    const s = content("Perception takes five stages from pixels to floor metres",
      "Each stage is one small module. The mock replaces all of them and still feeds the real rules.");
    table(s, [
      [header("Stage"), header("Module"), header("What it does")],
      [cell("Ingest", "key"), code("ingest.py"), cell("GStreamer hardware decode, looping, real time, 1280x720; OpenCV fallback. Files, a webcam or frames shared from a browser.")],
      [cell("Detect", "key"), code("detector.py"), cell("YOLO exported to TensorRT FP16. The latest frame of every stream goes through in one batch.")],
      [cell("Track", "key"), code("tracker.py"), cell("ByteTrack-style two-stage association per stream, in pure Python. Gives each person a stable id.")],
      [cell("Map", "key"), code("mapper.py"), cell("The foot point of each box goes through the camera homography to floor metres. Four clicked points calibrate a camera.")],
      [cell("Mock", "key"), code("mock.py"), cell("Simulated people and vehicles. A scripted scenario every 30 s makes the real rules raise a real event.")],
    ], [1.4, 2.0, 8.73], "Perception table", 0.66);
    note(s, "The camera view is the same data: one JPEG of the focused floor with every track boxed, about four times a second.", TOP + 4.25);
  }
  {
    const s = content("Rules are pure functions with fixed thresholds",
      "Thresholds are constants in app/events/rules.py. Each rule has unit tests.");
    table(s, [
      [header("Event"), header("Raised when"), header("Notes")],
      [code("near_miss"), cell("A person and a forklift are within 2 m and closing faster than 0.5 m/s."), cell("Severity 3.")],
      [code("restricted_zone"), cell("A person is inside a restricted polygon for more than 2 s."), cell("Once per stay. Authorised people raise nothing.")],
      [code("no_helmet"), cell("The vision model says no about a person crop."), cell("One unchecked person every 3 s.")],
      [code("crowding"), cell("More than 4 people are within a 3 m radius."), cell("Severity 1.")],
    ], [2.5, 5.6, 4.03], "Rules detail table", 0.62);
    bullets(s, ["Unit-tested: each rule has its own tests", "Debounced: no repeat within 30 seconds for the same tracks", "Backend-neutral: the same rules run on mock and real tracks"], M, TOP + 3.3, FULL, 1.5, 16);
  }
  {
    const s = content("Tracks live in memory, and events live in SQLite",
      "The event row is the source of truth for the report and for every question about history.");
    const boxes = [["TRACK, IN MEMORY", "id, zone, cls\nx, y, vx, vy\nbbox, last_seen", "Class is person, forklift or vehicle. Positions are floor metres. Sent to the browser five times a second.", M, 4.6],
      ["EVENT, ONE ROW IN SQLITE", "id, ts, plant, floor, camera_id\ntype, severity, track_ids\nx, y, snapshot_path, summary, person_id", "Indexed by time. Queried by plant, floor, type and time range. The snapshot is a file beside the database. An event is open for ten minutes.", M + 4.9, FULL - 4.9]];
    boxes.forEach(([label, fields, body, x, w], i) => {
      s.addShape(pres.ShapeType.roundRect, { x, y: TOP + 0.05, w, h: 3.0, rectRadius: 0.1, fill: { color: CARD }, line: { color: CARD, width: 0 }, objectName: `Data card ${i + 1}` });
      s.addText(label, { x: x + 0.3, y: TOP + 0.25, w: w - 0.6, h: 0.3, fontSize: 12, bold: true, color: LIME, charSpacing: 3, margin: 0, isTextBox: true, objectName: `Data ${i + 1} label` });
      s.addText(fields, { x: x + 0.3, y: TOP + 0.65, w: w - 0.6, h: 1.1, fontSize: 15, fontFace: "Consolas", color: INK, valign: "top", margin: 0, isTextBox: true, objectName: `Data ${i + 1} fields` });
      s.addText(body, { x: x + 0.3, y: TOP + 1.9, w: w - 0.6, h: 1.0, fontSize: 13, color: SOFT, valign: "top", margin: 0, isTextBox: true, objectName: `Data ${i + 1} body` });
    });
    lead(s, "The report is filled from the event row, not generated, so it cannot contain invented facts.", M, TOP + 3.4, FULL, 0.9);
  }
  {
    const s = content("One WebSocket carries eleven message types",
      "Every message is a pydantic model in app/protocol.py; the field type tells them apart.");
    const small = (t) => ({ text: t, options: { color: SOFT, fill: { color: CARD }, fontSize: 12 } });
    const key = (t) => ({ text: t, options: { color: INK, fontFace: "Consolas", fill: { color: CARD }, fontSize: 12 } });
    s.addTable([
      [header("Server to browser"), header("Carries")],
      [key("site"), small("the whole site, on connect")], [key("state"), small("every track per floor, 5 times a second")],
      [key("event"), small("one event row, when a rule fires")], [key("ui"), small("focus, highlight or open a panel")],
      [key("transcript"), small("what was heard or typed")], [key("answer"), small("one sentence per message")],
      [key("audio"), small("that sentence, spoken")], [key("metrics"), small("fps, latency, GPU, memory, once a second")],
    ], { x: M, y: TOP + 0.05, w: 6.6, colW: [2.2, 4.4], rowH: 0.42, border: { type: "solid", color: THEME.colors.dk1, pt: 1.5 }, valign: "middle", margin: [0.03, 0.12, 0.03, 0.12], objectName: "Server messages table" });
    s.addTable([
      [header("Browser to server"), header("Carries")],
      [key("audio_query"), small("16 kHz mono WAV")], [key("text_query"), small("a typed question")], [key("select_event"), small("a marker click")],
    ], { x: M + 7.0, y: TOP + 0.05, w: FULL - 7.0, colW: [2.3, FULL - 9.3], rowH: 0.42, border: { type: "solid", color: THEME.colors.dk1, pt: 1.5 }, valign: "middle", margin: [0.03, 0.12, 0.03, 0.12], objectName: "Client messages table" });
    s.addText("PLAIN HTTP", { x: M + 7.0, y: TOP + 2.1, w: 4, h: 0.3, fontSize: 12, bold: true, color: LIME, charSpacing: 3, margin: 0, isTextBox: true, objectName: "HTTP label" });
    s.addText("/api/health\n/api/camera/{plant}/{floor}", { x: M + 7.0, y: TOP + 2.45, w: FULL - 7.0, h: 0.7, fontSize: 14, fontFace: "Consolas", color: INK, valign: "top", margin: 0, isTextBox: true, objectName: "HTTP endpoints" });
    s.addText("Health reports which backends are real and which are mocks.", { x: M + 7.0, y: TOP + 3.2, w: FULL - 7.0, h: 0.6, fontSize: 13, color: SOFT, valign: "top", margin: 0, isTextBox: true, objectName: "HTTP note" });
  }
  {
    const s = content("The assistant must call a tool before it states a fact",
      "Tool calling is JSON-constrained and parsed by the app, so it does not depend on a model's chat template.");
    steps(s, ["Question, spoken or typed", "Model sees the tool schemas", "Tool runs, twin reacts", "Up to three rounds", "Final answer, two sentences", "Spoken, sentence by sentence"], TOP + 0.2);
    cards(s, [
      ["JSON tool calls", "The model answers with a tool name and arguments. The app parses them, so any model can be used."],
      ["Short memory", "The last six turns, the current view and the last event id, so “that” and “there” resolve."],
      ["Honest", "“I can’t see that” when the tools return nothing. No guessing."],
    ], TOP + 2.1, 2.2);
  }
  {
    const s = content("Seven tools connect the model to the site",
      "On a laptop a keyword router calls the same seven tools, so the interface never changes.");
    table(s, [
      [header("Tool"), header("Returns"), header("Effect on the twin")],
      [code("query_events"), cell("Events by plant, floor, type and time."), cell("Highlights their markers.")],
      [code("live_state"), cell("People, vehicles and open events now."), cell("None.")],
      [code("look"), cell("The vision model’s answer on the live frame."), cell("Focuses that floor.")],
      [code("focus_view"), cell("Nothing."), cell("Flies the camera there.")],
      [code("show_event"), cell("Nothing."), cell("Opens the event panel.")],
      [code("identify_person"), cell("Employee, visit timing, other incidents."), cell("Opens the person panel.")],
      [code("write_report"), cell("What, where, when, who, severity, action."), cell("Opens the report panel.")],
    ], [2.6, 5.5, 4.03], "Tools table", 0.5);
    note(s, "On a laptop a keyword router calls the same seven tools, so the interface never changes.", TOP + 4.3);
  }
  {
    const s = content("Voice: the target is 2.5 seconds to the first spoken word",
      "3.8 s was measured on a laptop CPU with the mock assistant. Nothing has been measured on the Jetson.");
    steps(s, ["Hold to talk", "16 kHz WAV over the socket", "Whisper transcribes", "Agent answers", "Piper speaks each sentence", "Queued playback"], TOP + 0.2);
    [["2.5 s", "target, from release to first audio", GREEN], ["3.8 s", "measured on a laptop CPU, mock assistant", LIME], ["5 s", "hard limit. Jetson: not measured yet", MUTED]].forEach(([value, label, color], i) => {
      const x = M + i * 4.15;
      s.addText(value, { x, y: TOP + 2.0, w: 3.7, h: 1.0, fontSize: 54, bold: true, color, margin: 0, valign: "middle", isTextBox: true, objectName: `Voice stat ${i + 1} value` });
      s.addText(label, { x, y: TOP + 3.05, w: 3.7, h: 0.6, fontSize: 14, color: SOFT, valign: "top", margin: 0, isTextBox: true, objectName: `Voice stat ${i + 1} label` });
    });
  }
  {
    const s = content("Identity comes from a badge feed, never from a face",
      "Say it plainly: fictional people, a simulated badge feed, no face recognition.");
    cards(s, [
      ["Synthetic directory", "Fictional employees: role, shift, supervisor, authorised zones."],
      ["Simulated badge feed", "Gives each tracked person on a floor one of its employees."],
      ["One class to replace", "A real access-control system plugs in at BadgeFeed."],
      ["Authorised means silent", "A person allowed in a zone raises no event."],
      ["Visit timing", "Entered, alert raised, left, time in the zone."],
      ["Prompt rule", "The model may not name anyone from appearance."],
    ], TOP + 0.05, 1.75, 3);
    note(s, "With real footage the badge goes to whoever the tracker sees: it shows the flow, it does not know who is in the video.", TOP + 4.25);
  }
  {
    const s = content("The frontend is plain ES modules and Three.js",
      "No bundler and no framework. Three.js is vendored, so the page loads with no network.");
    table(s, [
      [header("Module"), header("Role")],
      [code("twin.js, fixtures.js"), cell("Plants, floors, equipment and zones built from the site message.")],
      [code("tracks.js"), cell("Instanced markers, positions interpolated between state messages.")],
      [code("events.js"), cell("Pulsing event markers, click picking, the side panel.")],
      [code("camera.js"), cell("Camera view of the focused floor; share a webcam or a recording.")],
      [code("voice.js, wave.js"), cell("Push-to-talk, queued playback of the answer, the waveform.")],
      [code("hud.js"), cell("Per-stream fps, voice latency, GPU, memory, the privacy line.")],
      [code("scene.js, ws.js"), cell("Renderer and camera tweens; the one WebSocket.")],
    ], [3.4, 8.73], "Frontend table", 0.5);
    note(s, "No bundler and no framework. Three.js is vendored, so the page loads with no network.", TOP + 4.3);
  }
  {
    const s = content("Three scripts take a bare Jetson to a running demo",
      "These scripts are written and reviewed. They have not run on the device yet.");
    cards(s, [
      ["setup_jetson.sh", "Once, with the network. Installs packages one at a time, downloads the models, exports the detector to TensorRT, fetches the videos.", true],
      ["preflight.sh", "Every start. Checks CUDA, the hardware decoder, disk in /cache, port 8000, the Python modules, every model and every video.", true],
      ["run.sh", "Every start. All four backends real, data in /cache, offline flags set, then the app on port 8000.", true],
    ], TOP + 0.05, 2.5);
    bullets(s, ["No sudo, apt or Docker; torch, torchvision and numpy are never touched", "8 CPU cores, 15 GB of memory, one GPU shared with other teams", "Written and reviewed. Not yet run on the device."], M, TOP + 2.95, FULL, 1.6, 16);
  }
  {
    const s = content("Built spec first, and tested without a GPU",
      "Scope is frozen in the spec; the plan and the tasks follow it.");
    const cols = [["How the work is organised", ["spec.md says what: user stories with acceptance criteria", "plan.md says how: modules, protocol, models, memory budget", "tasks.md says in what order: one task at a time, each with a “done when”"]],
      ["How it is checked", ["77 automated tests, mock mode only, no GPU needed", "A tool-calling test set of 15 questions; the real model must get 13", "The golden path: seven steps, three clean runs on the Jetson"]]];
    cols.forEach(([head, items], i) => {
      const x = M + i * 6.2;
      s.addText(head, { x, y: TOP + 0.05, w: 5.8, h: 0.4, fontSize: 18, bold: true, color: INK, margin: 0, isTextBox: true, objectName: `Process ${i + 1} head` });
      bullets(s, items, x, TOP + 0.65, 5.8, 3.4, 16);
    });
  }
  {
    const s = content("Known risks, and what is already in place for each",
      "Every row has a fallback that is already in the code or the plan.");
    table(s, [
      [header("Risk"), header("Mitigation")],
      [cell("The shared GPU slows everything.", "key"), cell("Detector held at 10 fps, models pre-warmed, a backup video recorded.")],
      [cell("A dependency replaces torch.", "key"), cell("Every install is dry-run checked first; setup stops if a version changes.")],
      [cell("A small model is weak at tool calling.", "key"), cell("JSON-constrained calls, and the keyword router as the fallback.")],
      [cell("The microphone is blocked in the browser.", "key"), cell("The text box does the same thing.")],
      [cell("A model fails to load on stage.", "key"), cell("That backend starts as its mock and the rest keeps working.")],
    ], [4.8, 7.33], "Risks table", 0.62);
  }
};
