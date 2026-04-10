"""Supermicro adapter — enterprise GPU server catalog."""

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

_REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from shared.parsing import parse_price


def _derive_handle(product: Dict[str, Any]) -> str:
    sku = product.get("sku", "")
    if not sku:
        url = product.get("product_url", "")
        path = urlparse(url).path.rstrip("/")
        parts = path.split("/")
        if parts:
            sku = parts[-1]
    if not sku:
        return "product"

    handle = sku.lower().strip()
    handle = handle.replace("+", "-plus")
    handle = handle.replace("(", "").replace(")", "")
    handle = re.sub(r"[\s]+", "-", handle)
    handle = re.sub(r"-{2,}", "-", handle)
    handle = handle.strip("-")
    return handle or "product"


def _normalize_to_shopify_format(product: Dict[str, Any]) -> Dict[str, Any]:
    handle = _derive_handle(product)
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


class SupermicroAdapter(StoreAdapter):
    store_type = "supermicro"
    needs_playwright = True
    challenge_wait = 15

    def matches_url(self, url: str) -> bool:
        return "supermicro.com" in urlparse(url).netloc.lower()

    def scrape_products(self, url: str, max_products: int = 200) -> List[Dict[str, Any]]:
        from supermicro_scraper import SupermicroScraper

        logger.info("Running SupermicroScraper...")
        scraper = SupermicroScraper()
        result = scraper.run()

        raw_products = result.get("products", [])
        failed = result.get("failed_urls", [])
        if failed:
            logger.warning(f"{len(failed)} detail page enrichments failed (API data still used)")

        normalized = [_normalize_to_shopify_format(p) for p in raw_products[:max_products]]
        logger.info(f"Scraped and normalized {len(normalized)} Supermicro GPU products")
        return normalized

    def extract_store_context(
        self, products: List[Dict[str, Any]], domain: str
    ) -> Dict[str, Any]:
        return {
            "store_name": "Supermicro",
            "description": "enterprise GPU server and AI infrastructure catalog",
            "categories": "GPU servers, AI training systems, HPC rack servers, workstations, liquid-cooled systems",
            "price_range": "enterprise pricing (contact sales for quote)",
        }
