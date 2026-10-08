"""Write index.html (and STORYBOARD.md) from the scene list below, the narration lengths
(narration/timing.json) and the recording marks (capture/raw/*.json). Run it again whenever the
narration or the recordings change:

    python narration/generate.py kokoro && python build.py

Two kinds of scene: "shot" plays a cut of a screen recording inside a framed screen, "mg" is a
motion-graphic scene drawn in HTML. Edit this file, not index.html.
"""
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
RAW = HERE / "capture" / "raw"
ASSETS = HERE / "assets"
timing = json.loads((HERE / "narration" / "timing.json").read_text())
vo = timing["lines"]
script = {line["id"]: line["text"] for line in json.loads((HERE / "narration" / "script.json").read_text(encoding="utf-8"))}
marks = {name: json.loads((RAW / f"{name}.json").read_text()) for name in ("overview", "story")}
o, s = marks["overview"], marks["story"]

LEAD = 0.4  # narration starts this long after a scene opens
TAIL = 0.6  # and the scene holds this long after it ends
TESTS = 77  # `pytest -q` on 2026-10-08

# shot layout "wide": the whole 16:9 screen with a caption band below (simulated site)
# shot layout "side": the right 83% of the screen with a text column beside it (real detection on a laptop CPU)
# zoom = (scale, transform-origin) reached during the scene, to guide the eye
SCENES = [
    dict(id="title", kind="mg", extra=0.9),
    dict(id="problem", kind="mg", extra=0.4),
    dict(id="solution", kind="mg", extra=0.5),
    dict(id="twin", kind="shot", layout="wide", src="overview", at=o["overview"] - 0.1, tag="LIVE TWIN",
         head="Every person and vehicle, on the right floor", zoom=None),
    dict(id="plants", kind="shot", layout="wide", src="overview", at=o["plant1"], tag="SITE FROM CONFIG",
         head="Floors spread apart to show what is inside", zoom=None),
    dict(id="ask", kind="shot", layout="wide", src="overview", at=o["status"], tag="ASK",
         head="Plain questions, by voice or by text", zoom=(1.22, "50% 100%")),
    dict(id="goto", kind="shot", layout="wide", src="overview", at=o["goto"], tag="VOICE DRIVES THE TWIN",
         head="“Show me Plant 2, floor 3”", zoom=None, min=8.5),
    dict(id="safety", kind="shot", layout="wide", src="overview", at=o["safety"] + 1.6, tag="SAFETY EVENTS",
         head="The last ten minutes, lit up on the twin", zoom=None, min=6.5),
    dict(id="honest", kind="shot", layout="wide", src="overview", at=o["unknown"] + 1.0, tag="NO GUESSING",
         head="Out of scope gets an honest “I can’t see that”", zoom=(1.25, "50% 100%"), min=5.5),
    dict(id="camera", kind="shot", layout="side", src="story", at=s["floor"] + 2.0, tag="CAMERA VIEW",
         head="A live camera on every floor, detections boxed", zoom=(1.3, "100% 100%"), min=6.0),
    dict(id="alert", kind="shot", layout="side", src="story", at=s["issues"], tag="RESTRICTED ZONE",
         head="The alert names the person", zoom=(1.2, "70% 100%"), min=7.5),
    dict(id="who", kind="shot", layout="side", src="story", at=s["who"], tag="WHO IS THIS PERSON",
         head="Name, role, timing and authorisation", zoom=(1.22, "100% 0%"),
         note="Synthetic employees. Simulated badge feed. No face recognition."),
    dict(id="report", kind="shot", layout="side", src="story", at=s["report"], tag="INCIDENT REPORT",
         head="Written from one sentence", zoom=(1.22, "100% 0%"), min=8.0),
    dict(id="share", kind="shot", layout="side", src="story", at=s["share"] + 3.4, tag="SHARE A RECORDING",
         head="Drop a video or your webcam into any camera", zoom=(1.3, "100% 100%"), min=7.0),
    dict(id="arch", kind="mg", extra=0.5),
    dict(id="voice", kind="mg", extra=0.5),
    dict(id="thor", kind="mg", extra=0.8),
    dict(id="edge", kind="shot", layout="wide", src="overview", at=o["hud"] + 0.5, tag="EDGE HUD",
         head="No audio or video leaves the device", zoom=(1.5, "0% 100%"), max_footage=True,
         note_wide="Recorded on a laptop: the figures on screen are the laptop’s."),
    dict(id="mocks", kind="mg", extra=0.6),
    dict(id="close", kind="mg", extra=3.2),
]
LIMITS = {"overview": o["end"], "story": s["end"]}
SHOTS = [x for x in SCENES if x["kind"] == "shot"]


def sec(n: float) -> str:
    return f"{n:.2f}".rstrip("0").rstrip(".")


# ---- timeline
t = 0.0
for scene in SCENES:
    need = vo[scene["id"]] + LEAD + TAIL + scene.get("extra", 0.0)
    length = max(scene.get("min", 0.0), need)
    if scene["kind"] == "shot":
        room = LIMITS[scene["src"]] - scene["at"]
        if length > room and scene.get("max_footage"):
            scene["hold"] = round(room - 0.1, 2)  # the footage ends early; its last frame is held
        elif length > room:
            raise SystemExit(f"scene {scene['id']} needs {length:.1f} s of footage from {scene['at']:.1f}, "
                             f"but {scene['src']} ends at {LIMITS[scene['src']]:.1f}")
    scene.update(start=round(t, 2), length=round(length, 2))
    t = round(t + length, 2)
total = t
for number, scene in enumerate(SHOTS):
    scene["number"] = number + 1
BY = {scene["id"]: scene for scene in SCENES}


def said(sid: str, fragment: str, shift: float = 0.0) -> float:
    """Roughly when a phrase of a scene's narration is spoken (by its position in the text)."""
    text = script[sid]
    return round(BY[sid]["start"] + LEAD + vo[sid] * text.index(fragment) / len(text) + shift, 2)


# ---- stills
def still(source: Path, at: float, target: Path, size: str = "1920:1080") -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(at), "-i", str(source), "-frames:v", "1",
                    "-vf", f"scale={size}", "-q:v", "2", str(target)], check=True)


(ASSETS / "tiles").mkdir(parents=True, exist_ok=True)
for name in ("overview", "story"):
    target = ASSETS / f"{name}.mp4"
    if not target.exists() or target.stat().st_mtime < (RAW / f"{name}.mp4").stat().st_mtime:
        target.write_bytes((RAW / f"{name}.mp4").read_bytes())
still(ASSETS / "overview.mp4", o["overview"] + 4.0, ASSETS / "still_title.jpg")
still(ASSETS / "overview.mp4", o["plant1"] + 5.0, ASSETS / "still_end.jpg")
# six camera tiles for the problem scene: public sample clips (the same ones the app plays)
TILES = [("PLANT 1 · F3", "p1f3", 12), ("PLANT 2 · F3", "p2f3", 14), ("PLANT 1 · F2", "p1f2", 20),
         ("PLANT 2 · F2", "p2f2", 30), ("PLANT 1 · F1", "p2f2", 95), ("PLANT 2 · F1", "p2f1", 18)]
for i, (_, clip, at) in enumerate(TILES):
    if not (ASSETS / "tiles" / f"t{i}.jpg").exists():
        still(REPO / "data" / "demo-videos" / f"{clip}.mp4", at, ASSETS / "tiles" / f"t{i}.jpg", "880:496")

body, tw, audio, board = [], [], [], []


def win(scene: dict) -> str:
    return f'data-start="{sec(scene["start"])}" data-duration="{sec(scene["length"])}"'


def enter(sel: str, at: float, frm: str, dur: float = 0.55, ease: str = "power3.out") -> None:
    to = {"opacity": "1", "x": "0", "y": "0", "scale": "1", "scaleX": "1", "scaleY": "1"}
    keys = [part.split(":")[0].strip() for part in frm.split(",")]
    tw.append(f'tl.fromTo("{sel}", {{ {frm} }}, {{ {", ".join(f"{k}: {to[k]}" for k in keys)}, duration: {dur}, ease: "{ease}" }}, {sec(at)});')


def mg_open(scene: dict, kicker: str, head: str, head_css: str = "") -> None:
    sid = scene["id"]
    body.append(f'<div class="clip scene" id="sc-{sid}" {win(scene)} data-track-index="10"><div class="in" id="in-{sid}">')
    body.append(f'<p class="kicker" id="{sid}-kicker">{kicker}</p>')
    body.append(f'<h2 class="h" id="{sid}-h" style="{head_css}">{head}</h2>')
    a = scene["start"]
    tw.append(f'tl.set(".frame", {{ opacity: 0 }}, {sec(a)});')
    enter(f"#{sid}-kicker", a + 0.1, "opacity: 0, x: -30", 0.5, "power2.out")
    enter(f"#{sid}-h", a + 0.2, "opacity: 0, y: 36", 0.7)


def mg_close(scene: dict) -> None:
    sid = scene["id"]
    body.append("</div></div>")
    end = scene["start"] + scene["length"]
    tw.append(f'tl.fromTo("#in-{sid}", {{ opacity: 1 }}, {{ opacity: 0, duration: 0.3, ease: "power1.in", immediateRender: false }}, {sec(end - 0.3)});')


# ---- title
sc = BY["title"]
a = sc["start"]
body.append(f'<div class="clip scene" id="sc-title" {win(sc)} data-track-index="10"><div class="in" id="in-title">'
            f'<img class="card-bg" id="title-bg" src="assets/still_title.jpg" alt="" /><div class="card-shade"></div>'
            f'<p class="card-kicker" id="title-kicker">LIVE 3D TWIN · VOICE COPILOT · ON THE EDGE</p>'
            f'<h1 class="card-title" id="title-main">Talk to your Company</h1>'
            f'<div class="card-rule" id="title-rule"></div>'
            f'<p class="card-line" id="title-line">Ask a question. The twin flies to the right floor and answers out loud.</p>'
            f'<p class="chip chip-teal" id="title-chip">BUILT FOR ONE NVIDIA JETSON THOR</p>'
            f'</div></div>')
tw.append(f'tl.set(".frame", {{ opacity: 0 }}, 0);')
tw.append(f'tl.fromTo("#title-bg", {{ scale: 1.04, transformOrigin: "60% 50%" }}, {{ scale: 1.14, transformOrigin: "60% 50%", duration: {sec(sc["length"])}, ease: "none" }}, 0);')
enter("#title-kicker", 0.25, "opacity: 0, y: 18", 0.5, "power2.out")
enter("#title-main", 0.4, "opacity: 0, y: 44", 0.8)
tw.append('tl.fromTo("#title-rule", { scaleX: 0, transformOrigin: "0% 50%" }, { scaleX: 1, transformOrigin: "0% 50%", duration: 0.6, ease: "power2.out" }, 0.9);')
enter("#title-line", 1.2, "opacity: 0, y: 18", 0.6, "power2.out")
enter("#title-chip", said("title", "built for"), "opacity: 0, x: -24", 0.5, "back.out(1.6)")
mg_close(sc)
body.pop(-1)  # the title's markup was closed above

# ---- problem: six cameras, one pair of eyes
sc = BY["problem"]
a = sc["start"]
mg_open(sc, "THE PROBLEM", "Nobody can watch every camera.", "width: 740px;")
ROWS = [("Near misses", "Near misses"), ("People in restricted zones", "people in restricted"), ("Missing helmets", "missing helmets")]
for i, (label, fragment) in enumerate(ROWS):
    body.append(f'<div class="row" id="problem-row{i}" style="top: {452 + i * 84}px;"><span class="dot"></span>'
                f'<span class="row-t">{label}</span><span class="row-x">UNSEEN</span></div>')
    enter(f"#problem-row{i}", said("problem", fragment), "opacity: 0, x: -40", 0.5, ["power3.out", "back.out(1.4)", "expo.out"][i])
body.append('<p class="foot" id="problem-foot" style="top: 760px; width: 720px;">A simple question means walking there, or calling someone.</p>')
enter("#problem-foot", said("problem", "And a simple"), "opacity: 0, y: 20", 0.6, "power2.out")
TX, TY, TW_, TH, GAP = 920, 152, 440, 248, 22
pos = [(TX + (i % 2) * (TW_ + GAP), TY + (i // 2) * (TH + GAP)) for i in range(6)]
for i, (label, _, _) in enumerate(TILES):
    x, y = pos[i]
    body.append(f'<div class="tile" id="tile{i}" style="left: {x}px; top: {y}px;"><img src="assets/tiles/t{i}.jpg" alt="" />'
                f'<div class="tile-dim" id="tile-dim{i}"></div><span class="tile-l">{label}</span>'
                f'<span class="tile-a" id="tile-a{i}"></span></div>')
    enter(f"#tile{i}", a + 0.35 + i * 0.07, "opacity: 0, scale: 0.9", 0.5, "power2.out")
body.append(f'<div class="focus" id="focus" style="left: {pos[0][0] - 6}px; top: {pos[0][1] - 6}px;"><span>WATCHING</span></div>')
enter("#focus", a + 0.9, "opacity: 0, scale: 1.12", 0.4, "power2.out")
tw.append(f'tl.fromTo("#tile-dim0", {{ opacity: 0.72 }}, {{ opacity: 0.05, duration: 0.3 }}, {sec(a + 0.9)});')
hops, order, when, cur = [], [3, 4, 1, 2, 5, 0, 3, 4, 1], a + 2.2, 0
while when < a + sc["length"] - 1.0 and order:
    nxt = order.pop(0)
    hops.append((when, cur, nxt))
    tw.append(f'tl.fromTo("#focus", {{ x: {pos[cur][0] - pos[0][0]}, y: {pos[cur][1] - pos[0][1]} }}, {{ x: {pos[nxt][0] - pos[0][0]}, y: {pos[nxt][1] - pos[0][1]}, duration: 0.45, ease: "power3.inOut", immediateRender: false }}, {sec(when)});')
    tw.append(f'tl.fromTo("#tile-dim{cur}", {{ opacity: 0.05 }}, {{ opacity: 0.72, duration: 0.35, immediateRender: false }}, {sec(when)});')
    tw.append(f'tl.fromTo("#tile-dim{nxt}", {{ opacity: 0.72 }}, {{ opacity: 0.05, duration: 0.35, immediateRender: false }}, {sec(when + 0.2)});')
    cur, when = nxt, when + 1.7


def watched(at: float) -> set:
    """Tiles the focus frame is on, or moving between, around a moment."""
    seen = {0}
    for moment, frm, to in hops:
        if moment <= at + 1.2:
            seen = {to} | ({frm} if moment > at - 1.0 else set())
    return seen


used = set()
for (label, fragment), kind in zip(ROWS, ("NEAR MISS", "RESTRICTED ZONE", "NO HELMET")):
    at = said("problem", fragment, 0.15)
    tile = next(i for i in (5, 2, 1, 4, 3, 0) if i not in watched(at) and i not in used)
    used.add(tile)
    body[body.index(next(b for b in body if f'id="tile-a{tile}"' in b))] = \
        next(b for b in body if f'id="tile-a{tile}"' in b).replace(f'id="tile-a{tile}"></span>', f'id="tile-a{tile}">{kind}</span>')
    tw.append(f'tl.fromTo("#tile-a{tile}", {{ opacity: 0, scale: 0.6 }}, {{ opacity: 1, scale: 1, duration: 0.4, ease: "back.out(2.2)" }}, {sec(at)});')
for i in range(6):
    if i not in used:
        tw.append(f'tl.set("#tile-a{i}", {{ opacity: 0 }}, {sec(a)});')
mg_close(sc)

# ---- solution: three steps
sc = BY["solution"]
a = sc["start"]
mg_open(sc, "THE IDEA", "A twin you can ask.", "font-size: 104px; line-height: 116px; width: 1500px;")
STEPS = [("01", "Speak a question", "Hold to talk, or type it.", "Speak a question"),
         ("02", "The twin flies there", "Right plant, right floor, live camera.", "The twin flies"),
         ("03", "It answers out loud", "Spoken, on screen, events lit up.", "answers out loud")]
for i, (n, title, sub, fragment) in enumerate(STEPS):
    at = said("solution", fragment, -0.1)
    body.append(f'<div class="step" id="step{i}" style="left: {120 + i * 580}px;"><div class="step-rule" id="step-rule{i}"></div>'
                f'<p class="step-n">{n}</p><p class="step-t">{title}</p><p class="step-s">{sub}</p></div>')
    enter(f"#step{i}", at, ["opacity: 0, y: 50", "opacity: 0, scale: 0.88", "opacity: 0, x: 60"][i], 0.6, ["power3.out", "back.out(1.5)", "expo.out"][i])
    tw.append(f'tl.fromTo("#step-rule{i}", {{ scaleX: 0, transformOrigin: "0% 50%" }}, {{ scaleX: 1, transformOrigin: "0% 50%", duration: 0.7, ease: "power2.inOut" }}, {sec(at + 0.1)});')
QUESTION = "What is happening on floor 3 right now?"
body.append(f'<div class="ask-bar" id="ask-bar"><span class="ask-orb" id="ask-orb"></span><p class="ask-q" id="ask-q">“{QUESTION}”</p></div>')
enter("#ask-bar", a + 0.7, "opacity: 0, y: 30", 0.5, "power2.out")
tw.append(f'tl.fromTo("#ask-q", {{ clipPath: "inset(0% 100% 0% 0%)" }}, {{ clipPath: "inset(0% 0% 0% 0%)", duration: 1.9, ease: "steps({len(QUESTION) + 2})" }}, {sec(a + 1.1)});')
tw.append(f'tl.fromTo("#ask-orb", {{ scale: 1 }}, {{ scale: 1.35, duration: 0.5, ease: "sine.inOut", yoyo: true, repeat: {max(0, int((sc["length"] - 1.2) / 0.5) - 1)} }}, {sec(a + 0.9)});')
mg_close(sc)


# ---- pipelines
def pipeline(sid: str, kicker: str, head: str, nodes: list, chips_label: str, chips: list, chips_at: float, chip_class: str, foot: str) -> None:
    sc = BY[sid]
    a = sc["start"]
    mg_open(sc, kicker, head, "width: 1680px;")
    gap = 28 if len(nodes) > 5 else 45
    width = (1680 - gap * (len(nodes) - 1)) // len(nodes)
    eases = ["power3.out", "back.out(1.4)", "expo.out", "power2.out"]
    for i, (title, sub, fragment) in enumerate(nodes):
        at = a + 0.6 if fragment is None else said(sid, fragment, -0.15)
        x = 120 + i * (width + gap)
        body.append(f'<div class="node" id="{sid}-node{i}" style="left: {x}px; width: {width}px;"><p class="node-n">{i + 1:02d}</p>'
                    f'<p class="node-t">{title}</p><p class="node-s">{sub}</p></div>')
        enter(f"#{sid}-node{i}", at, "opacity: 0, y: 40" if i % 2 == 0 else "opacity: 0, y: -40", 0.5, eases[i % 4])
        if i:
            body.append(f'<div class="link" id="{sid}-link{i}" style="left: {x - gap}px; width: {gap}px;"></div>')
            tw.append(f'tl.fromTo("#{sid}-link{i}", {{ scaleX: 0, transformOrigin: "0% 50%" }}, {{ scaleX: 1, transformOrigin: "0% 50%", duration: 0.3, ease: "power2.out" }}, {sec(at - 0.2)});')
    body.append(f'<div class="pulse" id="{sid}-pulse"></div>')
    span = sc["length"] - 1.4
    tw.append(f'tl.fromTo("#{sid}-pulse", {{ x: 0, opacity: 0.9 }}, {{ x: 1660, opacity: 0.9, duration: 2.6, ease: "none", repeat: {max(0, int(span / 2.6) - 1)} }}, {sec(a + 1.0)});')
    body.append(f'<p class="chips-l" id="{sid}-chips-l">{chips_label}</p>')
    enter(f"#{sid}-chips-l", chips_at - 0.2, "opacity: 0, x: -20", 0.4, "power2.out")
    x = 120
    for i, chip in enumerate(chips):
        w = 34 + len(chip) * 17
        body.append(f'<p class="chip {chip_class} pchip" id="{sid}-chip{i}" style="left: {x}px; width: {w}px;">{chip}</p>')
        enter(f"#{sid}-chip{i}", chips_at + i * 0.09, "opacity: 0, scale: 0.7", 0.4, "back.out(2)")
        x += w + 18
    body.append(f'<p class="foot" id="{sid}-foot" style="top: 900px; width: 1680px;">{foot}</p>')
    enter(f"#{sid}-foot", chips_at + 1.2, "opacity: 0, y: 16", 0.5, "power2.out")
    mg_close(sc)


pipeline("arch", "UNDER THE HOOD · 1 OF 2", "Perception: from pixels to events",
         [("Streams", "6 looping videos", None), ("Decode", "GStreamer, OpenCV fallback", "Video is decoded"),
          ("Detect", "YOLO, one batch for all", "a YOLO detector"), ("Track", "stable ids per stream", "a tracker"),
          ("Map", "pixels to floor metres", "a homography"), ("Rules", "pure, tested, debounced", "Rules turn"),
          ("Events", "SQLite, on the device", "stored on the device")],
         "FOUR EVENT TYPES", ["near_miss", "restricted_zone", "no_helmet", "crowding"], said("arch", "four kinds"), "chip-red",
         "State goes to the twin five times a second, over one WebSocket.")
pipeline("voice", "UNDER THE HOOD · 2 OF 2", "Voice: from a question to a spoken answer",
         [("Your voice", "hold to talk, or type", None), ("Whisper", "speech to text", "Whisper transcribes"),
          ("Agent", "a vision language model that calls tools", "a vision language model"),
          ("Piper", "text to speech, sentence by sentence", "Piper speaks"), ("Answer", "spoken, while the twin moves", "sentence by sentence")],
         "THE AGENT’S TOOLS", ["query_events", "live_state", "look", "focus_view", "show_event", "identify_person", "write_report"],
         said("voice", "chooses a tool"), "chip-teal",
         "Design target: 2.5 seconds from releasing the button to the first spoken word.")

# ---- Jetson Thor
sc = BY["thor"]
a = sc["start"]
mg_open(sc, "THE EDGE", "Built to run live on one NVIDIA Jetson Thor", "width: 980px; font-size: 70px; line-height: 82px;")
body.append('<p class="chips-l" id="thor-targets" style="top: 372px;">DESIGN TARGETS</p>')
enter("#thor-targets", said("thor", "The detector"), "opacity: 0, x: -20", 0.4, "power2.out")
STATS = [("6", "", "streams in one TensorRT batch", "The detector", 6), ("10", " fps", "detection per stream", "batches all six", 10),
         ("15", " GB", "memory limit, all models inside", "fifteen gigabytes", 15)]
for i, (value, unit, label, fragment, n) in enumerate(STATS):
    at = said("thor", fragment)
    body.append(f'<div class="stat" id="thor-stat{i}" style="left: {120 + i * 330}px;"><p class="stat-v"><span id="thor-num{i}">{value}</span><span class="stat-u">{unit}</span></p>'
                f'<p class="stat-l">{label}</p></div>')
    enter(f"#thor-stat{i}", at, "opacity: 0, y: 40", 0.5, ["power3.out", "back.out(1.5)", "expo.out"][i])
    tw.append(f'tl.fromTo(count{i}, {{ v: 0 }}, {{ v: {n}, duration: 0.9, ease: "power2.out", onUpdate: () => {{ num{i}.textContent = Math.round(count{i}.v); }} }}, {sec(at)});')
BUDGET = [("Vision language model", 6.0), ("App, frames, buffers", 2.0), ("Headroom", 2.0), ("Speech recognition", 1.5),
          ("Detector", 1.0), ("Speech synthesis", 0.3)]
body.append('<div class="budget" id="thor-budget"><p class="budget-h">MEMORY BUDGET · 15 GB CONTAINER</p>')
bars_at = said("thor", "One vision language model")
for i, (name, gb) in enumerate(BUDGET):
    body.append(f'<div class="bar-row"><p class="bar-n">{name}</p><div class="bar-track"><div class="bar-fill{" bar-soft" if name == "Headroom" else ""}" id="thor-bar{i}" '
                f'style="width: {round(gb / 6.0 * 400)}px;"></div></div><p class="bar-v">{gb:g} GB</p></div>')
    tw.append(f'tl.fromTo("#thor-bar{i}", {{ scaleX: 0, transformOrigin: "0% 50%" }}, {{ scaleX: 1, transformOrigin: "0% 50%", duration: 0.7, ease: "power3.out" }}, {sec(bars_at + 0.2 + i * 0.08)});')
body.append('</div>')
enter("#thor-budget", bars_at, "opacity: 0, x: 50", 0.5, "power2.out")
COMMAND = "$ scripts/preflight.sh && scripts/run.sh"
body.append(f'<div class="term" id="thor-term"><p class="term-c" id="thor-cmd">{COMMAND.replace("&", "&amp;")}</p>'
            f'<p class="term-r" id="thor-off">all backends real · offline · port 8000</p></div>')
cmd_at = said("thor", "And one command")
enter("#thor-term", cmd_at - 0.3, "opacity: 0, y: 30", 0.4, "power2.out")
tw.append(f'tl.fromTo("#thor-cmd", {{ clipPath: "inset(0% 100% 0% 0%)" }}, {{ clipPath: "inset(0% 0% 0% 0%)", duration: 1.3, ease: "steps({len(COMMAND)})" }}, {sec(cmd_at)});')
enter("#thor-off", cmd_at + 1.5, "opacity: 0, x: 20", 0.4, "power2.out")
mg_close(sc)

# ---- mocks
sc = BY["mocks"]
a = sc["start"]
mg_open(sc, "ENGINEERING", "Same code, laptop or Jetson", "width: 1400px;")
SWITCHES = [("PERCEPTION", "real"), ("LLM", "local"), ("ASR", "local"), ("TTS", "local")]
for i, (name, real) in enumerate(SWITCHES):
    at = said("mocks", "Every heavy", 0.3 + i * 0.22)
    body.append(f'<div class="sw" id="sw{i}" style="top: {372 + i * 104}px;"><p class="sw-n">{name}</p><div class="sw-pill">'
                f'<div class="sw-knob" id="sw-knob{i}"></div><span class="sw-o">mock</span><span class="sw-o">{real}</span></div></div>')
    enter(f"#sw{i}", at, "opacity: 0, x: -40", 0.45, "power3.out")
    flip = said("mocks", "the same code", i * 0.18)
    # every switch starts on the real backend (the Jetson) and flips to its mock (the laptop)
    tw.append(f'tl.fromTo("#sw-knob{i}", {{ x: 170 }}, {{ x: 0, duration: 0.45, ease: "back.inOut(1.6)" }}, {sec(flip)});')
tests_at = said("mocks", "so the same code", 0.4)
body.append(f'<div class="tests" id="tests"><p class="tests-v" id="tests-v">{TESTS}</p><p class="tests-l">tests pass in mock mode, with no GPU</p>'
            f'<p class="tests-s">spec → plan → tasks, one task at a time</p></div>')
enter("#tests", tests_at, "opacity: 0, scale: 0.85", 0.6, "back.out(1.4)")
tw.append(f'tl.fromTo(countT, {{ v: 0 }}, {{ v: {TESTS}, duration: 1.1, ease: "power2.out", onUpdate: () => {{ numT.textContent = Math.round(countT.v); }} }}, {sec(tests_at)});')
body.append('<p class="foot" id="mocks-foot" style="top: 880px; width: 1680px;">If a real backend fails to load, the app falls back to its mock and keeps running.</p>')
enter("#mocks-foot", said("mocks", "That is how"), "opacity: 0, y: 16", 0.5, "power2.out")
mg_close(sc)

# ---- close
sc = BY["close"]
a = sc["start"]
body.append(f'<div class="clip scene" id="sc-close" {win(sc)} data-track-index="10"><div class="in" id="in-close">'
            f'<img class="card-bg" id="end-bg" src="assets/still_end.jpg" alt="" /><div class="card-shade"></div>'
            f'<p class="card-kicker" id="end-kicker">2 PLANTS · 6 FLOORS · 6 CAMERAS · 1 DEVICE</p>'
            f'<h1 class="card-title" id="end-main">Talk to your Company</h1>'
            f'<div class="card-rule" id="end-rule"></div>'
            f'<p class="card-line" id="end-line1">Ask your plant a question.</p>'
            f'<p class="card-line card-line2" id="end-line2">github.com/Yash-Kavaiya/talk-to-your-company</p>'
            f'<p class="card-small" id="end-line3">Built for NVIDIA Jetson Thor. Recorded on a laptop. Synthetic employees. No face recognition.</p>'
            f'</div></div>')
tw.append(f'tl.set(".frame", {{ opacity: 0 }}, {sec(a)});')
tw.append(f'tl.fromTo("#end-bg", {{ scale: 1.12, transformOrigin: "55% 45%" }}, {{ scale: 1.04, transformOrigin: "55% 45%", duration: {sec(sc["length"])}, ease: "none" }}, {sec(a)});')
enter("#end-kicker", a + 0.2, "opacity: 0, y: 18", 0.5, "power2.out")
enter("#end-main", a + 0.35, "opacity: 0, y: 44", 0.8)
tw.append(f'tl.fromTo("#end-rule", {{ scaleX: 0, transformOrigin: "0% 50%" }}, {{ scaleX: 1, transformOrigin: "0% 50%", duration: 0.6, ease: "power2.out" }}, {sec(a + 0.8)});')
enter("#end-line1", said("close", "Ask your plant"), "opacity: 0, y: 18", 0.6, "power2.out")
enter("#end-line2", a + vo["close"] + LEAD + 0.3, "opacity: 0, x: -24", 0.5, "power2.out")
enter("#end-line3", a + vo["close"] + LEAD + 0.8, "opacity: 0", 0.6, "power1.out")

# ---- shots
videos = {"wide": [], "side": []}
captions = []
previous = None
for scene in SHOTS:
    sid, start, length, layout, n = scene["id"], scene["start"], scene["length"], scene["layout"], scene["number"]
    play = scene.get("hold", length)
    videos[layout].append(
        f'<div class="zoom" id="zoom-{sid}" data-layout-allow-overflow><video id="v-{sid}" class="clip shot shot-{layout}" muted playsinline '
        f'src="assets/{scene["src"]}.mp4" data-start="{sec(start)}" data-duration="{sec(play)}" '
        f'data-media-start="{sec(scene["at"])}" data-track-index="{n}"></video></div>')
    if play < length:  # hold the last frame of the recording for the rest of the scene
        still(ASSETS / f'{scene["src"]}.mp4', scene["at"] + play - 0.1, ASSETS / f"hold_{sid}.jpg")
        videos[layout].append(f'<img id="hold-{sid}" class="clip shot shot-{layout}" src="assets/hold_{sid}.jpg" alt="" '
                              f'data-start="{sec(start + play)}" data-duration="{sec(length - play)}" data-track-index="{n}" />')
    window = win(scene)
    captions.append(f'<p class="clip tag tag-{layout}" id="tag-{sid}" {window} data-track-index="{20 + n}">{n:02d} / {len(SHOTS)} · {scene["tag"]}</p>')
    captions.append(f'<h2 class="clip head head-{layout}" id="head-{sid}" {window} data-track-index="{40 + n}">{scene["head"]}</h2>')
    if scene.get("note"):
        captions.append(f'<p class="clip note" id="note-{sid}" {window} data-track-index="60">{scene["note"]}</p>')
        tw.append(f'tl.fromTo("#note-{sid}", {{ opacity: 0 }}, {{ opacity: 1, duration: 0.6 }}, {sec(start + length * 0.55)});')
    if scene.get("note_wide"):
        captions.append(f'<p class="clip note-wide" id="note-{sid}" {window} data-track-index="60">{scene["note_wide"]}</p>')
        tw.append(f'tl.fromTo("#note-{sid}", {{ opacity: 0 }}, {{ opacity: 1, duration: 0.6 }}, {sec(start + 1.2)});')
    frame, other = f"#frame-{layout}", "#frame-side" if layout == "wide" else "#frame-wide"
    index = SCENES.index(scene)
    after_mg = SCENES[index - 1]["kind"] == "mg"
    tw.append(f'tl.set("{other}", {{ opacity: 0 }}, {sec(start)});')
    if after_mg or previous != layout:
        tw.append(f'tl.fromTo("{frame}", {{ opacity: 0, scale: 0.97 }}, {{ opacity: 1, scale: 1, duration: 0.45, ease: "power2.out", immediateRender: false }}, {sec(start)});')
    else:
        tw.append(f'tl.set("{frame}", {{ opacity: 1 }}, {sec(start)});')
    previous = layout
    tw.append(f'tl.fromTo("#tag-{sid}", {{ opacity: 0, y: 14 }}, {{ opacity: 1, y: 0, duration: 0.45, ease: "power2.out" }}, {sec(start + 0.1)});')
    tw.append(f'tl.fromTo("#head-{sid}", {{ opacity: 0, y: 22 }}, {{ opacity: 1, y: 0, duration: 0.6, ease: "power3.out" }}, {sec(start + 0.22)});')
    if scene["zoom"]:
        scale, origin = scene["zoom"]
        tw.append(f'tl.fromTo("#zoom-{sid}", {{ scale: 1, transformOrigin: "{origin}" }}, {{ scale: {scale}, transformOrigin: "{origin}", '
                  f'duration: {sec(min(2.2, length * 0.35))}, ease: "power2.inOut" }}, {sec(start + min(1.6, length * 0.2))});')

for i, scene in enumerate(SCENES):
    sid = scene["id"]
    audio.append(f'<audio id="vo-{sid}" src="assets/vo/{sid}.wav" data-start="{sec(scene["start"] + LEAD)}" '
                 f'data-duration="{vo[sid]}" data-track-index="{80 + i % 2}" data-volume="1"></audio>')
    what = "motion graphic" if scene["kind"] == "mg" else f'recording `{scene["src"]}` from {scene["at"]:.1f} s ({scene["layout"]} layout)'
    board.append(f'## Frame {i + 1}: {sid}\n\n- status: animated\n- src: index.html (generated by build.py)\n- window: {scene["start"]:.2f} to '
                 f'{scene["start"] + scene["length"]:.2f} s\n- picture: {what}\n- narration: {script[sid]}\n')

ambient = max(0, int(total / 9) - 1)
html = f"""<!doctype html>
<!-- Generated by build.py from narration/timing.json and capture/raw/*.json. Edit build.py, not this file. -->
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1920, height=1080" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ width: 1920px; height: 1080px; overflow: hidden; background: #0b1016; }}
      #root {{ position: relative; width: 100%; height: 100%; overflow: hidden; color: #dbe4ee; font-family: Montserrat, sans-serif; }}
      p, h1, h2, span {{ display: block; }}

      /* background: one field for the whole film */
      #stage {{ position: absolute; inset: 0; background: #0b1016; }}
      #grid {{ position: absolute; left: -60px; top: -60px; width: 2040px; height: 1200px; opacity: 0.5;
               background-image: linear-gradient(#16212d 2px, transparent 2px), linear-gradient(90deg, #16212d 2px, transparent 2px); background-size: 120px 120px; }}
      .glow {{ position: absolute; width: 1100px; height: 1100px; border-radius: 50%; }}
      #glow-a {{ left: -380px; top: -420px; background: radial-gradient(circle, rgba(79, 209, 197, 0.2) 0%, rgba(79, 209, 197, 0) 65%); }}
      #glow-b {{ left: 1180px; top: 420px; background: radial-gradient(circle, rgba(79, 209, 197, 0.13) 0%, rgba(79, 209, 197, 0) 65%); }}

      /* the framed screen the footage plays in: one per layout */
      .frame {{ position: absolute; overflow: hidden; border-radius: 14px; border: 2px solid #233244; background: #05080c; opacity: 0; }}
      #frame-wide {{ left: 160px; top: 48px; width: 1600px; height: 900px; }}
      #frame-side {{ left: 64px; top: 108px; width: 1272px; height: 864px; }}
      .zoom {{ position: absolute; inset: 0; display: block; }}
      .shot {{ position: absolute; top: 0; display: block; }}
      .shot-wide {{ left: 0; width: 1600px; height: 900px; }}
      .shot-side {{ left: -264px; width: 1536px; height: 864px; }} /* hides the left 330 px of the recording */

      .tag {{ position: absolute; font-family: "IBM Plex Mono", monospace; font-weight: 700; font-size: 22px; letter-spacing: 0.08em; color: #4fd1c5; white-space: nowrap; }}
      .head {{ position: absolute; font-weight: 700; letter-spacing: -0.01em; color: #eef3f8; }}
      .tag-wide {{ left: 160px; top: 962px; width: 1100px; height: 30px; }}
      .head-wide {{ left: 160px; top: 996px; width: 1600px; height: 56px; font-size: 42px; line-height: 56px; }}
      .tag-side {{ left: 1392px; top: 330px; width: 468px; height: 30px; }}
      .head-side {{ left: 1392px; top: 380px; width: 468px; height: 250px; font-size: 52px; line-height: 62px; }}
      .note {{ position: absolute; left: 1392px; top: 690px; width: 468px; height: 130px; font-family: "IBM Plex Mono", monospace; font-size: 22px; line-height: 33px; color: #9fb0c3; padding-top: 22px; border-top: 2px solid #233244; }}
      .note-wide {{ position: absolute; left: 1060px; top: 962px; width: 700px; height: 30px; text-align: right; font-family: "IBM Plex Mono", monospace; font-size: 22px; line-height: 30px; color: #9fb0c3; white-space: nowrap; }}

      /* motion-graphic scenes */
      .scene {{ position: absolute; left: 0; top: 0; width: 1920px; height: 1080px; }}
      .in {{ position: absolute; left: 0; top: 0; width: 1920px; height: 1080px; }}
      .kicker {{ position: absolute; left: 120px; top: 104px; width: 1400px; height: 34px; font-family: "IBM Plex Mono", monospace; font-weight: 700; font-size: 26px; line-height: 34px; letter-spacing: 0.1em; color: #4fd1c5; white-space: nowrap; }}
      .h {{ position: absolute; left: 120px; top: 152px; font-weight: 700; font-size: 76px; line-height: 88px; letter-spacing: -0.02em; color: #eef3f8; }}
      .foot {{ position: absolute; left: 120px; font-family: "IBM Plex Mono", monospace; font-size: 28px; line-height: 40px; color: #9fb0c3; }}
      .chip {{ font-family: "IBM Plex Mono", monospace; font-weight: 700; font-size: 26px; line-height: 52px; height: 56px; border-radius: 10px; text-align: center; white-space: nowrap; }}
      .chip-teal {{ color: #4fd1c5; border: 2px solid #2c7a73; background: #0f1f23; }}
      .chip-red {{ color: #ff8a80; border: 2px solid #a8423b; background: #23130f; }}
      .pchip {{ position: absolute; top: 760px; }}
      .chips-l {{ position: absolute; left: 120px; top: 704px; width: 900px; height: 30px; font-family: "IBM Plex Mono", monospace; font-weight: 700; font-size: 22px; line-height: 30px; letter-spacing: 0.1em; color: #9fb0c3; white-space: nowrap; }}

      /* problem */
      .row {{ position: absolute; left: 120px; width: 740px; height: 64px; display: flex; align-items: center; border-bottom: 2px solid #233244; }}
      .dot {{ width: 18px; height: 18px; border-radius: 50%; background: #ef5350; margin-right: 22px; flex: none; }}
      .row-t {{ font-weight: 700; font-size: 38px; line-height: 48px; color: #eef3f8; flex: 1; white-space: nowrap; }}
      .row-x {{ font-family: "IBM Plex Mono", monospace; font-weight: 700; font-size: 22px; letter-spacing: 0.1em; color: #ff8a80; }}
      .tile {{ position: absolute; width: 440px; height: 248px; overflow: hidden; border-radius: 10px; border: 2px solid #233244; background: #05080c; }}
      .tile img {{ position: absolute; left: 0; top: 0; width: 440px; height: 248px; display: block; object-fit: cover; }}
      .tile-dim {{ position: absolute; left: 0; top: 0; width: 440px; height: 248px; background: #0b1016; opacity: 0.72; }}
      .tile-l {{ position: absolute; left: 12px; top: 10px; height: 32px; padding: 0 10px; font-family: "IBM Plex Mono", monospace; font-weight: 700; font-size: 20px; line-height: 32px; color: #dbe4ee; background: rgba(5, 8, 12, 0.85); border-radius: 6px; white-space: nowrap; }}
      .tile-a {{ position: absolute; left: 12px; top: 196px; height: 40px; padding: 0 14px; font-family: "IBM Plex Mono", monospace; font-weight: 700; font-size: 22px; line-height: 40px; color: #1a0605; background: #ff6f61; border-radius: 6px; white-space: nowrap; }}
      .focus {{ position: absolute; width: 452px; height: 260px; border: 4px solid #4fd1c5; border-radius: 14px; }}
      .focus span {{ position: absolute; right: 10px; top: 10px; height: 32px; padding: 0 10px; font-family: "IBM Plex Mono", monospace; font-weight: 700; font-size: 20px; line-height: 32px; color: #06211e; background: #4fd1c5; border-radius: 6px; }}

      /* solution */
      .step {{ position: absolute; top: 420px; width: 520px; height: 280px; }}
      .step-rule {{ width: 520px; height: 5px; background: #4fd1c5; }}
      .step-n {{ margin-top: 26px; font-family: "IBM Plex Mono", monospace; font-weight: 700; font-size: 26px; line-height: 34px; color: #4fd1c5; }}
      .step-t {{ margin-top: 10px; font-weight: 700; font-size: 48px; line-height: 58px; letter-spacing: -0.01em; color: #eef3f8; white-space: nowrap; }}
      .step-s {{ margin-top: 12px; font-family: "IBM Plex Mono", monospace; font-size: 26px; line-height: 38px; color: #9fb0c3; }}
      .ask-bar {{ position: absolute; left: 120px; top: 800px; width: 1680px; height: 116px; border: 2px solid #233244; border-radius: 16px; background: #111a24; display: flex; align-items: center; padding: 0 40px; }}
      .ask-orb {{ width: 34px; height: 34px; border-radius: 50%; background: #4fd1c5; margin-right: 34px; flex: none; }}
      .ask-q {{ font-family: "IBM Plex Mono", monospace; font-size: 40px; line-height: 56px; color: #eef3f8; white-space: nowrap; }}

      /* pipelines */
      .node {{ position: absolute; top: 370px; height: 260px; border: 2px solid #2a3b50; border-radius: 14px; background: #111a24; padding: 20px 18px; }}
      .node-n {{ font-family: "IBM Plex Mono", monospace; font-weight: 700; font-size: 22px; line-height: 28px; color: #4fd1c5; }}
      .node-t {{ margin-top: 12px; font-weight: 700; font-size: 38px; line-height: 48px; color: #eef3f8; white-space: nowrap; }}
      .node-s {{ margin-top: 10px; font-family: "IBM Plex Mono", monospace; font-size: 24px; line-height: 32px; color: #9fb0c3; }}
      .link {{ position: absolute; top: 498px; height: 4px; background: #4fd1c5; }}
      .pulse {{ position: absolute; left: 120px; top: 352px; width: 20px; height: 8px; border-radius: 4px; background: #4fd1c5; }}

      /* Jetson Thor */
      .stat {{ position: absolute; top: 426px; width: 310px; height: 230px; border-top: 5px solid #4fd1c5; padding-top: 18px; }}
      .stat-v {{ font-weight: 900; font-size: 96px; line-height: 104px; letter-spacing: -0.03em; color: #eef3f8; white-space: nowrap; font-variant-numeric: tabular-nums; }}
      .stat-v span {{ display: inline; }}
      .stat-u {{ font-size: 44px; letter-spacing: 0; color: #4fd1c5; }}
      .stat-l {{ margin-top: 8px; font-family: "IBM Plex Mono", monospace; font-size: 24px; line-height: 34px; color: #9fb0c3; }}
      .budget {{ position: absolute; left: 1150px; top: 150px; width: 650px; height: 560px; border: 2px solid #233244; border-radius: 16px; background: #111a24; padding: 30px 34px; }}
      .budget-h {{ font-family: "IBM Plex Mono", monospace; font-weight: 700; font-size: 22px; line-height: 30px; letter-spacing: 0.08em; color: #4fd1c5; white-space: nowrap; margin-bottom: 20px; }}
      .bar-row {{ position: relative; width: 582px; height: 74px; }}
      .bar-n {{ font-family: "IBM Plex Mono", monospace; font-size: 22px; line-height: 30px; color: #dbe4ee; white-space: nowrap; }}
      .bar-track {{ position: absolute; left: 0; top: 36px; width: 400px; height: 16px; border-radius: 8px; background: #1b2836; }}
      .bar-fill {{ height: 16px; border-radius: 8px; background: #4fd1c5; }}
      .bar-soft {{ background: #5b7388; }}
      .bar-v {{ position: absolute; right: 0; top: 24px; width: 150px; text-align: right; font-weight: 700; font-size: 30px; line-height: 40px; color: #eef3f8; white-space: nowrap; }}
      .term {{ position: absolute; left: 120px; top: 800px; width: 1680px; height: 116px; border: 2px solid #233244; border-radius: 16px; background: #05080c; }}
      .term-c {{ position: absolute; left: 40px; top: 30px; width: 900px; height: 56px; font-family: "IBM Plex Mono", monospace; font-weight: 700; font-size: 36px; line-height: 56px; color: #4fd1c5; white-space: nowrap; }}
      .term-r {{ position: absolute; right: 40px; top: 38px; width: 640px; height: 40px; text-align: right; font-family: "IBM Plex Mono", monospace; font-size: 22px; line-height: 40px; color: #9fb0c3; white-space: nowrap; }}

      /* mocks */
      .sw {{ position: absolute; left: 120px; width: 760px; height: 84px; display: flex; align-items: center; border-bottom: 2px solid #233244; }}
      .sw-n {{ flex: 1; font-family: "IBM Plex Mono", monospace; font-weight: 700; font-size: 32px; line-height: 44px; letter-spacing: 0.04em; color: #eef3f8; }}
      .sw-pill {{ position: relative; width: 348px; height: 60px; border-radius: 30px; border: 2px solid #2a3b50; background: #111a24; display: flex; }}
      .sw-knob {{ position: absolute; left: 4px; top: 4px; width: 166px; height: 48px; border-radius: 24px; background: #1f6f68; }}
      .sw-o {{ position: relative; width: 174px; height: 56px; text-align: center; font-family: "IBM Plex Mono", monospace; font-weight: 700; font-size: 26px; line-height: 56px; color: #eef3f8; }}
      .tests {{ position: absolute; left: 1040px; top: 340px; width: 760px; height: 460px; border: 2px solid #233244; border-radius: 16px; background: #111a24; padding: 30px 44px; }}
      .tests-v {{ font-weight: 900; font-size: 220px; line-height: 230px; letter-spacing: -0.04em; color: #4fd1c5; font-variant-numeric: tabular-nums; }}
      .tests-l {{ font-weight: 700; font-size: 34px; line-height: 46px; color: #eef3f8; }}
      .tests-s {{ margin-top: 14px; font-family: "IBM Plex Mono", monospace; font-size: 24px; line-height: 34px; color: #9fb0c3; }}

      /* title and end cards */
      .card-bg {{ position: absolute; left: 0; top: 0; width: 1920px; height: 1080px; display: block; }}
      .card-shade {{ position: absolute; left: 0; top: 0; width: 1920px; height: 1080px; background: radial-gradient(ellipse at 100% 50%, rgba(11, 16, 22, 0.55) 0%, rgba(11, 16, 22, 0.92) 55%, rgba(11, 16, 22, 0.97) 100%); }}
      .card-kicker {{ position: absolute; left: 160px; top: 372px; width: 1400px; height: 40px; font-family: "IBM Plex Mono", monospace; font-weight: 700; font-size: 28px; letter-spacing: 0.1em; color: #4fd1c5; white-space: nowrap; }}
      .card-title {{ position: absolute; left: 160px; top: 430px; width: 1600px; height: 150px; font-weight: 900; font-size: 128px; line-height: 150px; letter-spacing: -0.03em; color: #f4f8fb; white-space: nowrap; }}
      .card-rule {{ position: absolute; left: 160px; top: 612px; width: 180px; height: 6px; background: #4fd1c5; }}
      .card-line {{ position: absolute; left: 160px; top: 654px; width: 1500px; height: 46px; font-family: "IBM Plex Mono", monospace; font-size: 30px; line-height: 46px; color: #c9d5e2; white-space: nowrap; }}
      .card-line2 {{ top: 712px; color: #4fd1c5; }}
      .card-small {{ position: absolute; left: 160px; top: 800px; width: 1600px; height: 34px; font-family: "IBM Plex Mono", monospace; font-size: 22px; line-height: 34px; color: #9fb0c3; white-space: nowrap; }}
      #title-chip {{ position: absolute; left: 160px; top: 736px; width: 560px; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{sec(total)}" data-width="1920" data-height="1080">
      <div id="stage"></div>
      <div id="grid"></div>
      <div class="glow" id="glow-a"></div>
      <div class="glow" id="glow-b"></div>

      <div class="frame" id="frame-wide">
        {chr(10).join("        " + v for v in videos["wide"]).strip()}
      </div>
      <div class="frame" id="frame-side">
        {chr(10).join("        " + v for v in videos["side"]).strip()}
      </div>

      {chr(10).join("      " + c for c in captions).strip()}

      {chr(10).join("      " + b for b in body).strip()}

      {chr(10).join("      " + x for x in audio).strip()}
    </div>
    <script>
      const tl = gsap.timeline({{ paused: true }});
      const count0 = {{ v: 0 }}, count1 = {{ v: 0 }}, count2 = {{ v: 0 }}, countT = {{ v: 0 }};
      const num0 = document.getElementById("thor-num0"), num1 = document.getElementById("thor-num1"),
        num2 = document.getElementById("thor-num2"), numT = document.getElementById("tests-v");

      // background drift, for the whole film
      tl.fromTo("#grid", {{ x: 0, y: 0 }}, {{ x: 60, y: 40, duration: 9, ease: "sine.inOut", yoyo: true, repeat: {ambient} }}, 0);
      tl.fromTo("#glow-a", {{ x: 0, y: 0, scale: 1 }}, {{ x: 220, y: 120, scale: 1.2, duration: 9, ease: "sine.inOut", yoyo: true, repeat: {ambient} }}, 0);
      tl.fromTo("#glow-b", {{ x: 0, y: 0, scale: 1.15 }}, {{ x: -260, y: -160, scale: 0.95, duration: 9, ease: "sine.inOut", yoyo: true, repeat: {ambient} }}, 0);

      {chr(10).join("      " + line for line in tw).strip()}

      window.__timelines["main"] = tl;
      tl.seek(0);
    </script>
  </body>
</html>
"""
(HERE / "index.html").write_text(html, encoding="utf-8")
(HERE / "STORYBOARD.md").write_text(
    f"# Storyboard: Talk-to-your-Company full demo\n\nGenerated by build.py. Total {total:.1f} s, 1920x1080, "
    f"narration {timing['provider']} ({timing['voice']}).\n\n" + "\n".join(board), encoding="utf-8")
print(f"narration: {timing['provider']} {timing['voice']}")
for scene in SCENES:
    print(f"{scene['id']:9} {scene['kind']:4} {scene['start']:7.2f} to {scene['start'] + scene['length']:7.2f}  (narration {vo[scene['id']]} s)")
print(f"total {total} s")
