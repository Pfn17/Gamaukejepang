#!/usr/bin/env bash
# Commits and pushes journal/status changes to GitHub.
# Reads GITHUB_TOKEN / GITHUB_REPO_URL / GITHUB_BRANCH from .env (already
# exported into the shell env before this runs — see README for how to
# source .env safely).
#
# Usage:
#   bash scripts/auto_push.sh              # one-shot push
#   bash scripts/auto_push.sh loop 300      # push every 300s in a loop
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -z "${GITHUB_TOKEN:-}" ] || [ -z "${GITHUB_REPO_URL:-}" ]; then
  echo "GITHUB_TOKEN / GITHUB_REPO_URL not set in environment. Source your .env first:"
  echo '  set -a; source .env; set +a'
  exit 1
fi

# Build an authenticated remote URL without ever printing the token to logs.
AUTH_URL=$(echo "$GITHUB_REPO_URL" | sed "s#https://#https://${GITHUB_TOKEN}@#")
BRANCH="${GITHUB_BRANCH:-main}"

push_once() {
  git add journal/ || true
  if git diff --cached --quiet; then
    echo "[auto_push] nothing new to commit"
    return 0
  fi
  git -c user.email="scalper-bot@local" -c user.name="scalper-bot" \
      commit -m "auto: journal update $(date -u +%Y-%m-%dT%H:%M:%SZ)" -q
  git push "$AUTH_URL" "HEAD:$BRANCH" -q
  echo "[auto_push] pushed at $(date -u)"
}

if [ "${1:-}" == "loop" ]; then
  INTERVAL="${2:-300}"
  echo "[auto_push] looping every ${INTERVAL}s"
  while true; do
    push_once || echo "[auto_push] push failed this cycle, will retry next cycle"
    sleep "$INTERVAL"
  done
else
  push_once
fi
