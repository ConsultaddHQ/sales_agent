# search-service load test

Measures whether the box can serve N simultaneous voice shoppers on the
latency-critical `/search` path.

## Run

Use the search-service venv (it already has `httpx`):

```bash
# realistic
~/sales_agent/search-service/.venv/bin/python testing/load/loadtest.py \
  --store-id <STORE_UUID> --concurrency 10 --total 200

# stress
~/sales_agent/search-service/.venv/bin/python testing/load/loadtest.py \
  --store-id <STORE_UUID> --concurrency 20 --total 400
```

Watch the box in another shell while it runs:
`free -h` (RAM/swap) and `journalctl -u tp-search -f` (errors).

## Reading the output

- **p95 latency** is the key number — keep it well under ~1000ms so search
  doesn't blow the voice loop. A steep climb from concurrency 10→20 is the
  **1-worker / 2 GB ceiling** → go 4 GB + `UVICORN_WORKERS=2` and/or add the
  search cache (Refactor A).
- **429** = rate limiter (`SEARCH_RATE_LIMIT`, default `600/min` = 10/s **per
  IP**). The test comes from one IP, so sustained >10 req/s will 429 —
  expected, not a failure. For a raw-capacity test, temporarily set
  `SEARCH_RATE_LIMIT=100000/minute`, restart `tp-search`, test, then revert.
- **503** = Supabase RPC timeout under load (watch free-tier connection limits).
- **ReadTimeout / connection errors** = saturation.

Hits real Supabase and burns real compute — keep `--total` modest.
