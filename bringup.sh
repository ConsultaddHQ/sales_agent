#!/usr/bin/env bash
# =============================================================================
# bringup.sh — one command to take the Pop Sales Agent live on the Team Pop
# site. Everything automatable is automated; the only things that stay yours
# are the irreducible ones: your secret keys in onboarding-service/.env
# (pasted once) and actually talking to the agent.
#
#   ./bringup.sh          bring it all up
#   ./bringup.sh --stop   tear down everything this started
#
# Reuses the unit-tested helpers in onboarding-service/services/bringup.py —
# no orchestration logic is reimplemented in bash.
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OBS="$ROOT/onboarding-service"
SITE="$ROOT/www.teampop/website"
WIDGET="$ROOT/www.teampop/frontend"
RUN="$ROOT/.context/bringup"        # .context is gitignored
mkdir -p "$RUN"
PY="$OBS/.venv/bin/python"

say()  { printf '\n\033[1;36m▶ %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m✅ %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31m❌ %s\033[0m\n' "$*" >&2; exit 1; }

# ── teardown ────────────────────────────────────────────────────────────────
stop() {
  for svc in website ngrok onboarding; do
    if [[ -f "$RUN/$svc.pid" ]]; then
      kill "$(cat "$RUN/$svc.pid")" 2>/dev/null || true
      rm -f "$RUN/$svc.pid"
      ok "stopped $svc"
    fi
  done
  exit 0
}
[[ "${1:-}" == "--stop" ]] && stop

# ── 0. prerequisites ────────────────────────────────────────────────────────
say "Checking prerequisites"
for bin in python3 node npm ngrok; do
  command -v "$bin" >/dev/null 2>&1 || die "$bin not found — install it first."
done
ok "python3 / node / npm / ngrok present"

# ── 1. secrets gate (irreducibly yours) ─────────────────────────────────────
say "Checking your secrets in onboarding-service/.env"
[[ -f "$OBS/.env" ]] || { cp "$OBS/.env.example" "$OBS/.env"; die "Created onboarding-service/.env from the example — paste your keys into it and re-run."; }
# Reuse the tested missing_secrets() rather than re-checking in bash.
MISSING="$(cd "$OBS" && python3 -c '
import os, sys
from dotenv import dotenv_values
sys.path.insert(0, ".")
from services.bringup import missing_secrets
print(",".join(missing_secrets(dotenv_values(".env"))))')"
if [[ -n "$MISSING" ]]; then
  die "Missing in onboarding-service/.env: $MISSING
   Add them (see .env.example), then re-run ./bringup.sh
   (Optional but recommended: SUPABASE_DB_URL to auto-apply migrations,
    NGROK_AUTHTOKEN so the tunnel needs no separate setup.)"
fi
ok "required secrets present"

# ── 2. python env ───────────────────────────────────────────────────────────
say "Python environment (onboarding-service/.venv)"
if [[ ! -x "$PY" ]]; then
  python3 -m venv "$OBS/.venv"
  "$PY" -m pip install -q --upgrade pip
  "$PY" -m pip install -q -r "$OBS/requirements.txt"
  ok "venv created + deps installed"
else
  ok "venv present (run with deps already installed)"
fi

# ── 3. build the widget IIFE ────────────────────────────────────────────────
say "Building widget"
( cd "$WIDGET" && { [[ -d node_modules ]] || npm install --silent; } && npm run build --silent )
ok "widget built → dist/widget.js"

# ── 4. ngrok first (URL is baked into the agent at provision time) ──────────
say "Starting ngrok tunnel on :8005"
[[ -n "${NGROK_AUTHTOKEN:-}" ]] && ngrok config add-authtoken "$NGROK_AUTHTOKEN" >/dev/null 2>&1 || true
ngrok http 8005 --log=stdout > "$RUN/ngrok.log" 2>&1 &
echo $! > "$RUN/ngrok.pid"
PUBLIC_URL=""
for _ in $(seq 1 30); do
  sleep 1
  PUBLIC_URL="$(curl -s http://127.0.0.1:4040/api/tunnels | "$PY" -c '
import sys; sys.path.insert(0,"'"$OBS"'")
from services.bringup import parse_ngrok_url
print(parse_ngrok_url(sys.stdin.read()) or "")' 2>/dev/null || true)"
  [[ -n "$PUBLIC_URL" ]] && break
done
[[ -n "$PUBLIC_URL" ]] || die "ngrok did not expose an https URL (see $RUN/ngrok.log)"
ok "public URL: $PUBLIC_URL"

# ── 5. wire env (idempotent, via tested env_upsert) ─────────────────────────
say "Wiring environment"
upsert() { # file KEY VALUE
  "$PY" -c '
import sys; sys.path.insert(0,"'"$OBS"'")
from services.bringup import env_upsert
f,k,v=sys.argv[1:4]
open(f,"w").write(env_upsert(open(f).read() if __import__("os").path.exists(f) else "", k, v))' "$1" "$2" "$3"
}
upsert "$OBS/.env" SEARCH_API_URL "$PUBLIC_URL"
[[ -f "$SITE/.env" ]] || cp "$SITE/.env.example" "$SITE/.env"
upsert "$SITE/.env" VITE_API_URL "$PUBLIC_URL"
upsert "$SITE/.env" VITE_WIDGET_URL "$PUBLIC_URL/widget/widget.js"
ok "SEARCH_API_URL + site VITE_API_URL/VITE_WIDGET_URL set"

# ── 6. start onboarding-service (after env is correct) ──────────────────────
say "Starting onboarding-service on :8005"
( cd "$OBS" && "$PY" main.py > "$RUN/onboarding.log" 2>&1 & echo $! > "$RUN/onboarding.pid" )
for _ in $(seq 1 30); do
  sleep 1
  curl -sf http://127.0.0.1:8005/health >/dev/null 2>&1 && break
done
curl -sf http://127.0.0.1:8005/health >/dev/null 2>&1 || die "onboarding-service did not become healthy (see $RUN/onboarding.log)"
ok "onboarding-service healthy"

# ── 7. migrations (auto if SUPABASE_DB_URL, else preflight will flag) ───────
say "Applying migrations"
set +e
( cd "$OBS" && "$PY" apply_migrations.py )
MIG=$?
set -e
[[ $MIG -eq 1 ]] && die "migration failed — see output above"
[[ $MIG -eq 3 ]] && printf '\033[1;33m⚠️  apply the SQL files in the Supabase editor (above), then re-run if preflight fails.\033[0m\n'
[[ $MIG -eq 0 ]] && ok "migrations applied"

# ── 8. preflight gate ───────────────────────────────────────────────────────
say "Preflight"
( cd "$OBS" && "$PY" preflight_sales.py ) || die "preflight blocked — resolve the ❌ above, then re-run."

# ── 9. provision the agent + capture its id ─────────────────────────────────
say "Provisioning the sales agent"
PROV="$(cd "$OBS" && "$PY" provision_sales_agent.py --brain-url "$PUBLIC_URL")" || { echo "$PROV"; die "provisioning failed"; }
echo "$PROV"
AGENT_LINE="$(printf '%s\n' "$PROV" | grep -E '^\s*VITE_SALES_AGENT_ID=' | tail -1 | tr -d ' ')"
[[ -n "$AGENT_LINE" ]] || die "could not read VITE_SALES_AGENT_ID from provisioning output"
upsert "$SITE/.env" VITE_SALES_AGENT_ID "${AGENT_LINE#VITE_SALES_AGENT_ID=}"
ok "agent provisioned + id wired into the site"

# ── 10. build + serve the site ──────────────────────────────────────────────
say "Building + serving the Team Pop site"
( cd "$SITE" && { [[ -d node_modules ]] || npm install --silent; } && npm run build --silent )
( cd "$SITE" && npm run preview --silent -- --port 4173 > "$RUN/website.log" 2>&1 & echo $! > "$RUN/website.pid" )
sleep 3
ok "site served"

cat <<EOF

============================================================
🎉 Pop Sales Agent is LIVE
   Site (talk to it here): http://localhost:4173
   Public backend (ngrok): $PUBLIC_URL
   Agent dashboard:        see provisioning output above
   Logs:                   $RUN/*.log

Now do the one thing only you can: open the site, click the
orb, allow the mic, and sell-test it. On your first turn,
watch $RUN/onboarding.log for "/sales/brain … conv=<id>" —
a real id confirms cross-turn memory (DESIGN §8 Q2).

Tear it all down with:  ./bringup.sh --stop
============================================================
EOF
