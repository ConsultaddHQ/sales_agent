# onboarding-service

**Status:** early‑alpha / proof‑of‑concept

This Python FastAPI microservice is responsible for the first step of the
Team‑Pop pipeline: taking a Shopify‑style store URL and harvesting product
metadata, images, and embeddings for later semantic search. It is invoked
automatically by the dashboard when a user enters their domain.

## Responsibilities

- Crawl a Shopify store's `/products.json` endpoint (up to 500 items).
- Normalize fields: name, description, price, image URL, handle.
- Download the first product image into `./images/{store_id}/{handle}.jpg`.
- Compute sentence embeddings using the `all-MiniLM-L6-v2` model.
- Insert or upsert into a Supabase `products` table, creating it if needed.
- Expose a health check used by the dashboard.

The output becomes the vector store queried by `search-service` and feeds the
Avatar Widget responses.

## Setup & development

```bash
cd onboarding-service
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # populate with your keys
```

### Required environment variables

- `SUPABASE_URL`
- `SUPABASE_KEY` (service-role for automatic schema creation)
- `STORE_IMAGES_PATH` (default `./images`)

Example `.env.example`:

```env
SUPABASE_URL=https://xyz.supabase.co
SUPABASE_KEY=service-role-key
STORE_IMAGES_PATH=./images
```

### Running

```bash
uvicorn main:app --reload --port 8005
```

Endpoints:

- `GET /health` – simple JSON `{\"status\":\"ok\"}`.
- `POST /onboard` – body: `{\"url\":\"example.myshopify.com\"}`.

### Testing

```bash
curl http://localhost:8005/health

curl -X POST http://localhost:8005/onboard \
  -H "Content-Type: application/json" \
  -d '{"url":"example.myshopify.com"}'
```

### Best practices

- Run each service in its own virtual environment.
- Keep sensitive keys out of version control.
- Monitor request rate; Shopify has strict rate limiting.
- Clean up `./images/` periodically to avoid disk bloat.


