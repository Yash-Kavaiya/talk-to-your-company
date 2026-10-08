#!/usr/bin/env bash
# One-time setup on the Jetson Thor, run from the repo in /workspace. Needs the network; the app
# itself then runs offline. Safe to run again: finished steps are skipped.
#   scripts/setup_jetson.sh
set -eu
cd "$(dirname "$0")/.."

export MODELS_DIR="${MODELS_DIR:-/cache/models}"
export VIDEOS_DIR="${VIDEOS_DIR:-/cache/videos}"
# Ultralytics otherwise pip-installs missing export tools by itself, which could replace numpy.
export YOLO_AUTOINSTALL=false

echo "== 1/5 versions that must not change"
before=$(python3 -c "import torch, torchvision, numpy; print(torch.__version__, torchvision.__version__, numpy.__version__)")
echo "   torch, torchvision, numpy: $before"

echo "== 2/5 python packages (each one dry-run checked)"
pip install --user -r requirements.txt
for package in transformers pillow ultralytics piper-tts onnx onnxslim; do
  scripts/safe_install.sh "$package"
done
after=$(python3 -c "import torch, torchvision, numpy; print(torch.__version__, torchvision.__version__, numpy.__version__)")
if [ "$before" != "$after" ]; then
  echo "STOP: torch, torchvision or numpy changed: $before -> $after" >&2
  exit 1
fi

echo "== 3/5 models into $MODELS_DIR (several GB) and TensorRT export"
python3 scripts/download_models.py

echo "== 4/5 sample videos into $VIDEOS_DIR"
python3 scripts/get_sample_videos.py

echo "== 5/5 preflight"
scripts/preflight.sh || true

cat <<'EOF'

Setup finished. Next:
  scripts/run.sh                                        # start the app on 0.0.0.0:8000
  LLM=local python3 scripts/eval_tool_calling.py        # T19: needs 13 of 15
Calibrate each camera with scripts/calibrate.py before trusting marker positions.
EOF
