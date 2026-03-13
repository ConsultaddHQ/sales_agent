#!/usr/bin/env python3
"""
Universal E-commerce Product Scraper
Scrapes products from any e-commerce site and stores in Supabase
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()


class UniversalScraper:
    def __init__(self, supabase_url: str, supabase_key: str, images_dir: str = "./product_images"):
        self.supabase: Client = create_client(supabase_url, supabase_key)
        self.images_dir = Path(images_dir)
        self.images_dir.mkdir(exist_ok=True, parents=True)
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        
        # Load sentence transformer for embeddings
        logger.info("Loading embedding model...")
        self.embedder = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
        logger.info("Model loaded successfully")
    
    def download_image(self, image_url: str, store_id: str, product_handle: str) -> Optional[str]:
        """Download image and return local relative path"""
        try:
            # Create store directory
            store_dir = self.images_dir / store_id
            store_dir.mkdir(exist_ok=True, parents=True)
            
            # Generate filename
            url_hash = hashlib.md5(image_url.encode()).hexdigest()[:8]
            ext = Path(urlparse(image_url).path).suffix or '.jpg'
            if ext not in ['.jpg', '.jpeg', '.png', '.webp', '.gif']:
                ext = '.jpg'
            
            filename = f"{product_handle}_{url_hash}{ext}"
            filepath = store_dir / filename
            
            if filepath.exists():
                logger.info(f"  ✓ Image already exists: {filename}")
                return f"{store_id}/{filename}"
            
            # Download with timeout
            response = self.session.get(image_url, timeout=15, stream=True)
            response.raise_for_status()
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(f"  ✓ Downloaded: {filename}")
            return f"{store_id}/{filename}"
        
        except Exception as e:
            logger.warning(f"  ✗ Image download failed for {image_url}: {e}")
            return None
    
    def extract_products(self, url: str, max_products: int = 200) -> List[Dict]:
        """Extract products from any e-commerce page"""
        logger.info(f"Fetching URL: {url}")
        
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
        except Exception as e:
            logger.error(f"Failed to fetch page: {e}")
            return []
        
        base_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        products = []
        
        # Try multiple product container patterns
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
            if len(elements) >= 3:  # At least 3 products
                product_elements = elements
                logger.info(f"Found {len(elements)} products using: {selector}")
                break
        
        if not product_elements:
            logger.warning("⚠ No product containers found, trying fallback...")
            # Fallback: find all divs/articles with images
            product_elements = soup.find_all(['div', 'article'], class_=re.compile(r'.*'))
        
        for idx, element in enumerate(product_elements[:max_products], 1):
            try:
                product = self._extract_product_data(element, base_url, idx)
                if product and product.get('name'):
                    products.append(product)
            except Exception as e:
                logger.debug(f"Skipped element {idx}: {e}")
        
        logger.info(f"Successfully extracted {len(products)} products")
        return products
    
    def _extract_product_data(self, element, base_url: str, idx: int) -> Optional[Dict]:
        """Extract individual product data from element"""
        product = {'index': idx}
        
        # TITLE/NAME
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
            r'(\d+(?:,\d{3})*(?:\.\d{2})?)\s*€',
            r'(\d+(?:,\d{3})*(?:\.\d{2})?)\s*\$',
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
                        price_str = match.group(1).replace(',', '')
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
                if len(desc) > 20:  # Meaningful description
                    product['description'] = desc[:500]  # Limit length
                    break
        
        # IMAGE
        img_selectors = ['img[src]', 'img[data-src]']
        for sel in img_selectors:
            img_el = element.select_one(sel)
            if img_el:
                img_url = img_el.get('src') or img_el.get('data-src')
                if img_url:
                    # Handle relative URLs
                    if not img_url.startswith('http'):
                        img_url = urljoin(base_url, img_url)
                    # Skip placeholder/icons
                    if 'placeholder' not in img_url.lower() and 'icon' not in img_url.lower():
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
        
        return product if len(product) >= 3 else None  # At least name + 1 other field
    
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
        """Ensure Supabase table exists"""
        try:
            # Test if table exists
            self.supabase.table("products").select("id").limit(1).execute()
            logger.info("Table 'products' exists")
            return
        except:
            logger.info("Creating 'products' table...")
        
        # Create table SQL
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
          created_at timestamp default now()
        );

        create index if not exists products_store_id_idx on public.products (store_id);
        create unique index if not exists products_store_handle_idx on public.products (store_id, handle);
        create index if not exists products_embedding_idx on public.products using hnsw (embedding vector_cosine_ops);
        """
        
        # Try to create via meta API
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
                logger.info("Table created successfully")
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
            # Create handle from name
            handle = re.sub(r'[^a-z0-9]+', '-', product['name'].lower()).strip('-')
            handle = f"{handle}-{product.get('index', 0)}"
            
            # Download image
            local_path = None
            if product.get('image_url'):
                local_path = self.download_image(
                    product['image_url'],
                    store_id,
                    handle
                )
            
            # Determine final image URL
            final_image_url = product.get('image_url')
            if local_path and image_server_url:
                # Replace CDN URL with our server URL
                final_image_url = f"{image_server_url.rstrip('/')}/images/{local_path}"
            
            row = {
                'id': str(uuid.uuid4()),
                'store_id': store_id,
                'handle': handle,
                'name': product.get('name'),
                'description': product.get('description'),
                'price': str(product['price']) if product.get('price') else None,
                'image_url': final_image_url,  # Our server URL
                'local_image_path': local_path,  # For reference
                'product_url': product.get('product_url'),
                'embedding': self._vector_literal(product.get('embedding', []))
            }
            rows.append(row)
        
        # Insert in batches
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
        """Convert vector to PostgreSQL array literal"""
        return '[' + ','.join(f'{x:.8f}' for x in vec) + ']'


def main():
    parser = argparse.ArgumentParser(description='Universal E-commerce Scraper')
    parser.add_argument('url', help='Product page URL to scrape')
    parser.add_argument('--max-products', type=int, default=200, help='Maximum products to scrape')
    parser.add_argument('--image-server', help='Image server URL (e.g., http://localhost:8000)')
    args = parser.parse_args()
    
    # Load environment variables
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_KEY')
    
    if not supabase_url or not supabase_key:
        logger.error("Missing SUPABASE_URL or SUPABASE_KEY in environment")
        return
    
    # Create scraper
    scraper = UniversalScraper(supabase_url, supabase_key)
    
    # Ensure schema exists
    scraper.ensure_schema()
    
    # Generate store ID
    store_id = str(uuid.uuid4())
    logger.info(f"Store ID: {store_id}")
    
    # Extract products
    products = scraper.extract_products(args.url, args.max_products)
    
    if not products:
        logger.error("No products found!")
        return
    
    # Create embeddings
    products = scraper.create_embeddings(products)
    
    # Store in database
    scraper.store_products(store_id, products, args.image_server)
    
    logger.info(f"\n{'='*60}")
    logger.info(f"✅ SCRAPING COMPLETE!")
    logger.info(f"Store ID: {store_id}")
    logger.info(f"Products: {len(products)}")
    logger.info(f"{'='*60}\n")
    
    # Save store_id to file for easy reference
    with open('store_id.txt', 'w') as f:
        f.write(store_id)
    logger.info("Store ID saved to: store_id.txt")


if __name__ == '__main__':
    main()
