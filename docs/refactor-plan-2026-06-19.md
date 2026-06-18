# Refactor Plan — 2026-06-19

**Author:** Claude (Sonnet 4.6)  
**Branch:** feature/ui-enhancements-v2  
**Status:** Ready to implement — awaiting approval

---

## Overview

Two targeted performance refactors informed by the perf audit (`docs/perf-audit-2026-06-19.md`).  
No placeholders. Full production-grade rewrites of exactly the listed files.

---

## REFACTOR A — `search-service/main.py`

**Goal:** Add caching, metrics, structured logging, and security hardening  
**Audit findings addressed:** C3 (zero result cache), M5 (no metrics), L4 (log body in INFO), plus production-hardening gaps

### Changes

#### 1. In-process TTL + LRU cache (`_TTLCache`)
- Pure Python class backed by `collections.OrderedDict` + `threading.Lock`
- `maxsize=512`, `ttl=300s`
- Key: `(store_id, normalized_query)` where `normalized_query = " ".join(q.strip().lower().split())`
- Store: `List[ProductOut]` (serialized, ready to return)
- Policy: cache only when `len(products) > 0` — empty results are not cached (re-search on empty is fine)
- Module-level singleton: `_search_cache = _TTLCache(maxsize=512, ttl=300.0)`
- Thread-safe: all `get()`/`set()` wrapped in `threading.Lock`; safe under `asyncio.to_thread()`

#### 2. Metrics (`_Metrics`)
- Pure Python class, `threading.Lock`-protected
- Counters: `search_total`, `search_cache_hits`, `search_errors`
- Latency: `deque(maxlen=1000)` of successful search durations; `snapshot()` computes p50/p95 from sorted copy
- `uptime_seconds` = `time.monotonic() - _SERVICE_START` (module-level timestamp)
- Module-level singleton: `_metrics = _Metrics()`
- No external deps (no Prometheus, no OpenTelemetry — pure Python only)

#### 3. `/metrics` endpoint (GET)
```
GET /metrics → 200 JSON
{
  "search_total": int,
  "search_cache_hits": int,
  "search_errors": int,
  "search_p50_ms": float,
  "search_p95_ms": float,
  "uptime_seconds": float,
  "cache_size": int,
  "cache_max_size": 512,
  "cache_ttl_seconds": 300
}
```
- Not rate-limited (aggregate data only, not sensitive)
- Not auth-gated
- Snapshot is O(N log N) on `_latencies` but N ≤ 1,000 and this endpoint is only hit by monitoring

#### 4. Structured per-request logging (`_log_search_result`)
```python
def _log_search_result(*, request_id, store_id, query, cache_hit, search_ms, result_count, status)
```
Emits one JSON log line per search call:
```
[CACHE HIT] {"request_id":"abc123","store_id":"...","query":"...","cache_hit":true,"search_ms":0.4,"result_count":5,"status":200}
```
- `[CACHE HIT]` prefix on cache hits so they're easily greppable
- `request_id` from `_request_id_ctx` (contextvars — see item 5)
- Called in both cache-hit and cache-miss paths, and in the error path via `finally`

#### 5. Request-ID correlation via `contextvars`
- `_request_id_ctx: ContextVar[str]` — set per request in `RequestLoggingMiddleware`
- Source: `X-Request-ID` header if present, else `uuid4().hex[:12]`
- Injected into every log line via `_RequestIdFilter(logging.Filter)` added to root logger handlers
- Log format: `"%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"`
- Request-ID echoed back as `X-Request-ID` response header

#### 6. `RequestLoggingMiddleware` — body at DEBUG only
- Currently logs body at INFO on every POST/PUT/PATCH (noisy in production)
- New: body preview only when `logger.isEnabledFor(logging.DEBUG)`
- Method/path/status still logged at INFO/WARNING

#### 7. WEBHOOK_SECRET + `_check_webhook_secret` dependency
```python
WEBHOOK_SECRET: str = os.getenv("WEBHOOK_SECRET", "").strip()

def _check_webhook_secret(request: Request) -> None:
    if not WEBHOOK_SECRET:
        return  # no-op in dev/demo
    provided = request.headers.get("X-TeamPop-Secret", "")
    if not hmac.compare_digest(provided.encode(), WEBHOOK_SECRET.encode()):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")
```
- Used as `Depends(_check_webhook_secret)` on `/search` and `/product-details`
- Constant-time comparison (no timing oracle)
- Backwards-compatible: no-op when `WEBHOOK_SECRET` is unset

#### 8. ALLOWED_ORIGINS env-var CORS
```python
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
```
- Replaces hardcoded `allow_origins=["*"]`
- Default `"*"` keeps existing behaviour when env var not set
- Production: set `ALLOWED_ORIGINS=https://yourstore.myshopify.com,https://widget.teampop.co`

#### 9. Input validation → typed HTTP codes
| Condition | Status | Detail |
|---|---|---|
| store_id not valid UUID | 400 | Specific message + truncation hint if 34/35 chars |
| query empty/whitespace | 400 | Clear message |
| query >500 chars | 400 | Via Pydantic `Field(max_length=500)` + exception handler |
| Embedding model failure | 422 | New — currently 500 |
| Embedding/RPC timeout | 503 | Unchanged |
| Supabase unreachable | 503 | Upgraded from 500 |
| Zero results | 200 | Empty `products: []` — not an error |

Pydantic `RequestValidationError` → 400 via:
```python
@app.exception_handler(RequestValidationError)
async def _validation_error_handler(request, exc) -> JSONResponse:
    return JSONResponse(status_code=400, content={"error_code": "validation_error", "details": exc.errors()})
```

#### 10. `/product-details` — Supabase call in `asyncio.to_thread()`
- Currently: blocking `sb.table(...).select(...).execute()` called directly in an `async def` handler (blocks event loop)
- Fix: wrap the Supabase call in a `_fetch()` sync function, called via `await asyncio.to_thread(_fetch)`
- Comment: if a second lookup is ever added, use `asyncio.gather()` on both

#### 11. Startup hook — semaphore initialized in event loop
- Currently `_embedding_semaphore` created lazily on first request (may attach to wrong loop in edge cases)
- Fix: initialize in `@app.on_event("startup")` which runs inside the correct event loop

#### 12. `/search` cache integration (flow)
```
1. Validate store_id (UUID) and query (non-empty, ≤500 chars)
2. Normalize query: " ".join(query.strip().lower().split())
3. Check _search_cache.get((store_id, normalized_query))
   → HIT: log [CACHE HIT], record metrics (cache_hit=True), return immediately
   → MISS: continue to step 4
4. _hybrid_search_products() → embed + RPC
5. Serialize List[ProductOut]
6. If len(serialized) > 0: _search_cache.set(cache_key, serialized)
7. _log_search_result(cache_hit=False, ...)
8. finally: _metrics.record(duration_ms=..., cache_hit=..., error=...)
```

#### Preserved invariants
- `all-MiniLM-L6-v2` model (unchanged)
- `hybrid_search_products` RPC (unchanged)
- `X-Search-Duration-Ms` response header (unchanged)
- slowapi rate limiting on `/search` and `/product-details` (unchanged)
- Embedding semaphore (max 2 concurrent, unchanged)
- Startup warmup (unchanged — just integrated into combined `_on_startup`)
- `_truncate_for_voice` helper (unchanged)
- `SearchRequest`, `ProductOut`, `SearchResponse`, `ProductResult` models (unchanged)
- `_encode_query_embedding`, `_execute_hybrid_search_rpc`, `_hybrid_search_products` (unchanged)

#### Removed
- Large commented-out OpenRouter price-parsing block (lines 226-250 in current file) — removed per audit finding P2.9

---

## REFACTOR B — `onboarding-service/services/products.py` + `onboarding-service/pipeline.py`

**Goal:** Parallel image downloads, batch embedding, step timing, ElevenLabs retry, structured summary  
**Audit findings addressed:** C2 (serial image downloads), C2 (per-product embedding), M1 (no step timing), H2 (no retry on ElevenLabs)

### B1 — `services/products.py`

#### `BuildProductsResult` dataclass (new)
```python
@dataclass
class BuildProductsResult:
    rows: List[ProductRow]
    image_success: int
    image_failed: int
```
Return type of `build_product_rows` (was `List[ProductRow]`).  
`pipeline.py` updated to access `.rows`, `.image_success`, `.image_failed`.

#### `_parse_product_metadata(domain, store_id, product)` helper (new)
Extracts all product fields into a plain dict (no I/O):
```
handle, name, description, price, metadata, image_url, product_url
```
Isolated so Phase 1 (parse) is pure CPU and easily testable.

#### `_download_images_parallel(parsed_products, store_images_dir, max_workers=5)` helper (new)
```python
with ThreadPoolExecutor(max_workers=5, thread_name_prefix="img-dl") as executor:
    results = list(executor.map(_download_one, parsed_products))
return results  # List[Optional[str]] — same order as input
```
- `executor.map()` preserves order, so index N of results corresponds to index N of inputs
- Each `_download_one` calls existing `download_product_image()` which already returns `None` on failure
- `store_images_dir.mkdir(parents=True, exist_ok=True)` called ONCE before the executor (safe under concurrent mkdir due to `exist_ok=True`, but avoids redundant syscalls)
- Max 5 concurrent downloads: 200 products × avg 2s/download → ~80s → ~20s (5× speedup)

#### Refactored `build_product_rows` — 4-phase pipeline
```
Phase 1 (sync, fast):   Parse all products into dicts — no I/O
Phase 2 (CPU):          Batch embed all texts: embedder.encode(all_texts, batch_size=32, normalize_embeddings=True)
Phase 3 (I/O parallel): _download_images_parallel() — ThreadPoolExecutor max 5
Phase 4 (sync, fast):   Assemble ProductRow objects combining phases 1-3
```

**Embedding improvement:** `embedder.encode(list_of_texts)` is 5–15× faster than `embedder.encode(single_text)` per-product in a loop. For 200 products this is the dominant CPU saving.

**Return type change:** returns `BuildProductsResult` instead of `List[ProductRow]`.

**Structured completion log:**
```python
logger.info(json.dumps({
    "event": "build_product_rows_complete",
    "total_products": len(rows),
    "image_success": image_success,
    "image_failed": image_failed,
    "total_ms": total_ms,
}))
```

#### `download_product_image` and `store_products_in_supabase` — unchanged
These functions are correct as-is. No changes.

---

### B2 — `pipeline.py`

#### `_timed_step(step_name)` context manager (new)
```python
@contextmanager
def _timed_step(step_name: str):
    start = time.perf_counter()
    step_info = {}
    try:
        yield step_info          # caller sets step_info["item_count"] = N
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        logger.info(json.dumps({
            "event": "pipeline_step",
            "step": step_name,
            "duration_ms": elapsed_ms,
            "status": "success",
            **({k: v for k, v in step_info.items()}),
        }))
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        logger.error(json.dumps({
            "event": "pipeline_step",
            "step": step_name,
            "duration_ms": elapsed_ms,
            "status": "failed",
            "error": str(exc)[:200],
        }))
        raise
```

Usage in `run()`:
```python
with _timed_step("scrape") as info:
    raw_products = adapter.scrape_products(clean_url, max_products=max_products)
    info["item_count"] = len(raw_products)
```

#### `_create_agent_with_retry(...)` helper (new)
```python
def _create_agent_with_retry(store_id, store_context, search_api_url, tags,
                              max_attempts=3, base_delay=2.0):
    last_exc = None
    for attempt in range(1, max_attempts + 1):
        try:
            return create_agent_for_store(store_id, store_context, search_api_url, tags)
        except Exception as exc:
            last_exc = exc
            if attempt < max_attempts:
                delay = base_delay * (2 ** (attempt - 1))  # 2s, 4s
                logger.warning(f"ElevenLabs attempt {attempt}/{max_attempts} failed: {exc}. Retry in {delay}s")
                time.sleep(delay)
            else:
                logger.error(f"ElevenLabs failed after {max_attempts} attempts: {exc}")
    raise last_exc
```
- Delays: 2s, 4s (then fail)
- `base_delay * (2 ** (attempt-1))` = exponential backoff
- Logs each failed attempt at WARNING; final failure at ERROR
- Wraps the `create_agent_for_store()` call in Step 4 of `run()`

#### Refactored `run()` — per-step timing + hardened errors

```
Step 1: scrape          — _timed_step("scrape"); fail fast → HTTPException(400, NO_PRODUCTS)
Step 2: build_products  — _timed_step("build_products"); returns BuildProductsResult
Step 3: store_supabase  — _timed_step("store_supabase"); passes result.rows
Step 4: create_agent    — _timed_step("create_agent"); uses _create_agent_with_retry
Step 5: test_page       — _timed_step("test_page"); log-and-continue on failure (unchanged)
Step 6: widget_snippet  — unchanged (trivial, no I/O)
```

**Error handling per step:**
- Steps 1–4: raise on failure (pipeline aborts, route handler catches)
- Step 5 (test page): wrap in try/except, log warning, continue with fallback URL
- IMAGE_DOWNLOAD_ERROR: individual image failures already return None — pipeline continues with partial images

**Structured summary log at completion:**
```python
logger.info(json.dumps({
    "event": "onboard_complete",
    "store_url": clean_url,
    "store_id": store_id,
    "product_count": len(build_result.rows),
    "image_success": build_result.image_success,
    "image_failed": build_result.image_failed,
    "agent_id": agent_id,
    "total_ms": total_ms,
    "status": "success" if build_result.image_failed == 0 else "partial",
}))
```

`status`:
- `"success"` — all images downloaded successfully
- `"partial"` — some images failed (products still stored and searchable)
- `"failed"` — not reached here; pipeline raised before this point

#### `run_background()` — update for new return type
```python
result = self.run(scrape_url, store_type=store_type)
sb.table("agent_requests").update({
    "status": "ready",
    "agent_id": result["agent_id"],   # unchanged — result is still success_response dict
    ...
```
`run()` still returns `success_response({...})` dict. No change to `run_background()` except ensuring it unpacks correctly.

#### Preserved invariants
- Adapter registry (unchanged)
- `error_codes.py` usage (unchanged)
- Supabase insert behaviour and `CHUNK_SIZE=100` (unchanged)
- `run_background()` DB update pattern (unchanged)
- Module-level `pipeline = OnboardingPipeline()` singleton (unchanged)

---

## Files to be written

| File | Lines (est.) | Status |
|---|---|---|
| `search-service/main.py` | ~480 | Ready |
| `onboarding-service/services/products.py` | ~210 | Ready |
| `onboarding-service/pipeline.py` | ~180 | Ready |

No other files change. `routes/onboard.py` does not need changes — `pipeline.run()` remains synchronous from the caller's perspective.

---

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| `build_product_rows` return type change breaks callers | Only called from `pipeline.py`. Both files written together. |
| ThreadPoolExecutor for image downloads adds threads | Max 5 workers per onboard call. Bounded and short-lived. |
| `asyncio.Semaphore` not initialized before first request | Moved to `@app.on_event("startup")` in search service. |
| Cache stores stale image URLs if ngrok restarts | IMAGE_SERVER_URL composed at search time from `local_image_path` (already the case). Only affects 5-min TTL window. |
| ElevenLabs retry adds up to 6s on last attempt | This is deliberate — 6s wait beats a permanent failure. Retry is only 3 attempts. |

---

## Not in scope for this refactor

- `onboarding-service/main.py` — proxy header forwarding for WEBHOOK_SECRET
- `routes/onboard.py` — no changes needed
- `routes/admin.py` / `routes/client.py` — separate executor consolidation (roadmap item L2)
- `AvatarWidget.jsx` — currency fix (separate task)
- Merging `production-hardening` branch (separate task)
