# onboarding-service

**Status:** early‑alpha / proof‑of‑concept

This Python FastAPI microservice is responsible for the first step of the
Team‑Pop pipeline: taking a Shopify‑style store URL and harvesting product
metadata, images, and embeddings for later semantic search. It is invoked
automatically by the dashboard when a user enters their domain.

## Responsibilities

- Crawl store products (Shopify via `/products.json`, Threadless via sitemap + Playwright).
- Normalize fields: name, description, price, image URL, handle.
- Download product images into `./images/{store_id}/{handle}.jpg`.
- Compute sentence embeddings using the `all-MiniLM-L6-v2` model.
- Insert into Supabase `products` table.
- Create ElevenLabs conversational AI agent with store-specific context and tools.
- Generate static demo page with injected voice widget.
- Expose a health check used by the dashboard.

The output becomes the vector store queried by `search-service` and feeds the
Avatar Widget responses.

### Supported Store Types

| Store Type | Endpoint | Scraper | Notes |
|-----------|----------|---------|-------|
| Shopify | `POST /onboard` | HTTP fetch `/products.json` | Standard flow |
| Threadless | `POST /onboard-threadless` | Playwright + sitemap XML | Uses `threadless_adapter.py` to normalize data |

## Setup & development

```bash
cd onboarding-service
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # populate with your keys
```

### Required environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SUPABASE_URL` | Yes | — | Supabase project URL |
| `SUPABASE_KEY` | Yes | — | Service-role key (bypasses RLS) |
| `ELEVENLABS_API_KEY` | Yes | — | ElevenLabs API key for agent creation |
| `SEARCH_API_URL` | No | `http://localhost:8006` | Search service URL (use ngrok URL for ElevenLabs webhook) |
| `IMAGE_SERVER_URL` | No | `http://localhost:8000` | Image server URL |
| `WIDGET_SCRIPT_URL` | No | `http://localhost:8005/widget/widget.js` | Built widget.js URL (NOT Vite dev server) |
| `STORE_IMAGES_PATH` | No | `./images` | Directory for downloaded product images |
| `ELEVENLABS_VOICE_ID` | No | `EXAVITQu4vr4xnSDxMaL` | ElevenLabs voice (default: Sarah) |
| `PORT` | No | `8005` | Server port |

### Running

```bash
uvicorn main:app --reload --port 8005
```

Endpoints:

- `GET /health` – simple JSON `{"status":"ok"}`.
- `POST /onboard` – Shopify stores. Body: `{"url":"example.myshopify.com"}`.
- `POST /onboard-threadless` – Threadless artist shops. Body: `{"url":"https://nurdluv.threadless.com"}`.

Both endpoints return:
```json
{
  "success": true,
  "store_id": "uuid",
  "agent_id": "elevenlabs_agent_id",
  "test_url": "/demo/test_xxx.html",
  "widget_snippet": "<script>...</script>",
  "products_count": 66,
  "store_url": "https://..."
}
```

### Testing

```bash
curl http://localhost:8005/health

# Shopify store
curl -X POST http://localhost:8005/onboard \
  -H "Content-Type: application/json" \
  -d '{"url":"example.myshopify.com"}'

# Threadless store
curl -X POST http://localhost:8005/onboard-threadless \
  -H "Content-Type: application/json" \
  -d '{"url":"https://nurdluv.threadless.com"}'
```

### Key files

| File | Purpose |
|------|---------|
| `main.py` | FastAPI app, `/onboard` and `/onboard-threadless` endpoints |
| `threadless_adapter.py` | Normalizes Threadless scraper output to Shopify format, Playwright-based demo page generation |
| `elevenlabs_agent.py` | ElevenLabs agent creation with store context and tools |
| `shopify_validator.py` | Shopify URL validation |
| `error_codes.py` | Structured error responses |

### Best practices

- Run each service in its own virtual environment.
- Keep sensitive keys out of version control.
- Monitor request rate; Shopify has strict rate limiting.
- Clean up `./images/` periodically to avoid disk bloat.


