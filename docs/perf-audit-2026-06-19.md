# Performance Audit Report — Team Pop Sales Voice Agent
**Date:** 2026-06-19  
**Auditor:** Principal Software Engineer / Performance Architect  
**Scope:** All three active branches — analytical blueprint only, no code fixes

---

## CRITICAL Issues

### [C1] Onboarding pipeline blocks a FastAPI threadpool worker for 2–10 minutes
**Service:** onboarding-service  
**File:** `routes/onboard.py:24` → `pipeline.py:60–115`  
**Root Cause:** `onboard()` is a synchronous `def` function. FastAPI runs sync handlers in a shared threadpool (default 40 workers). The pipeline calls scrape → image download loop → embedding loop → Supabase batch insert → ElevenLabs API → Playwright test page, all sequentially inside that thread. For a 200-product Shopify store this takes 3–10 minutes. One concurrent onboard occupies one threadpool slot for that entire duration.  
**Impact:** At 3 concurrent onboard calls, 3 of 40 threadpool slots are blocked for minutes. All other synchronous routes (admin, submit-request) share the same pool. Under demo load this is acceptable; at production scale this becomes a request-queuing bottleneck. The much more serious impact is that no parallelism exists within the pipeline itself (see C2).

---

### [C2] Per-product serial image download + embedding — O(N) sequential blocking I/O
**Service:** onboarding-service  
**File:** `services/products.py:86–152` (`build_product_rows`)  
**Root Cause:** The loop at line 87 processes every product one-by-one:
1. `download_product_image()` — blocking `requests.get()` with 15s timeout per image
2. `embedder.encode(text, normalize_embeddings=True)` — synchronous model inference per product

For 200 products at average 2s per image download + 14ms embed = **~400 seconds (6+ minutes)** just for this step. There is no parallelism, no batching.  
**Impact (concrete):**
- Image download at 1s avg × 200 products = 200s
- Embedding at 14ms/call × 200 products = 2.8s (vs ~200ms for a batch call)
- Total step 2 latency: ~200–400s for a typical Shopify store
- **Batching embeddings alone is a 14–20× speedup** (`embedder.encode(list_of_texts)` processes all at once via matrix ops)
- **Parallel image downloads (e.g. `concurrent.futures.ThreadPoolExecutor(max_workers=10)`) would reduce image step from 200s to ~20s**

---

### [C3] Zero caching on the hot voice search path
**Service:** search-service  
**File:** `search-service/main.py:371–432` (`search` endpoint)  
**Root Cause:** Every ElevenLabs user utterance triggers: ElevenLabs → onboarding proxy `/search` → search service → `_encode_query_embedding()` → Supabase `hybrid_search_products` RPC. There is no cache at any layer.  
**Impact (concrete):**
- 10 active sessions, each averaging 1 query/10s = 1 query/second through Supabase
- Queries repeat across sessions: "show me t-shirts", "something blue", "gift ideas" hit the DB identically multiple times per minute
- At SEARCH_RATE_LIMIT of 30/min, a single store at capacity generates 1,800 RPC calls/hour to Supabase
- An in-process LRU cache on `(store_id, normalized_query)` with a 60s TTL would eliminate ~40–60% of RPC calls for typical shopping patterns, cutting 600–1,000ms of latency per cache hit (network floor to Supabase from India is ~1s)
- No warmup needed — same cache already pre-loads the embedder on startup

---

## HIGH Issues

### [H1] Two independent ThreadPoolExecutors — unbounded queue, no backpressure
**Service:** onboarding-service  
**Files:** `routes/client.py:29`, `routes/admin.py:26`  
**Root Cause:** Both route modules create their own `ThreadPoolExecutor(max_workers=4)` at import time. Under concurrent `/submit-request` calls:
- Each call submits 3 tasks (Slack + 2 emails) to the `client.py` executor
- 4 concurrent requests → 12 tasks submitted to a 4-worker pool → 8 tasks queue
- `ThreadPoolExecutor` uses an unbounded internal queue — tasks accumulate silently
- The `admin.py` executor is separate, so a pipeline crash in `run_background()` cannot be observed by the client executor or vice versa  
**Impact:** Under a burst of 8 concurrent `POST /submit-request` calls (realistic on launch), 24 notification tasks queue behind a 4-worker pool. Slack/email latency of 2–5s each means tasks can stay queued for 15–30 seconds. No monitoring. No alerting. No circuit breaker.

---

### [H2] Synchronous `httpx.post()` inside a ThreadPoolExecutor worker
**Service:** onboarding-service  
**File:** `notifications.py:30` (`send_slack_notification`)  
**Root Cause:** `httpx.post(SLACK_WEBHOOK_URL, ...)` at line 30 is the synchronous httpx API — it is a blocking call that holds a threadpool worker for its full duration. If Slack is slow (2–10s) or temporarily unavailable (10–30s wait + retry), all 4 workers in the notification executor can be held.  
**Impact:** 4 slow Slack calls (10s each) block the notification executor for 40 worker-seconds. Subsequent notification tasks for incoming real clients queue silently. Clients receive no acknowledgement email until the backlog clears.

---

### [H3] `send_delivery_email()` called synchronously in the request thread
**Service:** onboarding-service  
**File:** `routes/client.py:93` (`send_agent`)  
**Root Cause:** Unlike the three notification calls in `submit_request()` which go through `_bg_executor.submit()`, `send_delivery_email()` is called directly:
```
send_delivery_email(name=..., email=..., ...)   # blocks here
```
The Resend API call is synchronous and can take 1–5s.  
**Impact:** Admin HTTP request to `POST /send-agent/{id}` is blocked for the duration of the Resend API call. If Resend is degraded, admin UI hangs for 5–30s per send action.

---

### [H4] `switch_agent_model` updates `agent_requests` by unindexed `agent_id`
**Service:** onboarding-service  
**File:** `routes/admin.py:145`  
**Root Cause:** `sb.table("agent_requests").update({...}).eq("agent_id", body.agent_id).execute()`. The `agent_requests` table schema in SHOPIFY_FLOW_COMPLETE.md defines no index on `agent_id` — only the primary key `id`. This query performs a full table scan on every hot-swap.  
**Impact:** Low now (small table), but grows linearly. At 1,000 onboarded agents this is 1,000 row scans per model switch.

---

### [H5] `list_requests` admin route loads unbounded rows
**Service:** onboarding-service  
**File:** `routes/admin.py:58`  
**Root Cause:** `sb.table("agent_requests").select("*").order("created_at", desc=True).execute()` — no `.limit()`. Returns all rows in the table on every admin dashboard load.  
**Impact:** At 500+ agent requests, the response payload grows without bound. Supabase serializes all rows; the Python layer deserializes and re-serializes to JSON. This will cause visible admin dashboard slowness at scale.

---

### [H6] GIN index covers only `name` but production RPC likely queries `name || description`
**Service:** search-service / Supabase  
**File:** `SHOPIFY_FLOW_COMPLETE.md:92`, `decisions.md` (2026-04-17 entry)  
**Root Cause:** The migration in SHOPIFY_FLOW_COMPLETE.md creates:
```sql
create index products_name_gin on public.products 
  using gin(to_tsvector('english', name));
```
But the 2026-04-17 decision documents the updated RPC using a GIN index on:
```sql
to_tsvector('english', coalesce(name,'') || ' ' || coalesce(description,''))
```
If the Supabase production function queries `name || description` but the GIN index is only on `name`, PostgreSQL cannot use the index for the FTS component. It falls back to a sequential tsvector computation on every row.  
**Impact:** The FTS component of hybrid search silently reverts to O(N) scan, losing the benefit of the GIN index. For a 250-product store this adds ~10–50ms; for multi-store deployments sharing one Supabase instance this compounds. **Requires live schema verification via `EXPLAIN ANALYZE` on the actual Supabase instance.**

---

## MEDIUM Issues

### [M1] Supabase singleton is not connection-pool-aware
**Service:** Both services  
**File:** `shared/db.py:13–21`  
**Root Cause:** `get_supabase()` creates one `supabase.Client` (backed by `httpx`) shared across all threads in a process. With 4 Uvicorn workers × multiple concurrent threads in the threadpool, up to 40 threads may share one httpx connection pool. The `supabase-py` client's default httpx pool has `max_connections=100` — adequate for current load but not explicitly configured.  
**Impact:** Not a problem today. Becomes a connection contention point at 50+ concurrent requests if the pool fills and httpx starts queuing internally without surfacing errors.

---

### [M2] Embeddings computed one-by-one instead of as a batch
**Service:** onboarding-service  
**File:** `services/products.py:134`  
**Root Cause:** `embedder.encode(text_to_embed, normalize_embeddings=True)` is called per-product inside the `for` loop. `SentenceTransformer.encode()` accepts a list of strings and processes them as a single matrix operation through the model.  
**Impact:** 200 individual `.encode()` calls vs one `.encode(list_of_200)`:
- Per-call overhead: Python function call + tensor allocation × 200
- Batch: single GPU/CPU kernel invocation for all 200
- Estimated speedup: 5–15× on CPU, 50–100× on GPU
- Practical: from ~2.8s (14ms × 200) to ~200ms for the embedding step

---

### [M3] Re-onboarding a store creates a new store_id with no deduplication
**Service:** onboarding-service  
**File:** `pipeline.py:55`  
**Root Cause:** `store_id = str(uuid.uuid4())` is generated fresh on every `POST /onboard` call. There is no check for an existing store by URL or domain. Re-onboarding accumulates orphaned store records in Supabase (old products, old agent IDs) and creates a new ElevenLabs agent, burning API quota.  
**Impact:** Every re-onboard call (common during testing/demos) inflates the `products` table with duplicate rows under different `store_id` values, adds dead ElevenLabs agents to the account, and wastes the full 3–10 minute pipeline.

---

### [M4] `p_min_score` hardcoded at 0.25 — no env-level tunability
**Service:** search-service  
**File:** `search-service/main.py:259`  
**Root Cause:** `"p_min_score": 0.25` is a hardcoded literal. Changing the similarity threshold requires a code change and redeploy.  
**Impact:** Stores with short product names or unusual vocabulary may silently return 0 results for valid queries because their embeddings cluster at lower cosine similarity. The threshold that works for a fashion store (rich descriptions) may not work for a hardware catalog. No way to tune per-store or via env without a deploy.

---

### [M5] `pipeline.run_background()` has a silent Supabase failure path
**Service:** onboarding-service  
**File:** `pipeline.py:140–146`  
**Root Cause:** The `except` block updates `agent_requests.status = "failed"` with `error_message = str(e)[:500]`. If the Supabase update itself fails (e.g., network partition), the exception is swallowed by the outer `except Exception` without re-raise. The admin dashboard will permanently show the request as `processing`.  
**Impact:** Requests enter a permanently stuck `processing` state. No alerting. Admin must manually diagnose via logs.

---

### [M6] Missing telemetry across the entire voice cycle
**Service:** Both services + Widget  
**Files:** `search-service/main.py` (logging), `onboarding-service/main.py` (proxy log), widget (console only)  
**Root Cause:** The only structured latency signal is `X-Search-Duration-Ms` (search-service) + one proxy log line. The following are completely unobserved:
- **Onboarding pipeline step durations** — which of the 7 steps is the bottleneck per store type?
- **ElevenLabs agent creation success/failure rate** — API errors are logged but not counted
- **Voice cycle p50/p95** — widget latency (`userSpeechAt → productsAt`) is only in browser console logs, never surfaced to a backend metric
- **Embedding batch throughput** — no timing on the onboarding embed step
- **Supabase RPC error rate** — errors are logged but not aggregated
- **Search result count distribution** — how often does search return 0 results vs 5?
- **ThreadPoolExecutor queue depth** — are notification tasks backing up?  
**Impact:** No alerting is possible. Performance regressions go undetected until user complaints.

---

## LOW / Quick Wins

### [L1] `send_delivery_email()` not fire-and-forget — one-line fix
**File:** `routes/client.py:93`  
Wrapping in `_bg_executor.submit(send_delivery_email, ...)` removes 1–5s from the admin `send-agent` response time. No other changes needed.

---

### [L2] Two separate `ThreadPoolExecutor` instances should be one shared module
**Files:** `routes/client.py:29`, `routes/admin.py:26`  
Two executors with `max_workers=4` each = up to 8 background threads serving different parts of the same service. A single shared executor in a common module lets you reason about total background concurrency and apply a unified queue depth limit.

---

### [L3] `IMAGE_SERVER_URL()` called inside the per-product loop
**File:** `services/products.py:84`  
`IMAGE_SERVER_URL()` calls `get_env()` → `os.getenv()` on every iteration. Hoist it above the loop. Zero functional impact but removes 200 redundant env lookups per onboard.

---

### [L4] Request logging middleware logs raw query body at INFO level with no guard
**File:** `search-service/main.py:147`  
The `RequestLoggingMiddleware` logs up to 500 bytes of request body unconditionally at `INFO`. In production this logs every search query in plaintext. Should be gated to `DEBUG` level or omit body in non-debug mode.

---

### [L5] Commented-out 25-line OpenRouter price-parsing block left in search service
**File:** `search-service/main.py:226–250`  
Dead code since the 2026-04-08 decision removed the pitch LLM. `max_price` is always `None`. The block adds confusion for future agents reading the file and makes the surrounding logic harder to follow. Remove or replace with a one-line `# TODO: price parsing` comment.

---

### [L6] `OPENROUTER_API_KEY` in search-service `.env.example` is misleading
**File:** `search-service/.env.example`  
The key is no longer used by the service. New engineers setting up the service will add it unnecessarily. Remove or move to a comment explaining it was removed in 2026-04-08.

---

## Summary Table

| ID | Area | Severity | Estimated Latency / Reliability Impact | Effort to Fix |
|----|------|----------|-----------------------------------------|---------------|
| C1 | Event loop / concurrency | CRITICAL | Ties up 1 threadpool worker per onboard for 3–10 min; no pipeline-level parallelism | Medium (2-3 days) |
| C2 | Pipeline parallelism | CRITICAL | Image download step: 200s serial → ~20s parallel; embed step: 2.8s serial → 200ms batch | Medium (1-2 days) |
| C3 | Caching | CRITICAL | ~1s saved per cache hit; 40–60% RPC call reduction at steady state; 600–1,000ms p50 improvement | Low (4-8 hrs) |
| H1 | ThreadPoolExecutor design | HIGH | Silent queue buildup; notification backpressure under burst | Low (2-4 hrs) |
| H2 | Sync httpx in executor | HIGH | 4 slow Slack calls can saturate notification pool for 40s | Low (1-2 hrs) |
| H3 | Delivery email not async | HIGH | Admin `send-agent` blocks 1–5s per call | Low (15 min) |
| H4 | Unindexed `agent_id` lookup | HIGH | Full table scan on every model switch; grows linearly | Low (30 min) |
| H5 | Unbounded admin list query | HIGH | Unbounded response size; admin dashboard slows at scale | Low (15 min) |
| H6 | GIN index / RPC expression mismatch | HIGH | FTS component silently reverts to sequential scan if mismatch; add 10–50ms per query | Low (verify + 30 min) |
| M1 | Supabase connection pooling | MEDIUM | Latent contention risk at 50+ concurrent requests | Low (1 hr) |
| M2 | Per-product embedding (no batching) | MEDIUM | 5–15× slower than batch encode; 2.8s → 200ms for 200 products | Low (30 min) |
| M3 | No re-onboard deduplication | MEDIUM | Inflated DB, dead ElevenLabs agents, wasted pipeline time on every re-run | Medium (2-4 hrs) |
| M4 | `p_min_score` hardcoded | MEDIUM | Silent zero-result returns on stores with unusual vocabulary; no per-store tunability | Low (15 min) |
| M5 | Silent `processing` stuck state | MEDIUM | Requests get permanently stuck on Supabase update failure; no alerting | Low (1 hr) |
| M6 | Missing telemetry | MEDIUM | No alerting on regressions; no p95 latency visibility; no error rate tracking | High (2-3 days for full OTel) |
| L1 | `send_delivery_email` not async | LOW | 1–5s admin UX improvement | Low (15 min) |
| L2 | Duplicate executor instances | LOW | Reasoning complexity; minor resource waste | Low (30 min) |
| L3 | `IMAGE_SERVER_URL()` in loop | LOW | 200 redundant `os.getenv()` calls per onboard | Low (5 min) |
| L4 | Body logged at INFO unconditionally | LOW | PII leakage risk in production logs | Low (15 min) |
| L5 | Dead OpenRouter code block | LOW | Developer confusion, harder to audit search service | Low (5 min) |
| L6 | Stale `.env.example` entries | LOW | Misleads new engineers on setup | Low (5 min) |

---

## Priority Order for Production Readiness

**Week 1 — Ship without breaking search:**
1. C3 — In-process LRU search cache (biggest latency win, self-contained)
2. L1, H3 — Make all email/notification sends async (prevents admin UI hangs)
3. H1, H2 — Consolidate executors, switch Slack to async httpx
4. H5 — Add `.limit()` to admin list query

**Week 2 — Onboarding pipeline performance:**
5. C2 — Batch embeddings + parallel image downloads
6. M2 — (covered by C2)
7. M3 — URL-based deduplication before pipeline starts
8. M4 — Move `p_min_score` to env var

**Week 3 — Observability foundation:**
9. M6 — Add structured timing to each pipeline step; add search result count to log
10. M5 — Handle nested Supabase failure in `run_background()`
11. H4 — Add `agent_id` index on `agent_requests`
12. H6 — Verify GIN index vs RPC expression via `EXPLAIN ANALYZE` on live Supabase

**Ongoing:**
- L1–L6 — quick cleanup items, any PR
- C1 — refactor `POST /onboard` to fully async with background task (larger rearchitecture, deferred)
