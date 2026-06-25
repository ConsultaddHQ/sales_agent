import asyncio
import logging
import os
import sys
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
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

SEARCH_RATE_LIMIT = os.getenv("SEARCH_RATE_LIMIT", "30/minute")
UVICORN_WORKERS = max(1, int(os.getenv("UVICORN_WORKERS", "4")))
RELOAD_ENABLED = os.getenv("RELOAD", "true").lower() == "true"

SEARCH_EMBEDDING_CONCURRENCY = int(os.getenv("SEARCH_EMBEDDING_CONCURRENCY", "2"))
EMBEDDING_TIMEOUT = float(os.getenv("EMBEDDING_TIMEOUT", "5.0"))
RPC_TIMEOUT = float(os.getenv("RPC_TIMEOUT", "5.0"))

_embedding_semaphore: Optional[asyncio.Semaphore] = None

def get_embedding_semaphore() -> asyncio.Semaphore:
    global _embedding_semaphore
    if _embedding_semaphore is None:
        _embedding_semaphore = asyncio.Semaphore(SEARCH_EMBEDDING_CONCURRENCY)
    return _embedding_semaphore



class SearchRequest(BaseModel):
    store_id: str = Field(..., examples=["c5a0c8a1-0e3a-4e0e-a5f4-4cb1f6c8a123"])
    query: str = Field(..., examples=["red sneakers under 100"])


class ProductDetailsRequest(BaseModel):
    store_id: str = Field(..., examples=["c5a0c8a1-0e3a-4e0e-a5f4-4cb1f6c8a123"])
    product_id: str = Field(..., examples=["some-product-id-uuid"])


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
    metadata: Optional[dict] = None
    local_image_path: Optional[str] = None


app = FastAPI(title="search-service", version="1.0.0")
limiter = Limiter(key_func=get_remote_address, default_limits=[])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Expose our custom timing header so downstream services/clients can read it.
    expose_headers=["X-Search-Duration-Ms"],
)


# ---------------------------------------------------------------------------
# Request logging middleware — logs every incoming request for debugging
# ---------------------------------------------------------------------------
from starlette.middleware.base import BaseHTTPMiddleware


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

from shared.config import IMAGE_SERVER_URL, RERANK_CANDIDATES, RERANK_TIMEOUT, RERANK_ENABLED
from shared.db import get_supabase
from shared.embeddings import get_embedder
from shared.parsing import strip_html
from shared.reranker import get_reranker, rerank


async def _encode_query_embedding(query: str) -> tuple[List[float], int, int]:
    """Encode in a worker thread so concurrent requests do not block the event loop.
    Gated by a semaphore and a timeout to prevent CPU thrashing and hangs.
    """
    t_start = time.perf_counter()
    try:
        t_acquired = t_start
        
        async def _run():
            nonlocal t_acquired
            async with get_embedding_semaphore():
                t_acquired = time.perf_counter()
                return await asyncio.to_thread(
                    lambda: get_embedder().encode(query, normalize_embeddings=True).tolist()
                )

        embedding = await asyncio.wait_for(
            _run(),
            timeout=EMBEDDING_TIMEOUT
        )
        t_now = time.perf_counter()
        queue_wait_ms = int((t_acquired - t_start) * 1000)
        embedding_ms = int((t_now - t_acquired) * 1000)
        return embedding, queue_wait_ms, embedding_ms
    except asyncio.TimeoutError as e:
        logger.error(f"Embedding timeout or semaphore acquisition timeout for query: {query}")
        raise HTTPException(
            status_code=503,
            detail="Search service overloaded. Please try again later.",
            headers={"Retry-After": "2"}
        ) from e


def _execute_hybrid_search_rpc(
    sb: Client,
    store_id: str,
    query: str,
    query_embedding: List[float],
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
    # 1. Optional: Parse max price from query (e.g. "under 150", "less than 80 dollars")
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

    # 2. Prepare RPC parameters
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
    
    # 3. Call the RPC
    try:
        resp = sb.rpc("hybrid_search_products", rpc_params).execute()
    except Exception as e:
        logger.exception("Supabase hybrid_search_products RPC failed")
        err_msg = str(e).lower()
        if "disconnected" in err_msg or "timeout" in err_msg or "connection" in err_msg or "pool" in err_msg:
            raise HTTPException(
                status_code=503,
                detail="Database query overloaded or connection failed. Please try again later.",
                headers={"Retry-After": "2"}
            ) from e
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
    
    # 4. Parse results (same as your original)
    results: List[ProductResult] = []
    for row in resp.data:
        try:
            price_raw = row.get("price")
            price_val: Optional[Decimal] = None
            if price_raw is not None:
                price_val = Decimal(str(price_raw))
        except Exception:
            price_val = None

        image_url = row.get("image_url")  # CDN URL (original)
        local_path = row.get("local_image_path")

        if local_path:
            local_image_url = f"{IMAGE_SERVER_URL()}/images/{local_path}"
        else:
            local_image_url = None

        results.append(
            ProductResult(
                id=str(row.get("id")),
                store_id=str(row.get("store_id", "")),
                name=str(row.get("name") or ""),
                description=row.get("description"),
                price=price_val,
                image_url=image_url,
                local_image_url=local_image_url,
                product_url=row.get("product_url"),
                score=float(row.get("similarity") or row.get("score") or 0.0),
                metadata=row.get("metadata") or {},
                local_image_path=local_path,
            )
        )
        
    return results


def _build_rerank_doc(p: ProductResult) -> str:
    """Build the text the cross-encoder sees for each product candidate.

    Includes name, product_type, colors, and description so the reranker
    can directly compare the query against all searchable attributes.
    """
    parts = [p.name]
    meta = p.metadata or {}
    if meta.get("product_type"):
        parts.append(meta["product_type"])
    for opt in meta.get("options", []):
        if opt.get("name", "").lower() in ("color", "colour", "size", "material", "style"):
            parts.extend(opt.get("values", []))
    if p.description:
        parts.append(p.description[:300])  # cap to keep pairs short
    return " ".join(p for p in parts if p)


async def _hybrid_search_products(
    sb: Client,
    store_id: str,
    query: str,
    final_limit: int = 5,
) -> tuple[List[ProductResult], int, int, int]:
    query_embedding, queue_wait_ms, embedding_ms = await _encode_query_embedding(query)

    # Stage 1: wide-net retrieval (more candidates → higher recall for reranker)
    stage1_limit = RERANK_CANDIDATES if RERANK_ENABLED else final_limit

    t_rpc_start = time.perf_counter()
    try:
        candidates = await asyncio.wait_for(
            asyncio.to_thread(
                _execute_hybrid_search_rpc,
                sb,
                store_id,
                query,
                query_embedding,
                stage1_limit,
            ),
            timeout=RPC_TIMEOUT
        )
        rpc_ms = int((time.perf_counter() - t_rpc_start) * 1000)
    except asyncio.TimeoutError as e:
        logger.error(f"Supabase RPC timeout for query: {query}")
        raise HTTPException(
            status_code=503,
            detail="Database query timeout. Please try again later.",
            headers={"Retry-After": "2"}
        ) from e

    # Stage 2: cross-encoder rerank (graceful fallback if disabled or error)
    if RERANK_ENABLED and len(candidates) > 1:
        try:
            docs = [_build_rerank_doc(p) for p in candidates]
            scores = await asyncio.wait_for(
                asyncio.to_thread(rerank, query, docs),
                timeout=RERANK_TIMEOUT,
            )
            ranked = sorted(zip(scores, candidates), key=lambda x: x[0], reverse=True)
            products = [p for _, p in ranked[:final_limit]]
            logger.info(
                f"Reranked {len(candidates)} → {len(products)} for query={query!r} "
                f"| top_score={ranked[0][0]:.3f} | rpc_ms={rpc_ms}"
            )
        except Exception as e:
            logger.warning(f"Reranker failed (falling back to Stage-1 order): {e}")
            products = candidates[:final_limit]
    else:
        products = candidates[:final_limit]

    return products, queue_wait_ms, embedding_ms, rpc_ms


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/search", response_model=SearchResponse)
@limiter.limit(SEARCH_RATE_LIMIT)
async def search(
    request: Request,
    response: Response,
    req: SearchRequest,
) -> SearchResponse:
    # --- Validation with clear diagnostic logging ---
    if not req.query.strip():
        logger.warning(
            f"🚫 400: Empty query received | store_id={req.store_id!r} | query={req.query!r}"
        )
        raise HTTPException(status_code=400, detail="query must not be empty")

    # Validate store_id early
    try:
        uuid.UUID(req.store_id)  # raises ValueError if invalid
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

    # ── Measure embed + RPC duration so callers can correlate latency ──
    t0 = time.perf_counter()
    products, queue_wait_ms, embedding_ms, rpc_ms = await _hybrid_search_products(
        sb=sb, store_id=req.store_id, query=req.query, final_limit=5
    )
    total_ms = int((time.perf_counter() - t0) * 1000)
    response.headers["X-Search-Duration-Ms"] = str(total_ms)
    logger.info(
        f"⏱  Search performance: total_ms={total_ms} | queue_wait_ms={queue_wait_ms} | "
        f"embedding_ms={embedding_ms} | rpc_ms={rpc_ms} | "
        f"store_id={req.store_id} | query={req.query!r} | results={len(products)}"
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
                image_url=p.local_image_url or p.image_url,
                product_url=p.product_url,
            )
        )

    return SearchResponse(products=serialized_products, pitch=pitch)


@app.post("/product-details")
@limiter.limit(SEARCH_RATE_LIMIT)
async def get_product_details(
    request: Request,
    req: ProductDetailsRequest,
) -> Dict[str, Any]:
    # --- Validation ---
    try:
        uuid.UUID(req.store_id)
        uuid.UUID(req.product_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid store_id or product_id format. Must be a valid UUID.")

    sb = get_supabase()
    
    # Query the products table
    try:
        resp = sb.table("products").select("name, metadata").eq("id", req.product_id).eq("store_id", req.store_id).execute()
    except Exception as e:
        logger.exception("Supabase product query failed")
        raise HTTPException(status_code=500, detail=f"database query failed: {str(e)}")

    if not resp.data:
        raise HTTPException(status_code=404, detail="Product not found")

    row = resp.data[0]
    name = row.get("name")
    metadata = row.get("metadata") or {}

    # Extract and clean up data for the LLM
    variants = metadata.get("variants", [])
    options = metadata.get("options", [])
    full_html = metadata.get("full_description_html", "")
    full_text = strip_html(full_html) if full_html else ""
    
    # We want to give the LLM a clean, concise representation
    return {
        "product_name": name,
        "available_options": options,
        "variants": variants,
        "full_description": full_text
    }


# ---------------------------------------------------------------------------
# Startup warmup — eliminates ~1.5–3s cold-start on the first real request.
#
# Without this, the first user request of a process pays:
#   1. SentenceTransformer("all-MiniLM-L6-v2") load   (~1.5–3s, 90 MB)
#   2. Supabase Python client init                    (~100 ms)
#   3. First embedding inference (kernel JIT warmup)  (~50–100 ms)
#
# STEP 1 goal from plan: bring Cycle 1 of a fresh session down from ~18s
# (observed in baseline) to <6s. Warmup moves those costs off the hot path.
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def _warmup_on_startup() -> None:
    def _warm_sync() -> None:
        try:
            logger.info("🔥 Warmup: loading embedding model...")
            t0 = time.perf_counter()
            get_embedder().encode("warmup", normalize_embeddings=True)
            logger.info(
                f"🔥 Warmup: embedder ready in {int((time.perf_counter() - t0) * 1000)} ms"
            )
        except Exception as e:
            logger.warning(f"Warmup: embedder load failed (non-fatal): {e}")

        if RERANK_ENABLED:
            try:
                logger.info("🔥 Warmup: loading reranker model...")
                t1 = time.perf_counter()
                get_reranker().predict([("warmup query", "warmup document")])
                logger.info(
                    f"🔥 Warmup: reranker ready in {int((time.perf_counter() - t1) * 1000)} ms"
                )
            except Exception as e:
                logger.warning(f"Warmup: reranker load failed (non-fatal): {e}")

        try:
            t1 = time.perf_counter()
            sb = get_supabase()
            # Cheap query to warm the Supabase HTTPS connection + auth headers.
            # Does not depend on any specific store_id existing.
            sb.table("products").select("id").limit(1).execute()
            logger.info(
                f"🔥 Warmup: Supabase connection ready in {int((time.perf_counter() - t1) * 1000)} ms"
            )
        except Exception as e:
            logger.warning(f"Warmup: Supabase warmup failed (non-fatal): {e}")

    # Run sync warmup in a worker thread so it doesn't block the event loop.
    await asyncio.to_thread(_warm_sync)


if __name__ == "__main__":
    import uvicorn

    uvicorn_kwargs = {
        "app": "main:app",
        "host": "0.0.0.0",
        "port": int(os.getenv("PORT", "8006")),
        "reload": RELOAD_ENABLED,
    }
    if not RELOAD_ENABLED:
        uvicorn_kwargs["workers"] = UVICORN_WORKERS

    uvicorn.run(
        **uvicorn_kwargs,
    )
