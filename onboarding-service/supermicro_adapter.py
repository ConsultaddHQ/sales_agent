"""
Supermicro Adapter
==================
Bridges the SupermicroScraper into the onboarding pipeline by normalizing
its output into Shopify-compatible dicts that build_product_rows() consumes.

Also provides Playwright-based page fetching for test page generation
(needed because Supermicro returns 403 on plain HTTP requests).

Usage:
    from supermicro_adapter import (
        scrape_supermicro_store,
        extract_supermicro_store_context,
        generate_supermicro_test_page,
    )

    products = scrape_supermicro_store("https://www.supermicro.com/en/products/gpu")
    context  = extract_supermicro_store_context(products, "www.supermicro.com")
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

# Add universal-scraper/scripts to import path so we can import SupermicroScraper
_SCRAPER_DIR = str(Path(__file__).resolve().parent.parent / "universal-scraper" / "scripts")
if _SCRAPER_DIR not in sys.path:
    sys.path.insert(0, _SCRAPER_DIR)

from supermicro_scraper import SupermicroScraper


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _derive_handle(product: Dict[str, Any]) -> str:
    """Derive a URL-safe and filesystem-safe handle from the product SKU.

    Supermicro SKUs contain spaces, '+', and parentheses that break
    image filenames and URLs:
        "AS -4124GO-NART+"       -> "as-4124go-nart-plus"
        "SYS-420GU-TNXR (in 5U)" -> "sys-420gu-tnxr-in-5u"
        "SYS-422GL-FNR2"         -> "sys-422gl-fnr2"
    """
    sku = product.get("sku", "")
    if not sku:
        # Fallback: extract from product_url
        url = product.get("product_url", "")
        path = urlparse(url).path.rstrip("/")
        parts = path.split("/")
        if parts:
            sku = parts[-1]

    if not sku:
        return "product"

    # Sanitize: lowercase, replace special chars with safe alternatives
    handle = sku.lower().strip()
    handle = handle.replace("+", "-plus")
    handle = handle.replace("(", "").replace(")", "")
    # Collapse spaces, tabs, and multiple dashes into single dash
    handle = re.sub(r"[\s]+", "-", handle)
    handle = re.sub(r"-{2,}", "-", handle)
    handle = handle.strip("-")
    return handle

    return "product"


def _parse_price(price_str: str) -> Optional[str]:
    """Strip currency symbols and whitespace from a price string.

    Supermicro is B2B — most products have no listed price.
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
    """Convert a single Supermicro product dict into the shape build_product_rows() expects.

    build_product_rows() reads these keys:
        product["handle"]              -> str
        product["title"]               -> str
        product["body_html"]           -> str  (HTML-stripped later; plain text is fine)
        product["variants"][0]["price"] -> str  (parsed to Decimal later)
        product["images"][0]["src"]     -> str
    """
    handle = _derive_handle(product)
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

def scrape_supermicro_store(
    url: str = "https://www.supermicro.com/en/products/gpu",
    max_products: int = 200,
) -> List[Dict[str, Any]]:
    """Run the SupermicroScraper and return Shopify-compatible product dicts.

    Args:
        url: Supermicro GPU products page URL (used for validation, not navigation).
        max_products: Cap on how many products to return.

    Returns:
        List of dicts compatible with build_product_rows().
    """
    logger.info("🔄 Running SupermicroScraper...")

    scraper = SupermicroScraper()
    result = scraper.run()

    raw_products = result.get("products", [])
    failed = result.get("failed_urls", [])

    if failed:
        logger.warning(f"⚠️ {len(failed)} detail page enrichments failed (API data still used)")

    # Normalize and cap
    normalized = [_normalize_to_shopify_format(p) for p in raw_products[:max_products]]

    logger.info(f"✅ Scraped and normalized {len(normalized)} Supermicro GPU products")
    return normalized


# ---------------------------------------------------------------------------
# Store context for agent creation
# ---------------------------------------------------------------------------

def extract_supermicro_store_context(
    products: List[Dict[str, Any]],
    domain: str,
) -> Dict[str, Any]:
    """Build store context dict for create_agent_for_store().

    Args:
        products: Shopify-normalized product dicts from scrape_supermicro_store().
        domain: Store domain (e.g. "www.supermicro.com").

    Returns:
        {"store_name", "description", "categories", "price_range"}
    """
    return {
        "store_name": "Supermicro",
        "description": "enterprise GPU server and AI infrastructure catalog",
        "categories": "GPU servers, AI training systems, HPC rack servers, workstations, liquid-cooled systems",
        "price_range": "enterprise pricing (contact sales for quote)",
    }


# ---------------------------------------------------------------------------
# Test page generation (Playwright-based for bot protection bypass)
# ---------------------------------------------------------------------------

DEMO_PAGES_DIR = Path("./demo_pages")


def _fetch_page_with_playwright(url: str) -> Optional[str]:
    """Fetch a page using Playwright to bypass bot protection.

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
            page.goto(url, wait_until="domcontentloaded", timeout=45_000)

            # Wait for bot challenge
            title = page.title()
            if "just a moment" in title.lower():
                logger.info("[CF] Challenge detected — waiting 15s")
                time.sleep(15)

            html = page.content()
            browser.close()

            if "just a moment" in html[:500].lower():
                logger.warning("[CF] Bot protection not resolved")
                return None

            return html

    except Exception as e:
        logger.error(f"Playwright fetch failed: {e}")
        return None


def generate_supermicro_test_page(
    store_url: str,
    store_id: str,
    agent_id: str,
) -> str:
    """Generate a static test page for a Supermicro store.

    Uses Playwright to fetch the real store HTML (bot protection bypass),
    then injects the widget config and script — same approach as
    generate_threadless_test_page() in threadless_adapter.py.

    Returns:
        Filename of the saved test page (e.g. "test_abc12345.html").
    """
    DEMO_PAGES_DIR.mkdir(exist_ok=True)

    widget_script_url = os.getenv(
        "WIDGET_SCRIPT_URL", "http://localhost:5173/src/main.jsx"
    )

    logger.info(f"🎨 Generating Supermicro test page for {store_url}")

    html = _fetch_page_with_playwright(store_url)

    if html:
        soup = BeautifulSoup(html, "html.parser")
        logger.info("✅ Fetched real store page via Playwright")
    else:
        logger.warning("⚠️ Playwright fetch failed, using blank template")
        soup = BeautifulSoup(
            '<html><head><title>Supermicro GPU Servers</title></head><body></body></html>',
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

    # Strip ALL existing scripts
    for script in soup.find_all("script"):
        script.decompose()

    # Remove <link rel="preload" as="script">
    for link in soup.find_all("link", attrs={"as": "script"}):
        link.decompose()

    # Remove bot-protection iframes
    for iframe in soup.find_all("iframe"):
        style = iframe.get("style", "")
        if "visibility: hidden" in style or (
            iframe.get("width") == "1" and iframe.get("height") == "1"
        ):
            iframe.decompose()

    # Remove <noscript> blocks
    for noscript in soup.find_all("noscript"):
        noscript.decompose()

    # Remove HTML comments (can break parsing)
    from bs4 import Comment
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    # --- Inject widget ---
    head = soup.find("head") or soup.new_tag("head")
    body = soup.find("body") or soup.new_tag("body")

    config_script = soup.new_tag("script")
    config_script.string = f"""
    window.__TEAM_POP_AGENT_ID__ = "{agent_id}";
    console.log('[TeamPop] Widget config loaded — agent: {agent_id}');
    """
    head.append(config_script)

    widget_tag = soup.new_tag("script")
    widget_tag["src"] = widget_script_url
    body.append(widget_tag)

    agent_el = soup.new_tag("team-pop-agent")
    body.append(agent_el)

    # Save file
    filename = f"test_{store_id[:8]}.html"
    output_path = DEMO_PAGES_DIR / filename
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(str(soup))

    logger.info(f"✅ Test page saved: {output_path}")
    return filename
