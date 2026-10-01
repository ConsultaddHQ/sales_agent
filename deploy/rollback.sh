#!/usr/bin/env bash
# Manual rollback on the Lightsail box, run FROM THE DEV MAC.
#   deploy/rollback.sh [<commit>]    (default: commit.txt of the latest ~/backups/deploy-*)
# If no commit is given, the matching backup's widget.js and .env files are restored too.
set -euo pipefail
SSH_KEY=${SSH_KEY:-$HOME/.ssh/teampop-lightsail.pem}
HOST=${HOST:-ubuntu@13.232.36.194}
LIB=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/remote-lib.sh
COMMIT=${1:-}

{ cat "$LIB"; cat <<'SNIP'
set -euo pipefail
COMMIT=${1:-}
B=$(ls -dt "$HOME"/backups/deploy-* 2>/dev/null | head -1 || true)
if [ -z "$COMMIT" ]; then
  [ -n "$B" ] && [ -f "$B/commit.txt" ] || { echo "no backup found and no commit given" >&2; exit 1; }
  COMMIT=$(cat "$B/commit.txt")
  echo "using backup $B"
else
  B=""   # explicit commit: do not restore envs/widget from an unrelated backup
fi
do_rollback "$COMMIT" "$B"
echo "ROLLBACK OK -> $(git -C "$REPO" rev-parse --short HEAD)"
SNIP
} | ssh -i "$SSH_KEY" -o ConnectTimeout=10 "$HOST" bash -s -- "$COMMIT"
