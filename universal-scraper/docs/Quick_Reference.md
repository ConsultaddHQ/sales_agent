# AI Shopping Assistant - Quick Reference

## 🚀 One-Liner Setup

```bash
# Complete demo in one command
python workflow.py https://example.com https://example.com --max-products 200
```

## 📝 Common Commands

### Scraping

```bash
# Basic scraping
python universal_scraper.py https://example.com

# With options
python universal_scraper.py https://example.com \
    --max-products 150 \
    --image-server http://localhost:8000

# Large site (filtered page)
python universal_scraper.py "https://amazon.com/s?k=laptops&rh=n:565108" --max-products 200
```

### Services

```bash
# Image server
python image_server.py                              # Port 8000

# Search service
cd search-service && uvicorn main:app --port 8006  # Port 8006

# Widget dev server
cd www.teampop/frontend && npm run dev             # Port 5173

# Demo page server
cd demo_pages && python3 -m http.server 8080       # Port 8080
```

### Demo Page Generation

```bash
# Generate demo
python static_page_generator.py \
    https://example.com \
    $(cat store_id.txt) \
    --widget-script http://localhost:5173/src/main.jsx \
    --search-api http://localhost:8006
```

### Docker

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Rebuild after changes
docker-compose up -d --build
```

### Deployment

```bash
# GitHub Pages
./deploy_github.sh

# Railway
railway login
railway init
railway up

# Check services
curl http://localhost:8000/health  # Image server
curl http://localhost:8006/health  # Search service
```

## 🔍 Debugging

```bash
# Check if products were scraped
cat store_id.txt

# Verify database
# In Supabase dashboard SQL editor:
SELECT count(*) FROM products WHERE store_id = 'YOUR_STORE_ID';
SELECT * FROM products WHERE store_id = 'YOUR_STORE_ID' LIMIT 5;

# Check images
ls -lh product_images/*/

# Test image server
curl http://localhost:8000/images/STORE_ID/FILENAME.jpg

# Test search API
curl -X POST http://localhost:8006/search \
  -H "Content-Type: application/json" \
  -d '{"store_id":"YOUR_STORE_ID","query":"laptop"}'

# Check widget loaded
# In browser console:
window.AVATAR_WIDGET_CONFIG
```

## 📊 Common Issues

| Problem | Solution |
|---------|----------|
| No products found | Add custom selectors to `universal_scraper.py` |
| Images 404 | Check image server running, verify paths |
| Widget not showing | Check browser console, verify script URLs |
| CORS errors | Update `allow_origins` in `image_server.py` |
| Search no results | Verify store_id, check embeddings created |
| Slow scraping | Reduce `--max-products`, check internet speed |

## 🎯 URLs Cheat Sheet

| Service | Local URL | Production |
|---------|-----------|------------|
| Image Server | http://localhost:8000 | https://your-app.railway.app |
| Search API | http://localhost:8006 | https://your-api.railway.app |
| Widget Dev | http://localhost:5173 | https://your-widget.vercel.app |
| Demo Page | http://localhost:8080 | https://your-username.github.io/repo |

## 🔧 Configuration Files

```
.env                    # Environment variables
store_id.txt           # Generated store ID
requirements.txt       # Python dependencies
docker-compose.yml     # Docker services
SETUP_GUIDE.md        # Full documentation
```

## 💡 Pro Tips

```bash
# Scrape multiple categories and merge
python universal_scraper.py URL1 --max-products 100
mv store_id.txt store1.txt
python universal_scraper.py URL2 --max-products 100
mv store_id.txt store2.txt
# Manually merge in database or use different store_ids

# Optimize images after scraping
find product_images -name '*.jpg' -exec jpegoptim --max=85 {} \;

# Backup scraped data
tar -czf backup-$(date +%Y%m%d).tar.gz product_images/ demo_pages/ store_id.txt

# Watch logs in real-time
tail -f scraper.log
```

## 🌐 Example Sites

```bash
# Shopify store
python workflow.py https://shop.example.com https://shop.example.com

# WooCommerce
python workflow.py https://wordpress-shop.com/shop https://wordpress-shop.com

# Custom e-commerce
python workflow.py https://custom-shop.com/products https://custom-shop.com

# Magento
python workflow.py https://magento-shop.com/catalog https://magento-shop.com

# Amazon (filtered)
python workflow.py "https://amazon.com/s?k=electronics" "https://amazon.com"
```

## 🎨 Customization

```bash
# Change widget colors
# Edit: www.teampop/frontend/src/components/AvatarWidget.jsx

# Add custom product selectors
# Edit: universal_scraper.py -> product_selectors

# Modify API responses
# Edit: search-service/main.py

# Customize demo page
# Edit: static_page_generator.py -> _inject_widget()
```

## 📈 Monitoring

```bash
# Check service health
watch -n 5 'curl -s http://localhost:8000/health && curl -s http://localhost:8006/health'

# Monitor image downloads
watch -n 2 'find product_images -type f | wc -l'

# Database size
# In Supabase dashboard:
SELECT pg_size_pretty(pg_database_size('postgres'));
```

## 🆘 Emergency Reset

```bash
# Clear everything and start fresh
rm -rf product_images demo_pages store_id.txt
# Delete products from Supabase dashboard
# Re-run workflow
python workflow.py URL URL
```

---

**Need help?** Check SETUP_GUIDE.md for detailed documentation.
