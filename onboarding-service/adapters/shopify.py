"""Shopify adapter — uses the /products.json public API."""

import json
import logging
import time
from typing import Any, Dict, List
from urllib.parse import urlparse

import requests

from .base import StoreAdapter

logger = logging.getLogger("onboarding-service")


class ShopifyAdapter(StoreAdapter):
    store_type = "shopify"
    needs_playwright = False

    def matches_url(self, url: str) -> bool:
        domain = urlparse(url).netloc.lower()
        return "myshopify.com" in domain

    def scrape_products(self, url: str, max_products: int = 200) -> List[Dict[str, Any]]:
        """Fetch products from Shopify /products.json with pagination."""
        domain = urlparse(url if url.startswith("http") else f"https://{url}").netloc
        products: List[Dict[str, Any]] = []
        page = 1
        session = requests.Session()
        headers = {"User-Agent": "TeamPop-Onboarding/2.0"}
        max_retries = 3

        logger.info(f"Fetching products from {domain} (max: {max_products})")

        while len(products) < max_products:
            api_url = f"https://{domain}/products.json"
            params = {"limit": 250, "page": page}

            for attempt in range(max_retries):
                try:
                    response = session.get(api_url, params=params, headers=headers, timeout=20)
                    if response.status_code == 429:
                        if attempt < max_retries - 1:
                            wait_time = 2 * (2 ** attempt)
                            logger.warning(f"Rate limited, waiting {wait_time}s...")
                            time.sleep(wait_time)
                            continue
                        raise Exception("Rate limited after max retries")
                    response.raise_for_status()
                    break
                except requests.RequestException as e:
                    if attempt < max_retries - 1:
                        logger.warning(f"Request failed, retrying... ({attempt + 1}/{max_retries})")
                        continue
                    raise Exception(f"Failed to fetch products: {e}")

            try:
                data = response.json()
            except json.JSONDecodeError:
                raise Exception("Invalid JSON response from products.json")

            page_products = data.get("products", [])
            if not page_products:
                break

            remaining = max_products - len(products)
            products.extend(page_products[:remaining])
            logger.info(f"  Fetched page {page}: {len(page_products)} products (total: {len(products)})")

            if "rel=\"next\"" not in response.headers.get("Link", ""):
                break

            page += 1
            if page > 20:
                logger.warning("Stopping at page 20 (safety limit)")
                break

        logger.info(f"Fetched {len(products)} Shopify products total")
        return products

    def extract_store_context(
        self, products: List[Dict[str, Any]], domain: str
    ) -> Dict[str, Any]:
        categories = set()
        min_price = None
        max_price = None

        for product in products[:50]:
            product_type = product.get("product_type")
            if product_type:
                categories.add(product_type)
            for variant in product.get("variants", []):
                price_str = variant.get("price")
                if price_str:
                    try:
                        price = float(price_str)
                        if min_price is None or price < min_price:
                            min_price = price
                        if max_price is None or price > max_price:
                            max_price = price
                    except (ValueError, TypeError):
                        pass

        store_name = domain.replace(".myshopify.com", "").replace(".com", "").replace(".in", "").title()

        return {
            "store_name": store_name,
            "description": "online store",
            "categories": ", ".join(list(categories)[:10]) if categories else "various products",
            "price_range": f"${min_price:.0f} to ${max_price:.0f}" if min_price and max_price else "affordable pricing",
        }
