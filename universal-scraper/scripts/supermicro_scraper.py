"""
Supermicro GPU Server Scraper
=============================
Two-phase scraper for Supermicro's GPU server catalog.

Phase 1 — Bulk discovery via internal JSON API (bypasses HTML parsing entirely)
Phase 2 — Detail enrichment per product page (key features, memory capacity, core count, etc.)

Uses Playwright (headless Chromium) to bypass bot protection (403 on plain HTTP).
The page's React product selector loads data from:
    /en/structuredbapi/ps2/system/gpu/all

Usage:
    python supermicro_scraper.py

Dependencies:
    pip install playwright beautifulsoup4
    python -m playwright install chromium
"""

import json
import logging
import random
import re
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup
from playwright.sync_api import Browser, BrowserContext, sync_playwright

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger("supermicro_scraper")
logger.setLevel(logging.INFO)

_handler = logging.StreamHandler(sys.stderr)
_handler.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(_handler)


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------


class SupermicroScraper:
    """Two-phase scraper for Supermicro GPU server catalog.

    Phase 1 — Bulk fetch all products from the internal JSON API.
    Phase 2 — Enrich each product with detail page specs (key features,
              memory capacity, core count, dimensions, etc.).

    Bot protection (403) is bypassed by Playwright establishing a browser
    session first, then reusing cookies for all subsequent requests.
    """

    BASE_URL = "https://www.supermicro.com"
    GPU_PAGE_URL = "https://www.supermicro.com/en/products/gpu"
    API_PATH = "/en/structuredbapi/ps2/system/gpu/all"
    SOURCE = "supermicro.com"

    # Timing
    PAGE_TIMEOUT = 45_000          # ms — Playwright navigation timeout
    CF_WAIT = 15                   # seconds to wait for bot challenge
    DELAY_MIN = 2.0                # seconds between detail page loads
    DELAY_MAX = 4.0
    MAX_RETRIES = 3

    USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    # Spec table fields to extract from detail pages
    DETAIL_TABLE_FIELDS = {
        "core_count": "Core Count",
        "memory_detail": "Memory",
        "cpu_gpu_interconnect": "CPU-GPU Interconnect",
        "tdp_note": "Note",
        "pcie_config": "PCI-Express (PCIe) Configuration",
        "drive_bays": "Drive Bays Configuration",
        "liquid_cooling": "Liquid Cooling",
        "lan_detail": "LAN",
        "weight": "Weight",
    }

    # Dimension fields to combine
    DIMENSION_FIELDS = ("Height", "Width", "Depth")

    def __init__(self) -> None:
        self.failed_urls: list[str] = []
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    # ------------------------------------------------------------------
    # Browser lifecycle
    # ------------------------------------------------------------------

    def _start_browser(self) -> None:
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)
        self._context = self._browser.new_context(
            user_agent=self.USER_AGENT,
            viewport={"width": 1920, "height": 1080},
        )
        logger.info("[BROWSER] Chromium launched")

    def _stop_browser(self) -> None:
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

    # ------------------------------------------------------------------
    # Pipeline
    # ------------------------------------------------------------------

    def _run_pipeline(self) -> dict:
        # Phase 1 — Bulk API fetch
        api_products = self._fetch_api_products()
        if not api_products:
            logger.error("[DONE] No products from API — aborting")
            return {"products": [], "total": 0, "failed_urls": []}

        logger.info("[PHASE 1] Got %d products from API", len(api_products))

        # Phase 2 — Detail page enrichment
        products: list[dict] = []
        for i, product in enumerate(api_products, 1):
            url = product.get("product_url", "")
            logger.info("[DETAIL] (%d/%d) %s", i, len(api_products), product.get("sku", ""))

            detail = self._extract_detail(url)
            if detail:
                product.update(detail)
            else:
                self.failed_urls.append(url)
                logger.warning("[DETAIL] Failed — using API-only data for %s", product.get("sku", ""))

            # Build the combined description
            product["description"] = self._build_description(product)
            products.append(product)

            self._polite_delay()

        logger.info(
            "[DONE] %d products scraped, %d detail enrichments failed",
            len(products), len(self.failed_urls),
        )

        return {
            "products": products,
            "total": len(products),
            "failed_urls": self.failed_urls,
        }

    # ------------------------------------------------------------------
    # Phase 1 — Bulk API fetch
    # ------------------------------------------------------------------

    def _fetch_api_products(self) -> List[Dict[str, Any]]:
        """Navigate to GPU page (establishes session), then fetch JSON API."""
        page = None
        try:
            page = self._context.new_page()

            # Visit GPU page to establish session and clear bot protection
            logger.info("[API] Navigating to %s", self.GPU_PAGE_URL)
            page.goto(self.GPU_PAGE_URL, wait_until="domcontentloaded", timeout=self.PAGE_TIMEOUT)

            # Check for bot challenge
            title = page.title()
            if "just a moment" in title.lower():
                logger.info("[CF] Challenge detected — waiting %ds", self.CF_WAIT)
                time.sleep(self.CF_WAIT)

            time.sleep(3)

            # Fetch the API via page context (uses established cookies)
            logger.info("[API] Fetching %s", self.API_PATH)
            data = page.evaluate(
                f'fetch("{self.API_PATH}").then(r => r.json())'
            )

            if not isinstance(data, dict) or "items" not in data:
                logger.error("[API] Unexpected response structure: %s", type(data))
                return []

            items = data["items"]
            logger.info("[API] Received %d items", len(items))

            return [self._parse_api_item(item) for item in items]

        except Exception as exc:
            logger.error("[API] Failed: %s", exc)
            return []
        finally:
            if page:
                try:
                    page.close()
                except Exception:
                    pass

    def _parse_api_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a raw API item into our product dict."""

        def detail(field: str) -> str:
            """Extract the 'detail' value from a field dict, or str/int directly."""
            val = item.get(field, "")
            if isinstance(val, dict):
                return str(val.get("detail", "")).strip()
            return str(val).strip() if val else ""

        return {
            "name": f"{item.get('Description', '')} ({item.get('SKU', '')})".strip(),
            "sku": item.get("SKU", ""),
            "product_url": item.get("Link", ""),
            "image_url": item.get("Image", ""),
            "price": "",
            "source": self.SOURCE,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "is_new": item.get("New", False),
            "is_coming": item.get("Coming", False),
            # API spec fields
            "form_factor": detail("Form Factor"),
            "max_gpu": detail("Max GPU"),
            "supported_gpus": detail("Supported GPUs"),
            "cpu_type": detail("CPU Type"),
            "gpu_architecture": detail("GPU Architecture"),
            "gpu_gpu_interconnect": detail("GPU-GPU"),
            "applications": detail("Applications"),
            "cooling_type": detail("Cooling Type"),
            "networking": detail("Networking"),
            "total_power": detail("Total Power"),
            "dimm_slots": detail("DIMM Slots"),
            "drives": detail("Drives"),
            "pcie_slots": detail("Total PCI-E Slots#"),
            "redundant_power": detail("Redundant Power"),
            "interface": detail("Interface"),
            "product_group": detail("Product Group"),
            "generation": detail("Generation"),
            # Detail page fields (populated in Phase 2)
            "key_features": "",
            "key_applications": "",
            "core_count": "",
            "memory_detail": "",
            "cpu_gpu_interconnect": "",
            "tdp_note": "",
            "pcie_config": "",
            "drive_bays": "",
            "liquid_cooling": "",
            "lan_detail": "",
            "dimensions": "",
            "weight": "",
            # Description built after enrichment
            "description": "",
        }

    # ------------------------------------------------------------------
    # Phase 2 — Detail page enrichment
    # ------------------------------------------------------------------

    def _extract_detail(self, url: str) -> Optional[Dict[str, Any]]:
        """Fetch a product detail page and extract enrichment fields."""
        if not url:
            return None

        html = self._fetch_page(url)
        if not html:
            return None

        soup = BeautifulSoup(html, "html.parser")
        result: Dict[str, Any] = {}

        # --- Key Applications & Key Features ---
        feature_el = soup.select_one('[class*="feature"]')
        if feature_el:
            text = feature_el.get_text("\n", strip=True)
            if "Key Applications" in text and "Key Features" in text:
                apps_part = text.split("Key Features")[0].replace("Key Applications", "").strip()
                features_part = text.split("Key Features")[1].strip()
                # Clean up trailing "Get Pricing", "Compare", "Configure & Buy"
                for cutoff in ["Get Pricing", "Compare", "Configure & Buy"]:
                    if cutoff in features_part:
                        features_part = features_part[:features_part.index(cutoff)].strip()
                result["key_applications"] = apps_part
                result["key_features"] = features_part
            elif "Key Applications" in text:
                apps_part = text.replace("Key Applications", "").strip()
                result["key_applications"] = apps_part

        # --- Spec table extraction ---
        spec_data = self._extract_spec_tables(soup)

        for our_key, table_label in self.DETAIL_TABLE_FIELDS.items():
            if table_label in spec_data:
                val = spec_data[table_label]
                # Clean "View ... Options" suffixes
                val = re.sub(r"\s*View \w+ Options\s*", "", val).strip()
                result[our_key] = val

        # --- Dimensions (combine H x W x D) ---
        dims = []
        for dim_field in self.DIMENSION_FIELDS:
            if dim_field in spec_data:
                dims.append(spec_data[dim_field])
        if dims:
            result["dimensions"] = " x ".join(dims)

        return result

    def _extract_spec_tables(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Extract key-value pairs from all spec tables on the page."""
        spec_data: Dict[str, str] = {}

        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all(["td", "th"])
                if len(cells) >= 2:
                    key = cells[0].get_text(strip=True)
                    val = cells[1].get_text("\n", strip=True)
                    if key and val and len(key) < 80:
                        spec_data[key] = val[:500]

        return spec_data

    # ------------------------------------------------------------------
    # Description builder
    # ------------------------------------------------------------------

    def _build_description(self, product: Dict[str, Any]) -> str:
        """Build a rich natural-language description from all available fields.

        This text feeds the embedding model (all-MiniLM-L6-v2) and should
        contain all searchable specs in readable form.
        """
        parts: list[str] = []

        sku = product.get("sku", "")
        form_factor = product.get("form_factor", "")
        api_desc = product.get("name", "").split("(")[0].strip()

        # Header
        header = f"Supermicro SuperServer {sku}."
        if form_factor:
            header += f" {form_factor} rackmount GPU server."
        parts.append(header)

        # Key features (from detail page — natural language, great for embeddings)
        if product.get("key_features"):
            parts.append(product["key_features"])

        # GPU info
        gpu_parts = []
        if product.get("max_gpu"):
            gpu_parts.append(product["max_gpu"])
        if product.get("supported_gpus"):
            gpu_parts.append(f"Supporting {product['supported_gpus']}")
        if product.get("gpu_architecture"):
            gpu_parts.append(f"GPU architecture: {product['gpu_architecture']}")
        if product.get("gpu_gpu_interconnect"):
            gpu_parts.append(f"GPU-GPU interconnect: {product['gpu_gpu_interconnect']}")
        if gpu_parts:
            parts.append(". ".join(gpu_parts) + ".")

        # CPU info
        cpu_parts = []
        if product.get("cpu_type"):
            cpu_parts.append(product["cpu_type"])
        if product.get("core_count"):
            cpu_parts.append(f"{product['core_count']} cores")
        if product.get("tdp_note"):
            cpu_parts.append(product["tdp_note"])
        if product.get("cpu_gpu_interconnect"):
            cpu_parts.append(f"CPU-GPU interconnect: {product['cpu_gpu_interconnect']}")
        if cpu_parts:
            parts.append(". ".join(cpu_parts) + ".")

        # Memory
        if product.get("memory_detail"):
            parts.append(f"Memory: {product['memory_detail']}.")
        elif product.get("dimm_slots"):
            parts.append(f"{product['dimm_slots']} DIMM slots.")

        # Storage
        storage_parts = []
        if product.get("drive_bays"):
            storage_parts.append(product["drive_bays"])
        elif product.get("drives"):
            storage_parts.append(f"{product['drives']} drives")
        if product.get("interface"):
            storage_parts.append(product["interface"])
        if storage_parts:
            parts.append("Storage: " + ". ".join(storage_parts) + ".")

        # Networking
        if product.get("lan_detail"):
            parts.append(f"Networking: {product['lan_detail']}.")
        elif product.get("networking"):
            parts.append(f"Networking: {product['networking']}.")

        # PCIe
        if product.get("pcie_config"):
            parts.append(f"PCIe: {product['pcie_config']}.")
        elif product.get("pcie_slots"):
            parts.append(f"{product['pcie_slots']} PCIe slots.")

        # Cooling & Power
        infra_parts = []
        if product.get("cooling_type"):
            infra_parts.append(product["cooling_type"])
        if product.get("liquid_cooling"):
            infra_parts.append(f"Liquid cooling: {product['liquid_cooling']}")
        if product.get("total_power"):
            infra_parts.append(product["total_power"])
        if product.get("redundant_power") == "Yes":
            infra_parts.append("Redundant power")
        if infra_parts:
            parts.append(". ".join(infra_parts) + ".")

        # Physical
        phys_parts = []
        if product.get("dimensions"):
            phys_parts.append(f"Dimensions: {product['dimensions']}")
        if product.get("weight"):
            phys_parts.append(f"Weight: {product['weight']}")
        if phys_parts:
            parts.append(". ".join(phys_parts) + ".")

        # Applications
        if product.get("applications"):
            parts.append(f"Applications: {product['applications']}.")

        # Status flags
        if product.get("is_new"):
            parts.append("New product.")
        if product.get("is_coming"):
            parts.append("Coming soon.")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Page fetching (Playwright — handles bot protection)
    # ------------------------------------------------------------------

    def _fetch_page(self, url: str) -> Optional[str]:
        """Fetch a page using Playwright, waiting for bot protection to clear.

        Returns the rendered HTML string, or None on failure.
        Retries up to MAX_RETRIES times.
        """
        for attempt in range(1, self.MAX_RETRIES + 1):
            page = None
            try:
                page = self._context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=self.PAGE_TIMEOUT)

                title = page.title()
                if "just a moment" in title.lower():
                    logger.info("[CF] Challenge detected — waiting %ds", self.CF_WAIT)
                    time.sleep(self.CF_WAIT)

                # Wait for content to settle
                time.sleep(2)

                content = page.content()

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
    scraper = SupermicroScraper()
    result = scraper.run()
    # Products to stdout (for piping), logs to stderr
    print(json.dumps(result, indent=2))
