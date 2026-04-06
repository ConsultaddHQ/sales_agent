"""Threadless adapter — artist merchandise stores on threadless.com."""

import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from .base import StoreAdapter

logger = logging.getLogger("onboarding-service")

# Add universal-scraper/scripts to import path
_SCRAPER_DIR = str(Path(__file__).resolve().parent.parent.parent / "universal-scraper" / "scripts")
if _SCRAPER_DIR not in sys.path:
    sys.path.insert(0, _SCRAPER_DIR)

# Shared repo root for shared imports
_REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from shared.parsing import parse_price


def _derive_handle(product_url: str) -> str:
    path = urlparse(product_url).path.rstrip("/")
    parts = path.split("/")
    if parts and parts[-1]:
        return parts[-1]
    return "product"


def _normalize_to_shopify_format(product: Dict[str, Any]) -> Dict[str, Any]:
    handle = _derive_handle(product.get("product_url", ""))
    price = parse_price(product.get("price", ""))
    price_str = str(price) if price else None

    return {
        "handle": handle,
        "title": product.get("name", "Untitled Product"),
        "body_html": product.get("description", ""),
        "variants": [{"price": price_str}] if price_str else [],
        "images": [{"src": product["image_url"]}] if product.get("image_url") else [],
        "_original_product_url": product.get("product_url", ""),
    }


class ThreadlessAdapter(StoreAdapter):
    store_type = "threadless"
    needs_playwright = True
    challenge_wait = 10

    def matches_url(self, url: str) -> bool:
        return "threadless.com" in urlparse(url).netloc.lower()

    def scrape_products(self, url: str, max_products: int = 200) -> List[Dict[str, Any]]:
        from threadless_scraper import ThreadlessScraper

        logger.info("Running ThreadlessScraper...")
        scraper = ThreadlessScraper()
        result = scraper.run()

        raw_products = result.get("products", [])
        failed = result.get("failed_urls", [])
        if failed:
            logger.warning(f"{len(failed)} URLs failed during scraping")

        normalized = [_normalize_to_shopify_format(p) for p in raw_products[:max_products]]
        logger.info(f"Scraped and normalized {len(normalized)} Threadless products")
        return normalized

    def extract_store_context(
        self, products: List[Dict[str, Any]], domain: str
    ) -> Dict[str, Any]:
        subdomain = domain.split(".")[0] if "." in domain else domain
        store_name = subdomain.replace("-", " ").title()

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
