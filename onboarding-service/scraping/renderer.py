"""Playwright-based page renderer for JS-heavy sites."""

import logging
import time
from typing import Optional

logger = logging.getLogger("onboarding-service")


def render_with_playwright(url: str, scroll: bool = True, wait: int = 3) -> Optional[str]:
    """Render a page with headless Playwright and return the HTML.

    Handles Cloudflare challenges, lazy loading via scrolling.
    """
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
                timezone_id="America/New_York",
            )
            # Hide automation signals
            context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)

            # Handle Cloudflare challenge
            title = page.title()
            if "just a moment" in title.lower():
                logger.info("[CF] Challenge detected — waiting 12s")
                time.sleep(12)

            # Scroll to trigger lazy loading
            if scroll:
                for i in range(5):
                    page.mouse.wheel(0, 800)
                    time.sleep(1.5)

            # Wait for content to stabilize
            time.sleep(wait)

            html = page.content()
            browser.close()

            if "just a moment" in html[:500].lower():
                logger.warning("[CF] Bot protection not resolved after wait")
                return None

            return html

    except Exception as e:
        logger.error(f"Playwright render failed: {e}")
        return None
