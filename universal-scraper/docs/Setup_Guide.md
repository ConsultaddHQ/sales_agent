# AI Shopping Assistant - Complete Demo Setup

This solution scrapes any e-commerce website, stores products in Supabase, serves images from your own server, and creates a static demo page with an AI shopping assistant widget.

## 📋 Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Components](#components)
- [Deployment Options](#deployment-options)
- [Troubleshooting](#troubleshooting)

## 🎯 Overview

**What this solution does:**

1. **Scrapes products** from any e-commerce site (not just Shopify)
2. **Downloads images** locally and serves them from your server
3. **Stores products** in Supabase with embeddings for AI search
4. **Generates static demo pages** that avoid JS conflicts
5. **Injects AI widget** for voice/chat shopping assistance
6. **Provides multiple hosting options** (local, GitHub Pages, Railway, etc.)

## 🏗️ Architecture

```
┌─────────────────┐
│  Client Website │ ← Scrape products
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌──────────────┐
│ Universal       │────▶│  Supabase    │
│ Scraper         │     │  (Products + │
│                 │     │   Embeddings)│
└────────┬────────┘     └──────────────┘
         │
         │ Downloads images
         ▼
┌─────────────────┐     ┌──────────────┐
│ Local Storage   │────▶│ Image Server │
│ (product_images)│     │ (Port 8000)  │
└─────────────────┘     └──────────────┘
                               │
                               │ Serves images
                               ▼
┌─────────────────┐     ┌──────────────┐
│ Static Demo     │────▶│ Demo Page    │
│ Page Generator  │     │ (Port 8080)  │
└─────────────────┘     └──────┬───────┘
                               │
                               │ Uses widget
                               ▼
                        ┌──────────────┐
                        │ Avatar       │
                        │ Widget       │
                        │ (AI Chat)    │
                        └──────────────┘
```

## 🚀 Quick Start

### Prerequisites

```bash
# Install Python 3.10+
python --version

# Install Node.js 18+ (for widget)
node --version

# Install dependencies
pip install -r requirements.txt
```

### Environment Setup

Create `.env` file:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-role-key
SEARCH_API_URL=http://localhost:8006
WIDGET_SCRIPT_URL=http://localhost:5173/src/main.jsx
```

### One-Command Demo

```bash
# Run complete workflow
python workflow.py \
    https://example.com/products \
    https://example.com \
    --max-products 200
```

This will:
1. Scrape 200 products from the URL
2. Download all images
3. Create embeddings
4. Store in Supabase
5. Generate static demo page
6. Print next steps

### Manual Steps (Detailed Control)

#### Step 1: Scrape Products

```bash
# For small shops (100-200 products on homepage)
python universal_scraper.py https://example.com --max-products 200

# For large shops (use filtered page)
python universal_scraper.py https://amazon.com/s?k=laptops --max-products 150

# With custom image server URL
python universal_scraper.py https://example.com \
    --image-server https://your-domain.com
```

**Output:** 
- `store_id.txt` - Your store ID for next steps
- `product_images/` - Downloaded images organized by store

#### Step 2: Start Services

**Terminal 1 - Image Server:**
```bash
python image_server.py
# Runs on http://localhost:8000
```

**Terminal 2 - Search Service:**
```bash
cd search-service
source .venv/bin/activate
uvicorn main:app --port 8006
```

**Terminal 3 - Widget Frontend:**
```bash
cd www.teampop/frontend
npm install
npm run dev
# Runs on http://localhost:5173
```

#### Step 3: Generate Demo Page

```bash
# Read store_id from file
STORE_ID=$(cat store_id.txt)

# Generate demo page
python static_page_generator.py \
    https://example.com \
    $STORE_ID \
    --widget-script http://localhost:5173/src/main.jsx \
    --search-api http://localhost:8006
```

**Output:** `demo_pages/demo_*.html`

#### Step 4: Serve Demo

```bash
cd demo_pages
python3 -m http.server 8080

# Visit: http://localhost:8080/demo_index.html
```

## 📦 Components

### 1. Universal Scraper (`universal_scraper.py`)

Scrapes ANY e-commerce site (not just Shopify):

**Features:**
- Generic product detection (works on most e-commerce sites)
- Handles multiple HTML patterns
- Downloads images locally
- Creates embeddings with `all-MiniLM-L6-v2`
- Stores in Supabase with vector support

**Usage:**
```bash
python universal_scraper.py <URL> [options]

Options:
  --max-products INT    Max products to scrape (default: 200)
  --image-server URL    Image server URL for replacements
```

**Database Schema:**
```sql
create table products (
  id uuid primary key,
  store_id uuid not null,
  handle text not null,
  name text,
  description text,
  price numeric,
  image_url text,              -- Our server URL
  local_image_path text,        -- Local file path
  product_url text,
  embedding vector(384),
  created_at timestamp default now()
);
```

### 2. Image Server (`image_server.py`)

Serves downloaded product images with CORS:

**Features:**
- FastAPI-based image server
- CORS enabled for cross-origin requests
- Organized by store_id
- Security: prevents path traversal

**Endpoints:**
```
GET /images/{store_id}/{filename}
GET /health
```

**Production Deployment:**
- Update CORS origins in `image_server.py`
- Deploy to Railway/Render/Fly.io
- Use CDN for better performance

### 3. Static Page Generator (`static_page_generator.py`)

Clones client's page and injects widget:

**Why Static?**
- Avoids JS conflicts with client's scripts
- More reliable than dynamic injection
- Easier to debug and modify
- Works offline

**Features:**
- Removes analytics/tracking scripts
- Fixes relative URLs
- Injects widget configuration
- Preserves original styling

**You're absolutely correct about JS conflicts!** If client has heavy JS frameworks or one script fails, it could break widget loading. Static pages solve this.

### 4. Workflow Orchestrator (`workflow.py`)

End-to-end automation:

```bash
python workflow.py <product_url> <demo_url> [options]

Arguments:
  product_url          URL to scrape (homepage or filtered page)
  demo_url            URL to clone for demo (can be same or different)

Options:
  --max-products INT  Max products (default: 200)
  --image-server-port INT  Port for image server
  --image-server-url URL   Public image server URL
```

**Example Use Cases:**

**Case 1: Small Shop (Entire Homepage)**
```bash
python workflow.py \
    https://smallshop.com \
    https://smallshop.com \
    --max-products 200
```

**Case 2: Large Shop (Filtered Page)**
```bash
# Scrape laptops category, demo on homepage
python workflow.py \
    https://amazon.com/s?k=laptops&rh=n:565108 \
    https://amazon.com \
    --max-products 150
```

**Case 3: MediaMarkt (EU)**
```bash
python workflow.py \
    https://www.mediamarkt.de/de/category/_fernseher-47.html \
    https://www.mediamarkt.de \
    --max-products 200
```

## 🚢 Deployment Options

### Option A: Local Testing (Easiest)

**Pros:** Free, immediate, no deployment needed
**Cons:** Not accessible online

```bash
# Start all services locally (see Quick Start)
# Demo accessible at: http://localhost:8080
```

### Option B: GitHub Pages (Free Static Hosting)

**Pros:** Free, easy, permanent URLs
**Cons:** Static only (no backend services)

```bash
# Deploy demo page
./deploy_github.sh

# Follow printed instructions to:
# 1. Create GitHub repo
# 2. Push gh-pages branch
# 3. Enable GitHub Pages in settings
```

**⚠️ Important:** GitHub Pages CANNOT host backend services. You need to host image server and search API elsewhere (see Option C/D).

### Option C: Railway (Backend Services)

**Pros:** Free tier, easy deployment, automatic HTTPS
**Cons:** Limited free hours

**Deploy Image Server:**

1. Install Railway CLI:
```bash
npm install -g @railway/cli
railway login
```

2. Deploy:
```bash
cd /path/to/project
railway init
railway up
```

3. Set environment variables in Railway dashboard:
   - `SUPABASE_URL`
   - `SUPABASE_KEY`

4. Get public URL from Railway dashboard

5. Update demo page with Railway URL:
```bash
python static_page_generator.py \
    https://example.com \
    YOUR_STORE_ID \
    --widget-script https://your-widget-url.vercel.app \
    --search-api https://your-railway-url.railway.app
```

### Option D: Complete Custom Domain Setup

**Requirements:**
- VPS or cloud server (DigitalOcean, AWS, etc.)
- Domain name
- SSL certificate (Let's Encrypt)

**Architecture:**
```
your-domain.com
├── /demo              → Static demo pages (Nginx)
├── /api/search        → Search service (proxy to port 8006)
└── /images            → Image server (proxy to port 8000)
```

**Nginx Configuration:**
```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    # Static demo pages
    location /demo {
        root /var/www;
        index demo_index.html;
    }
    
    # Image server
    location /images {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
    }
    
    # Search API
    location /api/search {
        proxy_pass http://localhost:8006;
        proxy_set_header Host $host;
    }
}
```

**Setup:**
```bash
# 1. Copy files to server
scp -r demo_pages/* user@your-server:/var/www/demo/
scp -r product_images user@your-server:/var/www/images/

# 2. Install dependencies on server
ssh user@your-server
cd /opt/ai-assistant
pip install -r requirements.txt

# 3. Run services with systemd
# See: systemd/ folder for service files

# 4. Configure Nginx (see above)

# 5. Get SSL certificate
sudo certbot --nginx -d your-domain.com
```

### Option E: All-in-One Docker

```dockerfile
# Dockerfile (create this)
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8000 8006

CMD ["sh", "-c", "uvicorn image_server:app --host 0.0.0.0 --port 8000 & cd search-service && uvicorn main:app --host 0.0.0.0 --port 8006"]
```

```bash
# Build and run
docker build -t ai-assistant .
docker run -p 8000:8000 -p 8006:8006 \
    -e SUPABASE_URL=your-url \
    -e SUPABASE_KEY=your-key \
    ai-assistant
```

## 🎛️ Advanced Configuration

### Customizing the Widget

Edit `www.teampop/frontend/src/components/AvatarWidget.jsx`:

```javascript
// Change appearance
const WIDGET_CONFIG = {
  theme: 'dark',  // or 'light'
  position: 'bottom-right',  // or 'bottom-left'
  primaryColor: '#667eea',
  // ...
};
```

### Customizing Scraper

Add custom selectors in `universal_scraper.py`:

```python
# Add site-specific selectors
product_selectors = [
    'div.product-card',  # Your custom selector
    'article[data-product]',
    # ... existing selectors
]
```

### Image Server Customization

Enable CDN, compression, caching:

```python
# image_server.py
from fastapi.responses import Response
from PIL import Image
import io

@app.get("/images/{store_id}/{filename}")
def serve_image_optimized(store_id: str, filename: str, width: int = None):
    # Load image
    img = Image.open(file_path)
    
    # Resize if requested
    if width:
        ratio = width / img.width
        height = int(img.height * ratio)
        img = img.resize((width, height))
    
    # Convert to WebP for better compression
    buffer = io.BytesIO()
    img.save(buffer, format='WEBP', quality=85)
    
    return Response(
        content=buffer.getvalue(),
        media_type='image/webp',
        headers={'Cache-Control': 'max-age=31536000'}
    )
```

## 🐛 Troubleshooting

### Problem: No products scraped

**Solutions:**
1. Check if URL is accessible
2. Try adding custom selectors for the specific site
3. Use browser DevTools to inspect product containers
4. Run with `--max-products 500` to get more attempts

### Problem: Images not loading

**Solutions:**
1. Check image server is running: `curl http://localhost:8000/health`
2. Verify CORS headers in browser DevTools
3. Check image paths in database match file system
4. Try accessing image directly: `http://localhost:8000/images/store-id/image.jpg`

### Problem: Widget not appearing

**Solutions:**
1. Check browser console for errors
2. Verify widget script URL is correct
3. Ensure search API is running
4. Check if `div#avatar-widget-root` exists in DOM
5. Try disabling browser extensions

### Problem: "Module not found" errors

**Solutions:**
```bash
# Reinstall dependencies
pip install --upgrade -r requirements.txt

# For widget
cd www.teampop/frontend
rm -rf node_modules package-lock.json
npm install
```

### Problem: Supabase connection errors

**Solutions:**
1. Verify `SUPABASE_URL` and `SUPABASE_KEY` in `.env`
2. Check key is **service role** key (not anon key)
3. Verify network connectivity
4. Check Supabase project is not paused

### Problem: Search returns no results

**Solutions:**
1. Check products exist: `supabase table products select count(*)`
2. Verify embeddings were created
3. Check store_id matches
4. Try increasing similarity threshold in search service

## 📊 Performance Tips

### For Large Catalogs

```python
# Batch processing
python universal_scraper.py URL --max-products 200

# Then manually scrape more and merge:
python merge_stores.py store1_id store2_id --output new_store_id
```

### Image Optimization

```bash
# Compress images after download
find product_images -name '*.jpg' -exec jpegoptim --size=200k {} \;

# Convert to WebP
find product_images -name '*.jpg' -exec cwebp -q 80 {} -o {}.webp \;
```

### Database Indexing

```sql
-- Add indexes for better performance
create index products_name_gin on products using gin(to_tsvector('english', name));
create index products_price_idx on products(price) where price is not null;
```

## 🎯 Next Steps

1. **Test locally** with the Quick Start guide
2. **Customize** widget appearance for your brand
3. **Deploy** using one of the deployment options
4. **Monitor** performance and user interactions
5. **Scale** by optimizing images and adding caching

## 📝 Notes

- **Free Tier Limits:** Supabase free tier has 500MB database limit
- **Rate Limiting:** Be respectful when scraping, add delays if needed
- **Static Pages:** Perfect for demos, but update them when site changes
- **Security:** Never commit `.env` files to git

## 🤝 Support

For issues or questions:
1. Check this README first
2. Review Troubleshooting section
3. Check browser console and server logs
4. Open an issue with details and logs

---

**Happy Building! 🚀**
