"""Check which browser channel can record the app smoothly: WebGL renderer and frame rate."""
import sys
import time

from playwright.sync_api import sync_playwright

url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8002/"
with sync_playwright() as p:
    for channel in ("chrome", "msedge"):
        try:
            browser = p.chromium.launch(channel=channel, headless=True,
                                        args=["--enable-gpu", "--use-angle=d3d11", "--ignore-gpu-blocklist"])
        except Exception as exc:
            print(channel, "unavailable:", str(exc).splitlines()[0])
            continue
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.goto(url)
        time.sleep(3)
        info = page.evaluate("""async () => {
            const gl = document.createElement('canvas').getContext('webgl2');
            const ext = gl.getExtension('WEBGL_debug_renderer_info');
            let frames = 0; const start = performance.now();
            await new Promise((done) => { const tick = () => { frames++; performance.now() - start < 2000 ? requestAnimationFrame(tick) : done(); }; tick(); });
            return { renderer: ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : 'unknown', fps: frames / 2,
                     h264: document.createElement('video').canPlayType('video/mp4; codecs="avc1.42E01E"') };
        }""")
        print(channel, info)
        browser.close()
