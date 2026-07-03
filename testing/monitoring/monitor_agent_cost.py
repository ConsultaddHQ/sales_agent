#!/usr/bin/env python3
"""Per-agent cost/usage alert for ONE ElevenLabs agent — no workspace/billing access needed.

Workspace spend caps are admin-only. This instead polls YOUR agent's own
conversations (GET /v1/convai/conversations?agent_id=...), sums call minutes over
a window, and alerts if it crosses a minute budget you set. Needs only your API key.

Env:
  ELEVENLABS_API_KEY    (required)  your key
  ELEVENLABS_AGENT_ID   (required)  e.g. agent_8601kwjyfh6mffbvht8yrs7bym4v
  BUDGET_MINUTES        (default 250)  alert threshold for the window
  SINCE                 month | 24h | 7d  (default month)  window start
  SLACK_WEBHOOK_URL     (optional)  if set, posts the alert there

Cost note: ElevenLabs Agents overage is ~$0.08/min; est_cost = minutes * 0.08 is
shown for reference (actual billing depends on your plan's included minutes).

Exit code 1 when over budget → cron/email can catch it. Run hourly/daily via cron.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

API = "https://api.elevenlabs.io/v1/convai/conversations"
OVERAGE_PER_MIN = 0.08


def _cfg(name, required=False, default=None):
    v = os.getenv(name, default)
    if required and not v:
        sys.exit(f"Missing required env var: {name}")
    return v


def _get(url, key):
    req = urllib.request.Request(url, headers={"xi-api-key": key})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _window_start(since: str) -> int:
    now = datetime.now(timezone.utc)
    if since == "month":
        return int(datetime(now.year, now.month, 1, tzinfo=timezone.utc).timestamp())
    if since.endswith("h"):
        return int(now.timestamp()) - int(since[:-1]) * 3600
    if since.endswith("d"):
        return int(now.timestamp()) - int(since[:-1]) * 86400
    return int(since)  # raw unix


def main() -> None:
    key = _cfg("ELEVENLABS_API_KEY", required=True)
    agent = _cfg("ELEVENLABS_AGENT_ID", required=True)
    budget = float(_cfg("BUDGET_MINUTES", default="250"))
    since = _cfg("SINCE", default="month")
    slack = _cfg("SLACK_WEBHOOK_URL")
    start = _window_start(since)

    total_secs, count, cursor = 0, 0, None
    while True:
        q = {"agent_id": agent, "call_start_after_unix": start, "page_size": 100}
        if cursor:
            q["cursor"] = cursor
        data = _get(f"{API}?{urllib.parse.urlencode(q)}", key)
        for c in data.get("conversations", []):
            total_secs += c.get("call_duration_secs") or 0
            count += 1
        cursor = data.get("next_cursor")
        if not data.get("has_more") or not cursor:
            break

    minutes = total_secs / 60.0
    est_cost = minutes * OVERAGE_PER_MIN
    msg = (
        f"Agent {agent}: {count} conversations, {minutes:.1f} min since {since} "
        f"(~${est_cost:.2f} at ${OVERAGE_PER_MIN}/min). Budget: {budget:.0f} min."
    )
    print(msg)

    if minutes >= budget:
        alert = f"⚠️ ElevenLabs cost alert — {msg}"
        if slack:
            body = json.dumps({"text": alert}).encode()
            req = urllib.request.Request(
                slack, data=body, headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=15)
        print(alert, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
