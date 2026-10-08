// Talk-to-your-Company: presentation deck (PowerPoint). Same content as ../beamer/main.tex.
//   node build.js      -> ../talk-to-your-company.pptx
// Theme: NVIDIA green + Globant lime on black. Colours approximate each brand's public look; no logos.
const path = require("path");
const pptxgen = require("pptxgenjs");
const { applyTheme } = require(process.env.PPTX_SKILL_DIR
  ? path.join(process.env.PPTX_SKILL_DIR, "scripts", "apply_theme.js")
  : "./apply_theme.js");

const OUT = path.join(__dirname, "..", "talk-to-your-company.pptx");
const IMG = (name) => path.join(__dirname, "..", "assets", name);

const THEME = {
  name: "NVIDIA Globant Twin",
  headFontFace: "Arial",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "0B0B0B", lt1: "FFFFFF", dk2: "1A1A1A", lt2: "D9D9D9",
    accent1: "76B900", // NVIDIA green
    accent2: "BFD732", // Globant lime
    accent3: "5C8F00", // deep green
    accent4: "A6A6A6", // muted grey
    accent5: "F56565", // event red (from the app)
    accent6: "2A2A2A", // card surface
    hlink: "BFD732", folHlink: "A6A6A6",
  },
};

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5 in
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = "Talk-to-your-Company";
pres.author = "Yash Kavaiya";
pres.company = "Globant Physical AI Hackathon";
const C = pres.SchemeColor;
const INK = C.background1; // white, on the black content slides
const SOFT = C.background2; // light grey body text
const BLACK = C.text1;
const GREEN = C.accent1;
const LIME = C.accent2;
const MUTED = C.accent4;
const CARD = C.accent6;

const W = 13.33;
const M = 0.6; // side margin
const FOOT = "Talk-to-your-Company  ·  Globant Physical AI Hackathon";

// ---- layouts: one per slide frame
pres.defineSlideMaster({
  title: "Cover", background: { color: GREEN },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: M, y: 1.55, w: 5.9, h: 2.2, fontSize: 48, bold: true, color: BLACK, align: "left", valign: "top", margin: 0 }, text: "Title" } },
    { placeholder: { options: { name: "body", type: "body", x: M, y: 3.95, w: 5.6, h: 1.4, fontSize: 20, color: BLACK, align: "left", valign: "top", margin: 0 }, text: "Subtitle" } },
  ],
});
pres.defineSlideMaster({
  title: "Divider", background: { color: GREEN },
  objects: [
    { placeholder: { options: { name: "body", type: "body", x: M, y: 2.55, w: 8, h: 0.5, fontSize: 18, bold: true, color: BLACK, charSpacing: 4, align: "left", margin: 0 }, text: "SECTION" } },
    { placeholder: { options: { name: "title", type: "title", x: M, y: 3.05, w: 12.1, h: 1.5, fontSize: 60, bold: true, color: BLACK, align: "left", valign: "top", margin: 0 }, text: "Section title" } },
  ],
});
pres.defineSlideMaster({
  title: "Statement", background: { color: GREEN },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: M, y: 1.7, w: 11.6, h: 2.6, fontSize: 54, bold: true, color: BLACK, align: "left", valign: "bottom", margin: 0 }, text: "Statement" } },
    { placeholder: { options: { name: "body", type: "body", x: M, y: 4.6, w: 10.5, h: 1.4, fontSize: 22, color: BLACK, align: "left", valign: "top", margin: 0 }, text: "Support" } },
  ],
});
pres.defineSlideMaster({
  title: "Content", background: { color: BLACK },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: M, y: 0.42, w: W - 2 * M, h: 1.15, fontSize: 30, bold: true, color: GREEN, align: "left", valign: "top", margin: 0 }, text: "Slide title" } },
    { text: { text: FOOT, options: { x: M, y: 7.0, w: 8, h: 0.3, fontSize: 10, color: MUTED, margin: 0, isTextBox: true } } },
  ],
  slideNumber: { x: W - M - 0.8, y: 7.0, w: 0.8, h: 0.3, fontSize: 10, color: MUTED, align: "right" },
});

// ---- helpers
let section = "";
const start = (title) => { section = title; pres.addSection({ title }); };
const slide = (masterName) => pres.addSlide({ masterName, sectionTitle: section });
const TOP = 1.85; // where content starts under a content title

function content(title, notes) {
  const s = slide("Content");
  s.addText(title, { placeholder: "title" });
  if (notes) s.addNotes(notes);
  return s;
}

function picture(s, name, x, y, w, aspect, objectName) {
  const h = w / aspect;
  s.addShape(pres.ShapeType.rect, { x: x - 0.03, y: y - 0.03, w: w + 0.06, h: h + 0.06, fill: { color: CARD }, line: { color: MUTED, width: 0.75 }, objectName: `${objectName} frame` });
  s.addImage({ path: IMG(name), x, y, w, h, objectName, altText: objectName });
  return h;
}

function lead(s, text, x, y, w, h = 1.0) {
  s.addText(text, { x, y, w, h, fontSize: 22, bold: true, color: INK, valign: "top", margin: 0, isTextBox: true, objectName: "Lead" });
}

function bullets(s, items, x, y, w, h, fontSize = 18) {
  s.addText(items.map((text, i) => ({ text, options: { bullet: true, breakLine: i < items.length - 1 } })),
    { x, y, w, h, fontSize, color: SOFT, valign: "top", paraSpaceAfter: 8, margin: 0, isTextBox: true, objectName: "Points" });
}

// Screenshot on one side, lead and bullets on the other.
function feature({ title, img, aspect, imgW, side, leadText, points, note, notes }) {
  const s = content(title, notes);
  const gap = 0.5;
  const textW = W - 2 * M - imgW - gap;
  const imgX = side === "left" ? M : W - M - imgW;
  const textX = side === "left" ? M + imgW + gap : M;
  picture(s, img, imgX, TOP + 0.05, imgW, aspect, title);
  lead(s, leadText, textX, TOP, textW, 1.2);
  bullets(s, points, textX, TOP + 1.4, textW, 2.7);
  if (note) s.addText(note, { x: textX, y: TOP + 4.2, w: textW, h: 0.7, fontSize: 13, italic: true, color: MUTED, valign: "top", margin: 0, isTextBox: true, objectName: "Note" });
  return s;
}

function divider(number, title) {
  start(title);
  const s = slide("Divider");
  s.addText(`SECTION ${number}`, { placeholder: "body" });
  s.addText(title, { placeholder: "title" });
}

function chip(s, label, x, y, size = 0.46) {
  s.addShape(pres.ShapeType.ellipse, { x, y, w: size, h: size, fill: { color: GREEN }, line: { color: GREEN, width: 0 }, objectName: `Chip ${label}` });
  s.addText(String(label), { x, y, w: size, h: size, fontSize: 14, bold: true, color: BLACK, align: "center", valign: "middle", margin: 0, isTextBox: true, objectName: `Chip ${label} text` });
}

// ============================================================ cover
start("Opening");
{
  const s = slide("Cover");
  s.addText("Talk-to-your-Company", { placeholder: "title" });
  s.addText("A live 3D twin of your plants that you can talk to, built for one NVIDIA Jetson Thor", { placeholder: "body" });
  s.addText("Yash Kavaiya  ·  Globant Physical AI Hackathon  ·  October 2026", { x: M, y: 6.55, w: 7, h: 0.4, fontSize: 14, bold: true, color: BLACK, margin: 0, isTextBox: true, objectName: "Byline" });
  const w = 6.1;
  s.addShape(pres.ShapeType.rect, { x: W - M - w - 0.08, y: 1.72, w: w + 0.16, h: w / (16 / 9) + 0.16, fill: { color: BLACK }, line: { color: BLACK, width: 0 }, shadow: { type: "outer", color: "000000", opacity: 0.35, blur: 12, offset: 4, angle: 90 }, objectName: "Cover picture frame" });
  s.addImage({ path: IMG("twin.jpg"), x: W - M - w, y: 1.8, w, h: w / (16 / 9), objectName: "The live twin", altText: "Screenshot of the live 3D twin showing two plants" });
  s.addNotes("Open on the twin. One sentence: a live 3D twin of two plants that you talk to, built to run on a single Jetson Thor.");
}

// ============================================================ 1 the problem
divider(1, "The problem");
{
  const s = content("Safety events go unseen because nobody can watch every camera",
    "The manager is always looking at the wrong screen. Four pains, then the need.");
  const rows = [
    ["Events go unreported", "Near-misses, people in restricted zones and missing helmets slip by."],
    ["Simple questions are slow", "“What is happening on floor 3?” means walking there or calling someone."],
    ["Camera walls do not answer", "They show video. They cannot be asked anything."],
    ["Cloud video is a poor fit", "Sending factory video off site is slow, costly and often not allowed."],
  ];
  rows.forEach(([head, body], i) => {
    const y = TOP + 0.1 + i * 1.12;
    chip(s, i + 1, M, y + 0.04);
    s.addText(head, { x: M + 0.7, y, w: 6.2, h: 0.4, fontSize: 18, bold: true, color: INK, margin: 0, isTextBox: true, objectName: `Problem ${i + 1} head` });
    s.addText(body, { x: M + 0.7, y: y + 0.42, w: 6.2, h: 0.6, fontSize: 14, color: SOFT, valign: "top", margin: 0, isTextBox: true, objectName: `Problem ${i + 1} body` });
  });
  s.addShape(pres.ShapeType.roundRect, { x: 8.2, y: TOP + 0.2, w: 4.53, h: 4.1, rectRadius: 0.12, fill: { color: CARD }, line: { color: CARD, width: 0 }, objectName: "Need card" });
  s.addText("THE NEED", { x: 8.55, y: TOP + 0.55, w: 3.8, h: 0.35, fontSize: 12, bold: true, color: LIME, charSpacing: 4, margin: 0, isTextBox: true, objectName: "Need label" });
  s.addText("One view of the whole site, and a way to ask it things.", { x: 8.55, y: TOP + 1.0, w: 3.85, h: 2.9, fontSize: 28, bold: true, color: INK, valign: "top", margin: 0, isTextBox: true, objectName: "Need text" });
}
{
  const s = slide("Statement");
  s.addText("A live 3D twin of your company that you can talk to.", { placeholder: "title" });
  s.addText("Ask by voice. The twin flies to the right floor, shows what the cameras see, and answers out loud.", { placeholder: "body" });
  s.addNotes("The whole idea in one line.");
}

// ============================================================ 2 what it does
divider(2, "What it does");
feature({
  title: "Both plants and all six floors are live in one view", img: "twin.jpg", aspect: 16 / 9, imgW: 7.2, side: "left",
  leadText: "Every person and vehicle the cameras see is a marker on the right floor.",
  points: ["2 plants, 3 floors each, 6 cameras", "Positions update 5 times a second", "Pulsing red markers for safety events"],
  notes: "This is the simulated site in the screenshot: smooth, and identical in behaviour to the real pipeline.",
});
feature({
  title: "The whole site is generated from one configuration file", img: "plants.jpg", aspect: 16 / 9, imgW: 7.2, side: "right",
  leadText: "Select a plant and its floors spread apart to show what is inside.",
  points: ["Plants, floors, cameras and zones", "Conveyors, racks, machines, pallets, offices", "Change the file and the twin, the rules and the assistant all follow"],
  notes: "Nothing about the layout is in code. A new site is a new YAML file.",
});
feature({
  title: "You ask in plain language, by voice or by text", img: "ask.jpg", aspect: 1500 / 760, imgW: 7.2, side: "left",
  leadText: "The answer is spoken, shown as text, and drives the twin.",
  points: ["“Give me a status of both plants”", "“Show me Plant 2, floor 3” moves the camera there", "Out-of-scope questions get an honest “I can’t see that”"],
  notes: "Hold to talk, or type. The assistant must call a tool before stating any fact about the site.",
});
{
  const s = content("Four rules turn tracks into safety events on the right floor",
    "Rules are plain functions over tracks, unit-tested. Same-person repeats are debounced for 30 seconds.");
  const header = (t) => ({ text: t, options: { bold: true, color: BLACK, fill: { color: GREEN }, fontSize: 14 } });
  const cell = (t, bold = false) => ({ text: t, options: { color: bold ? INK : SOFT, bold, fill: { color: CARD }, fontSize: 14 } });
  s.addTable([
    [header("Event"), header("Raised when")],
    [cell("Near miss", true), cell("a person is within 2 m of a closing forklift")],
    [cell("Restricted zone", true), cell("a person stays inside for over 2 s")],
    [cell("No helmet", true), cell("the vision check on a person says no")],
    [cell("Crowding", true), cell("more than 4 people are within 3 m")],
  ], { x: M, y: TOP + 0.05, w: 5.6, colW: [1.9, 3.7], rowH: 0.55, border: { type: "solid", color: THEME.colors.dk1, pt: 1.5 }, valign: "middle", margin: [0.05, 0.12, 0.05, 0.12], objectName: "Rules table" });
  s.addText("Events are stored and can be asked about by plant, floor, type and time.", { x: M, y: TOP + 3.1, w: 5.6, h: 0.8, fontSize: 16, color: SOFT, valign: "top", margin: 0, isTextBox: true, objectName: "Rules note" });
  picture(s, "safety.jpg", 6.75, TOP + 0.05, 5.98, 16 / 9, "Safety events highlighted on the twin");
}
feature({
  title: "Every floor has a live camera view with detections boxed", img: "camera.jpg", aspect: 1590 / 1080, imgW: 6.5, side: "left",
  leadText: "Focus a floor and its camera appears beside the twin.",
  points: ["The same detection that places the marker draws the box", "One stream is shown at a time, so it stays light", "Nothing is published beyond the one app port"],
  notes: "Real video and real detection, recorded on a laptop CPU.",
});
feature({
  title: "Any camera can be fed from a recording or a webcam", img: "share.jpg", aspect: 1300 / 780, imgW: 7.0, side: "right",
  leadText: "For a live demo, drop your own footage into a floor.",
  points: ["Recorded mp4 files, looped as live streams", "A webcam shared from the browser, or attached to the machine", "“Share recording”: pick a video file and it is analysed on the spot"],
  notes: "Useful with judges: let them hand you a clip.",
});
feature({
  title: "The alert names the person, and one question gives the full picture", img: "who.jpg", aspect: 1180 / 1080, imgW: 4.9, side: "left",
  leadText: "“Who is this person?”",
  points: ["Name, role, shift, supervisor and training", "When they entered, when the alert fired, how long they stayed", "Whether they were authorised for that zone", "Where they are now, and their other incidents today"],
  note: "Employees are fictional. Identity comes from a simulated badge feed, not from face recognition.",
  notes: "Say the synthetic-data line out loud. To use real staff, the badge feed is the one piece to replace.",
});
feature({
  title: "One more sentence writes the incident report", img: "report.jpg", aspect: 1180 / 1080, imgW: 4.9, side: "right",
  leadText: "“Write the incident report.”",
  points: ["What, where, when, who, severity and recommended action", "Filled from the stored event, so it cannot contain invented facts", "The camera snapshot from the moment of the alert is attached"],
  note: "From alert to written report without leaving the twin.",
  notes: "The report is built from the event row, not generated freely.",
});

// ============================================================ 3 how it works
divider(3, "How it works");
{
  const s = content("One process on one device takes video to a spoken answer",
    "Top lane is perception for six streams. Bottom lane is voice. The assistant's tools read the event store and the live state.");
  const bw = 1.62, bh = 0.62, step = 2.02, x0 = M + 0.15;
  const y1 = TOP + 0.55, y2 = TOP + 2.25;
  const node = (label, col, y, kind) => {
    const fill = kind === "soft" ? CARD : kind === "lime" ? LIME : kind === "deep" ? C.accent3 : GREEN;
    const color = kind === "soft" || kind === "deep" ? INK : BLACK;
    s.addShape(pres.ShapeType.roundRect, { x: x0 + col * step, y, w: bw, h: bh, rectRadius: 0.08, fill: { color: fill }, line: { color: kind === "soft" ? MUTED : fill, width: kind === "soft" ? 0.75 : 0 }, objectName: `Node ${label}` });
    s.addText(label, { x: x0 + col * step, y, w: bw, h: bh, fontSize: 13, bold: true, color, align: "center", valign: "middle", margin: 0, isTextBox: true, objectName: `Node ${label} text` });
  };
  const arrow = (col, y, toCol = col + 1) => s.addShape(pres.ShapeType.line, { x: x0 + col * step + bw, y: y + bh / 2, w: (toCol - col) * step - bw, h: 0, line: { color: MUTED, width: 1.5, endArrowType: "triangle" }, objectName: `Arrow ${col} ${y.toFixed(1)}` });
  s.addText("PERCEPTION, 6 STREAMS", { x: x0, y: y1 - 0.45, w: 5, h: 0.3, fontSize: 11, bold: true, color: MUTED, charSpacing: 3, margin: 0, isTextBox: true, objectName: "Lane 1 label" });
  ["Cameras", "Ingest", "Detector", "Track + map", "Rules", "Event store"].forEach((label, i) => node(label, i, y1, i === 0 ? "soft" : i === 5 ? "deep" : "green"));
  for (let i = 0; i < 5; i++) arrow(i, y1);
  s.addText("VOICE", { x: x0, y: y2 - 0.45, w: 5, h: 0.3, fontSize: 11, bold: true, color: MUTED, charSpacing: 3, margin: 0, isTextBox: true, objectName: "Lane 2 label" });
  node("Microphone", 0, y2, "soft"); node("Speech in", 1, y2, "green"); node("Agent + tools", 2, y2, "lime"); node("Speech out", 3, y2, "green"); node("Browser twin", 5, y2, "soft");
  for (let i = 0; i < 3; i++) arrow(i, y2);
  arrow(3, y2, 5);
  s.addText("answer and speech", { x: x0 + 3 * step + bw, y: y2 + bh / 2 + 0.04, w: 2 * step - bw, h: 0.3, fontSize: 11, color: MUTED, align: "center", margin: 0, isTextBox: true, objectName: "Label answer" });
  s.addShape(pres.ShapeType.line, { x: x0 + 5 * step + bw / 2, y: y1 + bh, w: 0, h: y2 - y1 - bh, line: { color: MUTED, width: 1.5, endArrowType: "triangle" }, objectName: "Arrow store to browser" });
  s.addText("state, events", { x: x0 + 5 * step + bw / 2 + 0.1, y: y1 + bh + 0.3, w: 1.3, h: 0.3, fontSize: 11, color: MUTED, margin: 0, isTextBox: true, objectName: "Label state" });
  s.addShape(pres.ShapeType.line, { x: x0 + 2 * step + bw, y: y1 + bh, w: 3 * step - bw, h: y2 - y1 - bh, flipH: true, line: { color: MUTED, width: 1.25, dashType: "dash", endArrowType: "triangle" }, objectName: "Arrow store to agent" });
  s.addText("tools read events and live state", { x: x0 + 2.2 * step, y: y1 + bh + 0.12, w: 3.2, h: 0.3, fontSize: 11, color: MUTED, margin: 0, isTextBox: true, objectName: "Label tools" });
  bullets(s, ["One vision-language model serves the conversation and the “look at this frame” tool",
    "Seven tools: events, live state, look, focus, show event, identify person, write report"], M, TOP + 3.45, W - 2 * M, 1.2);
}
{
  const s = content("The planned model stack leaves headroom inside 15 GB",
    "This is the budget from the plan. It has not been measured on the Jetson yet.");
  const labels = ["Headroom", "App and buffers", "Speech synthesis", "Detector", "Speech recognition", "Vision-language model"];
  s.addChart(pres.charts.BAR, [{ name: "Memory budget (GB)", labels, values: [2, 2, 0.3, 1, 1.5, 6] }], {
    x: M, y: TOP - 0.05, w: 7.4, h: 4.6, barDir: "bar", chartColors: [THEME.colors.accent1],
    showTitle: true, title: "Memory budget (GB)", titleColor: THEME.colors.lt2, titleFontSize: 13, titleFontFace: "+mn-lt",
    showValue: true, dataLabelPosition: "outEnd", dataLabelColor: THEME.colors.lt1, dataLabelFontSize: 12, dataLabelFontFace: "+mn-lt", dataLabelFormatCode: "0.0",
    catAxisLabelColor: THEME.colors.lt2, valAxisLabelColor: THEME.colors.accent4, catAxisLabelFontSize: 12, valAxisLabelFontSize: 11,
    catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt",
    valGridLine: { color: THEME.colors.accent6, size: 0.75 }, catGridLine: { style: "none" }, showLegend: false, valAxisMaxVal: 8,
    objectName: "Memory budget chart", altText: "Bar chart of the planned memory budget per component in GB",
  });
  lead(s, "12.8 of 15 GB budgeted.", 8.5, TOP, 4.2, 0.5);
  bullets(s, ["3B-class vision-language model, half precision", "Whisper for speech in, Piper for speech out", "YOLO exported to TensorRT, one batch for all streams"], 8.5, TOP + 0.75, 4.2, 2.5);
  s.addText("This is the plan. The figures still have to be measured on the Jetson.", { x: 8.5, y: TOP + 3.5, w: 4.2, h: 0.8, fontSize: 12, italic: true, color: MUTED, valign: "top", margin: 0, isTextBox: true, objectName: "Budget note" });
}
{
  const s = content("Every heavy component has a mock, so the demo cannot die",
    "If a model fails on stage, that backend falls back to its mock at startup and the rest keeps working.");
  const header = (t) => ({ text: t, options: { bold: true, color: BLACK, fill: { color: GREEN }, fontSize: 14 } });
  const cell = (t, bold = false) => ({ text: t, options: { color: bold ? INK : SOFT, bold, fill: { color: CARD }, fontSize: 14 } });
  s.addTable([
    [header("Component"), header("Real"), header("Mock")],
    [cell("Perception", true), cell("video, detector, tracker"), cell("simulated people, scripted scenarios")],
    [cell("Assistant", true), cell("vision-language model"), cell("keyword router calling the same tools")],
    [cell("Speech in", true), cell("Whisper"), cell("fixed question")],
    [cell("Speech out", true), cell("Piper"), cell("chime")],
  ], { x: M, y: TOP + 0.05, w: W - 2 * M, colW: [2.4, 4.0, 5.73], rowH: 0.52, border: { type: "solid", color: THEME.colors.dk1, pt: 1.5 }, valign: "middle", margin: [0.05, 0.12, 0.05, 0.12], objectName: "Mocks table" });
  bullets(s, ["A backend that fails to load falls back to its mock at startup, and the app says which is running",
    "The whole app runs on a laptop without a GPU, which is how it was built and tested"], M, TOP + 3.0, W - 2 * M, 1.4);
}

// ============================================================ 4 status and demo
divider(4, "Status and demo");
{
  const s = content("The software is proven on a laptop; the Jetson run is the next step",
    "Be direct about this: nothing has run on a Jetson yet. The code paths for the real models have run on CPU with small stand-in models.");
  const stats = [["77", "automated tests passing", GREEN], ["6", "camera streams detected together on a laptop CPU", LIME], ["0", "runs on a Jetson so far", MUTED]];
  stats.forEach(([value, label, color], i) => {
    const x = M + i * 4.15;
    s.addText(value, { x, y: TOP - 0.1, w: 3.7, h: 1.0, fontSize: 64, bold: true, color, margin: 0, valign: "middle", isTextBox: true, objectName: `Stat ${i + 1} value` });
    s.addText(label, { x, y: TOP + 0.95, w: 3.7, h: 0.6, fontSize: 14, color: SOFT, valign: "top", margin: 0, isTextBox: true, objectName: `Stat ${i + 1} label` });
  });
  const cols = [["Shown working", ["Twin, events, conversation, report", "Real detection, speech in and speech out on CPU", "Webcam and shared recording"]],
    ["Still to prove on the Jetson", ["Hardware video decode and TensorRT", "3B model picks tools, 13 of 15", "10 fps on 6 streams, voice under 2.5 s"]]];
  cols.forEach(([head, items], i) => {
    const x = M + i * 6.2;
    s.addText(head, { x, y: TOP + 1.95, w: 5.8, h: 0.4, fontSize: 18, bold: true, color: INK, margin: 0, isTextBox: true, objectName: `Status ${i + 1} head` });
    bullets(s, items, x, TOP + 2.5, 5.8, 1.9);
  });
}
{
  const s = content("The demo is seven steps, from overview to incident report",
    "Then one unscripted question from a judge.");
  const steps = ["Twin loads: six streams live, metrics visible", "“Give me a status of both plants”", "“Show me Plant 2, floor 3”", "“Any safety issues in the last ten minutes?”",
    "Click the restricted-zone alert on Plant 1, floor 2", "“Who is this person?”", "“Write the incident report”"];
  steps.forEach((text, i) => {
    const col = i < 4 ? 0 : 1, row = i < 4 ? i : i - 4;
    const x = M + col * 6.2, y = TOP + 0.15 + row * 0.95;
    chip(s, i + 1, x, y);
    s.addText(text, { x: x + 0.7, y, w: 5.2, h: 0.46, fontSize: 18, color: INK, valign: "middle", margin: 0, isTextBox: true, objectName: `Step ${i + 1}` });
  });
  s.addShape(pres.ShapeType.roundRect, { x: M + 6.2, y: TOP + 3.0, w: 5.9, h: 0.9, rectRadius: 0.1, fill: { color: CARD }, line: { color: CARD, width: 0 }, objectName: "Judge card" });
  s.addText("Then one unscripted question from a judge.", { x: M + 6.45, y: TOP + 3.0, w: 5.4, h: 0.9, fontSize: 16, bold: true, color: LIME, valign: "middle", margin: 0, isTextBox: true, objectName: "Judge text" });
}
{
  const s = content("Why it matters: answers at the speed of a question, with data that stays on site",
    "The value is the time between something happening and someone knowing.");
  const cards = [["Safety", "Events are seen, named and written up in the moment, not at the end of a shift."],
    ["Operations", "One person can ask about any floor without walking to it."],
    ["Privacy and cost", "Audio and video are processed on one device, with no cloud calls at runtime."],
    ["Fit", "A new site is a new configuration file, not a new project."]];
  cards.forEach(([head, body], i) => {
    const x = M + (i % 2) * 6.2, y = TOP + 0.1 + Math.floor(i / 2) * 2.2;
    s.addShape(pres.ShapeType.roundRect, { x, y, w: 5.93, h: 1.9, rectRadius: 0.1, fill: { color: CARD }, line: { color: CARD, width: 0 }, objectName: `Value card ${i + 1}` });
    s.addText(head, { x: x + 0.35, y: y + 0.28, w: 5.2, h: 0.45, fontSize: 20, bold: true, color: GREEN, margin: 0, isTextBox: true, objectName: `Value ${i + 1} head` });
    s.addText(body, { x: x + 0.35, y: y + 0.8, w: 5.2, h: 0.95, fontSize: 15, color: SOFT, valign: "top", margin: 0, isTextBox: true, objectName: `Value ${i + 1} body` });
  });
}
{
  const s = slide("Statement");
  s.addText("Ask your company a question. It shows you, and it tells you.", { placeholder: "title" });
  s.addText("Talk-to-your-Company. Globant Physical AI Hackathon, on NVIDIA Jetson Thor.", { placeholder: "body" });
  s.addNotes("Close on the line, then go to the live demo.");
}

(async () => {
  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT);
})();
