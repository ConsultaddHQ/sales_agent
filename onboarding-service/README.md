# onboarding-service

Standalone FastAPI microservice to onboard a Shopify store by:
- Fetching up to 500 products from `https://{domain}/products.json`
- Extracting name/description/price/image/product_url
- Downloading first product images to `./images/{store_id}/{handle}.jpg`
- Embedding with `all-MiniLM-L6-v2`
- Inserting into Supabase table `products` (auto-create best-effort)

## Setup

```bash
cd onboarding-service
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env`:
- `SUPABASE_URL`
- `SUPABASE_KEY` (service-role recommended for auto-create)
- `STORE_IMAGES_PATH=./images`

## Run

```bash
uvicorn main:app --reload --port 8005
```

## Test with curl

Health:

```bash
curl -s http://localhost:8005/health
```

Onboard:

```bash
curl -s -X POST http://localhost:8005/onboard \
  -H "Content-Type: application/json" \
  -d '{"url":"example.myshopify.com"}'
```

