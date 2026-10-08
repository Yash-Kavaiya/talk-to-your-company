#!/usr/bin/env python3
"""Compute a camera's homography from four image points and their floor coordinates (plan section 7).

With a display: click four points on the first video frame, then type each one's floor position.
    python3 scripts/calibrate.py cam_p1f1

Without a display (the usual case in the container): save a frame, read pixel positions in any
image viewer, then pass the pairs as "u,v:x,y".
    python3 scripts/calibrate.py cam_p1f1 --save-frame /cache/p1f1.jpg
    python3 scripts/calibrate.py cam_p1f1 --points 100,600:0,0 1180,600:40,0 900,200:40,25 380,200:0,25

Prints the `homography:` line to paste into config/site.yaml for that camera.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import DEFAULT_SITE_PATH, Settings, load_site, resolve_video  # noqa: E402
from app.perception.mapper import apply_homography, solve_homography  # noqa: E402


def parse_pair(text: str) -> tuple[tuple[float, float], tuple[float, float]]:
    image, floor = text.split(":")
    u, v = (float(n) for n in image.split(","))
    x, y = (float(n) for n in floor.split(","))
    return (u, v), (x, y)


def first_frame(camera):
    import cv2

    kind = camera.source_kind()
    if kind == "browser":
        sys.exit("this camera is fed by a browser: share the webcam, then save a frame from the camera view "
                 "(right-click the picture) and use --points")
    device = camera.video.split(":", 1)[1] if kind == "webcam" else None
    video = (int(device) if device.isdigit() else device) if device else str(
        resolve_video(camera.video, Settings.from_env().videos_dir))
    capture = cv2.VideoCapture(video)
    ok, frame = capture.read()
    capture.release()
    if not ok:
        sys.exit(f"cannot read a frame from {video}")
    return cv2.resize(frame, (1280, 720))


def click_points(frame) -> list[tuple[float, float]]:
    import cv2

    points: list[tuple[float, float]] = []

    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and len(points) < 4:
            points.append((float(x), float(y)))
            cv2.circle(frame, (x, y), 6, (60, 60, 240), -1)
            cv2.putText(frame, str(len(points)), (x + 10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (60, 60, 240), 2)

    cv2.namedWindow("calibrate")
    cv2.setMouseCallback("calibrate", on_mouse)
    while len(points) < 4:
        cv2.imshow("calibrate", frame)
        if cv2.waitKey(30) == 27:
            sys.exit("cancelled")
    cv2.imshow("calibrate", frame)
    cv2.waitKey(300)
    cv2.destroyAllWindows()
    return points


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate one camera's image-to-floor homography.")
    parser.add_argument("camera_id")
    parser.add_argument("--site", default=str(DEFAULT_SITE_PATH))
    parser.add_argument("--save-frame", metavar="JPG", help="write the first frame (1280x720) and exit")
    parser.add_argument("--points", nargs=4, metavar="u,v:x,y", help="four image:floor point pairs")
    args = parser.parse_args()

    floor = next((f for _, f in load_site(args.site).floors() if f.camera.id == args.camera_id), None)
    if floor is None:
        sys.exit(f"no camera {args.camera_id} in {args.site}")

    if args.save_frame:
        import cv2

        cv2.imwrite(args.save_frame, first_frame(floor.camera))
        print(f"wrote {args.save_frame}; floor is {floor.size_m[0]} x {floor.size_m[1]} m")
        return

    if args.points:
        image_points, floor_points = zip(*(parse_pair(p) for p in args.points))
    else:
        image_points = click_points(first_frame(floor.camera))
        floor_points = []
        for i, (u, v) in enumerate(image_points, 1):
            x, y = (float(n) for n in input(f"floor x,y in metres of point {i} ({u:.0f},{v:.0f}): ").split(","))
            floor_points.append((x, y))

    h = solve_homography(list(image_points), list(floor_points))
    for (u, v), expected in zip(image_points, floor_points):
        x, y = apply_homography(h, u, v)
        print(f"  check ({u:.0f},{v:.0f}) -> ({x:.2f},{y:.2f}), wanted {expected}")
    rows = ", ".join("[" + ", ".join(f"{n:.6g}" for n in row) + "]" for row in h)
    print(f"\npaste under camera {args.camera_id} in {args.site}:\n          homography: [{rows}]")


if __name__ == "__main__":
    main()
