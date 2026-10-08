"""Write index.html from the scene list below, the narration lengths (narration/timing.json) and the
recording marks (capture/raw/*.json). Run it again whenever the narration is regenerated:

    python narration/generate.py deepgram && python build.py
"""
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
timing = json.loads((HERE / "narration" / "timing.json").read_text())
vo = timing["lines"]
marks = {name: json.loads((HERE / "capture" / "raw" / f"{name}.json").read_text()) for name in ("overview", "story")}
o, s = marks["overview"], marks["story"]

LEAD = 0.35  # narration starts this long after a scene opens
TAIL = 0.55  # and the scene holds this long after it ends

# layout "wide": the whole 16:9 screen with a caption band below (simulated site, smooth overview shots)
# layout "side": the right 83% of the screen with a text column beside it (real detection on a laptop)
# zoom = (scale, transform-origin) reached during the scene, to guide the eye
SCENES = [
    dict(id="twin", layout="wide", src="overview", at=o["overview"] - 0.1, min=7.0, tag="LIVE TWIN",
         head="Every person and vehicle, on the right floor", zoom=None),
    dict(id="plants", layout="wide", src="overview", at=o["plant1"], min=9.0, tag="SITE FROM CONFIG",
         head="Floors spread apart to show what is inside", zoom=None),
    dict(id="ask", layout="wide", src="overview", at=o["status"], min=8.0, tag="ASK",
         head="Plain questions, by voice or by text", zoom=(1.22, "50% 100%")),
    dict(id="safety", layout="wide", src="overview", at=o["safety"] + 1.6, min=6.5, tag="SAFETY EVENTS",
         head="The last ten minutes, lit up on the twin", zoom=None),
    dict(id="camera", layout="side", src="story", at=s["floor"] + 2.0, min=6.0, tag="CAMERA VIEW",
         head="A live camera on every floor, detections boxed", zoom=(1.3, "100% 100%")),
    dict(id="alert", layout="side", src="story", at=s["issues"], min=7.5, tag="RESTRICTED ZONE",
         head="The alert names the person", zoom=(1.2, "70% 100%")),
    dict(id="who", layout="side", src="story", at=s["who"], min=12.0, tag="WHO IS THIS PERSON",
         head="Name, role, timing and authorisation", zoom=(1.22, "100% 0%"),
         note="Synthetic employees. Simulated badge feed. No face recognition."),
    dict(id="report", layout="side", src="story", at=s["report"], min=8.0, tag="INCIDENT REPORT",
         head="Written from one sentence", zoom=(1.22, "100% 0%")),
    dict(id="share", layout="side", src="story", at=s["share"] + 3.4, min=7.0, tag="SHARE A RECORDING",
         head="Drop a video or your webcam into any camera", zoom=(1.3, "100% 100%")),
    dict(id="edge", layout="wide", src="overview", at=o["overview"], min=6.4, tag="EDGE", fixed=6.4,
         head="Built to run on one NVIDIA Jetson Thor", zoom=(1.45, "0% 100%")),
]
LIMITS = {"overview": o["end"], "story": s["end"]}


def seconds(n: float) -> str:
    return f"{n:.2f}".rstrip("0").rstrip(".")


# ---- timeline
title_len = round(vo["title"] + LEAD + TAIL + 0.6, 2)
t = title_len
for i, scene in enumerate(SCENES):
    length = scene.get("fixed") or max(scene["min"], vo[scene["id"]] + LEAD + TAIL)
    if scene["at"] + length > LIMITS[scene["src"]]:
        raise SystemExit(f"scene {scene['id']} needs {length:.1f} s of footage from {scene['at']:.1f}, "
                         f"but {scene['src']} ends at {LIMITS[scene['src']]:.1f}")
    scene.update(start=round(t, 2), length=round(length, 2), number=i + 1)
    t += length
edge = SCENES[-1]
end_start = round(t, 2)
end_len = round(max(vo["edge"] + LEAD + TAIL - edge["length"], 4.0) + 0.8, 2)
total = round(end_start + end_len, 2)

# ---- stills for the title and end cards
for name, at in (("still_title", o["overview"] + 4.0), ("still_end", o["plant1"] + 5.0)):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(at), "-i", str(HERE / "assets" / "overview.mp4"),
                    "-frames:v", "1", "-q:v", "2", str(HERE / "assets" / f"{name}.jpg")], check=True)

# ---- html
videos, captions, audio, tweens = [], [], [], []
audio.append(f'<audio id="vo-title" src="assets/vo/title.wav" data-start="{LEAD + 0.5}" data-duration="{vo["title"]}" '
             f'data-track-index="80" data-volume="1"></audio>')
for scene in SCENES:
    sid, start, length = scene["id"], scene["start"], scene["length"]
    videos.append(
        f'<div class="zoom" id="zoom-{sid}" data-layout-allow-overflow><video id="v-{sid}" class="clip shot shot-{scene["layout"]}" muted playsinline '
        f'src="assets/{scene["src"]}.mp4" data-start="{seconds(start)}" data-duration="{seconds(length)}" '
        f'data-media-start="{seconds(scene["at"])}" data-track-index="{scene["number"]}"></video></div>')
    window = f'data-start="{seconds(start)}" data-duration="{seconds(length)}"'
    layout = scene["layout"]
    captions.append(f'<p class="clip tag tag-{layout}" id="tag-{sid}" {window} data-track-index="{20 + scene["number"]}">'
                    f'{scene["number"]:02d} / {len(SCENES)} · {scene["tag"]}</p>')
    captions.append(f'<h2 class="clip head head-{layout}" id="head-{sid}" {window} data-track-index="{40 + scene["number"]}">{scene["head"]}</h2>')
    if scene.get("note"):
        captions.append(f'<p class="clip note" id="note-{sid}" {window} data-track-index="60">{scene["note"]}</p>')
    audio.append(f'<audio id="vo-{sid}" src="assets/vo/{sid}.wav" data-start="{seconds(start + LEAD)}" '
                 f'data-duration="{vo[sid]}" data-track-index="{80 + scene["number"] % 2}" data-volume="1"></audio>')
    frame = f"#frame-{scene['layout']}"
    other = "#frame-side" if scene["layout"] == "wide" else "#frame-wide"
    tweens.append(f'tl.set("{frame}", {{ opacity: 1 }}, {seconds(start)}); tl.set("{other}", {{ opacity: 0 }}, {seconds(start)});')
    tweens.append(f'tl.fromTo("#tag-{sid}", {{ opacity: 0, y: 14 }}, {{ opacity: 1, y: 0, duration: 0.45, ease: "power2.out" }}, {seconds(start + 0.1)});')
    tweens.append(f'tl.fromTo("#head-{sid}", {{ opacity: 0, y: 22 }}, {{ opacity: 1, y: 0, duration: 0.6, ease: "power3.out" }}, {seconds(start + 0.22)});')
    if scene.get("note"):
        tweens.append(f'tl.fromTo("#note-{sid}", {{ opacity: 0 }}, {{ opacity: 1, duration: 0.6 }}, {seconds(start + length * 0.55)});')
    if scene["zoom"]:
        scale, origin = scene["zoom"]
        tweens.append(f'tl.fromTo("#zoom-{sid}", {{ scale: 1, transformOrigin: "{origin}" }}, {{ scale: {scale}, transformOrigin: "{origin}", '
                      f'duration: {seconds(min(2.2, length * 0.35))}, ease: "power2.inOut" }}, {seconds(start + min(1.6, length * 0.2))});')

tw = f'data-start="0" data-duration="{seconds(title_len)}"'
ew = f'data-start="{seconds(end_start)}" data-duration="{seconds(end_len)}"'
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
      #stage {{ position: absolute; inset: 0; background: #0b1016; }}

      /* the framed screen the footage plays in: one per layout */
      .frame {{ position: absolute; overflow: hidden; border-radius: 14px; border: 2px solid #233244; background: #05080c; opacity: 0; }}
      #frame-wide {{ left: 160px; top: 48px; width: 1600px; height: 900px; }}
      #frame-side {{ left: 64px; top: 108px; width: 1272px; height: 864px; }}
      .zoom {{ position: absolute; inset: 0; display: block; }}
      .shot {{ position: absolute; top: 0; display: block; }}
      .shot-wide {{ left: 0; width: 1600px; height: 900px; }}
      .shot-side {{ left: -264px; width: 1536px; height: 864px; }} /* hides the left 330 px of the recording */

      .tag {{ position: absolute; display: block; font-family: "IBM Plex Mono", monospace; font-weight: 500; font-size: 22px; letter-spacing: 0.08em; color: #4fd1c5; white-space: nowrap; }}
      .head {{ position: absolute; display: block; font-weight: 700; letter-spacing: -0.01em; color: #eef3f8; }}
      .tag-wide {{ left: 160px; top: 962px; width: 1600px; height: 30px; }}
      .head-wide {{ left: 160px; top: 996px; width: 1600px; height: 56px; font-size: 42px; line-height: 56px; }}
      .tag-side {{ left: 1392px; top: 330px; width: 468px; height: 30px; }}
      .head-side {{ left: 1392px; top: 380px; width: 468px; height: 250px; font-size: 52px; line-height: 62px; }}
      .note {{ position: absolute; left: 1392px; top: 690px; width: 468px; height: 130px; display: block; font-family: "IBM Plex Mono", monospace; font-size: 22px; line-height: 33px; color: #9fb0c3; padding-top: 22px; border-top: 2px solid #233244; }}

      /* title and end cards */
      .card-bg {{ position: absolute; left: 0; top: 0; width: 1920px; height: 1080px; display: block; }}
      .card-shade {{ position: absolute; left: 0; top: 0; width: 1920px; height: 1080px; display: block; background: linear-gradient(90deg, rgba(11, 16, 22, 0.97) 0%, rgba(11, 16, 22, 0.9) 50%, rgba(11, 16, 22, 0.62) 100%); }}
      .card-kicker {{ position: absolute; left: 160px; top: 412px; width: 1400px; height: 40px; display: block; font-family: "IBM Plex Mono", monospace; font-weight: 500; font-size: 28px; letter-spacing: 0.1em; color: #4fd1c5; }}
      .card-title {{ position: absolute; left: 160px; top: 470px; width: 1600px; height: 150px; display: block; font-weight: 800; font-size: 128px; line-height: 150px; letter-spacing: -0.03em; color: #ffffff; white-space: nowrap; }}
      .card-rule {{ position: absolute; left: 160px; top: 652px; display: block; width: 180px; height: 6px; background: #4fd1c5; }}
      .card-line {{ position: absolute; left: 160px; width: 1500px; height: 46px; display: block; font-family: "IBM Plex Mono", monospace; font-size: 30px; line-height: 46px; color: #c9d5e2; }}
      .card-line1 {{ top: 694px; }}
      .card-line2 {{ top: 748px; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{seconds(total)}" data-width="1920" data-height="1080">
      <div id="stage"></div>

      <div class="frame" id="frame-wide">
        {chr(10).join("        " + v for v in videos if 'shot-wide' in v).strip()}
      </div>
      <div class="frame" id="frame-side">
        {chr(10).join("        " + v for v in videos if 'shot-side' in v).strip()}
      </div>

      {chr(10).join("      " + c for c in captions).strip()}

      <img class="clip card-bg" id="title-bg" src="assets/still_title.jpg" alt="" {tw} data-track-index="70" />
      <div class="clip card-shade" id="title-shade" {tw} data-track-index="71"></div>
      <p class="clip card-kicker" id="title-kicker" {tw} data-track-index="72">LIVE 3D TWIN · VOICE COPILOT · ON THE EDGE</p>
      <h1 class="clip card-title" id="title-main" {tw} data-track-index="73">Talk to your Company</h1>
      <div class="clip card-rule" id="title-rule" {tw} data-track-index="74"></div>
      <p class="clip card-line card-line1" id="title-line" {tw} data-track-index="75">Ask a question. The twin flies to the right floor and answers out loud.</p>

      <img class="clip card-bg" id="end-bg" src="assets/still_end.jpg" alt="" {ew} data-track-index="70" />
      <div class="clip card-shade" id="end-shade" {ew} data-track-index="71"></div>
      <p class="clip card-kicker" id="end-kicker" {ew} data-track-index="72">2 PLANTS · 6 FLOORS · 6 CAMERAS</p>
      <h1 class="clip card-title" id="end-main" {ew} data-track-index="73">Talk to your Company</h1>
      <div class="clip card-rule" id="end-rule" {ew} data-track-index="74"></div>
      <p class="clip card-line card-line1" id="end-line1" {ew} data-track-index="75">Built to run on one NVIDIA Jetson Thor. No audio or video leaves the device.</p>
      <p class="clip card-line card-line2" id="end-line2" {ew} data-track-index="76">Recorded on a laptop. Synthetic employees. No face recognition.</p>

      {chr(10).join("      " + a for a in audio).strip()}
    </div>
    <script>
      const tl = gsap.timeline({{ paused: true }});

      // title card
      tl.fromTo("#title-bg", {{ scale: 1.04, transformOrigin: "60% 50%" }}, {{ scale: 1.14, transformOrigin: "60% 50%", duration: {seconds(title_len)}, ease: "none" }}, 0);
      tl.fromTo("#title-kicker", {{ opacity: 0, y: 18 }}, {{ opacity: 1, y: 0, duration: 0.5, ease: "power2.out" }}, 0.25);
      tl.fromTo("#title-main", {{ opacity: 0, y: 40 }}, {{ opacity: 1, y: 0, duration: 0.8, ease: "power3.out" }}, 0.4);
      tl.fromTo("#title-rule", {{ scaleX: 0, transformOrigin: "0% 50%" }}, {{ scaleX: 1, transformOrigin: "0% 50%", duration: 0.6, ease: "power2.out" }}, 0.9);
      tl.fromTo("#title-line", {{ opacity: 0, y: 18 }}, {{ opacity: 1, y: 0, duration: 0.6, ease: "power2.out" }}, 1.2);

      // scenes
      {chr(10).join("      " + line for line in tweens).strip()}

      // end card
      tl.fromTo("#end-bg", {{ scale: 1.12, transformOrigin: "55% 45%" }}, {{ scale: 1.04, transformOrigin: "55% 45%", duration: {seconds(end_len)}, ease: "none" }}, {seconds(end_start)});
      tl.fromTo("#end-kicker", {{ opacity: 0, y: 18 }}, {{ opacity: 1, y: 0, duration: 0.5, ease: "power2.out" }}, {seconds(end_start + 0.2)});
      tl.fromTo("#end-main", {{ opacity: 0, y: 40 }}, {{ opacity: 1, y: 0, duration: 0.8, ease: "power3.out" }}, {seconds(end_start + 0.35)});
      tl.fromTo("#end-rule", {{ scaleX: 0, transformOrigin: "0% 50%" }}, {{ scaleX: 1, transformOrigin: "0% 50%", duration: 0.6, ease: "power2.out" }}, {seconds(end_start + 0.8)});
      tl.fromTo("#end-line1", {{ opacity: 0, y: 18 }}, {{ opacity: 1, y: 0, duration: 0.6, ease: "power2.out" }}, {seconds(end_start + 1.1)});
      tl.fromTo("#end-line2", {{ opacity: 0, y: 18 }}, {{ opacity: 1, y: 0, duration: 0.6, ease: "power2.out" }}, {seconds(end_start + 1.6)});

      window.__timelines["main"] = tl;
      tl.seek(0);
    </script>
  </body>
</html>
"""
(HERE / "index.html").write_text(html, encoding="utf-8")
print(f"narration: {timing['voice']}")
print(f"title 0.00 to {title_len}")
for scene in SCENES:
    print(f"{scene['number']:02d} {scene['id']:8} {scene['start']:6.2f} to {scene['start'] + scene['length']:6.2f}  "
          f"(narration {vo[scene['id']]} s, footage {scene['src']} from {scene['at']:.1f})")
print(f"end card {end_start} to {total}\ntotal {total} s")
