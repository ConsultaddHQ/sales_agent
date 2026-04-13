import logging
import os
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from supabase import Client
import uuid

# Add repo root for shared/ imports
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

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


def _truncate_for_voice(text: Optional[str], max_chars: int = 200) -> Optional[str]:
    """Shorten description for voice + UI card use without mid-word cuts.

    Full text is still stored in DB and used for embeddings; this only
    affects what ElevenLabs and the widget carousel see per turn.
    """
    if not text:
        return text
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    for sep in (". ", "\n", " "):
        idx = cut.rfind(sep)
        if idx >= max_chars // 2:
            cut = cut[:idx]
            break
    return cut.rstrip(" .,-") + "…"


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
    local_image_url: Optional[str]
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


# ---------------------------------------------------------------------------
# Request logging middleware — logs every incoming request for debugging
# ---------------------------------------------------------------------------
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
import json as _json


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs method, path, status, and body for every request.

    This is the FIRST thing to check when debugging 400/422 errors —
    it shows you exactly what payload the caller sent.
    """

    async def dispatch(self, request: Request, call_next):
        body = b""
        if request.method in ("POST", "PUT", "PATCH"):
            body = await request.body()

        # Log the incoming request
        body_preview = body[:500].decode("utf-8", errors="replace") if body else "<empty>"
        logger.info(
            f"➡️  {request.method} {request.url.path} "
            f"| client={request.client.host if request.client else '?'} "
            f"| body={body_preview}"
        )

        response = await call_next(request)

        # Log the response status
        level = logging.WARNING if response.status_code >= 400 else logging.INFO
        logger.log(
            level,
            f"⬅️  {request.method} {request.url.path} → {response.status_code}"
        )
        return response


app.add_middleware(RequestLoggingMiddleware)

from shared.config import get_env, IMAGE_SERVER_URL
from shared.db import get_supabase
from shared.embeddings import get_embedder


def _hybrid_search_products(
    sb: Client,
    store_id: str,
    query: str,
    limit: int = 10          # Increased default – you can still override from caller
) -> List[ProductResult]:
    """
    Hybrid pgvector + full-text search using real query embedding.

    Requires the updated Supabase function that accepts:
    - p_store_id
    - p_query
    - p_query_embedding (vector(384))
    - p_max_price (optional)
    - p_limit
    - p_min_score
    """
    # 1. Embed the user query (must use same model as onboarding)
    embedder = get_embedder()
    query_embedding = embedder.encode(query, normalize_embeddings=True).tolist()

    # 2. Optional: Parse max price from query (e.g. "under 150", "less than 80 dollars")
    max_price = None
    # try:
    #     client = get_openrouter_client()
    #     parse_prompt = f"""
    #             Extract ONLY the maximum budget/price limit the customer is willing to pay.
    #             Rules:
    #             - If the query says "under X", "max X", "less than X", "below X" → return X
    #             - If "around X" or "about X" → return X
    #             - Return ONLY a number like 3000 or 45.99 — no currency symbols, no text
    #             - If no price mentioned at all → return exactly the string "null"
    #             - Do NOT guess or add extra — be literal

    #             Query: {query}
    #             """.strip()
                
    #     completion = client.chat.completions.create(
    #         model=os.getenv("OPENROUTER_MODEL", "xai/grok-beta"),
    #         messages=[{"role": "user", "content": parse_prompt}],
    #         max_tokens=10,
    #         temperature=0.0,
    #     )
        
    #     parsed = completion.choices[0].message.content.strip().lower()
    #     if parsed != "null" and parsed.replace(".", "").isdigit():
    #         max_price = float(parsed)
    #     # else: stays None
    # except Exception as e:
    #     logger.warning(f"Failed to parse price from query '{query}': {e}", exc_info=True)

    # 3. Prepare RPC parameters
    rpc_params = {
        "p_store_id": store_id,
        "p_query": query,
        "p_query_embedding": "[" + ",".join(f"{x:.8f}" for x in query_embedding) + "]",
        "p_limit": limit,
        "p_min_score": 0.25,          # ← start here, tune between 0.15–0.45 based on tests
    }
    if max_price is not None:
        rpc_params["p_max_price"] = max_price
    
    logger.info(f"RPC params for store_id={store_id}, query='{query}': {rpc_params}")
    logger.info(f"Max price parsed: {max_price}")
    logger.info(f"Query: '{query}' → Parsed max_price = {max_price} (type: {type(max_price)})")
    
    # 4. Call the RPC
    try:
        resp = sb.rpc("hybrid_search_products", rpc_params).execute()
    except Exception as e:
        logger.exception("Supabase hybrid_search_products RPC failed")
        raise HTTPException(
            status_code=500,
            detail=f"supabase search failed: {str(e)}"
        ) from e

    if not isinstance(resp.data, list):
        raise HTTPException(
            status_code=500,
            detail="unexpected Supabase response shape"
        )
        
    logger.info(f"RPC response: data_len={len(resp.data)}, full_resp={resp}")
    
    if not resp.data:
       logger.warning(f"No results from RPC for query='{query}', store_id={store_id}. Check threshold={rpc_params['p_min_score']}, max_price={max_price}")
    
    # 5. Parse results (same as your original)
    results: List[ProductResult] = []
    for row in resp.data:
        try:
            price_raw = row.get("price")
            price_val: Optional[Decimal] = None
            if price_raw is not None:
                price_val = Decimal(str(price_raw))
        except Exception:
            price_val = None

         # ENHANCE: Prefer our server images over CDN 
        image_url = row.get("image_url")  # CDN URL (original)
        local_path = row.get("local_image_path")
        
        # If we have local image, prefer our server
        if local_path:
            local_image_url = f"{IMAGE_SERVER_URL()}/images/{local_path}"
        else:
            local_image_url = None
        
        results.append(
            ProductResult(
                id=str(row.get("id")),
                store_id=str(row.get("store_id")),
                name=str(row.get("name") or ""),
                description=row.get("description"),
                price=price_val,
                image_url=image_url,              # Original CDN URL (fallback)
                local_image_url=local_image_url,  # Our server URL (preferred)
                product_url=row.get("product_url"),
                score=float(row.get("score") or 0.0),
            )
        )
        
    return results


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/search", response_model=SearchResponse)
def search(req: SearchRequest) -> SearchResponse:
    # --- Validation with clear diagnostic logging ---
    if not req.query.strip():
        logger.warning(
            f"🚫 400: Empty query received | store_id={req.store_id!r} | query={req.query!r}"
        )
        raise HTTPException(status_code=400, detail="query must not be empty")

    # Validate store_id early
    try:
        uuid_obj = uuid.UUID(req.store_id)  # raises ValueError if invalid
    except ValueError:
        hint = ""
        if len(req.store_id) == 35:
            hint = " (35 chars — looks like a truncated UUID, missing 1 character. Check the agent webhook config.)"
        elif len(req.store_id) < 36:
            hint = f" ({len(req.store_id)} chars — too short, expected 36.)"
        logger.warning(
            f"🚫 400: Invalid store_id | store_id={req.store_id!r} ({len(req.store_id)} chars) | query={req.query!r}"
        )
        raise HTTPException(
            status_code=400,
            detail=f"Invalid store_id format: '{req.store_id}'. Must be a valid UUID (36 characters).{hint}"
        )
    
    sb = get_supabase()

    products = _hybrid_search_products(
        sb=sb, store_id=req.store_id, query=req.query, limit=5
    )
    pitch = f"Found {len(products)} products." if products else "No matching products found."

    serialized_products: List[ProductOut] = []
    for p in products:
        serialized_products.append(
            ProductOut(
                id=p.id,
                name=p.name,
                price=float(p.price) if p.price is not None else None,
                description=_truncate_for_voice(p.description, 200),
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

