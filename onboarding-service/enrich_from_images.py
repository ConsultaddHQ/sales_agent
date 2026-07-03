"""One-off product enrichment: extract text from product images via a vision LLM.

Cosmetics packaging carries info that isn't in the Shopify text description — this
pulls it out and writes it into the DB fields the agent actually reads, since there is
no ElevenLabs knowledge-base integration in this project (see docs/agents/decisions.md,
2026-07-03 "Rerank relevance cutoff" entry's sibling image-enrichment decision — the
agent's only retrieval path is the search webhook -> DB). Writing to a KB would sit
outside that path and never be found.

Two image sources per product (matches the client's two "sections"):
  1. Top gallery/carousel — Shopify's `images[]` array (products.json). Designed
     graphics that carry product detail + comparison-vs-other-products text.
  2. Description-area infographics — `<img>` tags embedded inside body_html. Benefit /
     certification badges ("paraben-free", "non-comedogenic").

Both are fed to a vision model (via OpenRouter, one API key for many providers) along
with the EXISTING text description, and asked to report only genuinely NEW information.
That gets merged into:
  - `description`   (short "Also: ..." addition — this also feeds the embedding and the
                      voice/card summary truncated to 200 chars by search-service)
  - `metadata.full_description_html` (full extract incl. comparisons/usage — this is
                      what /product-details reads for the spoken "full detail" answer)
  - `search_text` + `embedding` (rebuilt via the SAME _build_search_text() used at
                      onboarding, then re-encoded, so the new info is actually findable)

Rerunnable: the pristine originals are saved once to metadata._pre_enrichment on first
run; every run (including reruns) recomputes from those originals, so re-running never
stacks duplicate text.

Usage (from onboarding-service/, with the onboarding venv active):
    python enrich_from_images.py --store-id <uuid> --store-url https://goxfused.com
    python enrich_from_images.py --store-id <uuid> --store-url https://goxfused.com --dry-run
    python enrich_from_images.py --store-id <uuid> --store-url https://goxfused.com --product-id <id>
    python enrich_from_images.py --store-id <uuid> --store-url https://goxfused.com --model google/gemini-2.5-flash

Needs OPENROUTER_API_KEY. Reads it from onboarding-service/.env if present, else falls
back to search-service/.env, else pass --api-key directly.
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Load onboarding-service/.env first, then fall back to search-service/.env for
# OPENROUTER_API_KEY without clobbering anything already loaded.
load_dotenv(Path(__file__).resolve().parent / ".env")
load_dotenv(Path(__file__).resolve().parent.parent / "search-service" / ".env", override=False)

from shared.db import get_supabase
from shared.embeddings import get_embedder
from services.products import _build_search_text  # reuse the exact onboarding-time logic

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("enrich-from-images")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "google/gemini-2.5-flash"

EXTRACTION_PROMPT = """You are extracting product information from images of a skincare/cosmetics product for an e-commerce search catalog.

You will see:
1. Gallery/carousel images (product packaging photos and designed graphics)
2. Infographic/badge images (certifications, claims)

Existing text description (already in our catalog — do NOT repeat anything covered here):
---
{existing_description}
---

Extract ONLY information that is NOT already stated in the existing description above. Report:
- gallery_text_verbatim: any product detail text printed on the packaging/graphics, copied as written. Empty string if none or if fully redundant with the existing description.
- comparison_notes: any comparison this product makes against other/competing products (e.g. "unlike X", "vs regular Y"). Empty string if none.
- infographic_claims: a list of short benefit/certification claims shown on badge images (e.g. "Paraben-free", "Non-comedogenic", "Dermatologically tested"). Empty list if none or already covered.
- usage_instructions: how-to-use steps shown on images, if any. Empty string if none.
- new_info_found: true only if at least one field above is non-empty.

Respond with ONLY a JSON object with exactly these five keys. No markdown, no commentary."""


def fetch_store_products(store_url: str) -> Dict[str, Dict[str, Any]]:
    """Fetch products.json and index by handle. Single page (limit=250) — fine for
    small catalogs; this script doesn't paginate beyond that."""
    url = store_url.rstrip("/") + "/products.json"
    resp = requests.get(url, params={"limit": 250}, headers={"User-Agent": "TeamPop-Enrich/1.0"}, timeout=20)
    resp.raise_for_status()
    products = resp.json().get("products", [])
    return {p["handle"]: p for p in products if p.get("handle")}


def collect_image_urls(raw_product: Dict[str, Any]) -> List[str]:
    """Gallery images (images[]) + <img> tags inside body_html, deduped, gallery first."""
    gallery = [img["src"] for img in raw_product.get("images", []) if img.get("src")]
    soup = BeautifulSoup(raw_product.get("body_html") or "", "html.parser")
    infographics = [img["src"] for img in soup.find_all("img") if img.get("src")]
    seen = set()
    ordered = []
    for url in gallery + infographics:
        if url not in seen:
            seen.add(url)
            ordered.append(url)
    return ordered


def call_vision_model(
    image_urls: List[str],
    existing_description: str,
    model: str,
    api_key: str,
) -> Optional[Dict[str, Any]]:
    content = [{"type": "text", "text": EXTRACTION_PROMPT.format(existing_description=existing_description or "(none)")}]
    for url in image_urls:
        content.append({"type": "image_url", "image_url": {"url": url}})

    resp = requests.post(
        OPENROUTER_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "response_format": {"type": "json_object"},
        },
        timeout=90,
    )
    resp.raise_for_status()
    raw_text = resp.json()["choices"][0]["message"]["content"]
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        logger.warning(f"Model returned non-JSON response, skipping: {raw_text[:200]}")
        return None


def build_enrichment_text(extract: Dict[str, Any]) -> tuple[str, str]:
    """Returns (short_addition_for_description, full_addition_for_metadata_html)."""
    claims = extract.get("infographic_claims") or []
    short = f"Also: {', '.join(claims[:4])}." if claims else ""

    sections = []
    if extract.get("gallery_text_verbatim"):
        sections.append(f"Additional details from packaging:\n{extract['gallery_text_verbatim']}")
    if extract.get("comparison_notes"):
        sections.append(f"How this compares to other products:\n{extract['comparison_notes']}")
    if claims:
        sections.append("Certifications & claims:\n" + "\n".join(f"- {c}" for c in claims))
    if extract.get("usage_instructions"):
        sections.append(f"Usage:\n{extract['usage_instructions']}")
    full = "\n\n".join(sections)
    return short, full


def enrich_product(
    product: Dict[str, Any],
    raw_product: Dict[str, Any],
    model: str,
    api_key: str,
    dry_run: bool,
) -> None:
    name = product["name"]
    metadata = dict(product.get("metadata") or {})

    # Pristine originals — saved once, always the source for rebuilding on reruns
    # so re-running this script never stacks duplicate enrichment text.
    pre = metadata.get("_pre_enrichment")
    if not pre:
        pre = {
            "description": product.get("description", ""),
            "full_description_html": metadata.get("full_description_html", ""),
        }
        metadata["_pre_enrichment"] = pre

    image_urls = collect_image_urls(raw_product)
    if not image_urls:
        logger.info(f"[{name}] No images found (gallery+infographic) — skipping")
        return
    logger.info(f"[{name}] Sending {len(image_urls)} images to {model}...")

    extract = call_vision_model(image_urls, pre["description"], model, api_key)
    if not extract or not extract.get("new_info_found"):
        logger.info(f"[{name}] No new info found beyond the existing text — leaving unchanged")
        return

    short_addition, full_addition = build_enrichment_text(extract)
    new_description = f"{pre['description']} {short_addition}".strip() if short_addition else pre["description"]
    new_full_html = f"{pre['full_description_html']}\n\n{full_addition}".strip() if full_addition else pre["full_description_html"]

    metadata["full_description_html"] = new_full_html
    metadata["image_extract_v1"] = {
        "model": model,
        "image_count": len(image_urls),
        "enriched_at": datetime.now().isoformat(),
    }

    tags = raw_product.get("tags", "")
    new_search_text = _build_search_text(name, new_description, metadata, tags)
    embedder = get_embedder()
    new_embedding = embedder.encode(new_search_text, normalize_embeddings=True).tolist()

    logger.info(f"[{name}] Extracted: {json.dumps(extract, indent=2)}")
    logger.info(f"[{name}] New description: {new_description}")

    if dry_run:
        logger.info(f"[{name}] DRY RUN — not writing to DB")
        return

    sb = get_supabase()
    sb.table("products").update({
        "description": new_description,
        "metadata": metadata,
        "search_text": new_search_text,
        "embedding": new_embedding,
    }).eq("id", product["id"]).execute()
    logger.info(f"[{name}] Updated in DB (re-embedded, {len(new_search_text)} chars in search_text)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store-id", required=True)
    ap.add_argument("--store-url", required=True, help="e.g. https://goxfused.com")
    ap.add_argument("--product-id", default=None, help="Enrich only this product (by DB id)")
    ap.add_argument(
        "--model",
        default=os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL),
        help=f"OpenRouter vision model (default: {DEFAULT_MODEL}, or $OPENROUTER_MODEL)",
    )
    ap.add_argument("--api-key", default=None, help="Overrides OPENROUTER_API_KEY env var")
    ap.add_argument("--dry-run", action="store_true", help="Print extraction results without writing to DB")
    args = ap.parse_args()

    api_key = args.api_key or os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        sys.exit("Missing OPENROUTER_API_KEY (env var, .env, or --api-key)")

    sb = get_supabase()
    query = sb.table("products").select("*").eq("store_id", args.store_id)
    if args.product_id:
        query = query.eq("id", args.product_id)
    products = query.execute().data or []
    if not products:
        sys.exit(f"No products found for store_id={args.store_id}")

    logger.info(f"Fetching {args.store_url}/products.json to source gallery images + tags...")
    by_handle = fetch_store_products(args.store_url)

    for product in products:
        raw_product = by_handle.get(product.get("handle"))
        if not raw_product:
            logger.warning(f"[{product.get('name')}] handle '{product.get('handle')}' not found in {args.store_url}/products.json — skipping")
            continue
        try:
            enrich_product(product, raw_product, args.model, api_key, args.dry_run)
        except Exception as e:
            logger.error(f"[{product.get('name')}] Failed: {e}")
            continue

    logger.info("Done.")


if __name__ == "__main__":
    main()
