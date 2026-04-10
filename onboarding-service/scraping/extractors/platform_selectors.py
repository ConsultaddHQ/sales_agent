"""Platform-specific CSS selectors for HTML product extraction.

Each platform has known, stable CSS selectors from their default themes.
When we detect a platform, we use these selectors instead of generic heuristics.
"""

import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

logger = logging.getLogger("onboarding-service")


# ── Selector definitions per platform ──

PLATFORM_SELECTORS = {
    "woocommerce": {
        "listing": {
            "container": ".products .product, ul.products > li",
            "name": ".woocommerce-loop-product__title, h2.wc-block-grid__product-title",
            "price": ".price .amount, .price ins .amount",
            "image": ".woocommerce-LoopProduct-link img, .attachment-woocommerce_thumbnail",
            "link": "a.woocommerce-LoopProduct-link, a[href*='/product/']",
        },
        "detail": {
            "name": ".product_title, h1.entry-title",
            "price": ".price .woocommerce-Price-amount, p.price .amount",
            "image": ".woocommerce-product-gallery__image img, .wp-post-image",
            "description": ".woocommerce-product-details__short-description, #tab-description",
        },
    },
    "magento2": {
        "listing": {
            "container": ".product-item, .product-items > li",
            "name": ".product-item-name a, .product-item-link",
            "price": ".price-box .price, .price-wrapper .price",
            "image": ".product-image-photo",
            "link": ".product-item-link, .product-item-name a",
        },
        "detail": {
            "name": ".page-title span, h1.product-name",
            "price": ".price-box .price, [data-price-type='finalPrice'] .price",
            "image": ".gallery-placeholder img, .fotorama__img",
            "description": "#description .value, .product.attribute.description .value",
        },
    },
    "prestashop": {
        "listing": {
            "container": ".products .product-miniature, #js-product-list .product",
            "name": "h2.product-title a, .product-title a",
            "price": ".product-price-and-shipping .price, span.price",
            "image": ".product-thumbnail img, .thumbnail img",
            "link": ".product-title a, .thumbnail a",
        },
        "detail": {
            "name": "h1[itemprop='name'], h1.product-detail-name",
            "price": ".current-price .price, .product-price .current-price-value",
            "image": ".product-cover img, .js-qv-product-cover img",
            "description": "#product-description-short, .product-description-short",
        },
    },
    "opencart": {
        "listing": {
            "container": ".product-layout .product-thumb, .product-grid .product-thumb",
            "name": ".caption h4 a, .product-thumb .caption a",
            "price": ".price, .price-new",
            "image": ".image img, .product-thumb .image img",
            "link": ".caption h4 a, .image a",
        },
        "detail": {
            "name": "#product-product h1, h1.product-title",
            "price": ".price-new, #product-product .price",
            "image": ".thumbnails img, .product-image img",
            "description": "#tab-description, .product-description",
        },
    },
}


def _first_match(soup: BeautifulSoup, selectors: str) -> Optional[Any]:
    """Try multiple CSS selectors separated by commas, return first match."""
    for selector in selectors.split(","):
        result = soup.select_one(selector.strip())
        if result:
            return result
    return None


def _all_matches(soup: BeautifulSoup, selectors: str) -> List[Any]:
    """Try multiple CSS selectors, return all matches from first that works."""
    for selector in selectors.split(","):
        results = soup.select(selector.strip())
        if results:
            return results
    return []


def _extract_price_text(element) -> Optional[str]:
    """Get price text from an element, cleaning currency symbols."""
    if not element:
        return None
    text = element.get_text(strip=True)
    # Remove currency symbols and whitespace
    cleaned = re.sub(r"[^\d.,]", "", text)
    return cleaned if cleaned else None


def extract_products_with_selectors(
    html: str,
    platform: str,
    base_url: str = "",
    max_products: int = 200,
) -> List[Dict[str, Any]]:
    """Extract products from HTML using platform-specific CSS selectors.

    Args:
        html: Page HTML content.
        platform: Platform key from PLATFORM_SELECTORS.
        base_url: For resolving relative URLs.
        max_products: Maximum products to extract.

    Returns:
        List of Shopify-normalized product dicts.
    """
    if platform not in PLATFORM_SELECTORS:
        return []

    selectors = PLATFORM_SELECTORS[platform]["listing"]
    soup = BeautifulSoup(html, "html.parser")

    containers = _all_matches(soup, selectors["container"])
    if not containers:
        logger.debug(f"Platform selectors ({platform}): no product containers found")
        return []

    products = []
    for container in containers[:max_products]:
        name_el = _first_match(container, selectors["name"])
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name:
            continue

        price = _extract_price_text(_first_match(container, selectors["price"]))

        image = None
        img_el = _first_match(container, selectors["image"])
        if img_el:
            image = img_el.get("src") or img_el.get("data-src") or img_el.get("data-lazy-src")
            if image and base_url:
                image = urljoin(base_url, image)

        url = ""
        link_el = _first_match(container, selectors["link"])
        if link_el:
            url = link_el.get("href", "")
            if url and base_url:
                url = urljoin(base_url, url)

        handle = ""
        if url:
            path = url.rstrip("/").split("/")
            handle = path[-1] if path else ""
        if not handle:
            handle = re.sub(r"[^a-z0-9-]", "-", name.lower())[:60].strip("-")

        products.append({
            "handle": handle,
            "title": name,
            "body_html": "",
            "variants": [{"price": price}] if price else [],
            "images": [{"src": image}] if image else [],
            "_original_product_url": url,
        })

    logger.info(f"Platform selectors ({platform}): extracted {len(products)} products")
    return products
