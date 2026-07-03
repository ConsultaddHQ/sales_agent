#!/usr/bin/env python3
"""Load test for the search-service hot path (/search).

Fires concurrent POST /search requests and reports latency percentiles,
throughput, and status-code distribution — the numbers that tell you
whether the box can serve N simultaneous voice shoppers.

Run with the search-service venv (it already has httpx):

    ~/sales_agent/search-service/.venv/bin/python testing/load/loadtest.py \
        --store-id 9cec7cd0-9252-4aa2-985b-71c2a42018cb --concurrency 10 --total 200

    # stress
    ... --concurrency 20 --total 400

While it runs, watch the box: `free -h` (RAM/swap) and
`journalctl -u tp-search -f` (errors).

Interpreting results:
  * p95 latency is the number that matters — keep it well under ~1000ms so
    search doesn't blow the voice loop. A steep climb from conc 10→20 means
    the 1-worker / 2 GB ceiling → go 4 GB + UVICORN_WORKERS=2 and/or add the
    search cache (Refactor A).
  * 429 = rate limiter (SEARCH_RATE_LIMIT, default 600/min = 10/s PER IP).
    The test comes from one IP, so sustained >10 req/s will 429 — expected,
    not a failure. For raw-capacity tests, temporarily raise SEARCH_RATE_LIMIT
    (e.g. 100000/minute), restart tp-search, test, then set it back.
  * 503 = Supabase RPC timeout under load (watch free-tier connection limits).
  * ReadTimeout / connection errors = saturation.

Note: this hits the REAL Supabase and burns real compute — keep --total modest.
"""

import argparse
import asyncio
import time

import httpx

DEFAULT_QUERIES = [
    "face wash for acne",
    "moisturiser for oily skin",
    "hydrating cleanser",
    "lip balm",
    "something for dry skin",
    "barrier repair moisturiser",
]


async def _one(client: httpx.AsyncClient, url: str, store_id: str, query: str):
    t = time.perf_counter()
    try:
        r = await client.post(url, json={"query": query, "store_id": store_id}, timeout=30)
        return (time.perf_counter() - t) * 1000, r.status_code
    except Exception as e:  # noqa: BLE001 — we want the error class in the tally
        return (time.perf_counter() - t) * 1000, type(e).__name__


async def _run(args) -> None:
    queries = DEFAULT_QUERIES
    sem = asyncio.Semaphore(args.concurrency)

    async with httpx.AsyncClient() as client:
        async def bounded(i: int):
            async with sem:
                return await _one(client, args.url, args.store_id, queries[i % len(queries)])

        t0 = time.perf_counter()
        results = await asyncio.gather(*[bounded(i) for i in range(args.total)])
        wall = time.perf_counter() - t0

    latencies = sorted(r[0] for r in results)
    codes: dict = {}
    for _, code in results:
        codes[code] = codes.get(code, 0) + 1

    def pct(q: float) -> float:
        return latencies[min(int(len(latencies) * q), len(latencies) - 1)]

    print(f"target={args.url}  store_id={args.store_id}")
    print(f"N={args.total}  concurrency={args.concurrency}  wall={wall:.1f}s  throughput={args.total / wall:.1f} req/s")
    print(
        f"latency ms: p50={pct(.50):.0f} p90={pct(.90):.0f} p95={pct(.95):.0f} "
        f"p99={pct(.99):.0f} max={latencies[-1]:.0f}"
    )
    print(f"status: {codes}")


def main() -> None:
    p = argparse.ArgumentParser(description="Load test the search-service /search endpoint.")
    p.add_argument("--url", default="https://api.teampop.com/search", help="Search endpoint URL")
    p.add_argument("--store-id", required=True, help="Store UUID to search against")
    p.add_argument("--concurrency", type=int, default=10, help="Max in-flight requests")
    p.add_argument("--total", type=int, default=200, help="Total requests to send")
    asyncio.run(_run(p.parse_args()))


if __name__ == "__main__":
    main()
