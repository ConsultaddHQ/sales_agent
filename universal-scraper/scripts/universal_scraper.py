#!/usr/bin/env python3
"""
IMPROVED Universal E-commerce Product Scraper
With site-specific logic for Amazon, MediaMarkt, and generic fallback
"""

import os
import re
import json
import argparse
import requests
import hashlib
import uuid
from pathlib import Path
from urllib.parse import urljoin, urlparse
from typing import List, Dict, Optional, Any
from decimal import Decimal
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from supabase import create_client, Client
from sentence_transformers import SentenceTransformer
import logging
from scraping_strategies import scrape_with_fallback
from llm_extractor import LLMExtractor



logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()


class SiteSpecificScrapers:
    """Site-specific scraping logic for maximum reliability"""
    
    @staticmethod
    def is_amazon(domain: str) -> bool:
        return 'amazon' in domain.lower()
    
    @staticmethod
    def is_mediamarkt(domain: str) -> bool:
        return 'mediamarkt' in domain.lower()
    
    @staticmethod
    def scrape_amazon(soup: BeautifulSoup, base_url: str) -> List[Dict]:
        """Amazon-specific scraping - handles search results"""
        products = []
        
        # Amazon search results use this data attribute
        for idx, item in enumerate(soup.select('[data-component-type="s-search-result"]'), 1):
            try:
                product = {'index': idx}
                
                # Title
                title_el = item.select_one('h2 a span')
                if not title_el:
                    title_el = item.select_one('.a-size-medium')
                if title_el:
                    product['name'] = title_el.get_text(strip=True)
                
                # Price - Amazon has multiple formats
                price_whole = item.select_one('.a-price-whole')
                if price_whole:
                    price_str = price_whole.get_text(strip=True).replace(',', '').replace('.', '')
                    price_fraction = item.select_one('.a-price-fraction')
                    if price_fraction:
                        price_str += '.' + price_fraction.get_text(strip=True)
                    try:
                        product['price'] = Decimal(price_str)
                    except:
                        pass
                
                # Image - Amazon uses data-src for lazy loading
                img = item.select_one('img.s-image')
                if img:
                    product['image_url'] = img.get('src') or img.get('data-src')
                    # Remove size parameters for higher quality
                    if product.get('image_url'):
                        product['image_url'] = re.sub(r'_[A-Z0-9]+_\.', '.', product['image_url'])
                
                # Product URL
                link = item.select_one('h2 a')
                if not link:
                    link = item.select_one('a.a-link-normal')
                if link:
                    href = link.get('href')
                    if href:
                        product['product_url'] = urljoin(base_url, href)
                
                # Description from ratings and features
                desc_parts = []
                
                # Rating
                rating = item.select_one('.a-icon-alt')
                if rating:
                    desc_parts.append(rating.get_text(strip=True))
                
                # Features/bullets
                features = item.select('.a-size-base.a-color-secondary')
                for feat in features[:3]:
                    text = feat.get_text(strip=True)
                    if len(text) > 10 and text not in desc_parts:
                        desc_parts.append(text)
                
                if desc_parts:
                    product['description'] = ' | '.join(desc_parts)[:500]
                
                if product.get('name'):
                    products.append(product)
                    logger.debug(f"  ✓ Amazon product: {product['name'][:50]}")
                    
            except Exception as e:
                logger.debug(f"Failed to parse Amazon item {idx}: {e}")
                continue
        
        return products
    
    @staticmethod
    def scrape_mediamarkt(soup: BeautifulSoup, base_url: str) -> List[Dict]:
        """MediaMarkt-specific scraping"""
        products = []
        
        # MediaMarkt uses these selectors
        selectors_to_try = [
            '[data-test="mms-product-list-item"]',
            '.ProductListItem',
            'article[data-test*="product"]',
            'div[class*="ProductCard"]',
        ]
        
        product_elements = []
        for selector in selectors_to_try:
            elements = soup.select(selector)
            if elements:
                product_elements = elements
                logger.info(f"Found {len(elements)} MediaMarkt products using: {selector}")
                break
        
        for idx, item in enumerate(product_elements, 1):
            try:
                product = {'index': idx}
                
                # Title
                title_selectors = [
                    '[data-test="product-title"]',
                    'h2', 'h3',
                    '.ProductTitle',
                    '[class*="title"]',
                ]
                for sel in title_selectors:
                    title_el = item.select_one(sel)
                    if title_el:
                        product['name'] = title_el.get_text(strip=True)
                        break
                
                # Price - European format: 99,99 €
                price_selectors = [
                    '[data-test="product-price"]',
                    '.Price',
                    '[class*="price"]',
                ]
                for sel in price_selectors:
                    price_el = item.select_one(sel)
                    if price_el:
                        price_text = price_el.get_text(strip=True)
                        # Match "99,99" or "99.99" or "99"
                        match = re.search(r'(\d+[.,]?\d*)', price_text.replace('.', '').replace(',', '.'))
                        if match:
                            try:
                                product['price'] = Decimal(match.group(1))
                                break
                            except:
                                pass
                
                # Image
                img = item.select_one('img')
                if img:
                    product['image_url'] = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                
                # Product URL
                link = item.select_one('a[href]')
                if link:
                    href = link.get('href')
                    if href:
                        product['product_url'] = urljoin(base_url, href)
                
                # Description
                desc_parts = []
                desc_selectors = item.select('[data-test*="attribute"], [class*="feature"], li')
                for desc_el in desc_selectors[:3]:
                    text = desc_el.get_text(strip=True)
                    if len(text) > 10 and text not in desc_parts:
                        desc_parts.append(text)
                
                if desc_parts:
                    product['description'] = ' | '.join(desc_parts)[:500]
                
                if product.get('name'):
                    products.append(product)
                    logger.debug(f"  ✓ MediaMarkt product: {product['name'][:50]}")
                    
            except Exception as e:
                logger.debug(f"Failed to parse MediaMarkt item {idx}: {e}")
                continue
        
        return products


class UniversalScraper:
    def __init__(self, supabase_url: str, supabase_key: str, images_dir: str = "./product_images"):
        self.supabase: Client = create_client(supabase_url, supabase_key)
        self.images_dir = Path(images_dir)
        self.images_dir.mkdir(exist_ok=True, parents=True)
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        })
        
        logger.info("Loading embedding model...")
        self.embedder = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
        logger.info("Model loaded successfully")
    
    def validate_product(self, product: Dict) -> bool:
        """Ensure product has minimum required fields"""
        if not product.get('name'):
            return False
        
        # Should have at least 2 of these
        important_fields = ['price', 'image_url', 'product_url']
        has_count = sum(1 for field in important_fields if product.get(field))
        
        if has_count < 2:
            logger.warning(f"Product '{product.get('name')}' only has {has_count}/3 important fields")
            return False
        
        return True
    
    def download_image(self, image_url: str, store_id: str, product_handle: str) -> Optional[str]:
        """Download image and return local relative path"""
        try:
            store_dir = self.images_dir / store_id
            store_dir.mkdir(exist_ok=True, parents=True)
            
            url_hash = hashlib.md5(image_url.encode()).hexdigest()[:8]
            ext = Path(urlparse(image_url).path).suffix or '.jpg'
            if ext not in ['.jpg', '.jpeg', '.png', '.webp', '.gif']:
                ext = '.jpg'
            
            filename = f"{product_handle}_{url_hash}{ext}"
            filepath = store_dir / filename
            
            if filepath.exists():
                logger.info(f"  ✓ Image cached: {filename}")
                return f"{store_id}/{filename}"
            
            response = self.session.get(image_url, timeout=15, stream=True)
            response.raise_for_status()
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(f"  ✓ Downloaded: {filename}")
            return f"{store_id}/{filename}"
        
        except Exception as e:
            logger.warning(f"  ✗ Image download failed: {e}")
            return None
    
    def extract_products(self, url: str, max_products: int = 200) -> List[Dict]:
        """Extract products with 3-tier fallback strategy"""
        
        # Get OpenRouter API key for LLM fallback
        openrouter_key = os.getenv('OPENROUTER_API_KEY')
        
        # Use multi-tier scraping
        html, strategy, llm_products = scrape_with_fallback(
            url,
            openrouter_key=openrouter_key,
            use_llm_fallback=bool(openrouter_key)  # Only use LLM if key is set
        )
        
        if not html and not llm_products:
            logger.error("❌ All scraping strategies failed!")
            return []
        
        # If LLM extraction succeeded, return those products directly
        if strategy == "llm" and llm_products:
            logger.info(f"✅ Using LLM-extracted products ({len(llm_products)} items)")
            return llm_products[:max_products]
        
        # Otherwise, parse HTML with BeautifulSoup
        logger.info(f"✅ Using {strategy} strategy - parsing HTML...")
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
        except Exception as e:
            logger.error(f"Failed to parse HTML: {e}")
            return []
        
        base_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        domain = urlparse(url).netloc
        
        # Try site-specific scrapers first
        if SiteSpecificScrapers.is_amazon(domain):
            logger.info("🎯 Using Amazon-specific scraper")
            products = SiteSpecificScrapers.scrape_amazon(soup, base_url)
            if products:
                logger.info(f"✅ Amazon scraper found {len(products)} products")
                return products[:max_products]
            logger.warning("⚠️ Amazon scraper found no products, trying generic...")
        
        elif SiteSpecificScrapers.is_mediamarkt(domain):
            logger.info("🎯 Using MediaMarkt-specific scraper")
            products = SiteSpecificScrapers.scrape_mediamarkt(soup, base_url)
            if products:
                logger.info(f"✅ MediaMarkt scraper found {len(products)} products")
                return products[:max_products]
            logger.warning("⚠️ MediaMarkt scraper found no products, trying generic...")
        
        # Fallback to generic scraper
        logger.info("🔍 Using generic scraper")
        return self.extract_products_generic(soup, base_url, max_products)
    
    def extract_products_generic(self, soup: BeautifulSoup, base_url: str, max_products: int) -> List[Dict]:
        """Generic product extraction with common patterns"""
        products = []
        
        product_selectors = [
            'div[class*="product"][class*="item"]',
            'div[class*="product"][class*="card"]',
            'article[class*="product"]',
            'li[class*="product"]',
            'div[data-product-id]',
            'div[itemtype*="Product"]',
            '[data-testid*="product"]',
            '.product-item',
            '.product-card',
            '.product',
        ]
        
        product_elements = []
        for selector in product_selectors:
            elements = soup.select(selector)
            if len(elements) >= 3:
                product_elements = elements
                logger.info(f"Found {len(elements)} products using: {selector}")
                break
        
        if not product_elements:
            logger.warning("⚠ No products found with generic selectors")
            return products
        
        for idx, element in enumerate(product_elements[:max_products], 1):
            try:
                product = self._extract_product_data(element, base_url, idx)
                if product and self.validate_product(product):
                    products.append(product)
            except Exception as e:
                logger.debug(f"Skipped element {idx}: {e}")
        
        logger.info(f"Successfully extracted {len(products)} valid products")
        return products
    
    def _extract_product_data(self, element, base_url: str, idx: int) -> Optional[Dict]:
        """Extract individual product data from element"""
        product = {'index': idx}
        
        # TITLE
        title_selectors = [
            'h2', 'h3', 'h4',
            '[class*="title"]', '[class*="name"]',
            'a[class*="product"]', '[itemprop="name"]'
        ]
        for sel in title_selectors:
            title_el = element.select_one(sel)
            if title_el:
                product['name'] = title_el.get_text(strip=True)
                break
        
        if not product.get('name'):
            return None
        
        # PRICE
        price_patterns = [
            r'\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)',
            r'€\s*(\d+(?:,\d{3})*(?:\.\d{2})?)',
            r'£\s*(\d+(?:,\d{3})*(?:\.\d{2})?)',
            r'(\d+(?:,\d{3})*(?:[.,]\d{2})?)\s*[€$£]',
        ]
        
        price_selectors = [
            '[class*="price"]',
            '[itemprop="price"]',
            'span[class*="amount"]',
            '.price',
        ]
        
        price_text = None
        for sel in price_selectors:
            price_el = element.select_one(sel)
            if price_el:
                price_text = price_el.get_text(strip=True)
                break
        
        if price_text:
            for pattern in price_patterns:
                match = re.search(pattern, price_text)
                if match:
                    try:
                        price_str = match.group(1).replace(',', '').replace(' ', '')
                        # Handle European format (comma as decimal)
                        if '.' not in price_str and ',' in price_str:
                            price_str = price_str.replace(',', '.')
                        product['price'] = Decimal(price_str)
                        break
                    except:
                        pass
        
        # DESCRIPTION
        desc_selectors = [
            '[class*="description"]',
            '[itemprop="description"]',
            'p',
        ]
        for sel in desc_selectors:
            desc_el = element.select_one(sel)
            if desc_el:
                desc = desc_el.get_text(strip=True)
                if len(desc) > 20:
                    product['description'] = desc[:500]
                    break
        
        # IMAGE
        img_selectors = ['img[src]', 'img[data-src]', 'img[data-lazy-src]']
        for sel in img_selectors:
            img_el = element.select_one(sel)
            if img_el:
                img_url = img_el.get('src') or img_el.get('data-src') or img_el.get('data-lazy-src')
                if img_url and 'placeholder' not in img_url.lower():
                    if not img_url.startswith('http'):
                        img_url = urljoin(base_url, img_url)
                    product['image_url'] = img_url
                    break
        
        # PRODUCT URL
        link_el = element.select_one('a[href]')
        if link_el:
            product_url = link_el.get('href')
            if product_url:
                if not product_url.startswith('http'):
                    product_url = urljoin(base_url, product_url)
                product['product_url'] = product_url
        
        return product
    
    def create_embeddings(self, products: List[Dict]) -> List[Dict]:
        """Create embeddings for products"""
        logger.info("Creating embeddings...")
        
        texts = []
        for p in products:
            name = p.get('name', '')
            desc = p.get('description', '')
            text = f"{name}\n\n{desc}".strip()
            texts.append(text)
        
        embeddings = self.embedder.encode(texts, normalize_embeddings=True)
        
        for product, embedding in zip(products, embeddings):
            product['embedding'] = [float(x) for x in embedding]
        
        logger.info(f"Created {len(products)} embeddings")
        return products
    
    def ensure_schema(self):
        """Ensure Supabase table exists with ALL required fields"""
        try:
            self.supabase.table("products").select("id").limit(1).execute()
            logger.info("Table 'products' exists")
            return
        except:
            logger.info("Creating 'products' table...")
        
        ddl = """
        create extension if not exists vector;

        create table if not exists public.products (
          id uuid primary key default gen_random_uuid(),
          store_id uuid not null,
          handle text not null,
          name text,
          description text,
          price numeric,
          image_url text,
          local_image_path text,
          product_url text,
          embedding vector(384),
          scraper_type text default 'universal',
          created_at timestamp default now()
        );

        create index if not exists products_store_id_idx on public.products (store_id);
        create unique index if not exists products_store_handle_idx on public.products (store_id, handle);
        create index if not exists products_embedding_idx on public.products using hnsw (embedding vector_cosine_ops);
        create index if not exists products_created_at_idx on public.products (created_at desc);
        """
        
        base_url = os.getenv('SUPABASE_URL').rstrip('/')
        headers = {
            'Authorization': f'Bearer {os.getenv("SUPABASE_KEY")}',
            'apikey': os.getenv('SUPABASE_KEY'),
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.post(
                f'{base_url}/pg/meta/query',
                headers=headers,
                json={'query': ddl},
                timeout=30
            )
            if response.status_code < 300:
                logger.info("✅ Table created successfully")
            else:
                logger.warning(f"Table creation returned {response.status_code}")
        except Exception as e:
            logger.error(f"Failed to create table: {e}")
            raise
    
    def store_products(self, store_id: str, products: List[Dict], image_server_url: Optional[str] = None):
        """Store products in Supabase"""
        logger.info(f"Storing {len(products)} products for store_id={store_id}")
        
        rows = []
        for product in products:
            handle = re.sub(r'[^a-z0-9]+', '-', product['name'].lower()).strip('-')
            handle = f"{handle}-{product.get('index', 0)}"
            
            local_path = None
            if product.get('image_url'):
                local_path = self.download_image(
                    product['image_url'],
                    store_id,
                    handle
                )
            
            final_image_url = product.get('image_url')
            if local_path and image_server_url:
                final_image_url = f"{image_server_url.rstrip('/')}/images/{local_path}"
            
            row = {
                'id': str(uuid.uuid4()),
                'store_id': store_id,
                'handle': handle,
                'name': product.get('name'),
                'description': product.get('description'),
                'price': str(product['price']) if product.get('price') else None,
                'image_url': final_image_url,
                'local_image_path': local_path,
                'product_url': product.get('product_url'),
                'embedding': self._vector_literal(product.get('embedding', [])),
                'scraper_type': 'universal',
            }
            rows.append(row)
        
        batch_size = 50
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i+batch_size]
            try:
                self.supabase.table('products').insert(batch).execute()
                logger.info(f"Inserted batch {i//batch_size + 1} ({len(batch)} products)")
            except Exception as e:
                logger.error(f"Failed to insert batch: {e}")
                raise
        
        logger.info(f"✅ All products stored successfully!")
    
    def _vector_literal(self, vec: List[float]) -> str:
        return '[' + ','.join(f'{x:.8f}' for x in vec) + ']'


def main():
    parser = argparse.ArgumentParser(description='Universal E-commerce Scraper v2.0 (Site-Specific)')
    parser.add_argument('url', help='Product page URL to scrape')
    parser.add_argument('--max-products', type=int, default=200, help='Maximum products to scrape')
    parser.add_argument('--image-server', help='Image server URL (e.g., http://localhost:8000)')
    args = parser.parse_args()
    
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_KEY')
    
    if not supabase_url or not supabase_key:
        logger.error("Missing SUPABASE_URL or SUPABASE_KEY in environment")
        return
    
    scraper = UniversalScraper(supabase_url, supabase_key)
    scraper.ensure_schema()
    
    store_id = str(uuid.uuid4())
    logger.info(f"Store ID: {store_id}")
    
    products = scraper.extract_products(args.url, args.max_products)
    
    if not products:
        logger.error("❌ No products found!")
        return
    
    products = scraper.create_embeddings(products)
    scraper.store_products(store_id, products, args.image_server)
    
    logger.info(f"\n{'='*60}")
    logger.info(f"✅ SCRAPING COMPLETE!")
    logger.info(f"Store ID: {store_id}")
    logger.info(f"Products: {len(products)}")
    logger.info(f"{'='*60}\n")
    
    with open('store_id.txt', 'w') as f:
        f.write(store_id)
    logger.info("Store ID saved to: store_id.txt")


if __name__ == '__main__':
    main()
