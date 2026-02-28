import io
import json
import logging
import os
import re
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from html import unescape
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from PIL import Image
from sentence_transformers import SentenceTransformer
from supabase import Client, create_client


LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("onboarding-service")


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class OnboardRequest(BaseModel):
    url: str = Field(..., examples=["example.myshopify.com"])


@dataclass(frozen=True)
class ProductRow:
    id: str
    store_id: str
    name: str
    description: str
    price: Optional[Decimal]
    image_url: Optional[str]
    product_url: str
    embedding: List[float]
    handle: str


app = FastAPI(title="onboarding-service", version="1.0.0")

_model: Optional[SentenceTransformer] = None
_supabase: Optional[Client] = None
_schema_ensured: bool = False


def _get_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v


def get_supabase() -> Client:
    global _supabase
    if _supabase is not None:
        return _supabase
    url = _get_env("SUPABASE_URL").rstrip("/")
    key = _get_env("SUPABASE_KEY")
    _supabase = create_client(url, key)
    return _supabase


def get_embedder() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info("Loading embedding model all-MiniLM-L6-v2 (first request may be slow).")
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def clean_domain(raw: str) -> str:
    s = raw.strip()
    if not s:
        raise ValueError("url is empty")
    if "://" not in s:
        s = "https://" + s
    parsed = urlparse(s)
    host = parsed.netloc or parsed.path
    host = host.strip().lower()
    host = host.split("/")[0]
    host = host.rstrip(".")
    host = re.sub(r"^www\.", "", host)
    if not host or "." not in host:
        raise ValueError("invalid domain")
    return host


_TAG_RE = re.compile(r"<[^>]+>")


def html_to_text(value: Any) -> str:
    if not value:
        return ""
    s = unescape(str(value))
    s = _TAG_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _parse_price(product: Dict[str, Any]) -> Optional[Decimal]:
    variants = product.get("variants") or []
    if not variants:
        return None
    price = variants[0].get("price")
    if price is None:
        return None
    try:
        return Decimal(str(price))
    except (InvalidOperation, ValueError):
        return None


def _first_image_src(product: Dict[str, Any]) -> Optional[str]:
    images = product.get("images") or []
    if images and isinstance(images, list):
        src = images[0].get("src")
        if src:
            return str(src)
    image = product.get("image")
    if isinstance(image, dict) and image.get("src"):
        return str(image["src"])
    return None


def _product_handle(product: Dict[str, Any]) -> str:
    h = product.get("handle")
    if h:
        return str(h)
    title = product.get("title") or ""
    slug = re.sub(r"[^a-z0-9]+", "-", str(title).lower()).strip("-")
    return slug or "product"


def _shopify_products_page_url(domain: str, page_url: Optional[str], page: int) -> Tuple[str, Dict[str, Any]]:
    if page_url:
        return page_url, {}
    return f"https://{domain}/products.json", {"limit": 250, "page": page}


_LINK_RE = re.compile(r'<([^>]+)>\s*;\s*rel="([^"]+)"')


def _next_link(link_header: str) -> Optional[str]:
    for part in link_header.split(","):
        m = _LINK_RE.search(part.strip())
        if m and m.group(2) == "next":
            return m.group(1)
    return None


def fetch_shopify_products(domain: str, max_products: int = 500) -> List[Dict[str, Any]]:
    products: List[Dict[str, Any]] = []
    page = 1
    page_url: Optional[str] = None
    session = requests.Session()
    headers = {"User-Agent": "onboarding-service/1.0"}

    while len(products) < max_products:
        url, params = _shopify_products_page_url(domain, page_url, page)
        logger.info("Fetching products page (%s) params=%s", url, params or {})
        try:
            resp = session.get(url, params=params, headers=headers, timeout=20)
        except requests.RequestException as e:
            raise RuntimeError(f"failed to fetch products: {e}") from e

        if resp.status_code == 404:
            raise RuntimeError("products.json not found (store may block public product feed)")
        if resp.status_code >= 400:
            raise RuntimeError(f"failed to fetch products: HTTP {resp.status_code} {resp.text[:500]}")

        try:
            payload = resp.json()
        except json.JSONDecodeError as e:
            raise RuntimeError("invalid JSON from products.json") from e

        page_products = payload.get("products") if isinstance(payload, dict) else None
        if not page_products:
            break
        if not isinstance(page_products, list):
            raise RuntimeError("unexpected products.json shape")

        remaining = max_products - len(products)
        products.extend(page_products[:remaining])

        link = resp.headers.get("Link") or resp.headers.get("link") or ""
        nxt = _next_link(link) if link else None
        if nxt:
            page_url = nxt
            page += 1
            continue

        page += 1
        page_url = None

        if len(page_products) < 250:
            break

    return products


def _safe_filename(value: str) -> str:
    v = value.strip().lower()
    v = re.sub(r"[^a-z0-9._-]+", "-", v)
    v = re.sub(r"-{2,}", "-", v).strip("-")
    return v or "image"


def download_image(image_url: str, dest_path: Path) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if dest_path.exists():
        return

    headers = {"User-Agent": "onboarding-service/1.0"}
    try:
        resp = requests.get(image_url, headers=headers, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"failed to download image: {e}") from e

    try:
        img = Image.open(io.BytesIO(resp.content))
        img = img.convert("RGB")
        img.save(dest_path, format="JPEG", quality=90, optimize=True)
    except Exception as e:
        raise RuntimeError(f"failed to process image as JPEG: {e}") from e


def vector_literal(vec: Iterable[float]) -> str:
    return "[" + ",".join(f"{float(x):.8f}" for x in vec) + "]"


def _meta_headers() -> Dict[str, str]:
    key = _get_env("SUPABASE_KEY")
    return {
        "Authorization": f"Bearer {key}",
        "apikey": key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _meta_post(path: str, payload: Dict[str, Any]) -> requests.Response:
    base = _get_env("SUPABASE_URL").rstrip("/")
    url = f"{base}{path}"
    return requests.post(url, headers=_meta_headers(), json=payload, timeout=30)


def ensure_supabase_schema() -> None:
    """
    Best-effort auto-create for `public.products`.

    Uses Supabase's postgres-meta service (`/pg/meta/*`). This typically requires a
    service-role key.
    """
    global _schema_ensured
    if _schema_ensured:
        return

    sb = get_supabase()
    try:
        sb.table("products").select("id").limit(1).execute()
        _schema_ensured = True
        return
    except Exception:
        pass

    ddl = """
    create extension if not exists vector;

    create table if not exists public.products (
      id text primary key,
      store_id uuid not null,
      name text,
      description text,
      price numeric,
      image_url text,
      product_url text,
      embedding vector(384)
    );

    create index if not exists products_store_id_idx on public.products (store_id);
    """.strip()

    # Try SQL execution via meta query endpoint (preferred).
    candidates = [
        ("/pg/meta/query", {"query": ddl}),
        ("/pg/meta/query", {"sql": ddl}),
        ("/pg/meta/query/", {"query": ddl}),
        ("/pg/meta/query/", {"sql": ddl}),
    ]
    last_err = None
    for path, payload in candidates:
        try:
            resp = _meta_post(path, payload)
            if 200 <= resp.status_code < 300:
                logger.info("Ensured Supabase schema via %s", path)
                break
            last_err = f"{resp.status_code} {resp.text[:500]}"
        except Exception as e:
            last_err = str(e)
    else:
        raise RuntimeError(
            "Failed to auto-create Supabase table `products`. "
            "This usually means SUPABASE_KEY is not a service-role key or the /pg/meta API is disabled. "
            f"Last error: {last_err}"
        )

    # Verify the table is now reachable via PostgREST
    sb.table("products").select("id").limit(1).execute()
    _schema_ensured = True


def build_product_rows(domain: str, store_id: str, raw_products: List[Dict[str, Any]]) -> List[ProductRow]:
    embedder = get_embedder()

    rows: List[ProductRow] = []
    texts: List[str] = []
    metas: List[Tuple[str, str, str, Optional[Decimal], Optional[str], str]] = []
    # metas: (id/handle, name, description, product_url, price, image_url)

    for p in raw_products:
        handle = _product_handle(p)
        name = str(p.get("title") or "").strip()
        product_url = f"https://{domain}/products/{handle}"
        description = html_to_text(p.get("body_html"))
        price = _parse_price(p)
        image_url = _first_image_src(p)

        if not name:
            continue

        blob = f"{name}\n\n{description}".strip()
        texts.append(blob)
        metas.append((handle, name, description, product_url, price, image_url))

    if not texts:
        return []

    embeddings = embedder.encode(texts, normalize_embeddings=True)
    for (handle, name, description, product_url, price, image_url), emb in zip(metas, embeddings):
        rows.append(
            ProductRow(
                id=handle,
                store_id=store_id,
                name=name,
                description=description,
                price=price,
                image_url=image_url,
                product_url=product_url,
                embedding=[float(x) for x in emb],
                handle=handle,
            )
        )
    return rows


def chunked(items: List[Any], size: int) -> Iterable[List[Any]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/onboard")
def onboard(req: OnboardRequest) -> Dict[str, Any]:
    try:
        domain = clean_domain(req.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    store_id = str(uuid.uuid4())
    images_root = os.getenv("STORE_IMAGES_PATH", "./images")
    images_root_path = (BASE_DIR / images_root).resolve() if not Path(images_root).is_absolute() else Path(images_root)
    store_images_dir = images_root_path / store_id

    logger.info("Starting onboarding domain=%s store_id=%s", domain, store_id)

    try:
        raw_products = fetch_shopify_products(domain=domain, max_products=500)
    except Exception as e:
        logger.exception("Failed fetching Shopify products")
        raise HTTPException(status_code=502, detail=str(e)) from e

    try:
        ensure_supabase_schema()
    except Exception as e:
        logger.exception("Failed ensuring Supabase schema")
        raise HTTPException(status_code=500, detail=str(e)) from e

    try:
        rows = build_product_rows(domain=domain, store_id=store_id, raw_products=raw_products)
    except Exception as e:
        logger.exception("Failed building embeddings")
        raise HTTPException(status_code=500, detail=f"embedding failed: {e}") from e

    # Download images (best-effort)
    downloaded = 0
    for r in rows:
        if not r.image_url:
            continue
        fname = _safe_filename(r.handle) + ".jpg"
        dest = store_images_dir / fname
        try:
            download_image(r.image_url, dest)
            downloaded += 1
        except Exception as e:
            logger.warning("Image download failed handle=%s err=%s", r.handle, e)

    # Insert into Supabase in batches
    sb = get_supabase()
    inserted = 0
    try:
        for batch in chunked(rows, 50):
            payload = []
            for r in batch:
                payload.append(
                    {
                        "id": r.id,
                        "store_id": r.store_id,
                        "name": r.name,
                        "description": r.description,
                        "price": str(r.price) if r.price is not None else None,
                        "image_url": r.image_url,
                        "product_url": r.product_url,
                        "embedding": vector_literal(r.embedding),
                    }
                )
            sb.table("products").insert(payload).execute()
            inserted += len(payload)
    except Exception as e:
        logger.exception("Failed inserting into Supabase")
        raise HTTPException(status_code=500, detail=f"supabase insert failed: {e}") from e

    logger.info(
        "Onboarding finished store_id=%s products=%s images=%s",
        store_id,
        len(rows),
        downloaded,
    )

    return {"store_id": store_id, "product_count": len(rows), "status": "ready"}

