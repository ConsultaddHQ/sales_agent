"""Centralized configuration and constants for all services."""

import os
from pathlib import Path

# ── Embedding model (constraint #1: must stay aligned across services) ──
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

# ── Reranker (cross-encoder, runs in search-service only) ──
RERANK_MODEL = os.getenv("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
RERANK_CANDIDATES = int(os.getenv("RERANK_CANDIDATES", "30"))
RERANK_TIMEOUT = float(os.getenv("RERANK_TIMEOUT", "3.0"))
RERANK_ENABLED = os.getenv("RERANK_ENABLED", "true").lower() == "true"
# Relevance cutoff: after reranking, keep only results whose cross-encoder score is
# within this margin of the top score. Trims the irrelevant tail on specific queries
# ("moisturizer" -> just moisturizers) while keeping broad queries full (clustered
# scores all fall within the margin). Set very high (e.g. 999) to disable.
RERANK_SCORE_MARGIN = float(os.getenv("RERANK_SCORE_MARGIN", "4.0"))

# ── Defaults ──
MAX_PRODUCTS = 200
IMAGE_DOWNLOAD_TIMEOUT = 15  # seconds
CHUNK_SIZE = 100  # batch insert size


def get_env(name: str, default: str = None) -> str:
    """Get an environment variable, raise if required and missing."""
    val = os.getenv(name, default)
    if val is None:
        raise RuntimeError(f"Missing required env var: {name}")
    return val


# ── Service URLs (single source of truth for defaults) ──

def SUPABASE_URL() -> str:
    return get_env("SUPABASE_URL")


def SUPABASE_KEY() -> str:
    return get_env("SUPABASE_KEY")


def SEARCH_API_URL() -> str:
    return get_env("SEARCH_API_URL", "http://localhost:8006")


def IMAGE_SERVER_URL() -> str:
    return get_env("IMAGE_SERVER_URL", "http://localhost:8000")


def PUBLIC_SEARCH_API_URL() -> str:
    """Publicly reachable URL of the search service, injected into the widget snippet.
    On a live Shopify embed the widget runs cross-origin, so it needs an absolute URL
    to reach /product-details and /search. Default falls back to SEARCH_API_URL for dev."""
    return get_env("PUBLIC_SEARCH_API_URL", SEARCH_API_URL())


def WIDGET_SCRIPT_URL() -> str:
    return get_env("WIDGET_SCRIPT_URL", "http://localhost:5173/widget.js")


def STORE_IMAGES_PATH() -> Path:
    return Path(get_env("STORE_IMAGES_PATH", "./images"))


def ADMIN_PASSWORD() -> str:
    return get_env("ADMIN_PASSWORD", "changeme")
