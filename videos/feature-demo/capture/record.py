"""Record the running app in Chrome for the demo film. Each session writes one video plus a JSON
list of named moments (seconds from the start of the recording), used to cut the footage.

    python capture/record.py overview http://127.0.0.1:8002/
    python capture/record.py story    http://127.0.0.1:8001/  <video file to share>
"""
import base64
import json
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

OUT = Path(__file__).resolve().parent / "raw"
VIEWPORT = {"width": 1280, "height": 720}
SCALE = 1.5  # device pixels per CSS pixel: frames come out 1920x1080 with a readable interface


class Session:
    def __init__(self, page: Page, frames_dir: Path) -> None:
        self.page = page
        self.frames_dir = frames_dir
        self.frames: list[float] = []  # timestamp of each saved frame
        self.marks: dict[str, float] = {}
        self.cdp = page.context.new_cdp_session(page)
        self.cdp.on("Page.screencastFrame", self._frame)
        self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92, "everyNthFrame": 2})

    def _frame(self, event: dict) -> None:
        (self.frames_dir / f"{len(self.frames):06d}.jpg").write_bytes(base64.b64decode(event["data"]))
        self.frames.append(event["metadata"]["timestamp"])
        try:
            self.cdp.send("Page.screencastFrameAck", {"sessionId": event["sessionId"]})
        except Exception:
            pass  # a frame that arrives while the page is closing

    def mark(self, name: str) -> None:
        self.marks[name] = round(time.time() - self.frames[0], 2) if self.frames else 0.0
        print(f"{self.marks[name]:7.2f}  {name}", flush=True)

    def hold(self, seconds: float) -> None:
        self.page.wait_for_timeout(seconds * 1000)  # keeps Playwright pumping screencast frames

    def save(self, target: Path) -> None:
        """Assemble the frames into an mp4 at their real timing."""
        self.cdp.send("Page.stopScreencast")
        listing = self.frames_dir / "frames.txt"
        lines = []
        for i, stamp in enumerate(self.frames):
            following = self.frames[i + 1] if i + 1 < len(self.frames) else stamp + 0.04
            lines += [f"file '{i:06d}.jpg'", f"duration {max(following - stamp, 0.001):.4f}"]
        listing.write_text("\n".join(lines) + "\n")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
                        "-vf", "fps=30,scale=1920:1080:flags=lanczos,format=yuv420p", "-c:v", "libx264",
                        "-crf", "16", "-preset", "slow", "-g", "30", "-movflags", "+faststart", str(target)], check=True)
        span = self.frames[-1] - self.frames[0]
        print(f"{len(self.frames)} frames over {span:.1f} s ({len(self.frames) / span:.1f} fps captured)")

    def nav(self, plant: str = "", floor: str = "") -> None:
        self.page.click(f'#nav-items button[data-plant="{plant}"][data-floor="{floor}"]')

    def ask(self, text: str, settle: float) -> None:
        """Type a question at a readable speed, send it, and wait for the answer to land."""
        box = self.page.locator("#text")
        box.click()
        box.press_sequentially(text, delay=45)
        self.hold(0.4)
        box.press("Enter")
        self.page.wait_for_function("document.getElementById('answer').textContent.length > 0", timeout=30000)
        self.hold(settle)


def overview(s: Session) -> None:
    s.hold(2.0)
    s.mark("overview")
    s.hold(8.0)
    s.mark("plant1")
    s.nav("P1")
    s.hold(6.5)
    s.mark("plant2")
    s.nav("P2")
    s.hold(6.0)
    s.mark("back")
    s.nav()
    s.hold(3.5)
    s.mark("status")
    s.ask("Give me a status of both plants", 6.0)
    s.mark("safety")
    s.ask("Any safety issues in the last ten minutes?", 7.0)
    s.mark("end")


def story(s: Session, shared_video: str) -> None:
    page = s.page
    s.hold(2.0)
    s.mark("floor")
    s.nav("P1", "F2")
    s.hold(11.0)
    s.mark("issues")
    s.ask("Any safety issues on Plant 1 floor 2?", 6.0)
    s.mark("who")
    s.ask("Who is this person?", 9.0)
    s.mark("before")
    s.ask("Has this person done this before?", 6.0)
    s.mark("report")
    s.ask("Write the incident report", 8.0)
    page.click("#panel-close")
    s.mark("share_floor")
    s.nav("P2", "F2")
    s.hold(5.0)
    s.mark("share")
    page.set_input_files("#camera-file", shared_video)
    s.hold(14.0)
    s.mark("share_stop")
    page.click("#camera-stop")
    s.hold(2.5)
    s.mark("hud")
    s.nav()
    s.hold(6.0)
    s.mark("end")


def main() -> None:
    name, url = sys.argv[1], sys.argv[2]
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True,
                                    args=["--enable-gpu", "--use-angle=d3d11", "--ignore-gpu-blocklist"])
        context = browser.new_context(viewport=VIEWPORT, device_scale_factor=SCALE)
        page = context.new_page()
        page.goto(url)
        page.wait_for_selector("#nav-items button")
        frames_dir = OUT / f"{name}-frames"
        if frames_dir.exists():
            for old in frames_dir.iterdir():
                old.unlink()
        frames_dir.mkdir(parents=True, exist_ok=True)
        session = Session(page, frames_dir)
        if name == "overview":
            overview(session)
        else:
            story(session, sys.argv[3])
        target = OUT / f"{name}.mp4"
        session.save(target)
        context.close()
        browser.close()
        (OUT / f"{name}.json").write_text(json.dumps(session.marks, indent=2))
        print("saved", target)


if __name__ == "__main__":
    main()
