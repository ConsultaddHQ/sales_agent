"""
TeamPop Onboarding Service
Unified entry point — all business logic lives in routes/, services/, adapters/.
"""

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Ensure shared/ and this directory are importable
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
_SERVICE_DIR = str(Path(__file__).resolve().parent)
for p in (_REPO_ROOT, _SERVICE_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

# Load environment
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Logging + error tracking (see shared/observability.py for env vars)
from shared.observability import (
    CorrelationMiddleware,
    bind_conversation,
    current_request_id,
    init_sentry,
    log_event,
    run_system_stats_logger,
    setup_logging,
)

logger = setup_logging("onboarding-service")
init_sentry("onboarding-service")

# FastAPI app
app = FastAPI(title="TeamPop Onboarding Service", version="3.0.0")

# CORS allowlist: comma-separated origins via ALLOWED_ORIGINS; defaults to "*" for dev.
# Set to the client's storefront domain(s) in production (e.g. https://goxfused.com).
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-Id"],
)
app.add_middleware(CorrelationMiddleware)

# Serve built widget.js from frontend dist
WIDGET_DIST_DIR = Path(__file__).parent.parent / "www.teampop" / "frontend" / "dist"
if WIDGET_DIST_DIR.exists():
    app.mount("/widget", StaticFiles(directory=str(WIDGET_DIST_DIR)), name="widget")
    logger.info(f"Widget served from: {WIDGET_DIST_DIR}")
else:
    logger.warning(f"Widget dist not found at {WIDGET_DIST_DIR} — run npm run build in frontend/")

# Serve generated demo pages
DEMO_PAGES_DIR = Path("./demo_pages")
DEMO_PAGES_DIR.mkdir(exist_ok=True)
app.mount("/demo", StaticFiles(directory=str(DEMO_PAGES_DIR), html=True), name="demo")

# Serve product images directly (so everything works through a single tunnel)
IMAGES_DIR = Path(__file__).resolve().parent / "images"
IMAGES_DIR.mkdir(exist_ok=True)
app.mount("/images", StaticFiles(directory=str(IMAGES_DIR)), name="images")
logger.info(f"Images served from: {IMAGES_DIR}")

# Register routes
from routes.onboard import router as onboard_router
from routes.admin import router as admin_router
from routes.client import router as client_router
from routes.webhooks import router as webhooks_router

app.include_router(onboard_router)
app.include_router(admin_router)
app.include_router(client_router)
app.include_router(webhooks_router)

# Force adapter registration on startup
import adapters  # noqa: F401


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "onboarding-service",
        "version": "3.0.0",
    }


# ── Search proxy (so ElevenLabs webhook can hit the same ngrok tunnel) ──
import asyncio
import json as _json
import time as _time

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse

SEARCH_SERVICE_URL = os.getenv("SEARCH_SERVICE_INTERNAL", "http://localhost:8006")

# Module-scope client reused across all proxy calls. Keeps one HTTP/1.1
# connection pool alive instead of re-handshaking per request. Closed on
# application shutdown to avoid leaked sockets.
_search_proxy_client: httpx.AsyncClient | None = None


@app.on_event("startup")
async def _init_search_proxy_client() -> None:
    global _search_proxy_client
    _search_proxy_client = httpx.AsyncClient(
        timeout=25,
        limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
    )
    logger.info(f"Search proxy client initialized (target={SEARCH_SERVICE_URL})")
    asyncio.ensure_future(run_system_stats_logger(logger))
    asyncio.ensure_future(_keep_proxy_warm())


async def _keep_proxy_warm() -> None:
    """Ping search-service through the pooled client every minute so this
    process's proxy path (and its pages) stay resident — a cold proxy added
    ~700ms to the first search after idle (2026-10-01). 0 disables."""
    interval = float(os.getenv("KEEPWARM_INTERVAL_SECONDS", "60"))
    if interval <= 0:
        return
    while True:
        await asyncio.sleep(interval)
        try:
            if _search_proxy_client is not None:
                await _search_proxy_client.get(f"{SEARCH_SERVICE_URL}/health", timeout=5)
        except Exception as e:
            log_event(logger, "keepwarm.failed", logging.WARNING, error=repr(e))


@app.on_event("shutdown")
async def _close_search_proxy_client() -> None:
    global _search_proxy_client
    if _search_proxy_client is not None:
        await _search_proxy_client.aclose()
        _search_proxy_client = None


@app.post("/search")
async def search_proxy(request: Request):
    """Proxy search requests to the search service.

    - Single ngrok tunnel on port 8005 serves everything (demo pages,
      widget, images, and this search webhook for ElevenLabs).
    - Reuses a module-scope httpx.AsyncClient (no per-request handshake).
    - Forwards the `X-Search-Duration-Ms` header from the downstream
      search service so the caller (ElevenLabs / widget) can correlate
      end-to-end latency with search-only latency.
    - Logs a one-line summary correlating store_id + query + search_ms
      so STEP 1 of the latency plan can be verified from the server logs.
    """
    body = await request.body()

    # Best-effort parse for logging; never fail the proxy on bad JSON — let
    # the search service return its own clear 400.
    store_id_log = "?"
    query_log = "?"
    try:
        parsed = _json.loads(body or b"{}")
        if isinstance(parsed, dict):
            store_id_log = str(parsed.get("store_id", "?"))
            query_log = str(parsed.get("query", "?"))[:80]
            bind_conversation(parsed.get("conversation_id"))
    except Exception:
        pass

    return await _proxy_to_search("/search", body, store_id_log, query_log, request)


@app.post("/product-details")
async def product_details_proxy(request: Request):
    """Proxy get_product_details webhook calls to the search service.

    The ElevenLabs `get_product_details` tool posts to this path on the same
    single ngrok tunnel that serves `/search`. Without this route the tool
    would 404 (onboarding service is the only externally-tunneled origin).
    """
    body = await request.body()

    store_id_log = "?"
    product_id_log = "?"
    try:
        parsed = _json.loads(body or b"{}")
        if isinstance(parsed, dict):
            store_id_log = str(parsed.get("store_id", "?"))
            product_id_log = str(parsed.get("product_id", "?"))
            bind_conversation(parsed.get("conversation_id"))
    except Exception:
        pass

    return await _proxy_to_search(
        "/product-details", body, store_id_log, product_id_log, request
    )


async def _proxy_to_search(
    path: str,
    body: bytes,
    store_id_log: str,
    detail_log: str,
    request: Request,
):
    """Forward a request body to `{SEARCH_SERVICE_URL}{path}` and relay the response."""
    # Carry correlation + real client IP downstream: search-service logs the
    # same request_id, and its per-IP rate limit stops lumping every caller
    # under 127.0.0.1.
    headers = {"Content-Type": "application/json"}
    rid = current_request_id()
    if rid:
        headers["X-Request-Id"] = rid
    fwd = request.headers.get("x-forwarded-for") or (request.client.host if request.client else None)
    if fwd:
        headers["X-Forwarded-For"] = fwd
    client = _search_proxy_client
    if client is None:
        # Extremely unlikely — startup event hasn't fired. Fall back to a
        # one-shot client so we never 500 on this path.
        logger.warning("Search proxy client missing on startup; using one-shot client")
        async with httpx.AsyncClient(timeout=25) as one_shot:
            return await _do_proxy(one_shot, path, body, store_id_log, detail_log, headers)
    return await _do_proxy(client, path, body, store_id_log, detail_log, headers)


async def _do_proxy(
    client: httpx.AsyncClient,
    path: str,
    body: bytes,
    store_id_log: str,
    detail_log: str,
    headers: dict,
):
    proxy_start = _time.perf_counter()
    try:
        resp = await client.post(f"{SEARCH_SERVICE_URL}{path}", content=body, headers=headers)
    except Exception as e:
        log_event(
            logger, "proxy.error", logging.ERROR,
            path=path, store_id=store_id_log, detail=detail_log, error=repr(e),
        )
        return JSONResponse(content={"error": "search service unavailable"}, status_code=502)

    proxy_ms = int((_time.perf_counter() - proxy_start) * 1000)
    downstream_ms = resp.headers.get("X-Search-Duration-Ms")
    log_event(
        logger, "proxy.completed",
        path=path, store_id=store_id_log, detail=detail_log,
        search_ms=int(downstream_ms) if downstream_ms and downstream_ms.isdigit() else None,
        proxy_total_ms=proxy_ms, status=resp.status_code,
        cache=resp.headers.get("X-Search-Cache"),
    )

    # Forward the timing headers through to the caller (ElevenLabs webhook /
    # browser widget). Also preserve status code and JSON body.
    forward_headers = {
        h: resp.headers[h] for h in ("X-Search-Duration-Ms", "X-Search-Cache") if h in resp.headers
    }

    try:
        content = resp.json()
    except Exception:
        content = {"error": "search service returned non-JSON body"}

    return JSONResponse(
        content=content,
        status_code=resp.status_code,
        headers=forward_headers,
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8005))
    logger.info(f"Starting Onboarding Service on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
