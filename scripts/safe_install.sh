#!/usr/bin/env bash
# pip install --user, but only after a dry run shows that torch, torchvision and numpy stay untouched
# (CLAUDE.md hard constraint). Usage: scripts/safe_install.sh <package> [<package> ...]
set -eu
[ "$#" -ge 1 ] || { echo "usage: $0 <package> [<package> ...]"; exit 2; }

plan=$(pip install --user --dry-run "$@" 2>&1 | grep "^Would install" || true)
echo "${plan:-Nothing to install.}"
if echo "$plan" | tr ' ' '\n' | grep -Eiq '^(torch|torchvision|numpy)-[0-9]'; then
  echo "REFUSED: this would install or replace torch, torchvision or numpy. Stop and ask." >&2
  exit 1
fi
pip install --user "$@"
