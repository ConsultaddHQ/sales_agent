"""Extract products from JSON-LD structured data (@type: Product).

Coverage: ~65-70% of e-commerce sites embed JSON-LD Product markup.
Shopify, WooCommerce, BigCommerce, Squarespace, Wix all output this.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

logger = logging.getLogger("onboarding-service")


def _find_products_in_graph(data: Any) -> List[Dict]:
    """Recursively find Product objects in JSON-LD, handling @graph arrays."""
    products = []

    if isinstance(data, dict):
        type_val = data.get("@type", "")
        # @type can be a string or list: "Product" or ["Product", "ItemPage"]
        types = type_val if isinstance(type_val, list) else [type_val]
        if "Product" in types:
            products.append(data)

        # Recurse into @graph
        if "@graph" in data:
            products.extend(_find_products_in_graph(data["@graph"]))

    elif isinstance(data, list):
        for item in data:
            products.extend(_find_products_in_graph(item))

    return products


def _extract_price(product: Dict) -> Optional[str]:
    """Extract price from JSON-LD Offer/AggregateOffer."""
    offers = product.get("offers", {})

    # Single Offer
    if isinstance(offers, dict):
        price = offers.get("price") or offers.get("lowPrice")
        if price:
            return str(price)
        # AggregateOffer may have offers array
        inner = offers.get("offers", [])
        if isinstance(inner, list) and inner:
            return str(inner[0].get("price", ""))

    # Array of Offers
    if isinstance(offers, list) and offers:
        return str(offers[0].get("price", ""))

    # Direct price on product (rare)
    return str(product.get("price", "")) or None


def _extract_image(product: Dict) -> Optional[str]:
    """Extract image URL from JSON-LD Product."""
    image = product.get("image")
    if isinstance(image, str):
        return image
    if isinstance(image, list) and image:
        first = image[0]
        return first if isinstance(first, str) else first.get("url", "")
    if isinstance(image, dict):
        return image.get("url", "")
    return None


def _normalize_product(product: Dict, base_url: str = "") -> Dict[str, Any]:
    """Normalize a JSON-LD Product into Shopify-compatible format."""
    name = product.get("name", "Untitled Product")
    description = product.get("description", "")
    price = _extract_price(product)
    image = _extract_image(product)
    sku = product.get("sku", "")
    url = product.get("url", "")

    # Derive handle from URL or SKU
    handle = ""
    if url:
        path = url.rstrip("/").split("/")
        handle = path[-1] if path else ""
    if not handle and sku:
        handle = re.sub(r"[^a-z0-9-]", "-", sku.lower()).strip("-")
    if not handle:
        handle = re.sub(r"[^a-z0-9-]", "-", name.lower())[:60].strip("-")

    return {
        "handle": handle,
        "title": name,
        "body_html": description,
        "variants": [{"price": price}] if price else [],
        "images": [{"src": image}] if image else [],
        "_original_product_url": url,
    }


def extract_json_ld_products(html: str, base_url: str = "") -> List[Dict[str, Any]]:
    """Extract Product objects from JSON-LD scripts in HTML.

    Args:
        html: Page HTML content.
        base_url: Base URL for resolving relative URLs.

    Returns:
        List of Shopify-normalized product dicts. Empty list if none found.
    """
    soup = BeautifulSoup(html, "html.parser")
    products = []

    for script in soup.find_all("script", type="application/ld+json"):
        text = script.string
        if not text:
            continue
        try:
            data = json.loads(text)
            found = _find_products_in_graph(data)
            products.extend(found)
        except (json.JSONDecodeError, TypeError):
            continue

    if not products:
        return []

    normalized = [_normalize_product(p, base_url) for p in products]
    # Filter out products without a name
    normalized = [p for p in normalized if p["title"] and p["title"] != "Untitled Product"]

    logger.info(f"JSON-LD: extracted {len(normalized)} products")
    return normalized
