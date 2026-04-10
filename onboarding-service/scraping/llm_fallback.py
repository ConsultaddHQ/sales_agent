"""LLM-based product extraction — last resort fallback.

Uses OpenRouter (Gemini/Grok) to extract products from raw HTML.
~98% success rate but slower and costs money.
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("onboarding-service")


def extract_with_llm(html: str, max_products: int = 50) -> List[Dict[str, Any]]:
    """Extract products from HTML using an LLM.

    Sends truncated HTML to OpenRouter API and asks for structured product data.

    Returns list of Shopify-normalized product dicts.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        logger.warning("LLM extraction skipped: OPENROUTER_API_KEY not set")
        return []

    # Truncate HTML to avoid token limits
    body_html = html
    body_start = html.lower().find("<body")
    if body_start > 0:
        body_html = html[body_start:]
    body_html = body_html[:80_000]

    prompt = f"""Extract ALL products from this e-commerce page HTML.

For each product, return a JSON object with these fields:
- "name": product name (string)
- "price": price as a number string e.g. "29.99" (or null if not found)
- "image_url": full image URL (or null)
- "product_url": full product page URL (or null)
- "description": short description (or "")

Return a JSON array of products. Example:
[{{"name": "Red T-Shirt", "price": "29.99", "image_url": "https://...", "product_url": "https://...", "description": "Cotton blend tee"}}]

Return ONLY the JSON array, no other text.

HTML:
{body_html}"""

    try:
        import httpx

        model = os.getenv("OPENROUTER_MODEL_FALLBACK", "google/gemini-2.0-flash-exp:free")
        base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

        resp = httpx.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 4000,
                "temperature": 0.1,
            },
            timeout=60,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]

        # Extract JSON from response (may be wrapped in markdown code blocks)
        json_match = re.search(r"\[[\s\S]*\]", content)
        if not json_match:
            logger.warning("LLM extraction: no JSON array found in response")
            return []

        raw_products = json.loads(json_match.group())
        if not isinstance(raw_products, list):
            return []

        # Normalize to Shopify format
        products = []
        for p in raw_products[:max_products]:
            name = p.get("name", "").strip()
            if not name:
                continue

            handle = re.sub(r"[^a-z0-9-]", "-", name.lower())[:60].strip("-")

            products.append({
                "handle": handle,
                "title": name,
                "body_html": p.get("description", ""),
                "variants": [{"price": str(p["price"])}] if p.get("price") else [],
                "images": [{"src": p["image_url"]}] if p.get("image_url") else [],
                "_original_product_url": p.get("product_url", ""),
            })

        logger.info(f"LLM extraction: got {len(products)} products")
        return products

    except Exception as e:
        logger.error(f"LLM extraction failed: {e}")
        return []
