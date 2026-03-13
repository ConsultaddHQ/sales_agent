# Getting Started - 5 Minute Demo

Follow these steps to get your first demo running in 5 minutes!

## Step 1: Install Dependencies (2 minutes)

```bash
# Install Python packages
pip install -r requirements.txt

# Verify installation
python --version  # Should be 3.10+
```

## Step 2: Configure Environment (1 minute)

```bash
# Copy example env file
cp .env.example .env

# Edit .env with your Supabase credentials
# Get these from: https://supabase.com/dashboard
nano .env
```

Add your credentials:
```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-role-key-here
```

## Step 3: Run the Workflow (2 minutes)

```bash
# Example with a small e-commerce site
python workflow.py \
    https://example.com/products \
    https://example.com \
    --max-products 50
```

**This will:**
- ✅ Scrape 50 products
- ✅ Download images
- ✅ Create embeddings
- ✅ Store in Supabase
- ✅ Generate demo page
- ✅ Print next steps

## Step 4: Start Services (3 terminals)

**Terminal 1 - Image Server:**
```bash
python image_server.py
```

**Terminal 2 - Search Service:**
```bash
cd search-service
source .venv/bin/activate  # If you have a venv
uvicorn main:app --port 8006
```

**Terminal 3 - Widget (Optional - for development):**
```bash
cd www.teampop/frontend
npm install
npm run dev
```

## Step 5: View Demo

```bash
# In a new terminal
cd demo_pages
python3 -m http.server 8080

# Open browser:
# http://localhost:8080/demo_index.html
```

## 🎉 You're Done!

Your demo is now running! Click the orb on the page to start the AI assistant.

## What's Next?

### For Production:

1. **Deploy Backend Services**
   ```bash
   # See: SETUP_GUIDE.md -> Deployment Options
   # Quick option: Railway
   railway login
   railway init
   railway up
   ```

2. **Deploy Demo Page**
   ```bash
   # Quick option: GitHub Pages
   ./deploy_github.sh
   ```

3. **Custom Domain**
   - Point DNS to your servers
   - Configure CORS
   - Add SSL certificate

### For Customization:

1. **Change Colors/Branding**
   - Edit `www.teampop/frontend/src/components/AvatarWidget.jsx`

2. **Add More Products**
   ```bash
   python universal_scraper.py NEW_URL --max-products 200
   ```

3. **Improve Scraping**
   - Add custom selectors to `universal_scraper.py`
   - Handle site-specific patterns

## Common Issues

**Products not found?**
- Check URL is accessible
- Try different selectors in `universal_scraper.py`
- View page source to find product containers

**Images not loading?**
- Ensure image server is running: `curl http://localhost:8000/health`
- Check CORS settings in `image_server.py`

**Widget not showing?**
- Open browser console (F12)
- Check for JavaScript errors
- Verify widget script URL

## Need Help?

- 📖 Read `SETUP_GUIDE.md` for detailed documentation
- 📋 Check `QUICK_REFERENCE.md` for common commands
- 🐛 See Troubleshooting section in SETUP_GUIDE.md

---

**Happy Building! 🚀**

Next: Read SETUP_GUIDE.md for deployment options and advanced features.
