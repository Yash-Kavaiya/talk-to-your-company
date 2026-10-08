#!/usr/bin/env bash
# Checks the Jetson before a run (plan section 10). Exit code 0 only when every hard check passes.
# A failed check does not stop the app from starting: each real backend falls back to its mock.
set -u
cd "$(dirname "$0")/.."

MODELS_DIR="${MODELS_DIR:-/cache/models}"
failed=0
ok()   { echo "  ok    $1"; }
warn() { echo "  WARN  $1"; }
fail() { echo "  FAIL  $1"; failed=1; }

echo "Preflight"

if python3 -c "import torch, sys; sys.exit(0 if torch.cuda.is_available() else 1)" 2>/dev/null; then
  ok "CUDA available ($(python3 -c 'import torch, torchvision, numpy; print("torch", torch.__version__, "torchvision", torchvision.__version__, "numpy", numpy.__version__)' 2>/dev/null))"
else
  fail "CUDA not available through the pre-installed PyTorch"
fi

if command -v gst-inspect-1.0 >/dev/null && gst-inspect-1.0 nvv4l2decoder >/dev/null 2>&1; then
  ok "GStreamer hardware decoder nvv4l2decoder"
else
  warn "GStreamer hardware decoder missing: ingest will use OpenCV software decode"
fi

if [ -d /cache ]; then
  free_gb=$(df -Pk /cache | awk 'NR==2 {printf "%d", $4 / 1048576}')
  if [ "$free_gb" -ge 5 ]; then ok "/cache has ${free_gb} GB free"; else fail "/cache has only ${free_gb} GB free"; fi
else
  fail "/cache does not exist"
fi

if python3 -c "import socket, sys; s = socket.socket(); s.bind(('0.0.0.0', 8000))" 2>/dev/null; then
  ok "port 8000 free"
else
  fail "port 8000 is in use"
fi

for module in fastapi uvicorn yaml transformers ultralytics piper cv2 PIL; do
  if python3 -c "import $module" 2>/dev/null; then ok "python module $module"; else fail "python module $module missing (scripts/safe_install.sh)"; fi
done

if [ -f "$MODELS_DIR/yolo11s.engine" ]; then ok "detector TensorRT engine"
elif [ -f "$MODELS_DIR/yolo11s.pt" ]; then warn "detector has PyTorch weights only, no TensorRT engine (scripts/download_models.py)"
else fail "detector weights missing in $MODELS_DIR"; fi
if ls -d "$MODELS_DIR"/models--*VL* >/dev/null 2>&1; then ok "vision-language model"; else fail "vision-language model missing in $MODELS_DIR"; fi
if ls -d "$MODELS_DIR"/models--*whisper* >/dev/null 2>&1; then ok "speech recognition model"; else fail "Whisper model missing in $MODELS_DIR"; fi
if [ -f "${PIPER_VOICE:-$MODELS_DIR/piper/en_US-lessac-medium.onnx}" ]; then ok "Piper voice"; else fail "Piper voice missing"; fi

# videos and calibration come from config/site.yaml
python3 - <<'EOF' || failed=1
import os, sys
from pathlib import Path
from app.config import load_site, resolve_video
bad = False
videos = Path(os.environ.get("VIDEOS_DIR", "/cache/videos"))
for plant, floor in load_site(os.environ.get("SITE_CONFIG", "config/site.yaml")).floors():
    cam = floor.camera
    if cam.source_kind() != "file":
        print(f"  ok    {cam.id} is a live source ({cam.video})")
    elif resolve_video(cam.video, videos).is_file():
        print(f"  ok    video {cam.id}")
    else:
        print(f"  FAIL  video {cam.id} missing: {resolve_video(cam.video, videos)} (scripts/get_sample_videos.py)")
        bad = True
    if cam.homography is None:
        print(f"  FAIL  {cam.id} is not calibrated (scripts/calibrate.py)")
        bad = True
sys.exit(1 if bad else 0)
EOF

if [ "$failed" -eq 0 ]; then echo "Preflight passed."; else echo "Preflight FAILED: the affected backends will run as mocks."; fi
exit "$failed"
