"""Product processing — build rows, download images, store in Supabase."""

import io
import logging
import os
import re
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from PIL import Image

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from shared.config import IMAGE_SERVER_URL, IMAGE_DOWNLOAD_TIMEOUT, CHUNK_SIZE
from shared.db import get_supabase
from shared.embeddings import get_embedder
from shared.parsing import strip_html, parse_price

logger = logging.getLogger("onboarding-service")


@dataclass(frozen=True)
class ProductRow:
    id: str
    store_id: str
    name: str
    description: str
    price: Optional[Decimal]
    image_url: Optional[str]
    product_url: str
    local_image_path: Optional[str]
    embedding: List[float]
    handle: str
    created_at: datetime


def download_product_image(
    image_url: str,
    store_images_dir: Path,
    handle: str,
) -> Optional[str]:
    """Download a product image, convert to JPEG.

    Returns filename (e.g. "my-product.jpg") or None on failure.
    """
    if not image_url:
        return None
    try:
        store_images_dir.mkdir(parents=True, exist_ok=True)
        response = requests.get(image_url, timeout=IMAGE_DOWNLOAD_TIMEOUT, stream=True)
        response.raise_for_status()

        filename = f"{handle}.jpg"
        filepath = store_images_dir / filename

        img = Image.open(io.BytesIO(response.content))
        img = img.convert("RGB")
        img.save(filepath, format="JPEG", quality=90, optimize=True)

        logger.debug(f"  Downloaded: {filename}")
        return filename
    except Exception as e:
        logger.warning(f"  Image download failed for {handle}: {e}")
        return None


def build_product_rows(
    domain: str,
    store_id: str,
    raw_products: List[Dict[str, Any]],
    store_images_dir: Path,
) -> List[ProductRow]:
    """Build ProductRow objects with embeddings and downloaded images."""
    logger.info(f"Processing {len(raw_products)} products...")

    embedder = get_embedder()
    image_server_url = IMAGE_SERVER_URL()
    rows = []

    for product in raw_products:
        try:
            handle = product.get("handle") or "product"
            name = product.get("title") or "Untitled Product"
            description = strip_html(product.get("body_html") or "")

            # Price from first variant
            price = None
            variants = product.get("variants", [])
            if variants:
                price = parse_price(variants[0].get("price"))

            # Image URL (first image)
            image_url = None
            images = product.get("images", [])
            if images:
                image_url = images[0].get("src")

            # Download image
            local_image_path = download_product_image(image_url, store_images_dir, handle)

            db_image_url = None
            if local_image_path:
                db_image_url = f"{image_server_url}/images/{store_id}/{local_image_path}"

            product_url = product.get("_original_product_url") or f"https://{domain}/products/{handle}"

            # Create embedding
            text_to_embed = f"{name} {description}"
            embedding = embedder.encode(text_to_embed, normalize_embeddings=True).tolist()

            rows.append(ProductRow(
                id=str(uuid.uuid4()),
                store_id=store_id,
                name=name,
                description=description,
                price=price,
                image_url=db_image_url,
                product_url=product_url,
                local_image_path=f"{store_id}/{local_image_path}" if local_image_path else None,
                embedding=embedding,
                handle=handle,
                created_at=datetime.now(),
            ))
        except Exception as e:
            logger.warning(f"Failed to process product '{product.get('title', 'unknown')}': {e}")
            continue

    logger.info(f"Processed {len(rows)} products successfully")
    return rows


def store_products_in_supabase(rows: List[ProductRow]) -> None:
    """Batch-insert ProductRows into the products table."""
    if not rows:
        logger.warning("No products to store")
        return

    logger.info(f"Storing {len(rows)} products in Supabase...")
    supabase = get_supabase()

    records = []
    for row in rows:
        records.append({
            "id": row.id,
            "store_id": row.store_id,
            "handle": row.handle,
            "name": row.name,
            "description": row.description,
            "price": float(row.price) if row.price else None,
            "image_url": row.image_url,
            "product_url": row.product_url,
            "local_image_path": row.local_image_path,
            "embedding": row.embedding,
            "created_at": row.created_at.isoformat(),
        })

    for i in range(0, len(records), CHUNK_SIZE):
        chunk = records[i:i + CHUNK_SIZE]
        try:
            supabase.table("products").insert(chunk).execute()
            logger.info(f"  Inserted batch {i // CHUNK_SIZE + 1} ({len(chunk)} products)")
        except Exception as e:
            logger.error(f"Failed to insert batch: {e}")
            raise

    logger.info("All products stored in database")
