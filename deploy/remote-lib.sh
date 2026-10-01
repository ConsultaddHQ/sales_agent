# shellcheck shell=bash
# Sourced on the Lightsail box by deploy.sh / rollback.sh (sent over ssh stdin).
# Not meant to be run directly.
REPO=/home/ubuntu/sales_agent
WIDGET=$REPO/www.teampop/frontend/dist/widget.js
SEARCH_ENV=$REPO/search-service/.env
ONBOARD_ENV=$REPO/onboarding-service/.env
PUBLIC_URL=https://api.teampop.com/health

wait_health() { # url timeout_s
  local url=$1 limit=$2 t=0
  while [ "$t" -lt "$limit" ]; do
    if curl -fsS -m 5 -o /dev/null "$url" 2>/dev/null; then echo "healthy: $url (${t}s)"; return 0; fi
    sleep 3; t=$((t + 3))
  done
  echo "UNHEALTHY after ${limit}s: $url" >&2; return 1
}

restart_and_check() {
  sudo systemctl restart tp-search
  wait_health "http://localhost:8006/health?deep=1" 120 || return 1
  sudo systemctl restart tp-onboard
  wait_health "http://localhost:8005/health" 60 || return 1
  wait_health "$PUBLIC_URL" 30 || return 1
}

set_release() { # sha
  local f
  for f in "$SEARCH_ENV" "$ONBOARD_ENV"; do
    [ -f "$f" ] || continue
    if grep -q '^RELEASE=' "$f"; then sed -i "s|^RELEASE=.*|RELEASE=$1|" "$f"; else printf '\nRELEASE=%s\n' "$1" >> "$f"; fi
  done
}

restore_backup() { # backup_dir
  local b=$1
  [ -f "$b/search.env" ] && cp "$b/search.env" "$SEARCH_ENV"
  [ -f "$b/onboarding.env" ] && cp "$b/onboarding.env" "$ONBOARD_ENV"
  if [ -f "$b/widget.js" ]; then cp "$b/widget.js" "$WIDGET.rb" && mv -f "$WIDGET.rb" "$WIDGET"; fi
}

do_rollback() { # commit backup_dir
  local commit=$1 b=${2:-}
  echo "ROLLBACK to $commit"
  cd "$REPO" || return 1
  # detach so a branch ref is never dragged backwards; next deploy re-checks-out its branch
  git checkout -q --detach "$commit"
  [ -n "$b" ] && [ -d "$b" ] && restore_backup "$b"
  restart_and_check
}

reqs_changed() { # old new
  ! git -C "$REPO" diff --quiet "$1" "$2" -- 'search-service/requirements*.txt' 'onboarding-service/requirements*.txt' 'shared/requirements*.txt' 2>/dev/null
}
