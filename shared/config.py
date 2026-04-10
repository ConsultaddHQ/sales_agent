"""Centralized configuration and constants for all services."""

import os
from pathlib import Path

# ── Embedding model (constraint #1: must stay aligned across services) ──
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

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


def WIDGET_SCRIPT_URL() -> str:
    return get_env("WIDGET_SCRIPT_URL", "http://localhost:5173/widget.js")


def STORE_IMAGES_PATH() -> Path:
    return Path(get_env("STORE_IMAGES_PATH", "./images"))


def ADMIN_PASSWORD() -> str:
    return get_env("ADMIN_PASSWORD", "changeme")
