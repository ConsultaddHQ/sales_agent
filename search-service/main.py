import logging
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from pydantic import BaseModel, Field
from supabase import Client, create_client


LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("search-service")


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class SearchRequest(BaseModel):
    store_id: str = Field(..., examples=["c5a0c8a1-0e3a-4e0e-a5f4-4cb1f6c8a123"])
    query: str = Field(..., examples=["red sneakers under 100"])


class ProductOut(BaseModel):
    id: str
    name: str
    price: Optional[float] = None
    description: Optional[str] = None  # Changed from desc to description
    image_url: Optional[str] = None
    product_url: Optional[str] = None


class SearchResponse(BaseModel):
    products: List[ProductOut]
    pitch: str


@dataclass
class ProductResult:
    id: str
    store_id: str
    name: str
    description: Optional[str]
    price: Optional[Decimal]
    image_url: Optional[str]
    product_url: Optional[str]
    score: float


app = FastAPI(title="search-service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_supabase: Optional[Client] = None
_openrouter_client: Optional[OpenAI] = None


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


def get_openrouter_client() -> OpenAI:
    global _openrouter_client
    if _openrouter_client is not None:
        return _openrouter_client

    api_key = _get_env("OPENROUTER_API_KEY")
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

    _openrouter_client = OpenAI(api_key=api_key, base_url=base_url)
    return _openrouter_client


def _hybrid_search_products(
    sb: Client, store_id: str, query: str, limit: int = 5
) -> List[ProductResult]:
    """
    Hybrid pgvector + full-text search.

    This assumes a Postgres function in your Supabase project:

        create or replace function public.hybrid_search_products(
            p_store_id uuid,
            p_query text,
            p_limit int default 5
        )
        returns table (
            id uuid,
            store_id uuid,
            name text,
            description text,
            price numeric,
            image_url text,
            product_url text,
            score double precision
        )
        language sql as $$
        with
        query_embedding as (
          select
            coalesce(
              (select embedding from public.products
               where store_id = p_store_id
               order by embedding <#> (
                 select embedding from public.products
                 where store_id = p_store_id
                 limit 1
               )
               limit 1),
              '[0]'::vector
            ) as embedding
        ),
        vector_matches as (
          select
            p.*,
            1 - (p.embedding <#> (select embedding from query_embedding)) as vector_score
          from public.products p
          where p.store_id = p_store_id
        ),
        text_matches as (
          select
            p.*,
            ts_rank_cd(
              to_tsvector('english', coalesce(p.name, '') || ' ' || coalesce(p.description, '')),
              plainto_tsquery('english', p_query)
            ) as text_score
          from public.products p
          where p.store_id = p_store_id
        )
        select
          coalesce(v.id, t.id) as id,
          coalesce(v.store_id, t.store_id) as store_id,
          coalesce(v.name, t.name) as name,
          coalesce(v.description, t.description) as description,
          coalesce(v.price, t.price) as price,
          coalesce(v.image_url, t.image_url) as image_url,
          coalesce(v.product_url, t.product_url) as product_url,
          coalesce(v.vector_score, 0) * 0.6
            + coalesce(t.text_score, 0) * 0.4 as score
        from vector_matches v
        full outer join text_matches t using (id)
        where (coalesce(v.vector_score, 0) > 0 or coalesce(t.text_score, 0) > 0)
        order by score desc
        limit p_limit;
        $$;

    Adjust as needed for your schema. The Python side just calls this RPC.
    """
    try:
        # Prefer rpc call so we can leverage the SQL above.
        resp = (
            sb.rpc(
                "hybrid_search_products",
                {"p_store_id": store_id, "p_query": query, "p_limit": limit},
            )
            .execute()
        )
    except Exception as e:
        logger.exception("Supabase hybrid_search_products RPC failed")
        raise HTTPException(status_code=500, detail=f"supabase search failed: {e}") from e

    if not isinstance(resp.data, list):
        raise HTTPException(status_code=500, detail="unexpected Supabase response shape")

    results: List[ProductResult] = []
    for row in resp.data:
        try:
            price_raw = row.get("price")
            price_val: Optional[Decimal]
            if price_raw is None:
                price_val = None
            else:
                price_val = Decimal(str(price_raw))
        except Exception:
            price_val = None

        results.append(
            ProductResult(
                id=str(row.get("id")),
                store_id=str(row.get("store_id")),
                name=str(row.get("name") or ""),
                description=row.get("description"),
                price=price_val,
                image_url=row.get("image_url"),
                product_url=row.get("product_url"),
                score=float(row.get("score") or 0.0),
            )
        )

    return results


def _build_pitch(products: List[ProductResult], query: str) -> str:
    if not products:
        return "I couldn't find a great match for that request, but I’d be happy to help you explore similar products."

    client = get_openrouter_client()
    model = os.getenv("OPENROUTER_MODEL", "xai/grok-beta")
    best = products[0]

    feature_bits: List[str] = []
    if best.description:
        feature_bits.append(best.description)
    if best.product_url:
        feature_bits.append(f"URL: {best.product_url}")
    if best.image_url:
        feature_bits.append(f"Image: {best.image_url}")

    price_str = "Unknown price"
    if best.price is not None:
        price_str = f"${best.price:.2f}"

    system_prompt = (
        "You are a friendly retail assistant. "
        "Create a short enthusiastic 2-sentence sales pitch for the best matching product. "
        "Mention price and key features."
    )

    user_content = (
        f"Customer query: {query}\n\n"
        f"Selected product:\n"
        f"- Name: {best.name}\n"
        f"- Price: {price_str}\n"
        f"- Extra details: {' '.join(feature_bits) if feature_bits else 'N/A'}"
    )

    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            max_tokens=160,
            temperature=0.8,
        )
    except Exception as e:
        logger.exception("OpenRouter call failed")
        raise HTTPException(status_code=502, detail=f"pitch generation failed: {e}") from e

    choice = completion.choices[0].message.content if completion.choices else ""
    return (choice or "").strip()


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/search", response_model=SearchResponse)
def search(req: SearchRequest) -> SearchResponse:
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")

    sb = get_supabase()

    products = _hybrid_search_products(
        sb=sb, store_id=req.store_id, query=req.query, limit=5
    )
    pitch = _build_pitch(products, query=req.query)

    serialized_products: List[ProductOut] = []
    for p in products:
        serialized_products.append(
            ProductOut(
                id=p.id,
                name=p.name,
                price=float(p.price) if p.price is not None else None,
                description=p.description,  # Changed from desc to description
                image_url=p.image_url,
                product_url=p.product_url,
            )
        )

    return SearchResponse(products=serialized_products, pitch=pitch)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8002")),
        reload=True,
    )

