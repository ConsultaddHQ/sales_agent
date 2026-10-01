#!/usr/bin/env python3
"""External uptime check for api.teampop.com. Run every 5 min (see .github/workflows/uptime.yml).

Checks GET /health and POST /search (fixed query must return products), measures latency,
and posts to SLACK_WEBHOOK_URL on failure. Exit code 1 on failure.
Env: SLACK_WEBHOOK_URL (optional), BASE_URL (default https://api.teampop.com),
     SLOW_MS (default 4000; slow-but-ok only warns in the log).
"""
import os
import sys
import time

import requests

BASE = os.environ.get("BASE_URL", "https://api.teampop.com").rstrip("/")
SLOW_MS = int(os.environ.get("SLOW_MS", "4000"))
STORE_ID = "9cec7cd0-9252-4aa2-985b-71c2a42018cb"


def check() -> list[str]:
    problems: list[str] = []
    t = time.perf_counter()
    try:
        r = requests.get(f"{BASE}/health", timeout=10)
        ms = (time.perf_counter() - t) * 1000
        print(f"/health {r.status_code} {ms:.0f}ms")
        if r.status_code != 200:
            problems.append(f"/health returned {r.status_code}")
    except requests.RequestException as e:
        problems.append(f"/health unreachable: {type(e).__name__}")

    t = time.perf_counter()
    try:
        r = requests.post(f"{BASE}/search", json={"store_id": STORE_ID, "query": "face wash"}, timeout=15)
        ms = (time.perf_counter() - t) * 1000
        print(f"/search {r.status_code} {ms:.0f}ms")
        if r.status_code != 200:
            problems.append(f"/search returned {r.status_code}")
        else:
            body = r.json()
            products = body.get("products") if isinstance(body, dict) else body
            if not products:
                problems.append("/search returned 200 but no products")
            if ms > SLOW_MS:
                problems.append(f"/search slow: {ms:.0f}ms (> {SLOW_MS}ms)")
    except (requests.RequestException, ValueError) as e:
        problems.append(f"/search failed: {type(e).__name__}")
    return problems


def main() -> int:
    problems = check()
    if not problems:
        print("OK")
        return 0
    msg = ":rotating_light: TeamPop uptime check FAILED: " + "; ".join(problems)
    print(msg, file=sys.stderr)
    hook = os.environ.get("SLACK_WEBHOOK_URL")
    if hook:
        try:
            requests.post(hook, json={"text": msg}, timeout=10)
        except requests.RequestException as e:
            print(f"slack post failed: {e}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
