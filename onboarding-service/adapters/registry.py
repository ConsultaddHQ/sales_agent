"""Adapter registry — lookup by type or auto-detect from URL."""

import logging
from typing import Dict, Optional
from urllib.parse import urlparse

from .base import StoreAdapter

logger = logging.getLogger("onboarding-service")

_registry: Dict[str, StoreAdapter] = {}


def register(adapter: StoreAdapter) -> None:
    """Register an adapter instance."""
    _registry[adapter.store_type] = adapter
    logger.debug(f"Registered adapter: {adapter.store_type}")


def get_adapter(store_type: str) -> StoreAdapter:
    """Get adapter by type. Raises KeyError if not found."""
    if store_type not in _registry:
        available = ", ".join(_registry.keys())
        raise KeyError(f"Unknown store type '{store_type}'. Available: {available}")
    return _registry[store_type]


def detect_store_type(url: str) -> str:
    """Auto-detect store type from URL.

    Checks each registered adapter's matches_url() method.
    Falls back to 'universal' if available, else 'shopify'.
    """
    normalized = url if url.startswith("http") else f"https://{url}"
    for adapter in _registry.values():
        if adapter.matches_url(normalized):
            logger.info(f"Auto-detected store type: {adapter.store_type}")
            return adapter.store_type

    # Fallback
    fallback = "universal" if "universal" in _registry else "shopify"
    logger.info(f"No platform match — falling back to '{fallback}'")
    return fallback


def list_adapters() -> Dict[str, StoreAdapter]:
    """Return all registered adapters."""
    return dict(_registry)
