# search-service

Backend API for performing semantic + text search over product data.

**Status:** Beta; service is considered core to the voice agent and used by the frontend
widget.

## Purpose & Responsibilities

- Accept search queries from the Avatar Widget (or any client).
- Compute query embeddings with `all-MiniLM-L6-v2` (same model used by onboarding).
- Call a Supabase RPC (`hybrid_search_products`) that performs a pgvector /
  full-text hybrid search.
- Offload embedding generation and Supabase RPC execution to worker threads so
  concurrent requests do not block the FastAPI event loop.
- Apply request rate limiting to `/search` with `slowapi`.
- Optionally parse a max-price from the query (price parsing is disabled by default).
- Package results into a `SearchResponse` including a simple `pitch` string for
  backward compatibility with older consumers.
- Expose a simple healthcheck.

## Endpoints

- `GET /health` – Returns 200 OK if the service is running.
- `POST /search` – Accepts JSON:
  ```json
  { "store_id": "...", "query": "..." }
  ```
  Responds with a lean list of products (name, price, 200-char blurb, image/product URLs) and a marketing pitch.
- `POST /product-details` – On-demand rich detail for ONE product, called by the ElevenLabs `get_product_details` tool only when the user asks for specifics. Accepts JSON:
  ```json
  { "store_id": "...", "product_id": "..." }
  ```
  Returns `{ product_name, available_options, variants, full_description }` from the product's `metadata` JSONB (sizes, per-variant price/availability/SKU, fabric). 404 if not found; 400 on a bad UUID.

Both POST endpoints require an `X-TeamPop-Secret` header **when `WEBHOOK_SECRET` is set** (the ElevenLabs webhook sends it; the onboarding proxy relays it). Both also accept/echo an `X-Request-ID` for cross-service log correlation.

## Environment

Create a `.env` from `.env.example` with the following vars:

- `SUPABASE_URL` – your Supabase project URL.
- `SUPABASE_KEY` – service-role API key.
- `IMAGE_SERVER_URL` – base URL that serves product images (the tunnel/host pointing at onboarding-service `:8005`, which mounts `/images`). Search composes each result's `image_url` as `{IMAGE_SERVER_URL}/images/{local_image_path}` at query time, so this must be the **current** host. Defaults to `http://localhost:8000` (the legacy standalone image server) — set it explicitly in the single-tunnel setup or product images 404. Re-point it whenever a free ngrok tunnel restarts.
- `OPENROUTER_API_KEY` – legacy key for optional price parsing experiments.
- `OPENROUTER_BASE_URL` – optional custom endpoint.
- `OPENROUTER_MODEL` – model name for completions (default `xai/grok-beta`).
- `SEARCH_RATE_LIMIT` – per-client (IP) limit for the POST endpoints (default `30/minute`). Note: ElevenLabs webhook calls share egress IPs, so this is coarse — true per-store limiting is a tracked follow-up (needs Redis).
- `WEBHOOK_SECRET` – when set, `/search` and `/product-details` require a matching `X-TeamPop-Secret` header. Must equal `WEBHOOK_SECRET` in onboarding-service. Blank = no enforcement (dev/demo).
- `ALLOWED_ORIGINS` – comma-separated CORS allowlist; `*` (default) allows all (dev only). Set real widget/site domains in prod.
- `UVICORN_WORKERS` – worker count for non-reload runs (default `4`).
- `RELOAD` – set `false` to enable multi-worker process mode from `python main.py`.
- `LOG_LEVEL` – `INFO`/`DEBUG`.

## Setup

```bash
cd search-service
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in your values
uvicorn main:app --port 8006 --reload
```

For concurrent production-style local runs:

```bash
cd search-service
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8006 --workers 4
```

## Tests

A hermetic pytest suite lives in `search-service/tests/` (no DB, no model download — Supabase and the embedder are faked). Covers `/health`, `/search` (happy / empty query / bad store_id / no results), `/product-details` (happy / 404 / bad uuid), webhook-secret auth (401 + accept), and `_truncate_for_voice`.

```bash
cd search-service
.venv/bin/pip install -r requirements-dev.txt   # pytest, httpx (one-time)
.venv/bin/python -m pytest -q
```

## Debugging

The service includes a `RequestLoggingMiddleware` that logs every incoming request. Every line is prefixed with a `[request_id]` (read from the incoming `X-Request-ID` or generated, and echoed back in the response header) so a single voice turn can be traced across onboarding-proxy → search-service logs:

```
2026-06-17 ... search-service [a1b2c3d4] - ➡️  POST /search | client=34.59.11.47 | body={"store_id": "...", "query": "..."}
2026-06-17 ... search-service [a1b2c3d4] - 🚫 400: Invalid store_id | store_id='...' (35 chars) | query='...'
2026-06-17 ... search-service [a1b2c3d4] - ⬅️  POST /search → 400
```

Common 400 errors:
- **Invalid store_id**: Not a valid UUID (36 chars). Often caused by ElevenLabs LLM truncating the UUID — fix by setting `store_id` as `value_type: "constant"` in the webhook tool config.
- **Empty query**: Query string is empty or whitespace-only.

Common 429 errors:
- **Rate limit exceeded**: The same client exceeded `SEARCH_RATE_LIMIT`. Raise the limit for trusted internal traffic or put the service behind a proxy that forwards the real client IP.

## Performance / Latency

On startup the service runs a warmup hook (`@app.on_event("startup")`) that pre-loads the `all-MiniLM-L6-v2` embedder and opens the Supabase connection in a worker thread. You should see:

```
🔥 Warmup: loading embedding model...
🔥 Warmup: embedder ready in XXX ms
🔥 Warmup: Supabase connection ready in XXX ms
```

Without this, the first real request of each process pays a 1.5–3 s cold-start cost for the model load. If these lines do not appear, search will be slow on the first user query after each restart.

Every `/search` response carries an `X-Search-Duration-Ms` header measuring embed + Supabase RPC time. The `onboarding-service` proxy (both `/search` and `/product-details`) forwards this header and emits one correlated info log per call (`⏱ {path} proxy | req_id=… | store_id=… | detail=… | search_ms=… | proxy_total_ms=… | status=…`). CORS `expose_headers` includes `X-Search-Duration-Ms` so browser callers can read it too.

The Supabase `hybrid_search_products` function is index-aware as of 2026-04-17 — it uses HNSW via `ORDER BY embedding <=> p_query_embedding LIMIT 50` and a GIN-backed `@@ plainto_tsquery(...)` filter. See `docs/agents/decisions.md` for details. Warm typical search is ~1 s end-to-end; ~50 ms of that is DB compute, the rest is India↔Supabase network. Moving Supabase region or adding a short-TTL result cache in this service are the remaining levers if the network floor needs breaking.

## Notes

- The service assumes the Supabase table has been populated by onboarding-service.
- Response shape may change as features (price filters, pagination) are added.
- The Supabase Python client remains synchronous; concurrency is currently
  handled by FastAPI async endpoints, `asyncio.to_thread()`, and multi-worker
  Uvicorn instead of an async client migration.
- For production use, containerize with Docker and deploy behind a proper API
  gateway or Kubernetes.
- The ElevenLabs agent webhook calls this service via ngrok — the tunnel URL changes on restart and the agent must be re-created.
