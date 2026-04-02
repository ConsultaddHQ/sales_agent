"""
Threadless Store Scraper
========================
Scraping-only module for nurdluv.threadless.com.
No database, no embeddings — returns structured product dicts.

Strategy:
  Phase 1 — Discovery via sitemap-products.xml (bypasses Cloudflare pagination block)
  Phase 2 — Detail extraction per product page using HTML selectors

Uses Playwright (headless Chromium) to handle Cloudflare JS challenges,
then BeautifulSoup for HTML parsing.

Usage:
    python threadless_scraper.py

Dependencies:
    pip install playwright beautifulsoup4
    python -m playwright install chromium
"""

import json
import logging
import random
import sys
import time
from datetime import datetime, timezone
from typing import Optional

from bs4 import BeautifulSoup
from playwright.sync_api import Browser, BrowserContext, sync_playwright

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger("threadless_scraper")
logger.setLevel(logging.INFO)

_handler = logging.StreamHandler(sys.stderr)
_handler.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(_handler)


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------


class ThreadlessScraper:
    """Two-phase scraper for a Threadless artist shop.

    Phase 1 — Discovery:  fetch sitemap-products.xml for all product URLs.
    Phase 2 — Enrichment: fetch each product detail page, extract all fields
              via HTML selectors (h1, productDescription-container,
              productField-button--price, productHero-image).

    Cloudflare blocks headless-browser pagination (?page=N), so we use the
    sitemap for discovery (publicly accessible XML, not behind CF challenge).
    """

    BASE_URL = "https://nurdluv.threadless.com"
    SITEMAP_URL = "https://nurdluv.threadless.com/sitemap-products.xml"
    SOURCE = "nurdluv.threadless.com"

    # Timing
    PAGE_TIMEOUT = 30_000         # ms — Playwright navigation timeout
    CF_WAIT = 10                  # seconds to wait for Cloudflare challenge
    DELAY_MIN = 1.5               # seconds between page loads
    DELAY_MAX = 3.0
    MAX_RETRIES = 3

    USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    def __init__(self) -> None:
        self.failed_urls: list[str] = []
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    # ------------------------------------------------------------------
    # Browser lifecycle
    # ------------------------------------------------------------------

    def _start_browser(self) -> None:
        """Launch headless Chromium and create a persistent context."""
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)
        self._context = self._browser.new_context(
            user_agent=self.USER_AGENT,
            viewport={"width": 1280, "height": 900},
        )
        logger.info("[BROWSER] Chromium launched")

    def _stop_browser(self) -> None:
        """Shut down browser and Playwright."""
        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
        logger.info("[BROWSER] Closed")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> dict:
        """Run full scrape pipeline and return results.

        Returns:
            {
                "products": [ ... ],
                "total": int,
                "failed_urls": [ ... ]
            }
        """
        self._start_browser()
        try:
            return self._run_pipeline()
        finally:
            self._stop_browser()

    def _run_pipeline(self) -> dict:
        """Internal pipeline after browser is ready."""

        # Phase 1 — Discover all product URLs from sitemap
        product_urls = self.discover_products()

        if not product_urls:
            logger.error("[DONE] No products discovered — aborting")
            return {"products": [], "total": 0, "failed_urls": []}

        # Phase 2 — Extract each product from its detail page
        products: list[dict] = []
        for i, url in enumerate(product_urls, 1):
            logger.info("[DETAIL] (%d/%d) %s", i, len(product_urls), url)

            product = self._extract_product(url)
            if product:
                products.append(product)
            else:
                self.failed_urls.append(url)

            self._polite_delay()

        logger.info(
            "[DONE] %d products scraped, %d failed",
            len(products), len(self.failed_urls),
        )

        return {
            "products": products,
            "total": len(products),
            "failed_urls": self.failed_urls,
        }

    # ------------------------------------------------------------------
    # Phase 1 — Product discovery via sitemap
    # ------------------------------------------------------------------

    def discover_products(self) -> list[str]:
        """Fetch sitemap-products.xml and extract all /designs/ URLs.

        The sitemap is publicly accessible XML, not behind Cloudflare.
        Returns deduplicated list of product URLs.
        """
        logger.info("[DISCOVER] Fetching sitemap: %s", self.SITEMAP_URL)

        html = self._fetch_page(self.SITEMAP_URL)
        if html is None:
            logger.error("[DISCOVER] Failed to fetch sitemap")
            return []

        soup = BeautifulSoup(html, "html.parser")
        locs = soup.select("loc")

        product_urls: list[str] = []
        seen: set[str] = set()

        for loc in locs:
            url = loc.get_text(strip=True)
            if "/designs/" in url and url not in seen:
                seen.add(url)
                product_urls.append(url)

        logger.info("[DISCOVER] Found %d unique product URLs", len(product_urls))
        return product_urls

    # ------------------------------------------------------------------
    # Phase 2 — Product detail extraction
    # ------------------------------------------------------------------

    def _extract_product(self, url: str) -> Optional[dict]:
        """Fetch product detail page and extract all fields via HTML selectors.

        Selectors (verified against live site):
            h1                                             → product name
            div.productDescription-container → p           → description
            ul.productField-grid
                → li.productField-button--price → span     → price
            img.productHero-image                          → image URL
        """
        html = self._fetch_page(url)
        if html is None:
            return None

        soup = BeautifulSoup(html, "html.parser")

        # --- Name from <h1> ---
        name = ""
        h1 = soup.select_one("h1")
        if h1:
            name = h1.get_text(strip=True)
            # Strip "Shop ..., on a men's t-shirt" wrapper
            if name.startswith("Shop "):
                name = name[5:]
                if ", on a " in name:
                    name = name[: name.index(", on a ")]

        # --- Description ---
        description = ""
        desc_container = soup.select_one("div.productDescription-container")
        if desc_container:
            paragraphs = desc_container.select("p")
            description = " ".join(
                p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)
            )

        # --- Price ---
        price = ""
        price_item = soup.select_one(
            "ul.productField-grid li.productField-button--price"
        )
        if price_item:
            spans = price_item.select("span")
            no_class_spans = [s for s in spans if not s.get("class")]
            if no_class_spans:
                target = no_class_spans[1] if len(no_class_spans) >= 2 else no_class_spans[0]
                price = target.get_text(strip=True)

        # --- Image ---
        image_url = ""
        for selector in [
            "img.productHero-image",
            'img[alt*="Thumbnail image of the design"]',
            'img[src*="/products/"][src*="cdn-images.threadless.com"]',
        ]:
            img = soup.select_one(selector)
            if img:
                src = img.get("src", "") or img.get("data-src", "")
                if src and "/products/" in src:
                    image_url = src
                    break

        return {
            "name": name,
            "product_url": url,
            "image_url": image_url,
            "price": price,
            "description": description,
            "source": self.SOURCE,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # Page fetching (Playwright — handles Cloudflare)
    # ------------------------------------------------------------------

    def _fetch_page(self, url: str) -> Optional[str]:
        """Fetch a page using Playwright, waiting for Cloudflare to clear.

        Returns the rendered HTML string, or None on failure.
        Retries up to MAX_RETRIES times.
        """
        for attempt in range(1, self.MAX_RETRIES + 1):
            page = None
            try:
                page = self._context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=self.PAGE_TIMEOUT)

                # Wait for Cloudflare challenge to resolve
                title = page.title()
                if "just a moment" in title.lower():
                    logger.info("[CF] Challenge detected — waiting %ds", self.CF_WAIT)
                    time.sleep(self.CF_WAIT)

                content = page.content()

                # Verify we got real content
                if "just a moment" in content[:500].lower():
                    logger.warning("[CF] Not resolved on attempt %d", attempt)
                    continue

                return content

            except Exception as exc:
                logger.error("[ERROR] Attempt %d for %s — %s", attempt, url, exc)

            finally:
                if page:
                    try:
                        page.close()
                    except Exception:
                        pass

        logger.error("[ERROR] All %d attempts failed for %s", self.MAX_RETRIES, url)
        return None

    def _polite_delay(self) -> None:
        """Random sleep between requests to be respectful."""
        time.sleep(random.uniform(self.DELAY_MIN, self.DELAY_MAX))


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    scraper = ThreadlessScraper()
    result = scraper.run()
    # Products to stdout (for piping), logs to stderr
    print(json.dumps(result, indent=2))
