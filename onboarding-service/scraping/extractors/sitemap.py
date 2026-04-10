"""Discover product URLs via sitemap.xml.

Coverage: ~85-90% of e-commerce sites have sitemaps.
"""

import logging
import re
from typing import List, Optional
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET

import requests

logger = logging.getLogger("onboarding-service")

# Common product URL patterns
_PRODUCT_URL_PATTERNS = [
    r"/product[s]?/",
    r"/shop/",
    r"/catalog/",
    r"/item[s]?/",
    r"/p/",
    r"/dp/",  # Amazon
    r"/designs/",  # Threadless
]
_PRODUCT_URL_RE = re.compile("|".join(_PRODUCT_URL_PATTERNS), re.I)

# Sitemap XML namespace
_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

_HEADERS = {"User-Agent": "TeamPop-Onboarding/2.0"}


def _fetch_xml(url: str) -> Optional[str]:
    """Fetch XML content from URL."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.debug(f"Failed to fetch {url}: {e}")
        return None


def _parse_sitemap_urls(xml_text: str) -> List[str]:
    """Parse <loc> URLs from a sitemap XML string."""
    urls = []
    try:
        root = ET.fromstring(xml_text)
        # Try with namespace
        for loc in root.findall(".//sm:loc", _NS):
            if loc.text:
                urls.append(loc.text.strip())
        # If no results, try without namespace
        if not urls:
            for loc in root.iter():
                if loc.tag.endswith("loc") and loc.text:
                    urls.append(loc.text.strip())
    except ET.ParseError:
        logger.debug("XML parse error in sitemap")
    return urls


def _find_sitemap_urls_from_robots(base_url: str) -> List[str]:
    """Find sitemap URLs from robots.txt."""
    robots_url = f"{base_url}/robots.txt"
    sitemaps = []
    try:
        resp = requests.get(robots_url, headers=_HEADERS, timeout=10)
        if resp.ok:
            for line in resp.text.splitlines():
                if line.lower().startswith("sitemap:"):
                    url = line.split(":", 1)[1].strip()
                    sitemaps.append(url)
    except Exception:
        pass
    return sitemaps


def discover_product_urls(site_url: str, max_urls: int = 500) -> List[str]:
    """Discover product page URLs from a site's sitemap.

    Checks /sitemap.xml, robots.txt references, and common sitemap locations.
    Filters URLs to only include likely product pages.

    Returns list of product page URLs (up to max_urls).
    """
    parsed = urlparse(site_url if site_url.startswith("http") else f"https://{site_url}")
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    # Collect sitemap URLs to try
    sitemap_urls = [f"{base_url}/sitemap.xml"]
    sitemap_urls.extend(_find_sitemap_urls_from_robots(base_url))
    # Common sitemap locations
    sitemap_urls.extend([
        f"{base_url}/sitemap_index.xml",
        f"{base_url}/sitemap_products_1.xml",
        f"{base_url}/product-sitemap.xml",
    ])
    # Deduplicate
    sitemap_urls = list(dict.fromkeys(sitemap_urls))

    all_urls = []
    seen_sitemaps = set()

    for sitemap_url in sitemap_urls:
        if sitemap_url in seen_sitemaps:
            continue
        seen_sitemaps.add(sitemap_url)

        xml_text = _fetch_xml(sitemap_url)
        if not xml_text:
            continue

        urls = _parse_sitemap_urls(xml_text)

        # Check if this is a sitemap index (contains other sitemaps)
        sub_sitemaps = [u for u in urls if "sitemap" in u.lower() and u.endswith(".xml")]
        if sub_sitemaps:
            for sub_url in sub_sitemaps[:10]:  # Limit sub-sitemaps
                if sub_url in seen_sitemaps:
                    continue
                seen_sitemaps.add(sub_url)
                sub_xml = _fetch_xml(sub_url)
                if sub_xml:
                    all_urls.extend(_parse_sitemap_urls(sub_xml))
        else:
            all_urls.extend(urls)

        if len(all_urls) >= max_urls * 3:  # Over-fetch, filter later
            break

    # Filter to product URLs
    product_urls = [u for u in all_urls if _PRODUCT_URL_RE.search(u)]

    # If no product-pattern matches, try URLs that look like product pages
    # (not category pages, not static pages)
    if not product_urls and all_urls:
        product_urls = [
            u for u in all_urls
            if len(urlparse(u).path.strip("/").split("/")) >= 2
            and not any(
                skip in u.lower()
                for skip in ["/category", "/tag", "/page/", "/author/", "/blog", "/cart", "/checkout"]
            )
        ]

    product_urls = product_urls[:max_urls]
    logger.info(f"Sitemap: discovered {len(product_urls)} product URLs from {base_url}")
    return product_urls
