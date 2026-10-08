#!/usr/bin/env python3
"""Download public sample videos for every file camera in config/site.yaml. Needs the network once.

    python3 scripts/get_sample_videos.py [--videos-dir /cache/videos] [--site config/site.yaml]

The clips come from Intel's public `sample-videos` repository (people in a work zone, a store aisle,
people walking, street traffic). They are a starting set so the demo runs; replace any of them by
putting your own mp4 under the same name. Read the repository's terms before showing them publicly.
"""
from __future__ import annotations

import argparse
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import DEFAULT_SITE_PATH, load_site, resolve_video  # noqa: E402

BASE = "https://github.com/intel-iot-devkit/sample-videos/raw/master/"
CLIPS = ["worker-zone-detection.mp4", "people-detection.mp4", "store-aisle-detection.mp4",
         "one-by-one-person-detection.mp4", "person-bicycle-car-detection.mp4", "face-demographics-walking.mp4"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--videos-dir", type=Path, default=Path(os.environ.get("VIDEOS_DIR", "/cache/videos")))
    parser.add_argument("--site", default=os.environ.get("SITE_CONFIG", str(DEFAULT_SITE_PATH)))
    args = parser.parse_args()
    videos_dir = args.videos_dir.resolve()

    cameras = [f.camera for _, f in load_site(args.site).floors() if f.camera.source_kind() == "file"]
    for i, camera in enumerate(cameras):
        target = resolve_video(camera.video, videos_dir)
        if target.exists():
            print(f"have  {camera.id}: {target}")
            continue
        clip = CLIPS[i % len(CLIPS)]
        target.parent.mkdir(parents=True, exist_ok=True)
        print(f"fetch {camera.id}: {clip} -> {target}")
        partial = target.with_suffix(".part")
        urllib.request.urlretrieve(BASE + clip, partial)
        partial.replace(target)
    print("done")


if __name__ == "__main__":
    main()
