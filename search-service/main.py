import asyncio
import logging
import os
import sys
import time
from collections import OrderedDict
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

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

from shared.observability import (
    CorrelationMiddleware,
    bind_conversation,
    capture_exception,
    current_request_id,
    init_sentry,
    log_event,
    run_system_stats_logger,
    setup_logging,
)

logger = setup_logging("search-service")
init_sentry("search-service")

SEARCH_RATE_LIMIT = os.getenv("SEARCH_RATE_LIMIT", "30/minute")
UVICORN_WORKERS = max(1, int(os.getenv("UVICORN_WORKERS", "4")))
RELOAD_ENABLED = os.getenv("RELOAD", "true").lower() == "true"

SEARCH_EMBEDDING_CONCURRENCY = int(os.getenv("SEARCH_EMBEDDING_CONCURRENCY", "2"))
EMBEDDING_TIMEOUT = float(os.getenv("EMBEDDING_TIMEOUT", "5.0"))
RPC_TIMEOUT = float(os.getenv("RPC_TIMEOUT", "5.0"))

# Bump alongside LATENCY_CONFIG_VERSION in onboarding-service whenever a
# change here affects search timing (cache added, reranker toggled, model
# swapped) so search_latency rows can be grouped by "which backend config
# produced this number" the same way turn_latency groups by voice-agent config.
SEARCH_CONFIG_VERSION = os.getenv("SEARCH_CONFIG_VERSION", "v1-baseline")

# ── Search result cache ──────────────────────────────────────────────────
# Same store + same (normalized) query within TTL skips embedding + RPC +
# rerank entirely. Sized for a single-store pilot — bounded FIFO eviction,
# not LRU, to keep this dependency-free. Correctness note: this trades a
# few minutes of staleness for latency; fine for a product catalog that
# doesn't change minute-to-minute, NOT fine if that assumption stops holding
# for a future multi-tenant high-churn catalog.
SEARCH_CACHE_TTL_SECONDS = float(os.getenv("SEARCH_CACHE_TTL_SECONDS", "300"))
SEARCH_CACHE_MAX_ENTRIES = int(os.getenv("SEARCH_CACHE_MAX_ENTRIES", "200"))
SEARCH_CACHE_ENABLED = os.getenv("SEARCH_CACHE_ENABLED", "true").lower() == "true"

_search_cache: "OrderedDict[tuple[str, str], tuple[list, float]]" = OrderedDict()


def _cache_key(store_id: str, query: str) -> tuple:
    return (store_id, " ".join(query.strip().lower().split()))


def _cache_get(store_id: str, query: str):
    if not SEARCH_CACHE_ENABLED:
        return None
    key = _cache_key(store_id, query)
    entry = _search_cache.get(key)
    if entry is None:
        return None
    products, expires_at = entry
    if time.time() > expires_at:
        _search_cache.pop(key, None)
        return None
    _search_cache.move_to_end(key)
    return products


def _cache_put(store_id: str, query: str, products: list) -> None:
    if not SEARCH_CACHE_ENABLED:
        return
    key = _cache_key(store_id, query)
    _search_cache[key] = (products, time.time() + SEARCH_CACHE_TTL_SECONDS)
    _search_cache.move_to_end(key)
    while len(_search_cache) > SEARCH_CACHE_MAX_ENTRIES:
        _search_cache.popitem(last=False)

_embedding_semaphore: Optional[asyncio.Semaphore] = None

def get_embedding_semaphore() -> asyncio.Semaphore:
    global _embedding_semaphore
    if _embedding_semaphore is None:
        _embedding_semaphore = asyncio.Semaphore(SEARCH_EMBEDDING_CONCURRENCY)
    return _embedding_semaphore



class SearchRequest(BaseModel):
    store_id: str = Field(..., examples=["c5a0c8a1-0e3a-4e0e-a5f4-4cb1f6c8a123"])
    query: str = Field(..., examples=["red sneakers under 100"])
    # Filled by ElevenLabs from the `system__conversation_id` dynamic variable
    # (see elevenlabs_agent._get_tool_config). Optional so older agents and
    # direct widget calls keep working.
    conversation_id: Optional[str] = None


class ProductDetailsRequest(BaseModel):
    store_id: str = Field(..., examples=["c5a0c8a1-0e3a-4e0e-a5f4-4cb1f6c8a123"])
    product_id: str = Field(..., examples=["some-product-id-uuid"])
    conversation_id: Optional[str] = None


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

# CORS allowlist: comma-separated origins via ALLOWED_ORIGINS; defaults to "*" for dev.
# Set to the client's storefront domain(s) in production (e.g. https://goxfused.com).
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Expose our custom timing header so downstream services/clients can read it.
    expose_headers=["X-Search-Duration-Ms", "X-Search-Cache", "X-Request-Id"],
)


app.add_middleware(CorrelationMiddleware)

# 422s were the main reason the old middleware logged every request body.
# Log the offending body only when validation fails, not on every hot-path call.
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler


@app.exception_handler(RequestValidationError)
async def _log_validation_error(request: Request, exc: RequestValidationError):
    log_event(
        logger, "request.invalid", logging.WARNING,
        path=request.url.path, errors=exc.errors(), body=str(exc.body)[:500],
    )
    return await request_validation_exception_handler(request, exc)

from shared.config import IMAGE_SERVER_URL, RERANK_CANDIDATES, RERANK_TIMEOUT, RERANK_ENABLED, RERANK_SCORE_MARGIN
from shared.db import get_supabase, insert_tolerant
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
        log_event(logger, "search.timeout", logging.ERROR, stage="embedding", query=query, timeout_s=EMBEDDING_TIMEOUT)
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
        # Stage-1 favors recall (the cross-encoder reranker recovers precision).
        # Keyword/FTS hits are kept regardless of this threshold; this only gates
        # vector-only matches. Keep low so good candidates reach the reranker.
        "p_min_score": 0.15,
    }
    if max_price is not None:
        rpc_params["p_max_price"] = max_price
    
    # Never log p_query_embedding — 384 floats per line was pure hot-path noise.
    logger.debug(f"RPC store_id={store_id} query={query!r} limit={limit} max_price={max_price}")

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
        
    if not resp.data:
        log_event(
            logger, "search.rpc_empty", logging.WARNING,
            store_id=store_id, query=query, min_score=rpc_params["p_min_score"],
        )
    
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


# Browse/broad intent — the shopper wants the whole catalog, so the relevance
# cutoff must NOT trim results (the agent expands "show me everything" into queries
# like "all products facewash moisturiser lip balm", which otherwise score middling
# and lose the tail). Detected by phrase; a very low top score is a second signal.
_BROWSE_TERMS = (
    "everything", "all product", "all your", "all of them", "all items",
    "full range", "full catalog", "entire", "whole range",
    "show me all", "show all", "what do you have", "what do you sell", "what products",
)


def _is_browse_query(query: str) -> bool:
    q = query.lower()
    return any(term in q for term in _BROWSE_TERMS)


async def _hybrid_search_products(
    sb: Client,
    store_id: str,
    query: str,
    final_limit: int = 12,
) -> tuple[List[ProductResult], int, int, int, int]:
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
        log_event(logger, "search.timeout", logging.ERROR, stage="rpc", query=query, timeout_s=RPC_TIMEOUT)
        raise HTTPException(
            status_code=503,
            detail="Database query timeout. Please try again later.",
            headers={"Retry-After": "2"}
        ) from e

    # Stage 2: cross-encoder rerank (graceful fallback if disabled or error)
    rerank_ms = 0
    if RERANK_ENABLED and len(candidates) > 1:
        t_rerank = time.perf_counter()
        try:
            docs = [_build_rerank_doc(p) for p in candidates]
            scores = await asyncio.wait_for(
                asyncio.to_thread(rerank, query, docs),
                timeout=RERANK_TIMEOUT,
            )
            ranked = sorted(zip(scores, candidates), key=lambda x: x[0], reverse=True)
            top_score = ranked[0][0]
            # Explicit browse intent ("show me everything") → return the full ranked
            # set. Everything else → keep only results within RERANK_SCORE_MARGIN of
            # the top score, so "moisturizer" drops the irrelevant tail. Always keep
            # at least the top 1.
            # A low top score alone is NOT browse intent: "Xiaomi face wash" (brand
            # not carried) scored top=-1.2 and used to return all 6 products incl.
            # lip balms at -9.7 (2026-10-02, conv_1701m3ye21ytepvbz6318g2vgem1);
            # the margin keeps just the two face washes.
            browse = _is_browse_query(query)
            if browse:
                kept = ranked
            else:
                kept = [(s, p) for s, p in ranked if s >= top_score - RERANK_SCORE_MARGIN] or [ranked[0]]
            products = [p for _, p in kept[:final_limit]]
            rerank_ms = int((time.perf_counter() - t_rerank) * 1000)
            log_event(
                logger, "search.reranked",
                candidates=len(candidates), kept=len(products), browse=browse,
                top_score=round(float(top_score), 3),
                kept_scores=[round(float(s), 2) for s, _ in kept[:final_limit]],
                rerank_ms=rerank_ms,
            )
        except Exception as e:
            rerank_ms = int((time.perf_counter() - t_rerank) * 1000)
            log_event(logger, "search.rerank_failed", logging.WARNING, error=repr(e), rerank_ms=rerank_ms)
            capture_exception(e, stage="rerank")
            products = candidates[:final_limit]
    else:
        products = candidates[:final_limit]

    return products, queue_wait_ms, embedding_ms, rpc_ms, rerank_ms


@app.get("/health")
async def health(response: Response, deep: bool = False) -> Dict[str, Any]:
    """Liveness by default. `/health?deep=1` also checks what a real search
    needs — both models loaded and Supabase reachable — so an uptime monitor
    catches "process up but can't serve" (the failure mode that matters)."""
    if not deep:
        return {"status": "ok"}
    from shared import embeddings as _emb, reranker as _rr

    checks: Dict[str, Any] = {
        "embedder_loaded": getattr(_emb, "_model", None) is not None,
        "reranker_loaded": (not RERANK_ENABLED) or getattr(_rr, "_reranker", None) is not None,
    }
    t0 = time.perf_counter()
    try:
        await asyncio.wait_for(
            asyncio.to_thread(lambda: get_supabase().table("products").select("id").limit(1).execute()),
            timeout=3.0,
        )
        checks["supabase"] = True
    except Exception as e:
        checks["supabase"] = False
        checks["supabase_error"] = type(e).__name__
    checks["supabase_ms"] = int((time.perf_counter() - t0) * 1000)
    ok = checks["embedder_loaded"] and checks["reranker_loaded"] and checks["supabase"]
    if not ok:
        response.status_code = 503
    return {"status": "ok" if ok else "degraded", **checks}


def _persist_search_latency(
    store_id: str,
    query: str,
    result_count: int,
    total_ms: int,
    embedding_ms: int,
    rpc_ms: int,
    queue_wait_ms: int,
    cache_hit: bool = False,
    rerank_ms: int = 0,
    conversation_id: Optional[str] = None,
    endpoint: str = "search",
) -> None:
    """Fire-and-forget insert into search_latency — server-side truth for the
    timing breakdown, independent of whether the widget's own /api/turn-latency
    POST ever arrives. Never awaited by the request path; a failure here must
    never slow down or fail a search response."""
    request_id = current_request_id()  # capture now — the request context is gone by insert time

    async def _do_insert() -> None:
        try:
            await asyncio.to_thread(
                insert_tolerant,
                "search_latency",
                {
                    "store_id": store_id,
                    "query": query[:200],
                    "result_count": result_count,
                    "total_ms": total_ms,
                    "embedding_ms": embedding_ms,
                    "rpc_ms": rpc_ms,
                    "rerank_ms": rerank_ms,
                    "queue_wait_ms": queue_wait_ms,
                    "cache_hit": cache_hit,
                    "config_variant": SEARCH_CONFIG_VERSION,
                    "conversation_id": conversation_id,
                    "request_id": request_id,
                    "endpoint": endpoint,
                },
                logger,
            )
        except Exception as e:
            logger.warning(f"Failed to persist search_latency (non-blocking): {e}")

    asyncio.ensure_future(_do_insert())


async def _search_uncached(sb, store_id: str, query: str, t0: float, conversation_id: Optional[str] = None):
    try:
        return await _hybrid_search_products(
            sb=sb, store_id=store_id, query=query, final_limit=12
        )
    except HTTPException as e:
        total_ms = int((time.perf_counter() - t0) * 1000)
        log_event(
            logger, "search.failed", logging.ERROR,
            total_ms=total_ms, status=e.status_code, store_id=store_id, query=query,
        )
        _persist_search_latency(
            store_id=store_id,
            query=query,
            result_count=0,
            total_ms=total_ms,
            embedding_ms=0,
            rpc_ms=0,
            queue_wait_ms=0,
            cache_hit=False,
            conversation_id=conversation_id,
            endpoint="search_error",
        )
        # FastAPI builds a fresh response for HTTPException, so anything written to
        # `response` here is discarded. The timing headers only survive if they ride
        # on the exception itself.
        raise HTTPException(
            status_code=e.status_code,
            detail=e.detail,
            headers={
                **(getattr(e, "headers", None) or {}),
                "X-Search-Duration-Ms": str(total_ms),
                "X-Search-Cache": "error",
            },
        ) from e


@app.post("/search", response_model=SearchResponse)
@limiter.limit(SEARCH_RATE_LIMIT)
async def search(
    request: Request,
    response: Response,
    req: SearchRequest,
) -> SearchResponse:
    bind_conversation(req.conversation_id)

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

    cached = _cache_get(req.store_id, req.query)
    if cached is not None:
        total_ms = int((time.perf_counter() - t0) * 1000)
        response.headers["X-Search-Duration-Ms"] = str(total_ms)
        response.headers["X-Search-Cache"] = "hit"
        log_event(
            logger, "search.completed",
            total_ms=total_ms, cache="hit", store_id=req.store_id,
            query=req.query, results=len(cached),
        )
        _persist_search_latency(
            store_id=req.store_id, query=req.query, result_count=len(cached),
            total_ms=total_ms, embedding_ms=0, rpc_ms=0, queue_wait_ms=0,
            cache_hit=True, conversation_id=req.conversation_id,
        )
        pitch = f"Found {len(cached)} products." if cached else "No matching products found."
        return SearchResponse(products=cached, pitch=pitch)

    products, queue_wait_ms, embedding_ms, rpc_ms, rerank_ms = await _search_uncached(
        sb=sb, store_id=req.store_id, query=req.query, t0=t0,
        conversation_id=req.conversation_id,
    )
    total_ms = int((time.perf_counter() - t0) * 1000)
    response.headers["X-Search-Duration-Ms"] = str(total_ms)
    response.headers["X-Search-Cache"] = "miss"
    log_event(
        logger, "search.completed",
        total_ms=total_ms, queue_wait_ms=queue_wait_ms, embedding_ms=embedding_ms,
        rpc_ms=rpc_ms, rerank_ms=rerank_ms, cache="miss", store_id=req.store_id,
        query=req.query, results=len(products),
    )
    _persist_search_latency(
        store_id=req.store_id,
        query=req.query,
        result_count=len(products),
        total_ms=total_ms,
        embedding_ms=embedding_ms,
        rpc_ms=rpc_ms,
        queue_wait_ms=queue_wait_ms,
        cache_hit=False,
        rerank_ms=rerank_ms,
        conversation_id=req.conversation_id,
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

    _cache_put(req.store_id, req.query, serialized_products)
    return SearchResponse(products=serialized_products, pitch=pitch)


@app.post("/product-details")
@limiter.limit(SEARCH_RATE_LIMIT)
async def get_product_details(
    request: Request,
    req: ProductDetailsRequest,
) -> Dict[str, Any]:
    bind_conversation(req.conversation_id)

    # --- Validation ---
    try:
        uuid.UUID(req.store_id)
        uuid.UUID(req.product_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid store_id or product_id format. Must be a valid UUID.")

    sb = get_supabase()
    t0 = time.perf_counter()

    # Query the products table. to_thread: supabase-py is synchronous — calling
    # it directly inside this async handler blocked the event loop, stalling
    # every concurrent /search for the duration of the round-trip.
    try:
        resp = await asyncio.wait_for(
            asyncio.to_thread(
                lambda: sb.table("products").select("name, metadata")
                .eq("id", req.product_id).eq("store_id", req.store_id).execute()
            ),
            timeout=RPC_TIMEOUT,
        )
    except asyncio.TimeoutError as e:
        raise HTTPException(
            status_code=503, detail="Database query timeout. Please try again later.",
            headers={"Retry-After": "2"},
        ) from e
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
    
    total_ms = int((time.perf_counter() - t0) * 1000)
    log_event(
        logger, "product_details.completed",
        total_ms=total_ms, store_id=req.store_id, product_id=req.product_id,
        variants=len(variants), description_chars=len(full_text),
    )
    _persist_search_latency(
        store_id=req.store_id, query=req.product_id, result_count=1,
        total_ms=total_ms, embedding_ms=0, rpc_ms=total_ms, queue_wait_ms=0,
        conversation_id=req.conversation_id, endpoint="product_details",
    )

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
    # CPU/RAM sampler — decides whether the 2 GB box is actually a bottleneck.
    asyncio.ensure_future(run_system_stats_logger(logger))
    asyncio.ensure_future(_keep_warm_loop())


KEEPWARM_INTERVAL_SECONDS = float(os.getenv("KEEPWARM_INTERVAL_SECONDS", "60"))


async def _keep_warm_loop() -> None:
    """Keep the hot path hot between shoppers.

    Measured 2026-10-01: after a quiet period the kernel had swapped ~430 MB of
    this process (the models) to disk, so the first real search took 3.2s
    (embedding 1.1s, RPC 1.5s) and ElevenLabs' 5s webhook timeout fired — the
    shopper heard "technical issue". A tiny embed + rerank + Supabase ping every
    minute keeps model pages resident and the HTTPS connection open.
    0 disables.
    """
    if KEEPWARM_INTERVAL_SECONDS <= 0:
        return

    def _touch() -> int:
        t0 = time.perf_counter()
        get_embedder().encode("keep warm", normalize_embeddings=True)
        if RERANK_ENABLED:
            rerank("keep warm", ["warm document"])
        get_supabase().table("products").select("id").limit(1).execute()
        return int((time.perf_counter() - t0) * 1000)

    while True:
        await asyncio.sleep(KEEPWARM_INTERVAL_SECONDS)
        try:
            ms = await asyncio.to_thread(_touch)
            # Slow keep-warm = something was cold anyway (swap, network): worth seeing.
            log_event(logger, "keepwarm", logging.WARNING if ms > 1000 else logging.DEBUG, duration_ms=ms)
        except Exception as e:
            log_event(logger, "keepwarm.failed", logging.WARNING, error=repr(e))


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
