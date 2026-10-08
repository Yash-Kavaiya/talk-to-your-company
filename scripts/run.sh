#!/usr/bin/env bash
# Cold start on the Jetson with every real backend (NFR4). Override any mode from the shell,
# e.g. `LLM=mock scripts/run.sh`. A backend that fails to load falls back to its mock by itself.
set -eu
cd "$(dirname "$0")/.."

export PERCEPTION="${PERCEPTION:-real}"
export LLM="${LLM:-local}"
export ASR="${ASR:-local}"
export TTS="${TTS:-local}"
export MODELS_DIR="${MODELS_DIR:-/cache/models}"
export VIDEOS_DIR="${VIDEOS_DIR:-/cache/videos}"
export DATA_DIR="${DATA_DIR:-/cache/ttyc}"
# All inference is local: never reach for the Hugging Face Hub at runtime.
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export YOLO_OFFLINE=1

exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
