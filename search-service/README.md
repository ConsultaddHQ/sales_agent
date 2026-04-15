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
  Responds with a list of products and a marketing pitch.

## Environment

Create a `.env` from `.env.example` with the following vars:

- `SUPABASE_URL` – your Supabase project URL.
- `SUPABASE_KEY` – service-role API key.
- `OPENROUTER_API_KEY` – legacy key for optional price parsing experiments.
- `OPENROUTER_BASE_URL` – optional custom endpoint.
- `OPENROUTER_MODEL` – model name for completions (default `xai/grok-beta`).
- `SEARCH_RATE_LIMIT` – per-client limit for `POST /search` (default `30/minute`).
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

## Debugging

The service includes a `RequestLoggingMiddleware` that logs every incoming request:

```
➡️  POST /search | client=34.59.11.47 | body={"store_id": "...", "query": "..."}
🚫 400: Invalid store_id | store_id='...' (35 chars) | query='...'
⬅️  POST /search → 400
```

Common 400 errors:
- **Invalid store_id**: Not a valid UUID (36 chars). Often caused by ElevenLabs LLM truncating the UUID — fix by setting `store_id` as `value_type: "constant"` in the webhook tool config.
- **Empty query**: Query string is empty or whitespace-only.

Common 429 errors:
- **Rate limit exceeded**: The same client exceeded `SEARCH_RATE_LIMIT`. Raise the limit for trusted internal traffic or put the service behind a proxy that forwards the real client IP.

## Notes

- The service assumes the Supabase table has been populated by onboarding-service.
- Response shape may change as features (price filters, pagination) are added.
- The Supabase Python client remains synchronous; concurrency is currently
  handled by FastAPI async endpoints, `asyncio.to_thread()`, and multi-worker
  Uvicorn instead of an async client migration.
- For production use, containerize with Docker and deploy behind a proper API
  gateway or Kubernetes.
- The ElevenLabs agent webhook calls this service via ngrok — the tunnel URL changes on restart and the agent must be re-created.
