#!/usr/bin/env bash
# =============================================================================
# .cursor/install.sh — idempotent Cloud Agent bootstrap for sales-voice-agent.
#
# Prepares the full local dev experience after checkout:
#   - Python venvs + deps for onboarding-service and search-service
#   - pytest (test-only dep, not shipped in requirements.txt)
#   - Playwright Chromium (used by the universal scraper)
#   - the all-MiniLM-L6-v2 embedding model (warmed into the HF cache)
#   - npm deps + production builds for the widget and the marketing website
#
# Safe to run repeatedly. Heavy artifacts (apt packages, browser binaries,
# the embedding model) are provided by the environment snapshot; this script
# only refreshes source-derived state and is a no-op when already prepared.
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

log() { printf '\n\033[1;36m▶ %s\033[0m\n' "$*"; }

# ── Python services ─────────────────────────────────────────────────────────
setup_pyservice() { # dir  extra_pip_pkgs...
  local dir="$1"; shift
  log "Python env: $dir"
  if [[ ! -x "$dir/.venv/bin/python" ]]; then
    python3 -m venv "$dir/.venv"
  fi
  "$dir/.venv/bin/python" -m pip install --upgrade pip -q
  "$dir/.venv/bin/python" -m pip install -q -r "$dir/requirements.txt"
  if (( $# > 0 )); then
    "$dir/.venv/bin/python" -m pip install -q "$@"
  fi
}

# onboarding-service also runs the pytest suite (tests/) and Playwright.
setup_pyservice onboarding-service pytest
setup_pyservice search-service

# ── Playwright Chromium (browser binary lives in the HOME cache / snapshot) ──
log "Playwright Chromium"
onboarding-service/.venv/bin/python -m playwright install chromium

# ── Warm the shared embedding model (all-MiniLM-L6-v2, 384-dim) ─────────────
# Cached under ~/.cache/huggingface so onboarding + search start instantly.
log "Embedding model (all-MiniLM-L6-v2)"
onboarding-service/.venv/bin/python - <<'PY'
from sentence_transformers import SentenceTransformer
SentenceTransformer("all-MiniLM-L6-v2")
print("embedding model ready")
PY

# ── Frontends: widget (built IIFE served by onboarding /widget) + website ────
log "Widget (www.teampop/frontend)"
( cd www.teampop/frontend && npm install --no-audit --no-fund && npm run build )

log "Website (www.teampop/website)"
( cd www.teampop/website && npm install --no-audit --no-fund && npm run build )

# ── Local .env files (placeholders; real secrets injected as env vars) ──────
# The services read these via python-dotenv. Missing values are fine for boot,
# health checks, embeddings, and validation; live Supabase/ElevenLabs/LLM
# calls require the corresponding secrets to be set in the environment.
for svc in onboarding-service search-service www.teampop/website; do
  if [[ -f "$svc/.env.example" && ! -f "$svc/.env" ]]; then
    cp "$svc/.env.example" "$svc/.env"
  fi
done

log "install complete"
