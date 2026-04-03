"""
Threadless Adapter
==================
Bridges the ThreadlessScraper into the onboarding pipeline by normalizing
its output into Shopify-compatible dicts that build_product_rows() consumes.

Also provides Playwright-based page fetching for test page generation
(needed because Cloudflare blocks plain requests.get).

Usage:
    from threadless_adapter import (
        scrape_threadless_store,
        extract_threadless_store_context,
        generate_threadless_test_page,
    )

    products = scrape_threadless_store(max_products=200)
    context  = extract_threadless_store_context(products, "nurdluv.threadless.com")
"""

import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

logger = logging.getLogger("onboarding-service")

# Add universal-scraper/scripts to import path so we can import ThreadlessScraper
_SCRAPER_DIR = str(Path(__file__).resolve().parent.parent / "universal-scraper" / "scripts")
if _SCRAPER_DIR not in sys.path:
    sys.path.insert(0, _SCRAPER_DIR)

from threadless_scraper import ThreadlessScraper


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _derive_handle(product_url: str) -> str:
    """Extract handle from a Threadless product URL.

    Example: https://nurdluv.threadless.com/designs/my-design -> my-design
    """
    path = urlparse(product_url).path.rstrip("/")
    parts = path.split("/")
    if parts:
        handle = parts[-1]
        if handle:
            return handle
    # Fallback: slugify the name would happen upstream; return a safe default
    return "product"


def _parse_price(price_str: str) -> Optional[str]:
    """Strip currency symbols and whitespace from a price string.

    "$24.99"  -> "24.99"
    "$ 1,299" -> "1299"
    ""        -> None
    """
    if not price_str:
        return None
    cleaned = re.sub(r"[^\d.]", "", price_str)
    if not cleaned:
        return None
    return cleaned


# ---------------------------------------------------------------------------
# Normalize to Shopify-compatible format
# ---------------------------------------------------------------------------

def _normalize_to_shopify_format(product: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a single Threadless product dict into the shape build_product_rows() expects.

    build_product_rows() reads these keys:
        product["handle"]              -> str
        product["title"]               -> str
        product["body_html"]           -> str  (HTML-stripped later; plain text is fine)
        product["variants"][0]["price"] -> str  (parsed to Decimal later)
        product["images"][0]["src"]     -> str
    """
    handle = _derive_handle(product.get("product_url", ""))
    price = _parse_price(product.get("price", ""))

    return {
        "handle": handle,
        "title": product.get("name", "Untitled Product"),
        "body_html": product.get("description", ""),
        "variants": [{"price": price}] if price else [],
        "images": [{"src": product["image_url"]}] if product.get("image_url") else [],
        # Preserve original URL so the endpoint can build product_url correctly
        "_original_product_url": product.get("product_url", ""),
    }


# ---------------------------------------------------------------------------
# Scrape
# ---------------------------------------------------------------------------

def scrape_threadless_store(max_products: int = 200) -> List[Dict[str, Any]]:
    """Run the ThreadlessScraper and return Shopify-compatible product dicts.

    Args:
        max_products: Cap on how many products to return.

    Returns:
        List of dicts compatible with build_product_rows().
    """
    logger.info("🔄 Running ThreadlessScraper...")

    scraper = ThreadlessScraper()
    result = scraper.run()

    raw_products = result.get("products", [])
    failed = result.get("failed_urls", [])

    if failed:
        logger.warning(f"⚠️ {len(failed)} URLs failed during scraping")

    # Normalize and cap
    normalized = [_normalize_to_shopify_format(p) for p in raw_products[:max_products]]

    logger.info(f"✅ Scraped and normalized {len(normalized)} Threadless products")
    return normalized


# ---------------------------------------------------------------------------
# Store context for agent creation
# ---------------------------------------------------------------------------

def extract_threadless_store_context(
    products: List[Dict[str, Any]],
    domain: str,
) -> Dict[str, Any]:
    """Build store context dict for create_agent_for_store().

    Args:
        products: Shopify-normalized product dicts from scrape_threadless_store().
        domain: Store domain (e.g. "nurdluv.threadless.com").

    Returns:
        {"store_name", "description", "categories", "price_range"}
    """
    # Store name from subdomain
    subdomain = domain.split(".")[0] if "." in domain else domain
    store_name = subdomain.replace("-", " ").title()

    # Price range
    min_price = None
    max_price = None
    for product in products:
        variants = product.get("variants", [])
        if variants:
            price_str = variants[0].get("price")
            if price_str:
                try:
                    price = float(price_str)
                    if min_price is None or price < min_price:
                        min_price = price
                    if max_price is None or price > max_price:
                        max_price = price
                except (ValueError, TypeError):
                    pass

    price_range = (
        f"${min_price:.0f} to ${max_price:.0f}"
        if min_price is not None and max_price is not None
        else "affordable pricing"
    )

    return {
        "store_name": store_name,
        "description": "artist merchandise store on Threadless",
        "categories": "apparel, accessories, art prints, home decor",
        "price_range": price_range,
    }


# ---------------------------------------------------------------------------
# Test page generation (Playwright-based for Cloudflare bypass)
# ---------------------------------------------------------------------------

DEMO_PAGES_DIR = Path("./demo_pages")


def _fetch_page_with_playwright(url: str) -> Optional[str]:
    """Fetch a page using Playwright to bypass Cloudflare.

    Returns rendered HTML string or None on failure.
    """
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)

            # Wait for Cloudflare challenge
            title = page.title()
            if "just a moment" in title.lower():
                logger.info("[CF] Challenge detected — waiting 10s")
                time.sleep(10)

            html = page.content()
            browser.close()

            # Verify we got past Cloudflare
            if "just a moment" in html[:500].lower():
                logger.warning("[CF] Cloudflare not resolved")
                return None

            return html

    except Exception as e:
        logger.error(f"Playwright fetch failed: {e}")
        return None


def generate_threadless_test_page(
    store_url: str,
    store_id: str,
    agent_id: str,
) -> str:
    """Generate a static test page for a Threadless store.

    Uses Playwright to fetch the real store HTML (Cloudflare bypass),
    then injects the widget config and script — same approach as
    generate_static_test_page() in main.py but with Playwright fetch.

    Returns:
        Filename of the saved test page (e.g. "test_abc12345.html").
    """
    DEMO_PAGES_DIR.mkdir(exist_ok=True)

    widget_script_url = os.getenv(
        "WIDGET_SCRIPT_URL", "http://localhost:5173/src/main.jsx"
    )

    logger.info(f"🎨 Generating Threadless test page for {store_url}")

    # Fetch real store page via Playwright (bypasses Cloudflare)
    html = _fetch_page_with_playwright(store_url)

    if html:
        soup = BeautifulSoup(html, "html.parser")
        logger.info("✅ Fetched real store page via Playwright")
    else:
        logger.warning("⚠️ Playwright fetch failed, using blank template")
        soup = BeautifulSoup(
            '<html><head><title>Store Preview</title></head><body></body></html>',
            "html.parser",
        )

    base_url = f"{urlparse(store_url).scheme}://{urlparse(store_url).netloc}"

    # Fix relative URLs -> absolute so assets load cross-origin
    for tag in soup.find_all(["img", "source"], src=True):
        tag["src"] = urljoin(base_url, tag["src"])
    for tag in soup.find_all("link", href=True):
        tag["href"] = urljoin(base_url, tag["href"])
    for tag in soup.find_all("a", href=True):
        href = tag["href"]
        if not href.startswith(("http", "https", "mailto", "tel", "#", "javascript")):
            tag["href"] = urljoin(base_url, href)

    # ---------------------------------------------------------------
    # Strip ALL existing scripts — they break when served from localhost.
    # ---------------------------------------------------------------
    for script in soup.find_all("script"):
        script.decompose()

    # Remove <link rel="preload" as="script">
    for link in soup.find_all("link", attrs={"as": "script"}):
        link.decompose()

    # Remove Cloudflare-injected iframes (1x1 invisible challenge frames)
    for iframe in soup.find_all("iframe"):
        style = iframe.get("style", "")
        if "visibility: hidden" in style or (
            iframe.get("width") == "1" and iframe.get("height") == "1"
        ):
            iframe.decompose()

    # Remove <noscript> blocks
    for noscript in soup.find_all("noscript"):
        noscript.decompose()

    # ---------------------------------------------------------------
    # Remove ALL HTML comments — critical fix.
    # Threadless HTML has commented-out <script> blocks like:
    #   <!--<script>...code...</script>-->
    # Browsers parse <script> inside comments using special rules
    # (HTML spec "script data" mode), which can break parsing of
    # everything that follows, including our injected widget script.
    # ---------------------------------------------------------------
    from bs4 import Comment
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    # --- Inject widget ---
    head = soup.find("head") or soup.new_tag("head")
    body = soup.find("body") or soup.new_tag("body")

    # Config script (must come BEFORE widget.js)
    config_script = soup.new_tag("script")
    config_script.string = f"""
    window.__TEAM_POP_AGENT_ID__ = "{agent_id}";
    console.log('[TeamPop] Widget config loaded — agent: {agent_id}');
    """
    head.append(config_script)

    # Widget script tag
    widget_tag = soup.new_tag("script")
    widget_tag["src"] = widget_script_url
    body.append(widget_tag)

    # Custom element
    agent_el = soup.new_tag("team-pop-agent")
    body.append(agent_el)

    # Save file
    filename = f"test_{store_id[:8]}.html"
    output_path = DEMO_PAGES_DIR / filename
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(str(soup))

    logger.info(f"✅ Test page saved: {output_path}")
    return filename
