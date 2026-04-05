"""
TeamPop Onboarding Service - Complete Shopify Flow
Handles: Validation → Scraping → Embeddings → Agent Creation → Test Page
"""

import io
import json
import logging
import os
import re
import uuid
import subprocess
import sys
from dataclasses import dataclass, asdict
from decimal import Decimal, InvalidOperation
from html import unescape
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse
from datetime import datetime

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from PIL import Image
from sentence_transformers import SentenceTransformer
from supabase import Client, create_client
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import httpx
from bs4 import BeautifulSoup

# Import our custom modules
from shopify_validator import validate_shopify_store
from error_codes import ErrorCodes, get_error_response, success_response
from elevenlabs_agent import create_agent_for_store
from threadless_adapter import (
    scrape_threadless_store,
    extract_threadless_store_context,
    generate_threadless_test_page,
)
from supermicro_adapter import (
    scrape_supermicro_store,
    extract_supermicro_store_context,
    generate_supermicro_test_page,
)

# Setup logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("onboarding-service")

# Load environment
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# FastAPI app
app = FastAPI(title="TeamPop Onboarding Service", version="2.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve built widget.js from frontend dist
WIDGET_DIST_DIR = Path(__file__).parent.parent / "www.teampop" / "frontend" / "dist"
if WIDGET_DIST_DIR.exists():
    app.mount("/widget", StaticFiles(directory=str(WIDGET_DIST_DIR)), name="widget")
    logger.info(f"✅ Widget served from: {WIDGET_DIST_DIR}")
else:
    logger.warning(f"⚠️ Widget dist not found at {WIDGET_DIST_DIR} — run npm run build in frontend/")

# Serve generated demo pages
app.mount("/demo", StaticFiles(directory="demo_pages", html=True), name="demo")

# Models
class OnboardRequest(BaseModel):
    url: str = Field(..., examples=["sensesindia.in", "https://example.myshopify.com"])

@dataclass(frozen=True)
class ProductRow:
    id: str
    store_id: str
    name: str
    description: str
    price: Optional[Decimal]
    image_url: Optional[str]
    product_url: str
    local_image_path: Optional[str]
    embedding: List[float]
    handle: str
    created_at: datetime

# Global state
_model: Optional[SentenceTransformer] = None
_supabase: Optional[Client] = None
_schema_ensured: bool = False

# Constants
MAX_PRODUCTS = 200  # Maximum products to scrape per store
IMAGE_DOWNLOAD_TIMEOUT = 15  # seconds


def get_supabase() -> Client:
    """Get or create Supabase client"""
    global _supabase
    if _supabase is not None:
        return _supabase
    
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    
    if not url or not key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_KEY environment variables")
    
    _supabase = create_client(url.rstrip("/"), key)
    return _supabase


def get_embedder() -> SentenceTransformer:
    """Get or load embedding model"""
    global _model
    if _model is None:
        logger.info("🔄 Loading embedding model all-MiniLM-L6-v2...")
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("✅ Model loaded")
    return _model


def fetch_shopify_products(
    domain: str,
    max_products: int = MAX_PRODUCTS
) -> List[Dict[str, Any]]:
    """
    Fetch products from Shopify /products.json with pagination and rate limiting
    
    Args:
        domain: Clean domain (e.g., sensesindia.in)
        max_products: Maximum products to fetch
    
    Returns:
        List of raw product dictionaries
    
    Raises:
        Exception on failure
    """
    products: List[Dict[str, Any]] = []
    page = 1
    session = requests.Session()
    headers = {"User-Agent": "TeamPop-Onboarding/2.0"}
    
    # Retry configuration for rate limiting
    max_retries = 3
    retry_delay = 2  # seconds
    
    logger.info(f"📥 Fetching products from {domain} (max: {max_products})")
    
    while len(products) < max_products:
        url = f"https://{domain}/products.json"
        params = {"limit": 250, "page": page}
        
        for attempt in range(max_retries):
            try:
                response = session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=20
                )
                
                # Handle rate limiting
                if response.status_code == 429:
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                        logger.warning(f"⚠️ Rate limited, waiting {wait_time}s...")
                        import time
                        time.sleep(wait_time)
                        continue
                    else:
                        raise Exception("Rate limited after max retries")
                
                response.raise_for_status()
                break
                
            except requests.RequestException as e:
                if attempt < max_retries - 1:
                    logger.warning(f"⚠️ Request failed, retrying... ({attempt + 1}/{max_retries})")
                    continue
                raise Exception(f"Failed to fetch products: {str(e)}")
        
        try:
            data = response.json()
        except json.JSONDecodeError:
            raise Exception("Invalid JSON response from products.json")
        
        page_products = data.get("products", [])
        if not page_products:
            break
        
        remaining = max_products - len(products)
        products.extend(page_products[:remaining])
        
        logger.info(f"  📦 Fetched page {page}: {len(page_products)} products (total: {len(products)})")
        
        # Check for pagination via Link header
        link_header = response.headers.get("Link", "")
        if "rel=\"next\"" not in link_header:
            break
        
        page += 1
        
        # Safety: stop if too many pages
        if page > 20:
            logger.warning("⚠️ Stopping at page 20 (safety limit)")
            break
    
    logger.info(f"✅ Fetched {len(products)} products total")
    return products


def download_product_image(
    image_url: str,
    store_images_dir: Path,
    handle: str
) -> Optional[str]:
    """
    Download first product image
    
    Args:
        image_url: URL of the image
        store_images_dir: Directory to save image
        handle: Product handle for filename
    
    Returns:
        Local image path (relative to store_images_dir) or None if failed
    """
    if not image_url:
        return None
    
    try:
        # Create directory
        store_images_dir.mkdir(parents=True, exist_ok=True)
        
        # Download image
        response = requests.get(image_url, timeout=IMAGE_DOWNLOAD_TIMEOUT, stream=True)
        response.raise_for_status()
        
        # Save as JPEG
        filename = f"{handle}.jpg"
        filepath = store_images_dir / filename
        
        # Convert to JPEG using PIL
        img = Image.open(io.BytesIO(response.content))
        img = img.convert("RGB")
        img.save(filepath, format="JPEG", quality=90, optimize=True)
        
        logger.debug(f"  ✅ Downloaded: {filename}")
        return filename
        
    except Exception as e:
        logger.warning(f"  ⚠️ Image download failed for {handle}: {e}")
        return None


def build_product_rows(
    domain: str,
    store_id: str,
    raw_products: List[Dict[str, Any]],
    store_images_dir: Path
) -> List[ProductRow]:
    """
    Build product rows with embeddings and download images
    
    Args:
        domain: Store domain
        store_id: UUID of the store
        raw_products: Raw products from Shopify
        store_images_dir: Directory to save images
    
    Returns:
        List of ProductRow objects
    """
    logger.info(f"🔄 Processing {len(raw_products)} products...")
    
    embedder = get_embedder()
    rows = []
    image_server_url = os.getenv("IMAGE_SERVER_URL", "http://localhost:8000")
    
    for product in raw_products:
        try:
            # Extract fields
            handle = product.get("handle") or "product"
            name = product.get("title") or "Untitled Product"
            
            # Description (strip HTML)
            desc_html = product.get("body_html") or ""
            description = unescape(re.sub(r"<[^>]+>", " ", desc_html))
            description = re.sub(r"\s+", " ", description).strip()
            
            # Price (from first variant)
            price = None
            variants = product.get("variants", [])
            if variants:
                price_str = variants[0].get("price")
                if price_str:
                    try:
                        price = Decimal(str(price_str))
                    except:
                        pass
            
            # Image URL (first image)
            image_url = None
            images = product.get("images", [])
            if images:
                image_url = images[0].get("src")
            
            # Download image
            local_image_path = download_product_image(image_url, store_images_dir, handle)
            
            # Build image URL for database
            db_image_url = None
            if local_image_path:
                db_image_url = f"{image_server_url}/images/{store_id}/{local_image_path}"
            
            # Product URL — use original URL if provided (e.g. Threadless /designs/ path),
            # otherwise fall back to Shopify /products/ format
            product_url = product.get("_original_product_url") or f"https://{domain}/products/{handle}"
            
            # Create embedding
            text_to_embed = f"{name} {description}"
            embedding = embedder.encode(text_to_embed, normalize_embeddings=True).tolist()
            
            # Create row
            row = ProductRow(
                id=str(uuid.uuid4()),
                store_id=store_id,
                name=name,
                description=description,
                price=price,
                image_url=db_image_url,
                product_url=product_url,
                local_image_path=f"{store_id}/{local_image_path}" if local_image_path else None,
                embedding=embedding,
                handle=handle,
                created_at=datetime.now()
            )
            
            rows.append(row)
            
        except Exception as e:
            logger.warning(f"⚠️ Failed to process product '{product.get('title', 'unknown')}': {e}")
            continue
    
    logger.info(f"✅ Processed {len(rows)} products successfully")
    return rows


def store_products_in_supabase(rows: List[ProductRow]) -> None:
    """
    Store products in Supabase with batch inserts
    
    Args:
        rows: List of ProductRow objects
    
    Raises:
        Exception on database error
    """
    if not rows:
        logger.warning("⚠️ No products to store")
        return
    
    logger.info(f"💾 Storing {len(rows)} products in Supabase...")
    
    supabase = get_supabase()
    
    # Convert to dicts for insertion
    records = []
    for row in rows:
        record = {
            "id": row.id,
            "store_id": row.store_id,
            "handle": row.handle,
            "name": row.name,
            "description": row.description,
            "price": float(row.price) if row.price else None,
            "image_url": row.image_url,
            "product_url": row.product_url,
            "local_image_path": row.local_image_path,
            "embedding": row.embedding,
            "created_at": row.created_at.isoformat()
        }
        records.append(record)
    
    # Batch insert (chunks of 100)
    chunk_size = 100
    for i in range(0, len(records), chunk_size):
        chunk = records[i:i + chunk_size]
        try:
            supabase.table("products").insert(chunk).execute()
            logger.info(f"  ✅ Inserted batch {i // chunk_size + 1} ({len(chunk)} products)")
        except Exception as e:
            logger.error(f"❌ Failed to insert batch: {e}")
            raise
    
    logger.info(f"✅ All products stored in database")


DEMO_PAGES_DIR = Path("./demo_pages")
DEMO_PAGES_DIR.mkdir(exist_ok=True)


def generate_static_test_page(
    store_url: str,
    store_id: str,
    agent_id: str
) -> str:
    """
    Fetch client's page, inject widget snippet, save to demo_pages/
    Returns relative path like /demo/test_abc12345.html
    """
    import re as _re
    from urllib.parse import urljoin, urlparse

    logger.info(f"🎨 Generating static test page for {store_url}")

    widget_script_url = os.getenv("WIDGET_SCRIPT_URL", "http://localhost:5173/widget.js")
    search_api_url = os.getenv("SEARCH_API_URL", "http://localhost:8006")

    try:
        headers = {"User-Agent": "TeamPop-Onboarding/2.0"}
        response = requests.get(store_url, headers=headers, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
    except Exception as e:
        logger.warning(f"⚠️ Could not fetch store page ({e}), using blank template")
        soup = BeautifulSoup(
            f"<html><head><title>Store Preview</title></head><body></body></html>",
            "html.parser"
        )

    base_url = f"{urlparse(store_url).scheme}://{urlparse(store_url).netloc}"

    # Fix relative URLs → absolute so assets load cross-origin
    for tag in soup.find_all(["img", "source"], src=True):
        tag["src"] = urljoin(base_url, tag["src"])
    for tag in soup.find_all("link", href=True):
        tag["href"] = urljoin(base_url, tag["href"])
    for tag in soup.find_all("a", href=True):
        href = tag["href"]
        if not href.startswith(("http", "https", "mailto", "tel", "#", "javascript")):
            tag["href"] = urljoin(base_url, href)

    # Remove analytics / tracking scripts that could break the page
    kill_patterns = ["google-analytics", "googletagmanager", "gtag", "hotjar",
                     "clarity", "facebook", "mixpanel", "posthog", "snitcher"]
    for script in soup.find_all("script"):
        src = script.get("src", "")
        content = script.string or ""
        combined = (src + content).lower()
        if any(p in combined for p in kill_patterns):
            script.decompose()
    
    # --- Inject widget ---
    head = soup.find("head") or soup.new_tag("head")
    body = soup.find("body") or soup.new_tag("body")

    # Config script (must come BEFORE widget.js)
    config_script = soup.new_tag("script")
    config_script.string = f"""
    window.__TEAM_POP_AGENT_ID__ = "{agent_id}";
    console.log('[TeamPop] Widget config loaded', window.AVATAR_WIDGET_CONFIG);
    """
    head.append(config_script)


    # Widget script tag
    widget_tag = soup.new_tag("script")
    widget_tag["src"] = widget_script_url
    # widget_tag["defer"] = True
    body.append(widget_tag)

    # team-pop-agent custom element (used by the web component in main.jsx)
    agent_el = soup.new_tag("team-pop-agent")
    body.append(agent_el)

    # Save file
    filename = f"test_{store_id[:8]}.html"
    output_path = DEMO_PAGES_DIR / filename
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(str(soup))

    logger.info(f"✅ Test page saved: {output_path}")
    return filename  # just the filename, not the full path

def extract_store_context(products: List[Dict[str, Any]], domain: str) -> Dict:
    """
    Extract store context for agent personalization
    
    Args:
        products: Raw product list
        domain: Store domain
    
    Returns:
        Store context dict
    """
    # Extract categories (product types)
    categories = set()
    min_price = None
    max_price = None
    
    for product in products[:50]:  # Sample first 50
        product_type = product.get("product_type")
        if product_type:
            categories.add(product_type)
        
        variants = product.get("variants", [])
        for variant in variants:
            price_str = variant.get("price")
            if price_str:
                try:
                    price = float(price_str)
                    if min_price is None or price < min_price:
                        min_price = price
                    if max_price is None or price > max_price:
                        max_price = price
                except:
                    pass
    
    # Build context
    store_name = domain.replace(".myshopify.com", "").replace(".com", "").replace(".in", "").title()
    
    return {
        "store_name": store_name,
        "description": "online store",
        "categories": ", ".join(list(categories)[:10]) if categories else "various products",
        "price_range": f"₹{int(min_price)} to ₹{int(max_price)}" if min_price and max_price else "affordable pricing"
    }


# === API ENDPOINTS ===

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {
        "status": "ok",
        "service": "onboarding-service",
        "version": "2.0.0"
    }


@app.post("/onboard")
def onboard(req: OnboardRequest) -> Dict[str, Any]:
    """
    Complete onboarding flow:
    1. Validate Shopify store
    2. Scrape products (max 200)
    3. Download images
    4. Create embeddings
    5. Store in Supabase
    6. Create ElevenLabs agent
    7. Generate test page
    
    Returns:
        {
            "success": true,
            "store_id": "uuid",
            "agent_id": "elevenlabs_agent_id",
            "test_url": "/demo/test_xyz.html",
            "widget_snippet": "<script>...</script>",
            "products_count": 123
        }
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"🚀 ONBOARDING STARTED: {req.url}")
    logger.info(f"{'='*60}\n")
    
    # STEP 1: Validate Store
    logger.info("📋 Step 1/7: Validating Shopify store...")
    validation = validate_shopify_store(req.url)
    
    if not validation.get("valid"):
        logger.error(f"❌ Validation failed: {validation.get('error_code')}")
        raise HTTPException(status_code=400, detail=validation)
    
    clean_url = validation["url"]
    domain = urlparse(clean_url).netloc
    logger.info(f"✅ Validation passed: {domain}")
    
    # Generate store_id
    store_id = str(uuid.uuid4())
    logger.info(f"🆔 Store ID: {store_id}")
    
    # STEP 2: Scrape Products
    logger.info(f"\n📦 Step 2/7: Scraping products (max {MAX_PRODUCTS})...")
    try:
        raw_products = fetch_shopify_products(domain, max_products=MAX_PRODUCTS)
    except Exception as e:
        logger.error(f"❌ Scraping failed: {e}")
        raise HTTPException(
            status_code=502,
            detail=get_error_response(ErrorCodes.UNKNOWN_ERROR, str(e))
        )
    
    if not raw_products:
        raise HTTPException(
            status_code=400,
            detail=get_error_response(ErrorCodes.NO_PRODUCTS)
        )
    
    # STEP 3: Process Products & Download Images
    logger.info(f"\n🖼️  Step 3/7: Processing products and downloading images...")
    images_root = Path(os.getenv("STORE_IMAGES_PATH", "./images"))
    store_images_dir = images_root / store_id
    
    try:
        product_rows = build_product_rows(domain, store_id, raw_products, store_images_dir)
    except Exception as e:
        logger.error(f"❌ Product processing failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=get_error_response(ErrorCodes.EMBEDDING_ERROR, str(e))
        )
    
    # STEP 4: Store in Supabase
    logger.info(f"\n💾 Step 4/7: Storing products in database...")
    try:
        store_products_in_supabase(product_rows)
    except Exception as e:
        logger.error(f"❌ Database storage failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=get_error_response(ErrorCodes.SUPABASE_ERROR, str(e))
        )
    
    # STEP 5: Create ElevenLabs Agent
    logger.info(f"\n🤖 Step 5/7: Creating ElevenLabs conversational agent...")
    try:
        store_context = extract_store_context(raw_products, domain)
        search_api_url = os.getenv("SEARCH_API_URL", "http://localhost:8006")
        
        agent_result = create_agent_for_store(
            store_id=store_id,
            store_context=store_context,
            search_api_url=search_api_url
        )
        
        agent_id = agent_result["agent_id"]
        logger.info(f"✅ Agent created: {agent_id}")
        
    except Exception as e:
        logger.error(f"❌ Agent creation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=get_error_response(ErrorCodes.ELEVENLABS_ERROR, str(e))
        )
    
    # STEP 6: Generate Test Page
    logger.info(f"\n🎨 Step 6/7: Generating static test page...")
    try:
        filename = generate_static_test_page(clean_url, store_id, agent_id)
        test_url = f"/demo/{filename}"
    except Exception as e:
        logger.warning(f"⚠️ Test page generation failed: {e}")
        test_url = f"/demo/test_{store_id[:8]}.html"  # Placeholder
    
    # STEP 7: Generate Widget Snippet
    logger.info(f"\n📝 Step 7/7: Generating widget snippet...")
    widget_script_url = os.getenv("WIDGET_SCRIPT_URL", "http://localhost:5173/src/main.jsx")
    
    # CORRECT — config BEFORE script, correct variable name
    widget_snippet = f"""<!-- TeamPop Voice Widget -->
    <script>
    window.__TEAM_POP_AGENT_ID__ = "{agent_id}";
    </script>
    <script src="{widget_script_url}"></script>
    <team-pop-agent></team-pop-agent>"""
    
    # SUCCESS
    logger.info(f"\n{'='*60}")
    logger.info(f"✅ ONBOARDING COMPLETE!")
    logger.info(f"Store ID: {store_id}")
    logger.info(f"Agent ID: {agent_id}")
    logger.info(f"Products: {len(product_rows)}")
    logger.info(f"{'='*60}\n")
    
    return success_response({
        "store_id": store_id,
        "agent_id": agent_id,
        "test_url": test_url,
        "widget_snippet": widget_snippet,
        "products_count": len(product_rows),
        "store_url": clean_url
    })


class ThreadlessOnboardRequest(BaseModel):
    url: str = Field(
        default="https://nurdluv.threadless.com",
        examples=["https://nurdluv.threadless.com"],
    )


@app.post("/onboard-threadless")
def onboard_threadless(req: ThreadlessOnboardRequest) -> Dict[str, Any]:
    """
    Onboarding flow for Threadless artist stores:
    1. Validate URL
    2. Scrape products via ThreadlessScraper
    3. Process products (images + embeddings)
    4. Store in Supabase
    5. Create ElevenLabs agent
    6. Generate test page
    7. Generate widget snippet

    Returns same shape as /onboard.
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"🚀 THREADLESS ONBOARDING STARTED: {req.url}")
    logger.info(f"{'='*60}\n")

    # STEP 1: Validate URL
    logger.info("📋 Step 1/7: Validating Threadless store URL...")
    clean_url = req.url.strip().rstrip("/")
    if not clean_url.startswith("http"):
        clean_url = f"https://{clean_url}"

    parsed = urlparse(clean_url)
    domain = parsed.netloc

    if "threadless.com" not in domain:
        raise HTTPException(
            status_code=400,
            detail=get_error_response(
                ErrorCodes.INVALID_URL,
                "URL must be a threadless.com store"
            ),
        )
    logger.info(f"✅ Validation passed: {domain}")

    # Generate store_id
    store_id = str(uuid.uuid4())
    logger.info(f"🆔 Store ID: {store_id}")

    # STEP 2: Scrape Products
    logger.info(f"\n📦 Step 2/7: Scraping Threadless products (max {MAX_PRODUCTS})...")
    try:
        raw_products = scrape_threadless_store(max_products=MAX_PRODUCTS)
    except Exception as e:
        logger.error(f"❌ Scraping failed: {e}")
        raise HTTPException(
            status_code=502,
            detail=get_error_response(ErrorCodes.UNKNOWN_ERROR, str(e)),
        )

    if not raw_products:
        raise HTTPException(
            status_code=400,
            detail=get_error_response(ErrorCodes.NO_PRODUCTS),
        )

    # STEP 3: Process Products & Download Images
    logger.info(f"\n🖼️  Step 3/7: Processing products and downloading images...")
    images_root = Path(os.getenv("STORE_IMAGES_PATH", "./images"))
    store_images_dir = images_root / store_id

    try:
        product_rows = build_product_rows(domain, store_id, raw_products, store_images_dir)
    except Exception as e:
        logger.error(f"❌ Product processing failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=get_error_response(ErrorCodes.EMBEDDING_ERROR, str(e)),
        )

    # STEP 4: Store in Supabase
    logger.info(f"\n💾 Step 4/7: Storing products in database...")
    try:
        store_products_in_supabase(product_rows)
    except Exception as e:
        logger.error(f"❌ Database storage failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=get_error_response(ErrorCodes.SUPABASE_ERROR, str(e)),
        )

    # STEP 5: Create ElevenLabs Agent
    logger.info(f"\n🤖 Step 5/7: Creating ElevenLabs conversational agent...")
    try:
        store_context = extract_threadless_store_context(raw_products, domain)
        search_api_url = os.getenv("SEARCH_API_URL", "http://localhost:8006")

        agent_result = create_agent_for_store(
            store_id=store_id,
            store_context=store_context,
            search_api_url=search_api_url,
            tags=["teampop", "threadless", store_id],
        )

        agent_id = agent_result["agent_id"]
        logger.info(f"✅ Agent created: {agent_id}")

    except Exception as e:
        logger.error(f"❌ Agent creation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=get_error_response(ErrorCodes.ELEVENLABS_ERROR, str(e)),
        )

    # STEP 6: Generate Test Page (Playwright-based for Cloudflare bypass)
    logger.info(f"\n🎨 Step 6/7: Generating static test page via Playwright...")
    try:
        filename = generate_threadless_test_page(clean_url, store_id, agent_id)
        test_url = f"/demo/{filename}"
    except Exception as e:
        logger.warning(f"⚠️ Test page generation failed: {e}")
        test_url = f"/demo/test_{store_id[:8]}.html"

    # STEP 7: Generate Widget Snippet
    logger.info(f"\n📝 Step 7/7: Generating widget snippet...")
    widget_script_url = os.getenv("WIDGET_SCRIPT_URL", "http://localhost:5173/src/main.jsx")

    widget_snippet = f"""<!-- TeamPop Voice Widget -->
    <script>
    window.__TEAM_POP_AGENT_ID__ = "{agent_id}";
    </script>
    <script src="{widget_script_url}"></script>
    <team-pop-agent></team-pop-agent>"""

    # SUCCESS
    logger.info(f"\n{'='*60}")
    logger.info(f"✅ THREADLESS ONBOARDING COMPLETE!")
    logger.info(f"Store ID: {store_id}")
    logger.info(f"Agent ID: {agent_id}")
    logger.info(f"Products: {len(product_rows)}")
    logger.info(f"{'='*60}\n")

    return success_response({
        "store_id": store_id,
        "agent_id": agent_id,
        "test_url": test_url,
        "widget_snippet": widget_snippet,
        "products_count": len(product_rows),
        "store_url": clean_url,
    })


# =========================================================================
# Supermicro GPU Onboarding
# =========================================================================

class SupermicroOnboardRequest(BaseModel):
    url: str = Field(
        default="https://www.supermicro.com/en/products/gpu",
        examples=["https://www.supermicro.com/en/products/gpu"],
    )


@app.post("/onboard-supermicro")
def onboard_supermicro(req: SupermicroOnboardRequest) -> Dict[str, Any]:
    """
    Onboarding flow for Supermicro GPU server catalog:
    1. Validate URL
    2. Scrape products via SupermicroScraper (API + detail pages)
    3. Process products (images + embeddings)
    4. Store in Supabase
    5. Create ElevenLabs agent
    6. Generate test page
    7. Generate widget snippet

    Returns same shape as /onboard.
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"🚀 SUPERMICRO ONBOARDING STARTED: {req.url}")
    logger.info(f"{'='*60}\n")

    # STEP 1: Validate URL
    logger.info("📋 Step 1/7: Validating Supermicro URL...")
    clean_url = req.url.strip().rstrip("/")
    if not clean_url.startswith("http"):
        clean_url = f"https://{clean_url}"

    parsed = urlparse(clean_url)
    domain = parsed.netloc

    if "supermicro.com" not in domain:
        raise HTTPException(
            status_code=400,
            detail=get_error_response(
                ErrorCodes.INVALID_URL,
                "URL must be a supermicro.com page"
            ),
        )
    logger.info(f"✅ Validation passed: {domain}")

    # Generate store_id
    store_id = str(uuid.uuid4())
    logger.info(f"🆔 Store ID: {store_id}")

    # STEP 2: Scrape Products
    logger.info(f"\n📦 Step 2/7: Scraping Supermicro GPU products (max {MAX_PRODUCTS})...")
    try:
        raw_products = scrape_supermicro_store(url=clean_url, max_products=MAX_PRODUCTS)
    except Exception as e:
        logger.error(f"❌ Scraping failed: {e}")
        raise HTTPException(
            status_code=502,
            detail=get_error_response(ErrorCodes.SCRAPING_BLOCKED, str(e)),
        )

    if not raw_products:
        raise HTTPException(
            status_code=400,
            detail=get_error_response(ErrorCodes.NO_PRODUCTS),
        )

    # STEP 3: Process Products & Download Images
    logger.info(f"\n🖼️  Step 3/7: Processing products and downloading images...")
    images_root = Path(os.getenv("STORE_IMAGES_PATH", "./images"))
    store_images_dir = images_root / store_id

    try:
        product_rows = build_product_rows(domain, store_id, raw_products, store_images_dir)
    except Exception as e:
        logger.error(f"❌ Product processing failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=get_error_response(ErrorCodes.EMBEDDING_ERROR, str(e)),
        )

    # STEP 4: Store in Supabase
    logger.info(f"\n💾 Step 4/7: Storing products in database...")
    try:
        store_products_in_supabase(product_rows)
    except Exception as e:
        logger.error(f"❌ Database storage failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=get_error_response(ErrorCodes.SUPABASE_ERROR, str(e)),
        )

    # STEP 5: Create ElevenLabs Agent
    logger.info(f"\n🤖 Step 5/7: Creating ElevenLabs conversational agent...")
    try:
        store_context = extract_supermicro_store_context(raw_products, domain)
        search_api_url = os.getenv("SEARCH_API_URL", "http://localhost:8006")

        agent_result = create_agent_for_store(
            store_id=store_id,
            store_context=store_context,
            search_api_url=search_api_url,
            tags=["teampop", "supermicro", store_id],
        )

        agent_id = agent_result["agent_id"]
        logger.info(f"✅ Agent created: {agent_id}")

    except Exception as e:
        logger.error(f"❌ Agent creation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=get_error_response(ErrorCodes.ELEVENLABS_ERROR, str(e)),
        )

    # STEP 6: Generate Test Page
    logger.info(f"\n🎨 Step 6/7: Generating static test page via Playwright...")
    try:
        filename = generate_supermicro_test_page(clean_url, store_id, agent_id)
        test_url = f"/demo/{filename}"
    except Exception as e:
        logger.warning(f"⚠️ Test page generation failed: {e}")
        test_url = f"/demo/test_{store_id[:8]}.html"

    # STEP 7: Generate Widget Snippet
    logger.info(f"\n📝 Step 7/7: Generating widget snippet...")
    widget_script_url = os.getenv("WIDGET_SCRIPT_URL", "http://localhost:5173/src/main.jsx")

    widget_snippet = f"""<!-- TeamPop Voice Widget -->
    <script>
    window.__TEAM_POP_AGENT_ID__ = "{agent_id}";
    </script>
    <script src="{widget_script_url}"></script>
    <team-pop-agent></team-pop-agent>"""

    # SUCCESS
    logger.info(f"\n{'='*60}")
    logger.info(f"✅ SUPERMICRO ONBOARDING COMPLETE!")
    logger.info(f"Store ID: {store_id}")
    logger.info(f"Agent ID: {agent_id}")
    logger.info(f"Products: {len(product_rows)}")
    logger.info(f"{'='*60}\n")

    return success_response({
        "store_id": store_id,
        "agent_id": agent_id,
        "test_url": test_url,
        "widget_snippet": widget_snippet,
        "products_count": len(product_rows),
        "store_url": clean_url,
    })


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8005))
    logger.info(f"🚀 Starting Onboarding Service on port {port}")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
