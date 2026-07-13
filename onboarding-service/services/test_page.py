"""Consolidated test page generator.

Replaces the older per-store test-page generators with one shared flow.
"""

import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Comment

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from shared.config import WIDGET_SCRIPT_URL, PUBLIC_SEARCH_API_URL

logger = logging.getLogger("onboarding-service")

DEMO_PAGES_DIR = Path("./demo_pages")


def _fetch_via_http(url: str) -> Optional[str]:
    """Fetch page via plain HTTP. Fast, works for most Shopify stores."""
    try:
        headers = {"User-Agent": "TeamPop-Onboarding/2.0"}
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        return response.text
    except Exception as e:
        logger.warning(f"HTTP fetch failed ({e})")
        return None


def _fetch_via_playwright(url: str, challenge_wait: int = 10) -> Optional[str]:
    """Fetch page via Playwright headless browser.

    Handles Cloudflare / bot protection challenges.
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
                viewport={"width": 1280, "height": 900},
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=45_000)

            title = page.title()
            if "just a moment" in title.lower():
                logger.info(f"[CF] Challenge detected — waiting {challenge_wait}s")
                time.sleep(challenge_wait)

            html = page.content()
            browser.close()

            if "just a moment" in html[:500].lower():
                logger.warning("[CF] Bot protection not resolved")
                return None
            return html
    except Exception as e:
        logger.error(f"Playwright fetch failed: {e}")
        return None


def _fix_srcset(base_url: str, srcset: str) -> str:
    """Resolve relative URLs inside a srcset attribute against base_url."""
    parts = []
    for candidate in srcset.split(","):
        candidate = candidate.strip()
        if not candidate:
            continue
        tokens = candidate.split(None, 1)
        url = urljoin(base_url, tokens[0])
        parts.append(f"{url} {tokens[1]}" if len(tokens) > 1 else url)
    return ", ".join(parts)


def _process_html(
    soup: BeautifulSoup,
    base_url: str,
    strip_all_scripts: bool = False,
) -> None:
    """Fix relative URLs, strip scripts/iframes/comments in-place."""
    # Fix relative URLs -> absolute
    for tag in soup.find_all(["img", "source"], src=True):
        tag["src"] = urljoin(base_url, tag["src"])
    for tag in soup.find_all(["img", "source"], srcset=True):
        tag["srcset"] = _fix_srcset(base_url, tag["srcset"])
    for tag in soup.find_all("script", src=True):
        tag["src"] = urljoin(base_url, tag["src"])
    for tag in soup.find_all("link", href=True):
        tag["href"] = urljoin(base_url, tag["href"])
    for tag in soup.find_all("a", href=True):
        href = tag["href"]
        if not href.startswith(("http", "https", "mailto", "tel", "#", "javascript")):
            tag["href"] = urljoin(base_url, href)

    # Force visibility for JS-dependent reveal animations that won't fire
    # on scraped pages (Shopify themes hide sections until theme.js runs).
    for tag in soup.find_all(attrs={"reveal-on-scroll": True}):
        del tag["reveal-on-scroll"]
    override_style = soup.new_tag("style")
    override_style.string = (
        "[reveal-on-scroll] { opacity: 1 !important; }"
        " img { opacity: 1 !important; visibility: visible !important; }"
    )
    head = soup.find("head")
    if head:
        head.append(override_style)

    if strip_all_scripts:
        # Playwright pages: strip ALL scripts (they break when served from localhost)
        for script in soup.find_all("script"):
            script.decompose()
    else:
        # HTTP pages: only strip analytics/tracking scripts
        kill_patterns = [
            "google-analytics", "googletagmanager", "gtag", "hotjar",
            "clarity", "facebook", "mixpanel", "posthog", "snitcher",
        ]
        for script in soup.find_all("script"):
            src = script.get("src", "")
            content = script.string or ""
            combined = (src + content).lower()
            if any(p in combined for p in kill_patterns):
                script.decompose()

    # Remove preload script links
    for link in soup.find_all("link", attrs={"as": "script"}):
        link.decompose()

    # Remove hidden iframes (Cloudflare challenge frames)
    for iframe in soup.find_all("iframe"):
        style = iframe.get("style", "")
        if "visibility: hidden" in style or (
            iframe.get("width") == "1" and iframe.get("height") == "1"
        ):
            iframe.decompose()

    # Remove <noscript> blocks
    for noscript in soup.find_all("noscript"):
        noscript.decompose()

    # Remove HTML comments (can break parsing of injected scripts)
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()


def _inject_widget(soup: BeautifulSoup, agent_id: str, store_id: str = "", cart_enabled: str = "false") -> None:
    """Inject TeamPop widget config and script into the page."""
    widget_script_url = WIDGET_SCRIPT_URL()
    api_url = PUBLIC_SEARCH_API_URL()

    head = soup.find("head") or soup.new_tag("head")
    body = soup.find("body") or soup.new_tag("body")

    # Agent id is baked into the page at generation time, but a URL override
    # (`?agent=<id>`) wins so the same demo page can be used to A/B test
    # multiple ElevenLabs agents without regenerating. Used by the latency
    # test protocol (docs/latency-test-protocol.md) to compare candidate LLMs.
    config_script = soup.new_tag("script")
    config_script.string = f"""
    (function() {{
      var params = new URLSearchParams(window.location.search);
      var override = params.get('agent');
      window.__TEAM_POP_AGENT_ID__ = override || "{agent_id}";
      window.__TEAM_POP_STORE_ID__ = "{store_id}";
      window.__TEAM_POP_CART_ENABLED__ = {cart_enabled};
      window.__TEAM_POP_API_URL__ = "{api_url}";
      window.__TEAM_POP_DEMO__ = true;
      console.log(
        '[TeamPop] Widget config loaded — agent:',
        window.__TEAM_POP_AGENT_ID__,
        override ? '(URL override)' : '(baked)'
      );
    }})();
    """
    head.append(config_script)

    widget_tag = soup.new_tag("script")
    widget_tag["src"] = widget_script_url
    body.append(widget_tag)

    agent_el = soup.new_tag("team-pop-agent")
    body.append(agent_el)


def generate_test_page(
    store_url: str,
    store_id: str,
    agent_id: str,
    use_playwright: bool = False,
    challenge_wait: int = 10,
    store_type: str = "shopify",
) -> str:
    """Generate a static test page with the widget injected.

    Args:
        store_url: The store's real URL.
        store_id: Store UUID.
        agent_id: ElevenLabs agent ID.
        use_playwright: Use Playwright (for Cloudflare/bot-protected sites).
        challenge_wait: Seconds to wait for bot challenge resolution.
        store_type: Platform type (shopify, threadless, supermicro, etc.).

    Returns:
        Filename of the saved page (e.g. "test_abc12345.html").
    """
    DEMO_PAGES_DIR.mkdir(exist_ok=True)

    logger.info(f"Generating test page for {store_url} (playwright={use_playwright})")

    # Fetch
    if use_playwright:
        html = _fetch_via_playwright(store_url, challenge_wait=challenge_wait)
    else:
        html = _fetch_via_http(store_url)

    if html:
        soup = BeautifulSoup(html, "html.parser")
        logger.info("Fetched real store page")
    else:
        logger.warning("Fetch failed, using blank template")
        soup = BeautifulSoup(
            "<html><head><title>Store Preview</title></head><body></body></html>",
            "html.parser",
        )

    base_url = f"{urlparse(store_url).scheme}://{urlparse(store_url).netloc}"

    _process_html(soup, base_url, strip_all_scripts=use_playwright)
    cart_enabled = "true" if store_type == "shopify" else "false"
    _inject_widget(soup, agent_id, store_id=store_id, cart_enabled=cart_enabled)

    filename = f"test_{store_id[:8]}.html"
    output_path = DEMO_PAGES_DIR / filename
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(str(soup))

    logger.info(f"Test page saved: {output_path}")
    return filename
