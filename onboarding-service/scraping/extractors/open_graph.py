"""Extract product data from Open Graph meta tags.

Coverage: ~80-90% of e-commerce sites have OG tags (needed for social sharing).
Best for supplementing other extraction methods with basic data.
"""

import logging
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

logger = logging.getLogger("onboarding-service")


def _get_meta(soup: BeautifulSoup, property_name: str) -> Optional[str]:
    """Get content from a meta tag by property or name."""
    tag = soup.find("meta", attrs={"property": property_name})
    if not tag:
        tag = soup.find("meta", attrs={"name": property_name})
    return tag.get("content", "").strip() if tag else None


def extract_og_product(html: str) -> Optional[Dict[str, Any]]:
    """Extract a single product from Open Graph tags.

    Returns a Shopify-normalized product dict, or None if insufficient data.
    """
    soup = BeautifulSoup(html, "html.parser")

    title = _get_meta(soup, "og:title")
    image = _get_meta(soup, "og:image")
    description = _get_meta(soup, "og:description")
    url = _get_meta(soup, "og:url")
    price = _get_meta(soup, "product:price:amount") or _get_meta(soup, "og:price:amount")

    if not title:
        return None

    import re
    handle = ""
    if url:
        path = url.rstrip("/").split("/")
        handle = path[-1] if path else ""
    if not handle:
        handle = re.sub(r"[^a-z0-9-]", "-", title.lower())[:60].strip("-")

    product = {
        "handle": handle,
        "title": title,
        "body_html": description or "",
        "variants": [{"price": price}] if price else [],
        "images": [{"src": image}] if image else [],
        "_original_product_url": url or "",
    }

    logger.debug(f"OG: extracted product '{title}'")
    return product


def extract_og_products_from_pages(htmls: List[str]) -> List[Dict[str, Any]]:
    """Extract products from multiple page HTMLs using OG tags.

    Args:
        htmls: List of HTML strings (one per product page).

    Returns:
        List of Shopify-normalized product dicts.
    """
    products = []
    for html in htmls:
        product = extract_og_product(html)
        if product:
            products.append(product)
    logger.info(f"OG: extracted {len(products)} products from {len(htmls)} pages")
    return products
