"""Detect e-commerce platform from HTTP response headers and HTML content.

Fingerprints the platform to guide which extraction strategy to use.
"""

import logging
import re
from dataclasses import dataclass
from typing import Dict, Optional
from urllib.parse import urlparse

import requests

logger = logging.getLogger("onboarding-service")


@dataclass
class PlatformInfo:
    name: str          # Platform key (matches PLATFORM_SELECTORS keys)
    confidence: float  # 0.0-1.0
    needs_js: bool     # Whether the site requires JS rendering

    @property
    def detected(self) -> bool:
        return self.name != "unknown"


# ── Detection rules ──

def _check_headers(headers: Dict[str, str]) -> Optional[PlatformInfo]:
    """Detect platform from HTTP response headers."""
    h = {k.lower(): v for k, v in headers.items()}

    # Shopify
    if "x-shopid" in h or "x-shopify-stage" in h:
        return PlatformInfo("shopify", 0.95, False)

    # BigCommerce
    if "x-bc-store-version" in h:
        return PlatformInfo("bigcommerce", 0.95, False)

    # Squarespace
    served_by = h.get("x-servedby", "")
    server = h.get("server", "")
    if "squarespace" in served_by.lower() or "squarespace" in server.lower():
        return PlatformInfo("squarespace", 0.90, False)

    # Wix
    if "x-wix-renderer-server" in h or "x-wix-request-id" in h:
        return PlatformInfo("wix", 0.90, True)  # Wix needs JS rendering

    # Magento
    if "x-magento-vary" in h or "x-magento-tags" in h:
        return PlatformInfo("magento2", 0.90, False)

    return None


def _check_html(html: str) -> Optional[PlatformInfo]:
    """Detect platform from HTML content patterns."""
    html_lower = html[:50000].lower()  # Only check first 50KB

    # WooCommerce (most reliable signals)
    if "woocommerce" in html_lower or "/wp-content/plugins/woocommerce/" in html_lower:
        return PlatformInfo("woocommerce", 0.90, False)

    # Shopify (fallback if headers didn't catch it)
    if "cdn.shopify.com" in html_lower or "shopify.theme" in html_lower:
        return PlatformInfo("shopify", 0.85, False)

    # Magento 2
    if "/static/version" in html_lower and "requirejs" in html_lower:
        return PlatformInfo("magento2", 0.80, False)

    # PrestaShop
    if re.search(r'<meta[^>]+content="PrestaShop"', html, re.I):
        return PlatformInfo("prestashop", 0.90, False)
    if "/modules/ps_" in html_lower:
        return PlatformInfo("prestashop", 0.80, False)

    # OpenCart
    if "route=product" in html_lower or "catalog/view/theme" in html_lower:
        return PlatformInfo("opencart", 0.75, False)

    # Wix (HTML fallback)
    if "wix.com" in html_lower and ("_wixCIDX" in html or "wixstatic.com" in html_lower):
        return PlatformInfo("wix", 0.80, True)

    # BigCommerce (HTML fallback)
    if "data-content-region" in html_lower or "bigcommerce" in html_lower:
        return PlatformInfo("bigcommerce", 0.75, False)

    # Squarespace (HTML fallback)
    if re.search(r'<meta[^>]+content="Squarespace"', html, re.I):
        return PlatformInfo("squarespace", 0.85, False)

    # Shopware
    if "shopware" in html_lower:
        return PlatformInfo("shopware", 0.70, False)

    return None


def detect_platform(
    url: str,
    html: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
) -> PlatformInfo:
    """Detect the e-commerce platform for a given URL.

    If html/headers are not provided, makes an HTTP request to fetch them.

    Returns PlatformInfo with platform name, confidence, and JS requirement.
    """
    # Fetch if not provided
    if html is None or headers is None:
        try:
            resp = requests.get(
                url if url.startswith("http") else f"https://{url}",
                headers={"User-Agent": "TeamPop-Onboarding/2.0"},
                timeout=15,
                allow_redirects=True,
            )
            html = html or resp.text
            headers = headers or dict(resp.headers)
        except Exception as e:
            logger.warning(f"Platform detection fetch failed: {e}")
            return PlatformInfo("unknown", 0.0, False)

    # Check headers first (faster, more reliable)
    result = _check_headers(headers or {})
    if result:
        logger.info(f"Platform detected from headers: {result.name} ({result.confidence:.0%})")
        return result

    # Check HTML content
    result = _check_html(html or "")
    if result:
        logger.info(f"Platform detected from HTML: {result.name} ({result.confidence:.0%})")
        return result

    logger.info("Platform detection: unknown")
    return PlatformInfo("unknown", 0.0, False)
