#!/usr/bin/env bash
# Deploy a branch to the Lightsail box FROM THE DEV MAC, with automatic rollback.
#   deploy/deploy.sh [--branch <name>] [--widget] [--dry-run]
# Env: SSH_KEY (default ~/.ssh/teampop-lightsail.pem), HOST (default ubuntu@13.232.36.194)
set -euo pipefail

SSH_KEY=${SSH_KEY:-$HOME/.ssh/teampop-lightsail.pem}
HOST=${HOST:-ubuntu@13.232.36.194}
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
LIB=$SCRIPT_DIR/remote-lib.sh
BRANCH="" WIDGET=0 DRY=0

while [ $# -gt 0 ]; do
  case $1 in
    --branch) BRANCH=${2:?--branch needs a value}; shift 2 ;;
    --widget) WIDGET=1; shift ;;
    --dry-run) DRY=1; shift ;;
    -h|--help) sed -n '2,5p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

cd "$ROOT"
BRANCH=${BRANCH:-$(git rev-parse --abbrev-ref HEAD)}
SSH=(ssh -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 "$HOST")
START=$(date +%s)

# remote <mode> args... : run remote-lib + a mode snippet on the box
remote() {
  local snippet=$1; shift
  if [ "$DRY" = 1 ]; then
    echo "[dry-run] ssh $HOST bash -s -- $* <<< (remote-lib.sh + snippet):" >&2
    echo "    ${snippet//$'\n'/$'\n'    }" >&2
    return 0
  fi
  { cat "$LIB"; echo "$snippet"; } | "${SSH[@]}" bash -s -- "$@"
}

# --- (a) local safety checks -------------------------------------------------
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "ABORT: local working tree has uncommitted changes." >&2; exit 1
fi
git fetch -q origin "$BRANCH" || { echo "ABORT: cannot fetch origin/$BRANCH (not pushed?)" >&2; exit 1; }
LOCAL_SHA=$(git rev-parse "$BRANCH")
REMOTE_SHA=$(git rev-parse "origin/$BRANCH")
if [ "$LOCAL_SHA" != "$REMOTE_SHA" ]; then
  echo "ABORT: local $BRANCH ($LOCAL_SHA) != origin/$BRANCH ($REMOTE_SHA). Push first." >&2; exit 1
fi
NEW_SHA=$REMOTE_SHA SHORT=${NEW_SHA:0:7}
echo "Deploying $BRANCH @ $SHORT to $HOST (widget=$WIDGET dry=$DRY)"

# --- (b) widget build --------------------------------------------------------
if [ "$WIDGET" = 1 ]; then
  if [ "$DRY" = 1 ]; then
    echo "[dry-run] (cd www.teampop/frontend && VITE_RELEASE=$SHORT npm run build)"
  else
    ( cd "$ROOT/www.teampop/frontend" && PATH="$HOME/.local/node/bin:$PATH" VITE_RELEASE="$SHORT" npm run build )
    [ -f "$ROOT/www.teampop/frontend/dist/widget.js" ] || { echo "ABORT: widget build produced no dist/widget.js" >&2; exit 1; }
  fi
fi

# --- (c) remote update + restart + health -----------------------------------
STAMP=$(date +%Y%m%d-%H%M%S)
BACKUP="backups/deploy-$STAMP"   # relative to $HOME on the box
read -r -d '' DEPLOY_SNIPPET <<'SNIP' || true
set -euo pipefail
BRANCH=$1 NEW_SHA=$2 BACKUP=$HOME/$3
cd "$REPO"
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then echo "ABORT: box has local changes in $REPO" >&2; exit 10; fi
OLD=$(git rev-parse HEAD)
mkdir -p "$BACKUP"; echo "$OLD" > "$BACKUP/commit.txt"
[ -f "$WIDGET" ] && cp "$WIDGET" "$BACKUP/widget.js"
[ -f "$SEARCH_ENV" ] && cp "$SEARCH_ENV" "$BACKUP/search.env"
[ -f "$ONBOARD_ENV" ] && cp "$ONBOARD_ENV" "$BACKUP/onboarding.env"
echo "OLD_COMMIT=$OLD"
git fetch -q origin "$BRANCH"
git checkout -q "$BRANCH" 2>/dev/null || git checkout -q -b "$BRANCH" "origin/$BRANCH"
if ! git merge-base --is-ancestor HEAD "origin/$BRANCH"; then echo "ABORT: not a fast-forward" >&2; exit 11; fi
fail() { echo "FAILED during deploy; rolling back" >&2; do_rollback "$OLD" "$BACKUP" || echo "ROLLBACK ALSO FAILED - manual intervention needed" >&2; exit 20; }
trap fail ERR
git reset -q --hard "origin/$BRANCH"
[ "$(git rev-parse HEAD)" = "$NEW_SHA" ] || { echo "box HEAD != expected $NEW_SHA" >&2; false; }
if reqs_changed "$OLD" "$NEW_SHA"; then
  echo "requirements changed -> pip install"
  "$REPO/search-service/.venv/bin/pip" install -q -r "$REPO/search-service/requirements.txt"
  "$REPO/onboarding-service/.venv/bin/pip" install -q -r "$REPO/onboarding-service/requirements.txt"
else echo "requirements unchanged"; fi
set_release "${NEW_SHA:0:7}"
restart_and_check
echo "REMOTE_DEPLOY_OK"
SNIP

OLD_COMMIT=""
rollback_all() {
  echo "!!! DEPLOY FAILED - rolling back" >&2
  if [ "$DRY" = 1 ]; then return 0; fi
  if [ -n "$OLD_COMMIT" ]; then
    # shellcheck disable=SC2016  # expanded on the box, not here
    remote 'set -euo pipefail; do_rollback "$1" "$HOME/$2"' "$OLD_COMMIT" "$BACKUP" \
      && echo "Rolled back to $OLD_COMMIT; services healthy." >&2 \
      || echo "ROLLBACK FAILED: manual intervention needed (backup: $BACKUP)" >&2
  fi
}

if [ "$DRY" = 1 ]; then
  remote "$DEPLOY_SNIPPET" "$BRANCH" "$NEW_SHA" "$BACKUP"
else
  OUT=$(mktemp); trap 'rm -f "$OUT"' EXIT
  if ! { cat "$LIB"; echo "$DEPLOY_SNIPPET"; } | "${SSH[@]}" bash -s -- "$BRANCH" "$NEW_SHA" "$BACKUP" 2>&1 | tee "$OUT"; then :; fi
  OLD_COMMIT=$(sed -n 's/^OLD_COMMIT=//p' "$OUT" | head -1)
  if ! grep -q '^REMOTE_DEPLOY_OK' "$OUT"; then
    # remote trap already rolled back for post-reset failures; for earlier aborts nothing changed.
    echo "DEPLOY FAILED (see output above). Remote auto-rollback runs for post-update failures; old commit: ${OLD_COMMIT:-unknown}" >&2
    exit 1
  fi
fi

# --- (d) widget upload (atomic) ---------------------------------------------
if [ "$WIDGET" = 1 ]; then
  W=/home/ubuntu/sales_agent/www.teampop/frontend/dist/widget.js
  if [ "$DRY" = 1 ]; then
    echo "[dry-run] scp widget.js -> $HOST:$W.new && ssh mv -f $W.new $W"
  else
    if scp -i "$SSH_KEY" -q "$ROOT/www.teampop/frontend/dist/widget.js" "$HOST:$W.new" \
       && "${SSH[@]}" "mv -f '$W.new' '$W' && curl -fsS -m 10 -o /dev/null https://api.teampop.com/widget/widget.js"; then
      echo "widget uploaded"
    else
      rollback_all; exit 1
    fi
  fi
fi

# --- (f) summary -------------------------------------------------------------
echo
echo "=== DEPLOY OK ==="
echo "branch:   $BRANCH"
echo "commit:   ${OLD_COMMIT:-<dry-run>} -> $NEW_SHA"
echo "widget:   $([ "$WIDGET" = 1 ] && echo deployed || echo unchanged)"
echo "backup:   ~/backups/deploy-$STAMP (on box)"
echo "duration: $(( $(date +%s) - START ))s"
