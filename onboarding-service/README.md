# onboarding-service

**Status:** early-alpha / proof-of-concept

This Python FastAPI microservice handles the full onboarding pipeline: taking any
e-commerce store URL and harvesting product metadata, images, and embeddings for
later semantic search. It uses a plug-and-play adapter system so new store types
can be added with a single class.

## Architecture

```
main.py              # App setup, CORS, route wiring (~80 lines)
pipeline.py          # Unified 7-step onboarding flow
adapters/            # Plug-and-play store adapters
  base.py            # StoreAdapter ABC
  registry.py        # Adapter lookup + auto-detection
  shopify.py         # Shopify /products.json API
  threadless.py      # Threadless sitemap + Playwright
  supermicro.py      # Supermicro internal JSON API
  universal.py       # Catch-all: 6-tier scraping fallback chain
routes/              # API endpoints
  onboard.py         # POST /onboard (unified) + legacy aliases
  admin.py           # Admin dashboard endpoints
  client.py          # Public client submission + delivery
services/            # Business logic
  products.py        # Build rows, download images, store in Supabase
  test_page.py       # Generate demo pages with widget injected
  agent_creator.py   # ElevenLabs agent creation
scraping/            # Universal extraction strategies
  platform_detect.py # Platform fingerprinting (WooCommerce, Magento, etc.)
  renderer.py        # Playwright headless rendering
  llm_fallback.py    # LLM-based extraction (last resort)
  extractors/
    json_ld.py       # JSON-LD @type:Product extraction
    open_graph.py    # Open Graph meta tag extraction
    microdata.py     # Schema.org itemprop extraction
    sitemap.py       # Sitemap.xml product URL discovery
    platform_selectors.py  # WooCommerce/Magento/PrestaShop/OpenCart CSS selectors
```

## Supported Store Types

| Store Type | Adapter | Method | Notes |
|-----------|---------|--------|-------|
| Shopify | `ShopifyAdapter` | `/products.json` API | Auto-detected via `myshopify.com` domain |
| Threadless | `ThreadlessAdapter` | Sitemap XML + Playwright | Auto-detected via `threadless.com` |
| Supermicro | `SupermicroAdapter` | Internal JSON API + Playwright | Auto-detected via `supermicro.com` |
| Any other | `UniversalAdapter` | 6-tier fallback chain | JSON-LD > microdata > platform CSS > Playwright > sitemap > LLM |

### Adding a new store type

```python
# 1. Create adapters/woocommerce.py
class WooCommerceAdapter(StoreAdapter):
    store_type = "woocommerce"
    def matches_url(self, url): ...
    def scrape_products(self, url, max_products): ...
    def extract_store_context(self, products, domain): ...

# 2. Register in adapters/__init__.py
register(WooCommerceAdapter())
# Done. No new endpoints or pipeline changes needed.
```

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
| `WIDGET_SCRIPT_URL` | No | `http://localhost:5173/widget.js` | Built widget.js URL |
| `STORE_IMAGES_PATH` | No | `./images` | Directory for downloaded product images |
| `ELEVENLABS_VOICE_ID` | No | `EXAVITQu4vr4xnSDxMaL` | ElevenLabs voice (default: Sarah) |
| `ADMIN_PASSWORD` | No | `changeme` | Admin dashboard password |
| `RESEND_API_KEY` | No | — | Resend email API key |
| `SLACK_WEBHOOK_URL` | No | — | Slack incoming webhook for notifications |
| `PORT` | No | `8005` | Server port |

### Running

```bash
uvicorn main:app --reload --port 8005
```

## Endpoints

### Onboarding

- `POST /onboard` — Unified endpoint for all store types. Body: `{"url": "...", "store_type": "auto"}`. Auto-detects platform or specify: `shopify`, `threadless`, `supermicro`, `universal`.
- `POST /onboard-threadless` — Legacy alias, delegates to `/onboard` with `store_type=threadless`.
- `POST /onboard-supermicro` — Legacy alias, delegates to `/onboard` with `store_type=supermicro`.

### Client acquisition

- `POST /api/submit-request` — Public: submit interest form (triggers Slack + email).
- `POST /api/admin/login` — Validate admin password.
- `GET /api/requests` — Admin: list all client requests.
- `POST /api/process-request/{id}` — Admin: start onboarding pipeline.
- `POST /api/update-request/{id}` — Admin: update request metadata.
- `POST /api/send-agent/{id}` — Admin: send delivery email with test link.

### Other

- `GET /health` — Health check.

All onboarding endpoints return:
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

## Testing

```bash
curl http://localhost:8005/health

# Shopify store (auto-detected)
curl -X POST http://localhost:8005/onboard \
  -H "Content-Type: application/json" \
  -d '{"url":"example.myshopify.com"}'

# Any e-commerce site (universal fallback)
curl -X POST http://localhost:8005/onboard \
  -H "Content-Type: application/json" \
  -d '{"url":"https://some-woocommerce-store.com", "store_type":"universal"}'
```

## Key files

| File | Purpose |
|------|---------|
| `main.py` | App setup, CORS, route wiring |
| `pipeline.py` | Unified 7-step onboarding flow |
| `adapters/base.py` | StoreAdapter ABC — implement this to add store types |
| `adapters/registry.py` | Adapter lookup + URL-based auto-detection |
| `adapters/universal.py` | Catch-all adapter with 6-tier extraction fallback |
| `scraping/platform_detect.py` | Platform fingerprinting from headers + HTML |
| `elevenlabs_agent.py` | ElevenLabs agent creation |
| `shopify_validator.py` | Shopify URL validation |
| `error_codes.py` | Structured error responses |

## Best practices

- Run each service in its own virtual environment.
- Keep sensitive keys out of version control.
- Monitor request rate; Shopify has strict rate limiting.
- Clean up `./images/` periodically to avoid disk bloat.
