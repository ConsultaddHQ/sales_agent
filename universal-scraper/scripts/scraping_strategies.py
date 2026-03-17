#!/usr/bin/env python3
"""
Multi-Tier Scraping Strategies with Fallback
Strategy 1: Basic HTTP (fastest)
Strategy 2: Playwright (handles JS rendering)
Strategy 3: LLM Extraction (most reliable, uses OpenRouter)
"""

import httpx
import time
import random
import logging
from typing import Optional, Tuple, List, Dict, Any
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

logger = logging.getLogger(__name__)


class ScrapingStrategy:
    """Multi-tier scraping with intelligent fallback"""
    
    @staticmethod
    def strategy_1_basic_http(url: str) -> Optional[str]:
        """
        Strategy 1: Basic HTTP request with improved headers
        - Fastest (1-2 seconds)
        - Works for ~70-80% of sites
        - No JavaScript execution
        """
        logger.info("🚀 Strategy 1: Basic HTTP Request")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
            'Referer': 'https://www.google.com/',
        }
        
        try:
            # Random delay to appear more human
            time.sleep(random.uniform(1, 2))
            
            response = httpx.get(
                url,
                headers=headers,
                follow_redirects=True,
                timeout=30
            )
            response.raise_for_status()
            
            html = response.text
            logger.info(f"✅ Strategy 1 succeeded - fetched {len(html)} bytes")
            return html
            
        except httpx.HTTPStatusError as e:
            logger.warning(f"❌ Strategy 1 failed - HTTP {e.response.status_code}: {e}")
            return None
        except Exception as e:
            logger.warning(f"❌ Strategy 1 failed: {e}")
            return None
    
    @staticmethod
    def strategy_2_playwright(url: str, headless: bool = True) -> Optional[str]:
        """
        Strategy 2: Playwright with browser rendering
        - Slower (5-10 seconds)
        - Handles JavaScript rendering
        - Works for ~95% of sites
        - Bypasses basic bot detection
        """
        logger.info("🎭 Strategy 2: Playwright (Browser Rendering)")
        
        try:
            with sync_playwright() as p:
                # Launch Chromium browser
                browser = p.chromium.launch(
                    headless=headless,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-dev-shm-usage',
                        '--no-sandbox',
                    ]
                )
                
                # Create context with realistic settings
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080},
                    locale='en-US',
                    timezone_id='America/New_York',
                    extra_http_headers={
                        'Accept-Language': 'en-US,en;q=0.9',
                    }
                )
                
                # Hide automation signals
                context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                """)
                
                page = context.new_page()
                
                logger.info(f"  → Loading: {url}")
                
                # Navigate with network idle wait
                page.goto(url, wait_until='domcontentloaded', timeout=60000)
                
                logger.info("  → Waiting for product grid...")

                logger.info("  → Waiting for product images...")

                page.wait_for_selector(
                    'img[src*="bewakoof"]',
                    state="visible",
                    timeout=30000
                )
                
                
                logger.info("  → Triggering lazy loading...")

                for _ in range(5):
                    page.mouse.wheel(0, 3000)
                    time.sleep(1.5)
                
                time.sleep(3)  # React hydration 
                
                # Scroll to trigger lazy loading (common for e-commerce)
                logger.info("  → Scrolling to load lazy content...")
                page.evaluate("window.scrollTo(0, document.body.scrollHeight / 3)")
                time.sleep(1)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight * 2 / 3)")
                time.sleep(1)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(2)
                
                # Get final HTML
                html = page.content()

                # Take screenshot BEFORE closing browser
                try:
                    page.screenshot(path="debug_bewakoof.png", full_page=True)
                except Exception as e:
                    logger.warning(f"❌ Failed to take screenshot: {e}")

                logger.info(f"✅ Strategy 2 succeeded - rendered {len(html)} bytes")

                browser.close()

                return html
                
        except PlaywrightTimeout:
            logger.warning(f"❌ Playwright timeout : {e}")
            return None
        except Exception as e:
            logger.warning(f"❌ Strategy 2 failed: {e}")
            return None
    
    @staticmethod
    def validate_html(html: str, min_length: int = 5000) -> bool:
        """
        Quick validation to check if HTML is usable
        Returns True if HTML seems valid and substantial
        """
        if not html or len(html) < min_length:
            return False
        
        # Check for common error pages
        error_indicators = [
            'access denied',
            'forbidden',
            'cloudflare',
            'captcha',
            'robot',
            'automated access',
        ]
        
        html_lower = html.lower()
        for indicator in error_indicators:
            if indicator in html_lower:
                logger.warning(f"  ⚠️  HTML contains '{indicator}' - might be blocked")
                # Don't reject entirely, just warn
        
        return True
    
    @staticmethod
    def contains_products(html: str) -> bool:
        """
        Detect REAL product cards instead of keywords
        """
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")

        product_selectors = [
            '[data-testid*="product"]',
            'article[class*="product"]',
            'div[class*="product-card"]',
            'li[class*="product"]',
            '[itemtype*="Product"]',
        ]

        for selector in product_selectors:
            elements = soup.select(selector)

            # Require REAL count, not UI elements
            if len(elements) >= 10:
                logger.info(f"  → Found {len(elements)} product-like elements")
                return True

        logger.info("  → No real product grid detected")
        return False


def scrape_with_fallback(
    url: str,
    openrouter_key: Optional[str] = None,
    use_llm_fallback: bool = True
) -> Tuple[Optional[str], str, Optional[List[Dict]]]:
    """
    Try scraping strategies in order until one succeeds
    
    Args:
        url: URL to scrape
        openrouter_key: OpenRouter API key for LLM fallback
        use_llm_fallback: Whether to use LLM as final fallback
    
    Returns:
        Tuple of (html_content, strategy_used, llm_products)
        - html_content: HTML string (None if all failed)
        - strategy_used: 'basic_http' | 'playwright' | 'llm' | 'failed'
        - llm_products: List of products if LLM extraction used, else None
    """
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Starting multi-tier scraping for: {url}")
    logger.info(f"{'='*60}\n")
    
    # Strategy 1: Basic HTTP (fastest)
    html = ScrapingStrategy.strategy_1_basic_http(url)
    if (html and ScrapingStrategy.validate_html(html) and ScrapingStrategy.contains_products(html)):
        return html, "basic_http", None
    
    logger.info("⏭️  Strategy 1 insufficient, trying Strategy 2...\n")
    
    # Strategy 2: Playwright (handles JS)
    html = ScrapingStrategy.strategy_2_playwright(url)
    if (html and ScrapingStrategy.validate_html(html) and ScrapingStrategy.contains_products(html)):
        return html, "playwright", None
    
    logger.info("⏭️  Strategy 2 insufficient, trying Strategy 3 (LLM)...\n")
    
    # Strategy 3: LLM Extraction (last resort)
    if use_llm_fallback and openrouter_key:
        from llm_extractor import LLMExtractor
        
        # Try to get HTML first (even if validation failed, LLM might extract from it)
        if not html:
            html = ScrapingStrategy.strategy_2_playwright(url, headless=False)
        
        if html:
            extractor = LLMExtractor(openrouter_key)
            products = extractor.extract_products(html, url)
            
            if products:
                logger.info(f"✅ Strategy 3 (LLM) succeeded - extracted {len(products)} products")
                return html, "llm", products
    
    logger.error(f"\n{'='*60}")
    logger.error(f"❌ All scraping strategies failed for: {url}")
    logger.error(f"{'='*60}\n")
    
    return None, "failed", None


# Quick test function
if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python scraping_strategies.py <url>")
        sys.exit(1)
    
    test_url = sys.argv[1]
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    html, strategy, products = scrape_with_fallback(test_url)
    
    print(f"\n{'='*60}")
    print(f"Result: {strategy}")
    print(f"HTML Length: {len(html) if html else 0}")
    print(f"LLM Products: {len(products) if products else 0}")
    print(f"{'='*60}\n")
