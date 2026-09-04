#!/usr/bin/env bash
# =============================================================================
# .cursor/start.sh — per-boot service bring-up for sales-voice-agent.
#
# Launches the three long-running dev services and stays attached:
#   - search-service      :8006  (hybrid product search API)
#   - onboarding-service  :8005  (pipeline API; serves the built widget at
#                                 /widget/widget.js and proxies /search)
#   - website (preview)   :4173  (marketing site + client acquisition flow)
#
# The two APIs run in the background (logs in /tmp/*.log); the website preview
# runs in the foreground so this process stays alive for the container.
# Idempotent: frees the ports first so restarts don't collide.
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

for p in 8005 8006 4173; do
  pids="$(lsof -ti "tcp:$p" 2>/dev/null || true)"
  [[ -n "$pids" ]] && kill $pids 2>/dev/null || true
done

echo "▶ starting search-service on :8006"
( cd search-service && exec .venv/bin/uvicorn main:app --host 0.0.0.0 --port 8006 ) \
  >/tmp/search-service.log 2>&1 &

echo "▶ starting onboarding-service on :8005"
( cd onboarding-service && exec .venv/bin/python main.py ) \
  >/tmp/onboarding-service.log 2>&1 &

echo "▶ starting website preview on :4173 (foreground)"
cd www.teampop/website
exec npm run preview -- --host 0.0.0.0 --port 4173
