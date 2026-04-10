"""Adapter registry — auto-registers all built-in adapters on import."""

from .registry import register, get_adapter, detect_store_type  # noqa: F401
from .shopify import ShopifyAdapter
from .threadless import ThreadlessAdapter
from .supermicro import SupermicroAdapter

# Register built-in adapters
register(ShopifyAdapter())
register(ThreadlessAdapter())
register(SupermicroAdapter())

# Universal adapter registered last (lowest priority, catch-all)
# Imported after Phase 8 is built; for now the pipeline falls back gracefully.
try:
    from .universal import UniversalAdapter
    register(UniversalAdapter())
except ImportError:
    pass
