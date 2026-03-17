#!/usr/bin/env python3
"""
LLM-Based Product Extraction
Uses OpenRouter API with cheap models (Gemini, DeepSeek, Grok)
"""

import json
import logging
from typing import List, Dict, Optional, Any
from decimal import Decimal
import re

logger = logging.getLogger(__name__)


class LLMExtractor:
    """Extract product data using LLM when traditional scraping fails"""
    
    # Model preferences (in order)
    MODELS = [
        "google/gemini-2.0-flash-exp:free",  # FREE tier - best choice
        "x-ai/grok-4.1-fast",                  # $0.15/1M tokens (fallback)
    ]
    
    def __init__(self, api_key: str, model: Optional[str] = None):
        """
        Initialize LLM extractor
        
        Args:
            api_key: OpenRouter API key
            model: Specific model to use (optional, defaults to first available)
        """
        self.api_key = api_key
        self.model = model or self.MODELS[0]
        
        logger.info(f"🤖 LLM Extractor initialized with model: {self.model}")
    
    def extract_products(
        self,
        html: str,
        url: str,
        max_products: int = 200
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Extract products from HTML using LLM
        
        Args:
            html: HTML content
            url: Original URL (for context)
            max_products: Maximum products to extract
        
        Returns:
            List of product dictionaries or None if failed
        """
        try:
            import openai
        except ImportError:
            logger.error("openai package not installed. Run: pip install openai")
            return None
        
        logger.info("🤖 Starting LLM extraction...")
        
        # Truncate HTML to avoid token limits
        # Most models have 128k context, but we'll be conservative
        max_html_chars = 80000  # ~20k tokens for HTML
        truncated_html = self._truncate_html_smartly(html, max_html_chars)
        
        logger.info(f"  → HTML truncated: {len(html)} → {len(truncated_html)} chars")
        
        # Create prompt
        prompt = self._build_extraction_prompt(truncated_html, url, max_products)
        
        # Call LLM via OpenRouter
        try:
            client = openai.OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=self.api_key,
            )
            
            logger.info(f"  → Calling {self.model}...")
            
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a precise web scraping assistant. Extract structured product data from HTML. Always return valid JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,  # Low temperature for consistency
                max_tokens=8000,  # Enough for ~50 products
            )
            
            # Parse response
            content = response.choices[0].message.content.strip()
            logger.info(f"  → LLM responded with {len(content)} chars")
            
            # Extract JSON from markdown code blocks if present
            content = self._extract_json_from_response(content)
            
            # Parse JSON
            products = json.loads(content)
            
            if not isinstance(products, list):
                logger.error("LLM response is not a list")
                return None
            
            # Validate and clean products
            valid_products = self._validate_products(products)
            
            logger.info(f"✅ LLM extracted {len(valid_products)} valid products")
            
            return valid_products
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.debug(f"Response was: {content[:500]}")
            return None
        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")
            return None
    
    def _truncate_html_smartly(self, html: str, max_chars: int) -> str:
        """
        Truncate HTML while preserving product-rich sections
        Prioritizes content in <body> and common product containers
        """
        if len(html) <= max_chars:
            return html
        
        # Try to extract just the body
        body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL | re.IGNORECASE)
        if body_match:
            html = body_match.group(1)
        
        # If still too long, take first max_chars
        if len(html) > max_chars:
            html = html[:max_chars]
        
        return html
    
    def _build_extraction_prompt(self, html: str, url: str, max_products: int) -> str:
        """Build the extraction prompt for LLM"""
        
        prompt = f"""Extract product information from this e-commerce page.

URL: {url}

Extract UP TO {max_products} products. For each product, extract:
- title: Product name/title (required)
- price: Numeric price value ONLY, no currency symbols (required)
- image_url: Full image URL (required)
- product_url: Full product page URL (optional)
- description: Brief description (optional)
- availability: "in_stock" or "out_of_stock" (optional, default "in_stock")

IMPORTANT RULES:
1. Return ONLY a JSON array of products
2. NO markdown formatting, NO code blocks, NO explanations
3. Each product MUST have: title, price, image_url
4. Price must be a NUMBER (e.g., 99.99) not a string
5. URLs must be complete (start with http:// or https://)
6. If you can't find enough products, return fewer (don't make up data)

HTML:
{html}

Return JSON array:"""
        
        return prompt
    
    def _extract_json_from_response(self, content: str) -> str:
        """Extract JSON from markdown code blocks if present"""
        
        # Remove markdown code blocks
        json_match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', content, re.DOTALL)
        if json_match:
            return json_match.group(1)
        
        # Try to find JSON array directly
        json_match = re.search(r'(\[\s*\{.*?\}\s*\])', content, re.DOTALL)
        if json_match:
            return json_match.group(1)
        
        return content
    
    def _validate_products(self, products: List[Dict]) -> List[Dict[str, Any]]:
        """
        Validate and clean product data from LLM
        Returns only valid products
        """
        valid_products = []
        
        for idx, product in enumerate(products, 1):
            if not isinstance(product, dict):
                logger.warning(f"Product {idx} is not a dict, skipping")
                continue
            
            # Required fields
            if not product.get('title') and not product.get('name'):
                logger.warning(f"Product {idx} missing title, skipping")
                continue
            
            # Normalize field names (handle both 'title' and 'name')
            cleaned = {
                'name': product.get('title') or product.get('name'),
                'price': None,
                'image_url': product.get('image_url'),
                'product_url': product.get('product_url'),
                'description': product.get('description'),
                'index': idx,
            }
            
            # Parse price
            price_value = product.get('price')
            if price_value is not None:
                try:
                    if isinstance(price_value, str):
                        # Remove currency symbols and commas
                        price_str = re.sub(r'[^\d.]', '', price_value)
                        cleaned['price'] = Decimal(price_str)
                    else:
                        cleaned['price'] = Decimal(str(price_value))
                except:
                    logger.warning(f"Product {idx}: invalid price '{price_value}'")
            
            # Validate URLs
            if cleaned['image_url'] and not cleaned['image_url'].startswith('http'):
                logger.warning(f"Product {idx}: invalid image URL")
                cleaned['image_url'] = None
            
            if cleaned['product_url'] and not cleaned['product_url'].startswith('http'):
                cleaned['product_url'] = None
            
            # Only add if we have minimum required data
            if cleaned['name'] and (cleaned['price'] or cleaned['image_url']):
                valid_products.append(cleaned)
            else:
                logger.warning(f"Product {idx} missing critical data, skipping")
        
        return valid_products


# Test function
if __name__ == '__main__':
    import sys
    import os
    
    if len(sys.argv) < 2:
        print("Usage: python llm_extractor.py <html_file>")
        sys.exit(1)
    
    api_key = os.getenv('OPENROUTER_API_KEY')
    if not api_key:
        print("Error: OPENROUTER_API_KEY not set in environment")
        sys.exit(1)
    
    with open(sys.argv[1], 'r') as f:
        html = f.read()
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s - %(message)s'
    )
    
    extractor = LLMExtractor(api_key)
    products = extractor.extract_products(html, "https://example.com")
    
    print(f"\n{'='*60}")
    print(f"Extracted {len(products) if products else 0} products")
    print(f"{'='*60}\n")
    
    if products:
        for p in products[:5]:
            print(f"- {p['name']}: ${p.get('price', 'N/A')}")
