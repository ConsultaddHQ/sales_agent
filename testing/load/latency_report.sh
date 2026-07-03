#!/usr/bin/env bash
# Report search-service latency percentiles from REAL traffic (production logs),
# not load tests. Reads the "Search performance" lines tp-search already emits.
#
# Usage (on the box):
#   ./testing/load/latency_report.sh                 # last 1 hour
#   ./testing/load/latency_report.sh "6 hours ago"
#   ./testing/load/latency_report.sh "2026-07-03 09:00"
#
# Watch p95 of total_ms: if it creeps past ~1500ms in real traffic (and
# queue_wait_ms is a big share of it), the box is starting to queue — that's
# the signal to enable the search cache (Refactor A) / add CPU.

SINCE="${1:-1 hour ago}"
LOG="$(journalctl -u tp-search --since "$SINCE" | grep 'Search performance')"

echo "Window: since \"$SINCE\""
if [ -z "$LOG" ]; then
  echo "No search traffic in this window."
  exit 0
fi

for metric in total_ms queue_wait_ms embedding_ms rpc_ms; do
  echo "$LOG" | grep -oE "${metric}=[0-9]+" | cut -d= -f2 | sort -n | awk -v m="$metric" '
    { a[NR] = $1 }
    END {
      if (NR == 0) { print m ": no data"; }
      else {
        printf "%-15s count=%d  p50=%d  p95=%d  p99=%d  max=%d\n",
          m, NR, a[int(NR*0.5)?int(NR*0.5):1], a[int(NR*0.95)?int(NR*0.95):1], a[int(NR*0.99)?int(NR*0.99):1], a[NR];
      }
    }'
done
