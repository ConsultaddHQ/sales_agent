# SHOPIFY FLOW - Complete Documentation

## 🎯 Overview

**What This System Does:**
1. Client enters Shopify store URL in dashboard
2. System validates, scrapes products, creates embeddings
3. Auto-creates ElevenLabs conversational agent
4. Generates static test page (clone of client's site + widget)
5. Client tests widget → Copies snippet → Deploys to real site

**Tech Stack:**
- **onboarding-service** (FastAPI, port 8005) - Orchestration
- **search-service** (FastAPI, port 8006) - Product search
- **image-server** (FastAPI, port 8000) - Image serving
- **dashboard** (React, port 5174) - Client interface
- **widget** (React, builds to static) - Voice assistant

---

## 📋 Prerequisites

### 1. Environment Variables

Create `.env` files in each service:

**`onboarding-service/.env`:**
```env
# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-role-key

# ElevenLabs
ELEVENLABS_API_KEY=your-elevenlabs-api-key
ELEVENLABS_VOICE_ID=optional-voice-id

# Service URLs
SEARCH_API_URL=http://localhost:8006
WIDGET_SCRIPT_URL=http://localhost:5173/src/main.jsx
IMAGE_SERVER_URL=http://localhost:8000

# Storage
STORE_IMAGES_PATH=./images

# Logging
LOG_LEVEL=INFO
```

**`search-service/.env`:**
```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-role-key
OPENROUTER_API_KEY=your-openrouter-key
OPENROUTER_MODEL=xai/grok-beta
LOG_LEVEL=INFO
```

**`www.teampop/dashboard/.env`:**
```env
VITE_BACKEND_URL=http://localhost:8005
```

### 2. Supabase Setup

Run this SQL in your Supabase SQL Editor:

```sql
-- Enable vector extension
create extension if not exists vector;

-- Create products table
create table if not exists public.products (
  id uuid primary key default uuid_generate_v4(),
  store_id uuid not null,
  handle text not null,
  name text,
  description text,
  price numeric,
  image_url text,
  product_url text,
  local_image_path text,
  embedding vector(384),
  created_at timestamp default now()
);

-- Indexes
create index if not exists products_store_id_idx on public.products (store_id);
create unique index if not exists products_store_handle_idx on public.products (store_id, handle);
create index if not exists products_embedding_idx on public.products using hnsw (embedding vector_cosine_ops);

-- Full-text search index
create index if not exists products_name_gin on public.products using gin(to_tsvector('english', name));

-- Hybrid search function
create or replace function hybrid_search_products(
  p_store_id uuid,
  p_query text,
  p_query_embedding vector(384),
  p_limit int default 10,
  p_min_score float default 0.25,
  p_max_price numeric default null
)
returns table (
  id uuid,
  name text,
  description text,
  price numeric,
  image_url text,
  product_url text,
  similarity float
)
language plpgsql
as $$
begin
  return query
  select
    p.id,
    p.name,
    p.description,
    p.price,
    p.image_url,
    p.product_url,
    (1 - (p.embedding <=> p_query_embedding)) as similarity
  from products p
  where p.store_id = p_store_id
    and (p_max_price is null or p.price <= p_max_price)
    and (1 - (p.embedding <=> p_query_embedding)) >= p_min_score
  order by similarity desc
  limit p_limit;
end;
$$;
```

---

## 🚀 Local Development Setup

### Step 1: Install Dependencies

```bash
# Onboarding Service
cd onboarding-service
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Search Service
cd ../search-service
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Dashboard
cd ../www.teampop/dashboard
npm install

# Widget Frontend
cd ../frontend
npm install
```

### Step 2: Start All Services

Open **4 terminal windows**:

**Terminal 1 - Onboarding Service (port 8005):**
```bash
cd onboarding-service
source .venv/bin/activate
python main.py
```

**Terminal 2 - Search Service (port 8006):**
```bash
cd search-service
source .venv/bin/activate
uvicorn main:app --port 8006 --reload
```

**Terminal 3 - Image Server (port 8000):**
```bash
python image_server.py
```

**Terminal 4 - Dashboard (port 5174):**
```bash
cd www.teampop/dashboard
npm run dev
```

**Terminal 5 (Optional) - Widget Dev Server (port 5173):**
```bash
cd www.teampop/frontend
npm run dev
```

### Step 3: Verify Services

```bash
# Check all services
curl http://localhost:8005/health  # Onboarding
curl http://localhost:8006/health  # Search
curl http://localhost:8000/health  # Images
```

Visit dashboard: `http://localhost:5174`

---

## 🧪 Testing Flow

### Test Case 1: Happy Path (sensesindia.in)

1. **Open Dashboard**: `http://localhost:5174`

2. **Enter Store URL**: `sensesindia.in`

3. **Expected Flow**:
   ```
   ✅ Validating Shopify store...
   ✅ Scraping products (max 200)...
   ✅ Processing products and downloading images...
   ✅ Storing products in database...
   ✅ Creating ElevenLabs conversational agent...
   ✅ Generating static test page...
   ✅ Your AI Agent is Ready!
   ```

4. **Verify Response**:
   - Store ID (UUID)
   - Agent ID (ElevenLabs ID)
   - Widget snippet (copy button)
   - "Preview Widget" button

5. **Test Widget**:
   - Click "Preview Widget"
   - Should open cloned sensesindia.in with widget
   - Click widget orb
   - Ask: "Show me blue shirts"
   - Should see product carousel

### Test Case 2: Error Scenarios

**A. Not a Shopify Store**
```
Input: google.com
Expected: "This doesn't appear to be a Shopify store"
```

**B. Password-Protected Store**
```
Input: example.myshopify.com (with password)
Expected: "This store is password-protected. Please disable..."
```

**C. Empty Store**
```
Input: shopify-store-with-no-products.myshopify.com
Expected: "No products found in this store"
```

**D. Invalid URL**
```
Input: not-a-real-url
Expected: "Please enter a valid URL"
```

**E. Rate Limited**
```
Expected: Auto-retry with exponential backoff (2s, 4s, 8s)
Should succeed eventually or show: "Rate limited, try again in 2-3 minutes"
```

### Test Case 3: Search Functionality

After successful onboarding:

```bash
# Test search API directly
curl -X POST http://localhost:8006/search \
  -H "Content-Type: application/json" \
  -d '{
    "store_id": "YOUR_STORE_ID_FROM_ONBOARDING",
    "query": "blue shirt"
  }'

# Expected: JSON with products array
```

### Test Case 4: Image Serving

```bash
# List images for store
curl http://localhost:8000/images/YOUR_STORE_ID

# Access specific image
curl http://localhost:8000/images/YOUR_STORE_ID/product-handle.jpg
```

---

## 📊 Monitoring & Debugging

### Check Logs

**Onboarding Service:**
```bash
# Watch logs in real-time
tail -f onboarding-service/logs/*.log

# Check for errors
grep "ERROR" onboarding-service/logs/*.log
```

**Search Service:**
```bash
tail -f search-service/logs/*.log
```

### Database Verification

```sql
-- Check products were stored
SELECT count(*) FROM products WHERE store_id = 'YOUR_STORE_ID';

-- View sample products
SELECT id, name, price, image_url FROM products WHERE store_id = 'YOUR_STORE_ID' LIMIT 5;

-- Check embeddings exist
SELECT count(*) FROM products WHERE store_id = 'YOUR_STORE_ID' AND embedding IS NOT NULL;
```

### Common Issues

| Problem | Solution |
|---------|----------|
| "ELEVENLABS_API_KEY not found" | Add key to onboarding-service/.env |
| "Connection refused" on port 8006 | Start search-service |
| Images returning 404 | Start image-server (port 8000) |
| Widget not loading | Check browser console for errors |
| "Database error" | Verify Supabase credentials |
| Agent creation fails | Check ElevenLabs API key and quota |

---

## 🌐 Production Deployment

### Option 1: Railway (Recommended for Backend)

**Deploy Onboarding Service:**
```bash
cd onboarding-service
railway login
railway init
railway up

# Set environment variables in Railway dashboard
```

**Deploy Search Service:**
```bash
cd search-service
railway init
railway up
```

**Deploy Image Server:**
```bash
railway init
railway up
```

### Option 2: Render.com

Create `render.yaml` in project root:

```yaml
services:
  - type: web
    name: onboarding-service
    env: python
    buildCommand: pip install -r onboarding-service/requirements.txt
    startCommand: cd onboarding-service && uvicorn main:app --host 0.0.0.0 --port $PORT
    
  - type: web
    name: search-service
    env: python
    buildCommand: pip install -r search-service/requirements.txt
    startCommand: cd search-service && uvicorn main:app --host 0.0.0.0 --port $PORT
    
  - type: web
    name: image-server
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: python image_server.py
```

### Option 3: Vercel (Dashboard Only)

```bash
cd www.teampop/dashboard
vercel --prod

# Update .env.production with deployed backend URLs
```

### Environment Variables for Production

Update these in deployed services:

```env
# Onboarding Service
SEARCH_API_URL=https://your-search-service.railway.app
IMAGE_SERVER_URL=https://your-image-server.railway.app
WIDGET_SCRIPT_URL=https://your-widget.vercel.app/widget.js

# Image Server CORS
ALLOWED_ORIGINS=https://your-dashboard.vercel.app,https://your-widget.vercel.app
```

---

## 📝 Widget Integration (Client Side)

After onboarding, client copies this snippet to their Shopify theme:

**Option A: Liquid Template (Recommended)**

Edit `theme.liquid`:

```liquid
<!-- Before </body> -->
<script src="https://your-widget.vercel.app/widget.js"></script>
<script>
  window.AVATAR_WIDGET_CONFIG = {
    agentId: "{{ shop.metafields.teampop.agent_id }}",
    storeId: "{{ shop.metafields.teampop.store_id }}"
  };
</script>
```

**Option B: Shopify Admin (Simple)**

1. Shopify Admin → Online Store → Themes → Edit Code
2. Open `theme.liquid`
3. Paste snippet before `</body>`
4. Save

---

## 🔧 Troubleshooting Production

### Agent Not Responding

1. Check ElevenLabs dashboard - is agent active?
2. Verify search-service is returning results
3. Check browser console for WebSocket errors

### Images Not Loading

1. Verify image-server is running
2. Check CORS headers allow your domain
3. Test image URL directly in browser

### Search Returning No Results

1. Verify store_id matches in database
2. Check embeddings were created
3. Lower `p_min_score` in search function (try 0.15)

---

## 📈 Scaling Considerations

**Current Limits:**
- Max 200 products per store (configurable)
- ElevenLabs Free Tier: 10,000 characters/month
- Supabase Free Tier: 500MB database, 2GB bandwidth

**To Scale:**
- Increase `MAX_PRODUCTS` constant
- Upgrade ElevenLabs plan
- Use CDN for images (Cloudflare, AWS CloudFront)
- Add Redis for caching search results
- Implement background job queue for onboarding

---

## 🎉 Success Metrics

**A successful deployment means:**
- ✅ Store onboards in <60 seconds
- ✅ Agent responds in <2 seconds
- ✅ Search returns relevant results
- ✅ Images load properly
- ✅ Widget works on client's site without conflicts
- ✅ Voice conversation flows naturally

---

## 🆘 Support

**Logs Location:**
- Onboarding: Check Railway/Render dashboard
- Search: Check Railway/Render dashboard
- Widget: Browser console (F12)

**Quick Fixes:**
```bash
# Reset everything locally
rm -rf onboarding-service/images/*
# Delete products from Supabase
# Re-run onboarding
```

**Contact:**
- Check GitHub issues
- Review ElevenLabs documentation
- Verify Supabase status page
