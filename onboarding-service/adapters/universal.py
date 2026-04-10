"""Universal adapter — the catch-all fallback for any e-commerce site.

Implements the 6-tier scraping fallback chain:
  1. JSON-LD structured data extraction
  2. Microdata (Schema.org itemprop) extraction
  3. Platform-specific CSS selectors (WooCommerce, Magento, PrestaShop, OpenCart)
  4. Playwright rendering + re-try JSON-LD + generic selectors
  5. Sitemap discovery + per-page scraping
  6. LLM extraction (last resort)
"""

import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests

from .base import StoreAdapter

logger = logging.getLogger("onboarding-service")

# Ensure repo root is importable
_REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scraping.platform_detect import detect_platform
from scraping.extractors.json_ld import extract_json_ld_products
from scraping.extractors.microdata import extract_microdata_products
from scraping.extractors.open_graph import extract_og_product
from scraping.extractors.platform_selectors import extract_products_with_selectors, PLATFORM_SELECTORS
from scraping.extractors.sitemap import discover_product_urls
from scraping.renderer import render_with_playwright
from scraping.llm_fallback import extract_with_llm

_HEADERS = {"User-Agent": "TeamPop-Onboarding/2.0"}


class UniversalAdapter(StoreAdapter):
    """Catch-all adapter that tries multiple extraction strategies."""

    store_type = "universal"
    needs_playwright = True  # May need it

    def matches_url(self, url: str) -> bool:
        # Universal adapter is the fallback — never auto-matches by URL.
        # It's selected when no other adapter matches.
        return False

    def scrape_products(self, url: str, max_products: int = 200) -> List[Dict[str, Any]]:
        """Run the multi-tier extraction pipeline."""
        clean_url = url if url.startswith("http") else f"https://{url}"
        base_url = f"{urlparse(clean_url).scheme}://{urlparse(clean_url).netloc}"

        # ── Fetch page via HTTP ──
        html = None
        headers = {}
        try:
            resp = requests.get(clean_url, headers=_HEADERS, timeout=20, allow_redirects=True)
            resp.raise_for_status()
            html = resp.text
            headers = dict(resp.headers)
        except Exception as e:
            logger.warning(f"HTTP fetch failed: {e}")

        # ── Detect platform ──
        platform = detect_platform(clean_url, html=html, headers=headers)
        logger.info(f"Platform: {platform.name} (confidence={platform.confidence:.0%}, needs_js={platform.needs_js})")

        # ── Tier 1: JSON-LD extraction ──
        if html:
            products = extract_json_ld_products(html, base_url)
            if len(products) >= 2:
                return products[:max_products]

        # ── Tier 2: Microdata extraction ──
        if html:
            products = extract_microdata_products(html)
            if len(products) >= 2:
                return products[:max_products]

        # ── Tier 3: Platform CSS selectors ──
        if html and platform.name in PLATFORM_SELECTORS:
            products = extract_products_with_selectors(html, platform.name, base_url, max_products)
            if len(products) >= 2:
                return products

        # ── Tier 4: Playwright rendering + re-try structured data ──
        if platform.needs_js or not html or (html and len(self._find_visible_products(html)) < 2):
            logger.info("Trying Playwright rendering...")
            rendered_html = render_with_playwright(clean_url)
            if rendered_html:
                html = rendered_html  # Use rendered HTML for subsequent tiers

                # Re-try JSON-LD on rendered DOM
                products = extract_json_ld_products(html, base_url)
                if len(products) >= 2:
                    return products[:max_products]

                # Re-try platform selectors on rendered DOM
                if platform.name in PLATFORM_SELECTORS:
                    products = extract_products_with_selectors(
                        html, platform.name, base_url, max_products
                    )
                    if len(products) >= 2:
                        return products

                # Re-try microdata
                products = extract_microdata_products(html)
                if len(products) >= 2:
                    return products[:max_products]

        # ── Tier 5: Sitemap discovery + per-page scraping ──
        logger.info("Trying sitemap discovery...")
        product_urls = discover_product_urls(clean_url, max_urls=max_products)
        if product_urls:
            products = self._scrape_individual_pages(product_urls[:max_products], base_url)
            if len(products) >= 2:
                return products

        # ── Tier 6: LLM extraction (last resort) ──
        if html:
            logger.info("Trying LLM extraction (last resort)...")
            products = extract_with_llm(html, max_products=max_products)
            if products:
                return products

        logger.warning(f"All extraction strategies failed for {clean_url}")
        return []

    def _find_visible_products(self, html: str) -> List:
        """Quick heuristic check: does the HTML seem to contain product data?"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html[:50000], "html.parser")
        # Look for common product indicators
        price_elements = soup.find_all(string=re.compile(r"[\$\€\£]\s*\d+"))
        return price_elements

    def _scrape_individual_pages(
        self, urls: List[str], base_url: str
    ) -> List[Dict[str, Any]]:
        """Scrape individual product pages using JSON-LD + OG tags."""
        import time
        products = []

        for i, url in enumerate(urls):
            try:
                resp = requests.get(url, headers=_HEADERS, timeout=15)
                resp.raise_for_status()
                page_html = resp.text

                # Try JSON-LD first
                page_products = extract_json_ld_products(page_html, base_url)
                if page_products:
                    products.extend(page_products)
                else:
                    # Fallback to OG tags
                    og_product = extract_og_product(page_html)
                    if og_product:
                        if not og_product.get("_original_product_url"):
                            og_product["_original_product_url"] = url
                        products.append(og_product)

                # Rate limit: ~2 req/s
                if i < len(urls) - 1:
                    time.sleep(0.5)

            except Exception as e:
                logger.debug(f"Failed to scrape {url}: {e}")
                continue

        logger.info(f"Individual pages: scraped {len(products)} products from {len(urls)} URLs")
        return products

    def extract_store_context(
        self, products: List[Dict[str, Any]], domain: str
    ) -> Dict[str, Any]:
        """Build generic store context from scraped products."""
        store_name = domain.replace("www.", "").split(".")[0].title()

        min_price = None
        max_price = None
        for product in products[:50]:
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

        # Collect unique words from product titles as crude categories
        words = set()
        for p in products[:20]:
            for word in p.get("title", "").split():
                if len(word) > 3:
                    words.add(word.lower())
        categories = ", ".join(list(words)[:8]) if words else "various products"

        price_range = (
            f"${min_price:.0f} to ${max_price:.0f}"
            if min_price is not None and max_price is not None
            else "various price points"
        )

        return {
            "store_name": store_name,
            "description": "online store",
            "categories": categories,
            "price_range": price_range,
        }
