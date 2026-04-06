"""Extract products from Schema.org microdata (itemprop attributes).

Coverage: ~30-40% of e-commerce sites, especially older WooCommerce, Magento, PrestaShop.
"""

import logging
import re
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger("onboarding-service")


def _get_itemprop(element: Tag, prop: str) -> Optional[str]:
    """Get itemprop value from an element or its children."""
    tag = element.find(attrs={"itemprop": prop})
    if not tag:
        return None
    # For meta tags, use content attribute
    if tag.name == "meta":
        return tag.get("content", "").strip()
    # For links, use href
    if tag.name == "a":
        return tag.get("href", "").strip()
    # For images, use src
    if tag.name == "img":
        return tag.get("src", "").strip()
    # Otherwise, text content
    return tag.get_text(strip=True)


def extract_microdata_products(html: str) -> List[Dict[str, Any]]:
    """Extract Products from Schema.org microdata markup.

    Looks for elements with itemtype containing "schema.org/Product".

    Returns list of Shopify-normalized product dicts.
    """
    soup = BeautifulSoup(html, "html.parser")
    products = []

    # Find all Product scope elements
    product_elements = soup.find_all(
        attrs={"itemtype": re.compile(r"schema\.org/Product", re.I)}
    )

    for elem in product_elements:
        name = _get_itemprop(elem, "name")
        if not name:
            continue

        description = _get_itemprop(elem, "description") or ""
        image = _get_itemprop(elem, "image") or ""
        url = _get_itemprop(elem, "url") or ""
        sku = _get_itemprop(elem, "sku") or ""

        # Price from Offer
        price = None
        offer = elem.find(attrs={"itemtype": re.compile(r"schema\.org/Offer", re.I)})
        if offer:
            price = _get_itemprop(offer, "price")
        if not price:
            price = _get_itemprop(elem, "price")

        handle = ""
        if url:
            path = url.rstrip("/").split("/")
            handle = path[-1] if path else ""
        if not handle and sku:
            handle = re.sub(r"[^a-z0-9-]", "-", sku.lower()).strip("-")
        if not handle:
            handle = re.sub(r"[^a-z0-9-]", "-", name.lower())[:60].strip("-")

        products.append({
            "handle": handle,
            "title": name,
            "body_html": description,
            "variants": [{"price": price}] if price else [],
            "images": [{"src": image}] if image else [],
            "_original_product_url": url,
        })

    if products:
        logger.info(f"Microdata: extracted {len(products)} products")
    return products
