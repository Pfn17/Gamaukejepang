#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD"
while true; do
  echo "Starting scalper cycle..."
  python -m src.main || true
  echo "Bot exited, restarting in 30s..."
  sleep 30
done
