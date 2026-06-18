# Enterprise Architecture Blueprint — Team Pop Sales Voice Agent
**Date:** 2026-06-19  
**Author:** Claude (Sonnet 4.6)  
**Target:** 50–500 simultaneous voice sessions at production quality  
**Stack:** FastAPI + Python · Supabase pgvector · ElevenLabs Conversational AI · React Shadow DOM IIFE widget

---

## 1. STRUCTURAL DECOUPLING — Event-Driven Patterns

### 1a. Async Task Queue for Onboarding Pipeline

#### Current synchronous lifecycle (30–120s blocking)

```
Client
  │
  ▼
POST /onboard
  │  [blocks entire HTTP connection]
  ├─ scrape_products()         5–30s  (I/O, playwright, JS rendering)
  ├─ build_product_rows()     10–60s  (image downloads + embeddings)
  ├─ store_products_in_supabase()  2–8s  (batch inserts)
  ├─ create_agent_for_store()      5–10s (ElevenLabs API)
  └─ generate_test_page()         1–3s  (playwright render)
          │
          ▼
     200 OK {agent_id, store_id, ...}   ← client has been waiting 20–120s
```

**Problems at scale:**
- HTTP timeout risk (client or proxy) above 30s
- Ties up a Uvicorn worker for the full pipeline duration
- One pipeline run at max_workers=4 means 4 simultaneous onboards saturate the service
- No retry if any step fails halfway (no state machine)

#### Recommended async lifecycle (202 + polling/webhook)

```
Client
  │
  ▼
POST /onboard
  │  [<1s — just validate URL + enqueue]
  ├─ validate URL format
  ├─ detect store type
  ├─ create agent_requests row  (status = "pending")
  └─ enqueue task(request_id, url, store_type) → Celery/Redis
          │
          ▼
     202 Accepted {request_id}   ← client gets this in <1s

          ─────────── [async, in Celery worker] ───────────
          │
          ├─ scrape_products()
          ├─ build_product_rows()   [Refactor B — parallel images + batch embed]
          ├─ store_products_in_supabase()
          ├─ create_agent_for_store()  [with retry]
          ├─ generate_test_page()
          └─ UPDATE agent_requests SET status="ready", agent_id=..., store_id=...
                    │
                    ├─ EITHER: client polls GET /onboard/status/{request_id}
                    └─ OR: call webhook_url if merchant provided one in POST body
```

#### Which steps move to the queue

| Step | Move to Queue? | Reason |
|------|---------------|--------|
| URL validation | No (stays sync) | Fast, gives immediate feedback |
| Store type detection | No (stays sync) | Fast, <100ms |
| Scrape products | **Yes** | 5–30s, I/O heavy |
| Build product rows (images + embed) | **Yes** | 10–60s, CPU + I/O heavy |
| Store in Supabase | **Yes** | Depends on step above |
| Create ElevenLabs agent | **Yes** | 5–10s, external API |
| Generate test page | **Yes** | 1–3s |
| Send notifications | **Yes** (separate queue) | I/O, no urgency, retryable |

#### Implementation: Celery vs. BackgroundTasks vs. ARQ

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| **FastAPI BackgroundTasks** | Zero infra, already partially used | Tasks lost on restart, no retry, no visibility, no priority | Not sufficient at scale |
| **Celery + Redis** | Persistent, retry, Flower UI, rate limiting, priority queues, battle-tested | Requires Redis, Celery workers as separate processes | **Recommended** |
| **ARQ** | Asyncio-native, lighter than Celery, simpler config | Smaller ecosystem, no Flower equivalent | Good alternative if team is small |
| **Supabase polling** | No extra infra | Anti-pattern for CPU/I/O-heavy tasks, adds DB load | Avoid |

**Migration path — zero breaking changes:**
1. The existing `run_background(request_id, scrape_url, store_type)` method signature is already a Celery task signature. Convert it: `@celery_app.task(bind=True, max_retries=3)`.
2. The `agent_requests` table and poll endpoint already exist (admin.py).
3. The `POST /onboard` route just changes from `executor.submit(pipeline.run_background, ...)` to `celery_task.apply_async(...)`.
4. No widget changes. No ElevenLabs changes. No DB schema changes.

---

### 1b. Notifications — Queue vs. Fire-and-Forget

#### Current failure mode with ThreadPoolExecutor fire-and-forget

```python
# routes/client.py — current pattern
_bg_executor.submit(send_slack_notification, ...)     # fire-and-forget
_bg_executor.submit(send_client_ack_email, ...)       # fire-and-forget
_bg_executor.submit(send_admin_notification_email, ...)
```

**Failure modes the current approach cannot recover from:**

| Failure | Current behavior | Queue behavior |
|---------|-----------------|----------------|
| Process crash during send | Notification silently lost | Task remains in queue, retried by next worker |
| Resend returns 5xx | Exception logged, notification dropped | Retry with exponential backoff (up to 3x) |
| Slack webhook timeout | Exception logged, Slack not notified | Retry after delay |
| Executor queue full (burst traffic) | New tasks queued in memory; crash → all lost | Persisted in Redis; survive process restart |
| Send fails after multiple retries | No visibility | Dead-letter queue; alert triggerable |

**Silent loss is the core problem.** The merchant ACK email (the most critical notification) can fail after `submit()` returns successfully — the route handler has no way to know.

#### Recommended approach for Team Pop

**Phase 1 (immediate, no extra infra):** Add retry logic inside the notification functions themselves. If `resend.Emails.send()` returns 5xx, catch and retry 3× with `time.sleep(2**attempt)` before the thread exits. This addresses transient failures without needing a queue.

```python
def send_client_ack_email(to_email, store_url, max_retries=3):
    for attempt in range(max_retries):
        try:
            resend.Emails.send(...)
            return
        except Exception as e:
            if attempt == max_retries - 1:
                logger.error(f"ACK email failed after {max_retries} attempts: {e}")
                return
            time.sleep(2 ** attempt)
```

**Phase 2 (with Celery):** Move notifications to a separate low-priority Celery queue. The onboarding task publishes to `notifications` queue on completion; a lightweight worker processes them independently. This gives retry, DLQ, and visibility.

**Note:** `send_delivery_email()` in `routes/client.py:send_agent()` is the most critical fix — it runs **synchronously** in the request thread right now (blocks the HTTP response). This must become fire-and-forget before Phase C. See roadmap item H3.

---

### 1c. Cache Invalidation on Re-Onboard

#### Current store_id strategy (favorable for caching)

Each onboard call generates a **new `store_id`** via `str(uuid.uuid4())`. This means:
- Cache key `(store_id, query)` for the old store_id naturally becomes orphaned after re-onboard
- The new store_id gets a cold cache and builds up its own entries
- **No explicit invalidation needed** for the current re-onboard flow

#### Future state: same store_id update (if implemented)

If we ever add "update existing store" (re-scrape without generating a new store_id), cached results would be stale. The invalidation flow depends on where the cache lives:

**With in-process TTLCache (Refactor A):**
```
Re-onboard completes → pipeline emits STORE_UPDATED event for store_id
  → onboarding-service POSTs to /cache/invalidate/{store_id} on each search-service instance
  → each instance iterates _search_cache._store and deletes keys matching store_id prefix
```
Problem: requires knowing all search-service instance addresses. Brittle at scale.

**With Redis cache (Phase B):**
```
Re-onboard completes
  → redis.delete_pattern(f"search:{store_id}:*")   # one atomic operation
  → all search-service instances see empty cache on next query
```
This is the correct architecture. Redis as the cache store makes invalidation trivial and instance-count-agnostic.

**Recommendation:** Ship Refactor A with in-process TTLCache now (5-minute TTL is acceptable stale window for re-onboard). In Phase B, move to Redis — invalidation becomes a single `DEL` pattern.

---

### 1d. Concurrency Ceiling and Horizontal Scaling Path

#### Current single-node throughput estimate

```
Search request path (cache miss):
  1. Embedding semaphore acquire    (queue wait, ~0ms if not saturated)
  2. embedder.encode() in thread    (~50–100ms, warmed)
  3. Supabase RPC in thread         (~500–1000ms, India → US-East)
  Total: ~600–1100ms per request (cache miss)
  
  Cache hit path: ~1ms
```

With 4 Uvicorn workers, `SEARCH_EMBEDDING_CONCURRENCY=2`:
- 4 workers × 2 semaphore slots = 8 concurrent embedding operations
- Each takes ~75ms → 8/0.075 = **~100 embedding-limited req/s**
- But Supabase is the real bottleneck at 500–1000ms/query: 8 concurrent / 0.75s = **~10 uncached RPC req/s per worker**, **40 total**
- Realistic ceiling without cache: **30–50 req/s**

With 60% cache hit rate (conservative for repeat voice sessions):
- 100 req/s × 60% cache = 60 req/s served in <1ms
- 40 req/s need full search = well within 30–50 req/s ceiling
- **Single node can handle 100 req/s with effective caching**

At 500 sessions × 1 query every 5s = 100 req/s — achievable with one well-cached node.

#### Horizontal scaling path

```
Phase 0 (current):    1 search-service, in-process TTLCache
                      Handles ~100 req/s with cache

Phase E1:             2 search-service instances, shared Redis cache
                      Load balancer (Caddy upstream): round-robin or least-connections
                      Handles ~200 req/s, cache is consistent across instances

Phase E2:             3–4 instances + Supabase read replica
                      Read replica handles search RPC; primary handles onboarding writes
                      Handles ~400 req/s — covers 2000+ concurrent sessions

Phase E3 (if needed): Embedding microservice (1 dedicated GPU instance)
                      search-service becomes thin (cache probe → /embed API → Supabase RPC)
                      Handles ~1000+ req/s
```

**Supabase connection math:**
- Supabase Pro: 25 direct Postgres connections
- With pgBouncer (transaction pooling): 500 logical → 25 real
- 4 workers × 4 nodes = 16 direct connections — fits Pro without pgBouncer
- Enable pgBouncer in Phase E as a precaution (it's a Supabase dashboard toggle)

---

## 2. STATE & STORAGE SCALING

### 2a. Supabase / Postgres / HNSW Scaling Strategy

#### HNSW bottleneck threshold

```
HNSW index stats for all-MiniLM-L6-v2 (384 dimensions):
  Index size:  ~1.5 KB per vector
  1,000 vectors:    1.5 MB  (trivial)
  100,000 vectors: 150 MB   (fits in shared_buffers on Pro)
  1,000,000 vectors: 1.5 GB (exceeds typical shared_buffers → disk I/O on HNSW traversal)

Practical limits on Supabase Pro (shared infra, 1 GB RAM):
  QPS ceiling for vector search: ~50–200 QPS before cache eviction degrades HNSW
  Products per store before performance degrades: ~50,000 vectors
```

**For Team Pop:** 95% of Shopify stores have <5,000 products. The HNSW index for a single store is tiny. The concern is **total vectors across all stores** in the shared `products` table. At 100 stores × 2,000 products avg = 200,000 vectors = 300 MB HNSW index — still fine on Pro.

**When to worry:** >500 stores, or stores with 10k+ products each (large merchants like large apparel brands).

#### Read replica strategy

Add a Supabase read replica (available on Pro/Team tiers) when:
- Onboarding bulk inserts (10k+ rows per session) cause measurable p95 degradation on `/search`
- Monitor: compare `search_p95_ms` from the `/metrics` endpoint during vs. between onboarding runs

For current scale: **not needed**. The write load (onboarding) is infrequent relative to search reads.

#### Dedicated vector DB (Pinecone / Weaviate)

| Criteria | Keep in Supabase | Move to Dedicated Vector DB |
|----------|-----------------|----------------------------|
| Total vectors | <1M | >1M |
| Vector search QPS | <200 | >200 uncached |
| Hybrid search needed | ✅ Stay — HNSW+FTS in one RPC is gold | ❌ Must merge results in app code |
| Operational complexity | Low | High |
| Cost | Included in Supabase Pro | $70–$700/month additional |

**Recommendation:** Stay in Supabase until 1M+ vectors or sustained >200 QPS on vector search. The `hybrid_search_products` RPC that combines pgvector + FTS in one call is a key competitive advantage — splitting it across two systems requires application-level merging, loses the single-pass relevance scoring, and adds latency.

**If you must move:** Weaviate self-hosted on Fly.io is the lowest-cost path. Keep Postgres for `products` metadata and `agent_requests`; store only (embedding, store_id, product_id) in Weaviate. Modify `_execute_hybrid_search_rpc` to fan out to both and merge results.

---

### 2b. Image Storage Migration to Object Storage

#### Current architecture (breaks horizontal scaling)

```
onboarding-service → writes JPEG to /images/{store_id}/{handle}.jpg (local disk)
image_server.py → serves from same local disk
search-service → composes URL: IMAGE_SERVER_URL() + "/images/" + local_image_path
widget → <img src={image_url}> from the search response
```

**Problem:** When search-service scales to multiple instances or moves to a different machine, the images are not accessible. Image server is a single point of failure.

#### Migration path to Cloudflare R2 (recommended)

**Zero code change in search-service.** Only `IMAGE_SERVER_URL` changes.

**Step 1: Modify `download_product_image()` in `services/products.py`**
```python
# Current: saves to local disk
img.save(filepath, format="JPEG", ...)
return filename

# New: upload to R2 and return the same filename (key)
import boto3  # boto3 works with R2 via S3-compatible API
s3 = boto3.client("s3", endpoint_url=R2_ENDPOINT, aws_access_key_id=R2_KEY, ...)
img_buffer = io.BytesIO()
img.save(img_buffer, format="JPEG", ...)
s3.put_object(Bucket=R2_BUCKET, Key=f"{store_id}/{filename}",
              Body=img_buffer.getvalue(), ContentType="image/jpeg",
              CacheControl="public, max-age=31536000, immutable")
return filename  # unchanged — still just "{handle}.jpg"
```

**Step 2: Update env vars**
```bash
# Before
IMAGE_SERVER_URL=https://abc123.ngrok.io

# After  
IMAGE_SERVER_URL=https://pub-xxx.r2.dev   # R2 public bucket URL
# OR (with custom domain + Cloudflare CDN)
IMAGE_SERVER_URL=https://cdn.teampop.co
```

**Step 3: The search-service pattern auto-adapts**
```python
# This line in search-service works unchanged:
local_image_url = f"{IMAGE_SERVER_URL()}/images/{local_path}"
# → becomes: https://cdn.teampop.co/images/{store_id}/{handle}.jpg
```

**`local_image_path` in DB stays as a relative path** (`{store_id}/{handle}.jpg`) — no DB migration needed.

#### CDN strategy for India (30ms target)

```
Cloudflare R2 (US-East storage)
    │
    └─► Cloudflare CDN (globally distributed PoPs)
            ├─ Mumbai PoP    → 20–30ms for Indian users (cache hit)
            ├─ Singapore PoP → 30–50ms (cache hit)
            └─ US-East PoP  → origin 
```

**Cache headers for product images:**
```http
Cache-Control: public, max-age=31536000, immutable
```
Images are keyed by `{store_id}/{handle}.jpg`. Since `handle` is the Shopify product slug (stable), the URL doesn't change when product details change. Images are effectively immutable CDN assets. When a store re-onboards, new images upload under the same key (overwrite) and the CDN key remains the same — use `Cache-Control: public, max-age=86400` (1 day) if image updates are possible.

**R2 vs. S3 + CloudFront:**
| | Cloudflare R2 + CDN | AWS S3 + CloudFront |
|---|---|---|
| Egress cost | **Free** (zero egress from R2) | $0.085/GB (India is expensive) |
| India CDN PoPs | Mumbai, Chennai, Hyderabad | Mumbai, Hyderabad |
| Setup complexity | Low | Medium |
| Boto3 compatible | ✅ (S3-compatible API) | ✅ |
| Recommendation | ✅ **R2** (free egress is significant) | If already on AWS |

---

### 2c. Embedding Model: Singleton vs. Dedicated Microservice

#### Current singleton pattern analysis

```python
# shared/embeddings.py
os.environ["OMP_NUM_THREADS"] = "1"  # prevents model from spinning multiple threads
os.environ["MKL_NUM_THREADS"] = "1"
_embedder: Optional[SentenceTransformer] = None
_lock = threading.Lock()

def get_embedder() -> SentenceTransformer:
    global _embedder
    if _embedder is None:
        with _lock:
            if _embedder is None:
                _embedder = SentenceTransformer(EMBEDDING_MODEL)
    return _embedder
```

**Key insight:** `OMP_NUM_THREADS=1` means the model uses only 1 CPU thread per inference. This prevents CPU thrashing under concurrent calls. But multiple `encode()` calls from different Python threads are serialized through the GIL during Python-heavy portions. For pure CPU math (NumPy/PyTorch), the GIL is released → true parallelism.

**For concurrent onboarding (10 stores simultaneously):**
- Refactor B adds batch embedding: 1 `encode(list)` call per store per onboard
- 10 concurrent batch calls: each is ~2–5s on CPU (200 products)
- Without semaphore in onboarding-service: CPU contest between 10 workers
- With `OMP_NUM_THREADS=1`: each thread uses 1 CPU core → 10 threads × 1 core = OK on multi-core servers, but on a 2-core VM this becomes 5× context switching
- **Add a semaphore in onboarding-service** (`MAX_CONCURRENT_EMBEDS = 2`) to bound this, similar to search-service

#### Dedicated embedding microservice: when it's worth it

| Scenario | Singleton | Microservice |
|----------|-----------|-------------|
| <5 concurrent onboardings/day | ✅ sufficient | Overkill |
| 10+ simultaneous onboardings | Degrades | ✅ isolates CPU |
| GPU acceleration needed | Not possible per-process | ✅ GPU service |
| Memory cost matters | Each process: 90MB | One process: 90MB shared |
| Network overhead concerns | None | 1–5ms per call (local), 10–20ms (cross-AZ) |

**Architecture for a dedicated embedding service:**
```
POST /embed
Body: {"texts": ["blue shoes", "red dress"], "normalize": true}
Response: {"embeddings": [[0.1, 0.2, ...], [0.3, 0.4, ...]]}

- Single FastAPI process with all-MiniLM-L6-v2 loaded once
- Semaphore(4) for concurrent batch calls
- Optional: ONNX Runtime instead of PyTorch → 3–5× CPU speedup
- Optional: GPU → 50–100× speedup (justified at 50+ onboardings/hour)
```

**Recommendation:** Keep singleton until experiencing CPU saturation on >5 simultaneous onboardings. When splitting: use ONNX Runtime (not PyTorch) for CPU deployments — it eliminates the PyTorch overhead and gives 3–5× speedup without GPU cost.

---

## 3. NETWORK & EDGE OPTIMIZATION

### 3a. Extra Network Hop (ElevenLabs → Proxy → Search-Service)

#### Current flow and latency breakdown

```
ElevenLabs (US/EU servers)
    │  HTTPS webhook call (~300ms RTT to India)
    ▼
onboarding-service /search proxy (India / same machine)
    │  HTTP localhost call (~0.1ms)
    ▼
search-service /search (India / same machine)
    │  asyncio.to_thread — embed + Supabase RPC (~700ms)
    ▼
search-service response → proxy → ElevenLabs

Total: ~1000ms. ElevenLabs hard limit: 5000ms.
```

**The proxy adds ~0.1ms on localhost (negligible).** But it creates two problems at scale:
1. **Single point of failure:** if onboarding-service crashes (deploy, OOM), all voice sessions lose search
2. **Resource coupling:** onboarding-service handles both scraping (CPU/I/O heavy) and search proxy (latency-sensitive) in the same process pool

#### Recommended fix: API gateway eliminates the proxy hop

```
Production target architecture:

ElevenLabs
    │  HTTPS
    ▼
[API Gateway — Caddy / Nginx / Kong]
    ├─ /api/search/* → search-service:8006
    ├─ /api/onboard/* → onboarding-service:8005
    ├─ /widget/* → R2/CDN (static)
    └─ /images/* → R2/CDN (static)
```

The `/search` proxy in `onboarding-service/main.py` (the `httpx.AsyncClient` proxy) can be **removed entirely**. ElevenLabs webhook URL in each agent is updated to point to `https://api.teampop.co/api/search` (the gateway route, not the proxy).

**Migration:** When re-onboarding a store after the gateway is live, the new `SEARCH_API_URL` is used (it's just an env var). Old agents continue using the proxy URL until re-onboarded. Zero-downtime migration.

**Why not Cloudflare Workers as the edge proxy?**
- Workers add ~1ms globally (sub-millisecond PoP RTT)
- Can inject WEBHOOK_SECRET header transparently (secret stays in Workers secrets, not visible to client)
- Useful if services are deployed in different clouds (Routes traffic between GCP search + Railway onboarding)
- Overkill if both services are on the same host or same cloud — use Caddy instead

---

### 3b. Production Reverse Proxy and Cloud Deployment

#### Self-hosted (single VPS: DigitalOcean, Hetzner, etc.)

```
Internet → Caddy (port 443, automatic TLS via Let's Encrypt)
              │
              ├─ api.teampop.co/search, /product-details, /metrics → :8006 (search-service)
              ├─ api.teampop.co/onboard, /admin, /client → :8005 (onboarding-service)
              ├─ api.teampop.co/widget/* → Cloudflare R2 (redirect or proxy)
              └─ api.teampop.co/images/* → Cloudflare R2 (redirect or proxy)
```

**Caddyfile (example):**
```
api.teampop.co {
    handle /search* {
        reverse_proxy localhost:8006
    }
    handle /product-details* {
        reverse_proxy localhost:8006
    }
    handle /metrics* {
        # Restrict to internal IPs or Grafana only
        @internal remote_ip 10.0.0.0/8
        handle @internal { reverse_proxy localhost:8006 }
        respond 403
    }
    handle * {
        reverse_proxy localhost:8005
    }
}
```

Caddy auto-renews TLS, handles HTTP/2, and supports automatic gzip. Zero config for basic use.

#### Cloud deployment (recommended: Fly.io)

```
fly.toml (search-service):
  app = "teampop-search"
  [env]
    PORT = "8006"
  [[services]]
    internal_port = 8006
    min_machines_running = 2   ← always-warm, no cold start
  [mounts]                     ← no disk mount needed (stateless)

fly.toml (onboarding-service):
  app = "teampop-onboard"
  [env]
    PORT = "8005"
  [[services]]
    internal_port = 8005
    min_machines_running = 1
  [[mounts]]                   ← mount for images/ (until R2 migration)
    source = "images_volume"
    destination = "/app/images"
```

**Fly.io advantages for Team Pop:**
- Singapore region (`sin`) — ~50ms from India (vs. US-East ~300ms). Deploy search-service here.
- Private networking between apps (no public hop between onboarding proxy and search)
- Built-in load balancing with multiple replicas
- `fly secrets set SUPABASE_KEY=...` — secrets management without `.env` files

**Monolith vs. two containers vs. more:**
- **Two containers** is the right answer: search-service and onboarding-service
- Do NOT merge them — they have different scaling needs (search scales horizontally, onboarding scales vertically for CPU)
- Shared code in `shared/` is not a third container — it's a Python package installed in both (`pip install -e ./shared` or direct path)
- When adding Celery (Phase C): add a **third container** for the Celery worker, sharing the same onboarding codebase but starting with `celery -A tasks worker` instead of uvicorn

**Where Cloudflare CDN fits:**
```
Cloudflare CDN layer (in front of everything):
  cdn.teampop.co → R2 bucket (images)
  widget.teampop.co → R2 bucket (widget.js)
  api.teampop.co → Fly.io apps (API calls — NOT cached, pass-through with DDoS protection)
```

Never put API calls behind CDN caching. CDN caching is only for static assets (widget.js, images).

---

### 3c. Widget Serving — Production-Grade Distribution

#### Current (problematic for scale)

Widget IIFE built by Vite → bundled into `www.teampop/frontend/dist/widget.js` → served by onboarding-service at `/widget/widget.js`.

**Problems:**
- Widget file co-located with a Python API service — unnecessary coupling
- No content-addressable versioning (browser caches stale widget on deploy)
- Cache-Control: none (or whatever FastAPI defaults to for StaticFiles)

#### Production widget distribution

```
Deploy pipeline:
  npm run build  →  dist/widget.{GIT_SHA[:8]}.js  (content-addressable)
                 →  upload to R2: /widget/widget.{SHA}.js
                 →  update WIDGET_SCRIPT_URL env var in onboarding-service

Merchant script tag (in ElevenLabs agent widget_snippet):
  <script src="https://widget.teampop.co/widget.v1.2.3.js"></script>
```

**Cache-Control strategy:**
```http
# For versioned files (widget.v1.2.3.js or widget.abc12345.js):
Cache-Control: public, max-age=31536000, immutable
# → Cached for 1 year. New deploy = new URL. Old URL still works for active sessions.

# For a "latest" alias (widget.latest.js) if you want to support it:
Cache-Control: public, max-age=3600, stale-while-revalidate=86400
# → Revalidated hourly, served stale for up to 1 day during revalidation
```

**Recommendation:** Use content-addressable versioning (`widget.{GIT_SHA[:8]}.js`). The `WIDGET_SCRIPT_URL()` function already makes this configurable. Merchants who never re-onboard continue using their script tag unchanged (it works forever from CDN). Merchants who re-onboard get the newest URL in their snippet.

**`<team-pop-agent>` custom element interface is an invariant** — it must NOT change across widget versions. The widget can change internally; the tag name and its attributes are the merchant-facing public API.

---

### 3d. ElevenLabs WebSocket Latency from India — Actionable Savings

**Baseline:** ~1000ms round-trip. ElevenLabs US-East → India TCP RTT = ~300–350ms (irreducible). Total voice cycle: STT (~200ms) + LLM (~400ms) + TTS first chunk (~200ms) = ~1000ms.

#### Things we control

**1. TTS model: `eleven_flash_v2_5` (save ~150–200ms)**
- Standard/multilingual TTS: ~300ms first audio chunk
- Flash TTS (`eleven_flash_v2_5`): ~75ms first audio chunk
- The agent prompt currently sets the voice; the TTS model is set in ElevenLabs agent config
- Check `elevenlabs_agent.py` for `tts` config block; set `model_id: "eleven_flash_v2_5"`

**2. `optimize_streaming_latency = 4` (save ~50–100ms)**
- ElevenLabs agent API parameter, range 0–4
- 4 = maximum latency optimization (slight quality reduction acceptable for voice commerce)
- Set in agent creation payload in `elevenlabs_agent.py`

**3. Connection pre-warming on page load (save ~200–400ms on first utterance)**
```jsx
// AvatarWidget.jsx — current: WebSocket created on mic click
// Proposed: create WebSocket on page load (invisible pre-warm)

useEffect(() => {
    // Pre-warm WebSocket on mount — don't start conversation yet
    const ws = new WebSocket(ELEVENLABS_WS_URL);
    ws.onopen = () => setPrewarmed(true);
    // Hold ws reference; pass to conversation.startSession() on mic click
}, []);
```
- TLS handshake (~150ms) + WebSocket upgrade (~50ms) = ~200ms saved on first click
- Connection kept alive (WebSocket ping/keepalive) until 30s inactivity timeout

**4. `turn_detection.threshold` tuning (save ~100–200ms per turn)**
- Lower VAD silence threshold = agent responds faster after user stops speaking
- Risk: false triggers on breath sounds
- Current widget has `USER_INACTIVITY_TIMEOUT_MS` and VAD settings — experiment with reducing end-of-speech silence by 100ms

**5. Reduced search RPC latency via Singapore deployment (save ~300ms)**
- If search-service is deployed on Fly.io Singapore (`sin` region), ElevenLabs webhook to search-service has ~100ms RTT instead of ~400ms (India → US-East)
- This is the highest-impact change and doesn't require any code changes — it's a deployment target change

#### Total achievable savings

| Optimization | Savings | Effort |
|---|---|---|
| Fly.io Singapore for search-service | ~300ms | Low (deploy config) |
| `eleven_flash_v2_5` TTS model | ~150ms | Low (agent config) |
| Connection pre-warming on page load | ~200ms | Medium (widget change) |
| `optimize_streaming_latency=4` | ~75ms | Low (agent creation param) |
| VAD threshold tuning | ~100ms | Medium (A/B test needed) |
| **Total** | **~825ms** | |

A voice cycle of ~200ms (from 1000ms) is competitive with native shopping assistant apps.

---

## 4. MIGRATION ROADMAP — Zero-Downtime Path

### Guiding principles

1. **Observability before optimization** — you can't measure improvement without baselines
2. **Cache before scale** — caching fixes 80% of throughput problems for 20% of the work
3. **Preserve all invariants** at every phase gate before proceeding
4. **Each phase is independently rollback-able** — no phase requires re-doing previous phases to undo

### Invariants that must never break across all phases

| Invariant | Risk area | Guard |
|-----------|-----------|-------|
| `all-MiniLM-L6-v2` (384-dim) | Phase C (Celery worker embed), Phase E (embedding service) | `EMBEDDING_MODEL` constant in `shared/config.py` — never change without full re-embed migration |
| `hybrid_search_products` RPC signature | Phase B (Redis cache), Phase E (read replica) | Never change RPC without updating search-service in the same deploy |
| ElevenLabs tool names (`search_products`, `get_product_details`, `update_products`, `update_carousel_main_view`) | Every phase | Tool names are the contract with ElevenLabs — stored in agent config. Change = re-push all agents |
| `store_id` as UUID constant in webhook | Every phase | `constant_value` in ElevenLabs tool config. Never switch to `llm_prompt` |
| `<team-pop-agent>` custom element API | Phase D (widget CDN), Phase F | Widget tag name and attributes are merchant-facing — semver-bump required for any breaking change |
| IIFE widget build (not ESM/CJS) | Phase D | Vite build must stay `lib.formats: ['iife']`. Shadow DOM + CSP require IIFE |

---

### Phase 0 — Pre-Refactor (Immediate, Current Sprint)

**Includes:**
- Refactor A: `search-service/main.py` — in-process TTLCache, /metrics, structured logging, WEBHOOK_SECRET, ALLOWED_ORIGINS, request-ID
- Refactor B: `services/products.py` + `pipeline.py` — parallel image downloads, batch embedding, step timing, ElevenLabs retry

**Validation gate:**
- `/metrics` returns `search_p50_ms`, `search_p95_ms`, `uptime_seconds`
- Second identical search query logs `[CACHE HIT]` in search-service
- Onboarding log contains `pipeline_step` JSON lines with `duration_ms`
- Onboarding log contains `onboard_complete` summary with `image_success`, `image_failed`

**Rollback:** git revert — no infra changes, no DB changes

**Invariants verified:** all-MiniLM-L6-v2 unchanged, hybrid_search_products unchanged, tool names unchanged

---

### Phase A — Observability (Week 1–2)

**Includes:**
- Add OpenTelemetry tracing to `search-service/main.py` — spans for embedding, RPC, cache probe
- Prometheus scrape endpoint at `/metrics` (already included in Refactor A — upgrade to Prometheus-compatible format with `prometheus-client` library if Grafana integration needed)
- Structured log shipping to Loki (free, works with Grafana Cloud free tier) or Papertrail
- Create Grafana dashboard: p50/p95/p99 search latency, cache hit rate, error rate, active Supabase connections
- Alert thresholds: p95 search > 2000ms, error rate > 1%, cache hit rate < 40%

**Validation gate:**
- Grafana shows live p50, p95, cache hit rate per endpoint
- Alert fires correctly on simulated error (wrong WEBHOOK_SECRET)
- Log search in Loki by request_id traces a single voice turn end-to-end

**Rollback:** Remove OTel instrumentation, revert `/metrics` to simple version — no functional change

**Invariants:** All unchanged. Phase A touches logging/metrics only.

---

### Phase B — Caching Layer (Week 2–3)

**Includes:**
- Deploy Redis (Fly.io Redis add-on, or Upstash Redis for serverless)
- Migrate in-process `_TTLCache` to Redis (`redis.asyncio` client):
  - Key: `search:v1:{store_id}:{sha256(normalized_query)[:16]}`
  - TTL: 300s
  - Value: JSON-serialized `List[ProductOut]`
  - Cache invalidation: `DEL search:v1:{store_id}:*` on re-onboard completion
- Cache session state (conversation context) in Redis if ElevenLabs session state is needed between calls (currently stateless — not needed yet)
- Fix `send_delivery_email()` to be fire-and-forget (H3 roadmap item)
- Add LIMIT to admin list query (H5)

**Validation gate:**
- Cache hit rate >60% on a 10-minute voice session simulation
- Eviction and TTL expiry work correctly (check Redis MONITOR)
- Two search-service instances share the same Redis cache (test: query on instance 1, observe cache hit on instance 2)
- p95 search latency <500ms under 50 req/s load test (wrk or locust)

**Rollback:** Set `CACHE_BACKEND=memory` env var to fall back to in-process cache; Redis becomes unused

**Invariants:** hybrid_search_products unchanged. Cache is a read-through layer — Supabase is still source of truth.

---

### Phase C — Async Onboarding (Week 3–5)

**Includes:**
- Add Redis (if not already done in Phase B) — shared with cache
- Convert `pipeline.run_background()` to a Celery task (`@celery_app.task(bind=True, max_retries=3)`)
- `POST /onboard` returns 202 + `request_id` immediately (no more 30-120s block)
- `GET /onboard/status/{request_id}` polls `agent_requests` table (already exists)
- Optional: webhook callback field in `POST /onboard` body — pipeline POSTs to `callback_url` on completion
- Move notification functions to a separate `notifications` Celery queue with retry
- Unify the two separate `ThreadPoolExecutor` instances in admin.py and client.py (L2 roadmap item)
- Deploy Flower (Celery monitoring UI) for task visibility

**Validation gate:**
- `POST /onboard` responds in <1s with 202
- `GET /onboard/status/{id}` transitions: pending → in_progress → ready
- Failed onboard (bad URL) sets status = "failed" with error_message
- Celery worker handles 5 simultaneous onboarding tasks without OOM
- Flower shows task history and retry counts

**Rollback:** Set `ASYNC_ONBOARD=false` env var to route back to synchronous pipeline.run(). Celery worker can be stopped without affecting synchronous path.

**Invariants:** adapter registry unchanged, error_codes.py unchanged, all-MiniLM-L6-v2 unchanged. agent_requests table schema unchanged.

---

### Phase D — Storage Migration (Week 4–6)

**Includes:**
- Create Cloudflare R2 bucket for product images
- Modify `download_product_image()` to upload to R2 via boto3 (S3-compatible)
- Update `IMAGE_SERVER_URL` to R2 public URL or `https://cdn.teampop.co`
- Configure Cloudflare CDN in front of R2 (Cache-Control: immutable for product images)
- Move widget.js build to R2/CDN:
  - Update deploy script to upload `dist/widget.{GIT_SHA}.js` to R2
  - Update `WIDGET_SCRIPT_URL` to CDN URL
  - Remove widget static serving from onboarding-service
- Remove local image serving (image_server.py) after all existing stores re-onboard
  - For existing stores: keep image_server.py running in parallel until they re-onboard (or batch-migrate existing images to R2)

**Validation gate:**
- New onboard: images load from CDN (verify with `curl -I` on image URL — `cf-cache-status: HIT`)
- India CDN latency: image load <50ms from Mumbai (use Pingdom or GTmetrix from India PoP)
- Widget loads from CDN: widget.js cache-control is `public, max-age=31536000, immutable`
- Existing stores (old local images) still work during transition

**Rollback:** Set `IMAGE_STORAGE=local` env var to fall back to local disk. R2 bucket contents remain for re-migration.

**Invariants:** `local_image_path` column format unchanged (`{store_id}/{handle}.jpg`). IMAGE_SERVER_URL() pattern unchanged. IIFE widget build unchanged (only hosting changes).

---

### Phase E — Horizontal Scaling (Week 6–8)

**Includes:**
- Deploy 2nd search-service instance (Fly.io: scale to 2 replicas)
- Enable Supabase pgBouncer (transaction pooling) — dashboard toggle
- Load balancer: Fly.io built-in proxy (round-robin) or Caddy upstream if self-hosted
- Deploy search-service in Singapore region (Fly.io `sin`) — biggest latency win (~300ms)
- Enable Supabase read replica for search path (if write contention measured in Phase A metrics)
- Add onboarding-service embedding semaphore (`MAX_CONCURRENT_EMBEDS=2`) to prevent CPU thrash
- Scale Celery workers to 2 processes for concurrent onboarding

**Validation gate:**
- 100 req/s sustained load test (locust): p95 <800ms, error rate <0.1%
- Cache hit rate >60% under realistic load (not synthetic — varies by query diversity)
- Supabase connection count <25 across all workers (check Supabase dashboard)
- Singapore deployment: search webhook latency from ElevenLabs <400ms (vs. current ~1000ms)
- Failover test: kill one search-service instance, load balancer routes to the other, no errors

**Rollback:** Scale back to 1 replica; revert to US region if Singapore causes issues. All changes are deployment-level, not code-level.

**Invariants:** HNSW+GIN indexes unchanged (read replica has same indexes). store_id UUID unchanged. all-MiniLM-L6-v2 unchanged across all instances.

---

### Phase F — Production Hardening Completion (Week 7–10)

**Includes:**
- Merge `production-hardening` branch: WEBHOOK_SECRET, ALLOWED_ORIGINS, contextvars request-ID, test suite, `max_duration_seconds=300`
- JWT admin auth (replace X-Admin-Password header)
  - `python-jose` + HS256; tokens issued by `/admin/auth` with password verification
  - Token expiry: 8 hours; refresh via `/admin/refresh`
- Rate limiting on all endpoints:
  - `/onboard`: 5/hour per IP (expensive, scrape-heavy)
  - `/submit-request`: 10/hour per IP (email quota)
  - `/search`, `/product-details`: already rate-limited (30/minute); adjust for production
- Circuit breakers on external calls:
  - ElevenLabs API: `tenacity` with `stop_after_attempt(3)` + `wait_exponential(multiplier=1, min=4, max=10)` (already in Refactor B; verify in place)
  - Supabase: already has timeout + HTTPException pattern; add `tenacity` for transient 5xx
  - Resend/Slack: add retry in notification functions (from Phase 1b above)
- `agent_requests.agent_id` DB index (H4)
- TTS model upgrade to `eleven_flash_v2_5` and `optimize_streaming_latency=4` in ElevenLabs agent config
- Widget connection pre-warming on page load

**Validation gate:**
- All `search-service/tests/` pass (from production-hardening test suite)
- `/admin/*` returns 401 without valid JWT
- `/onboard` rate limit fires correctly at 6th request/hour
- Circuit breaker test: mock ElevenLabs 5xx → 3 retries → graceful failure with ELEVENLABS_ERROR code
- p50 voice cycle latency <700ms (vs. current ~1000ms) in India load test

**Rollback:** JWT auth can be reverted to X-Admin-Password by reverting the admin route file. Other hardening changes are additive and do not break existing behavior.

**Invariants:** tool names unchanged, store_id constant unchanged, IIFE widget unchanged, HNSW+GIN unchanged. The test suite from production-hardening actively verifies these invariants on every deploy.

---

## Architecture Summary: Alpha → Enterprise

```
ALPHA (today)                          ENTERPRISE (Phase F)
─────────────────────────────────────  ──────────────────────────────────────────────
Single ngrok tunnel                →   Cloudflare CDN + Fly.io multi-region
Blocking /onboard (20-120s)        →   Async Celery + 202 Accepted (<1s)
In-process TTLCache (one worker)   →   Redis shared cache (all workers, all nodes)
Local disk images                  →   Cloudflare R2 + CDN (30ms India)
Widget from Python service         →   R2/CDN (immutable cache headers)
Proxy hop (onboard → search)       →   API gateway → search-service directly
Single search-service instance     →   2-4 replicas, Singapore PoP, load balanced
No metrics                         →   Grafana + OpenTelemetry + alerts
No retry (ElevenLabs)              →   Exponential backoff (3 attempts)
Plaintext X-Admin-Password         →   JWT + token expiry
No rate limiting on /onboard       →   5/hour per IP (slowapi)
fire-and-forget notifications      →   Celery notifications queue with retry + DLQ
~1000ms voice cycle (India)        →   ~200ms voice cycle (flash TTS + Singapore + prewarm)
```
