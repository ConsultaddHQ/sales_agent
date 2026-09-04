#!/usr/bin/env bash
# Idempotent Cloud Agent bootstrap for sales-voice-agent.
# Prepares both Python FastAPI services, the shared library, and both
# React (Vite) frontends so the full development experience is runnable.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Run apt/npm/pip non-interactively.
export DEBIAN_FRONTEND=noninteractive
export PIP_DISABLE_PIP_VERSION_CHECK=1

SUDO=""
if [[ "$(id -u)" -ne 0 ]]; then
  command -v sudo >/dev/null 2>&1 && SUDO="sudo"
fi

echo "▶ System packages (python venv + build toolchain)"
# The default image ships Python 3.12 and Node 22 but not python3-venv/ensurepip.
if ! python3 -c 'import ensurepip' >/dev/null 2>&1; then
  $SUDO apt-get update -qq
  $SUDO apt-get install -y -qq python3-venv python3-dev build-essential
fi

# ── Python service venvs ────────────────────────────────────────────────────
# Each service keeps its own venv (project invariant). pytest is the documented
# test runner but is not pinned in requirements.txt, so add it to the
# onboarding venv where the suite lives.
setup_py_service() {  # dir  extra_pip_pkgs...
  local dir="$1"; shift
  echo "▶ Python env: $dir"
  [[ -x "$dir/.venv/bin/python" ]] || python3 -m venv "$dir/.venv"
  "$dir/.venv/bin/python" -m pip install -q --upgrade pip
  "$dir/.venv/bin/python" -m pip install -q -r "$dir/requirements.txt"
  if [[ "$#" -gt 0 ]]; then
    "$dir/.venv/bin/python" -m pip install -q "$@"
  fi
}

setup_py_service onboarding-service pytest
setup_py_service search-service

# Chromium for the Playwright JS-render fallback used by the universal scraper.
# Best-effort: the scraper degrades gracefully if it is unavailable, so a
# transient download failure must not fail the whole environment build.
echo "▶ Playwright chromium (best-effort)"
if [[ -n "$SUDO" ]] || [[ "$(id -u)" -eq 0 ]]; then
  onboarding-service/.venv/bin/python -m playwright install --with-deps chromium || \
    echo "⚠️  chromium install skipped (scraper JS-render fallback disabled)"
else
  onboarding-service/.venv/bin/python -m playwright install chromium || \
    echo "⚠️  chromium install skipped (scraper JS-render fallback disabled)"
fi

# ── Node frontends ──────────────────────────────────────────────────────────
setup_node_app() {  # dir
  local dir="$1"
  echo "▶ Node deps: $dir"
  ( cd "$dir" && npm install --no-audit --no-fund )
}

setup_node_app www.teampop/frontend
setup_node_app www.teampop/website

# Build the widget IIFE (served by onboarding-service at /widget/widget.js —
# project invariant: never served from the Vite dev server) and the site.
echo "▶ Build widget + website"
( cd www.teampop/frontend && npm run build )
( cd www.teampop/website && npm run build )

# ── Local .env scaffolding (gitignored; placeholder values only) ─────────────
# Lets the services boot and the site build with sane local defaults. Real
# secrets (Supabase / ElevenLabs / OpenRouter) are added by the developer for
# full voice/search functionality.
seed_env() {  # example_path
  local ex="$1"; local target="${ex%.example}"
  [[ -f "$target" ]] || { [[ -f "$ex" ]] && cp "$ex" "$target"; }
}
seed_env onboarding-service/.env.example
seed_env search-service/.env.example
seed_env www.teampop/website/.env.example

echo "✅ install complete"
