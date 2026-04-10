"""Base adapter interface for store types.

Adding a new store type = implement this ABC + register in __init__.py.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class StoreAdapter(ABC):
    """Abstract base for all store adapters."""

    @property
    @abstractmethod
    def store_type(self) -> str:
        """Unique identifier for this store type (e.g. 'shopify', 'threadless')."""
        ...

    @property
    def needs_playwright(self) -> bool:
        """Whether test page generation needs Playwright (for bot-protected sites)."""
        return False

    @property
    def challenge_wait(self) -> int:
        """Seconds to wait for bot challenge resolution (Playwright only)."""
        return 10

    def matches_url(self, url: str) -> bool:
        """Return True if this adapter should handle the given URL.

        Override to implement URL-based auto-detection.
        Default returns False (must be selected explicitly).
        """
        return False

    @abstractmethod
    def scrape_products(self, url: str, max_products: int = 200) -> List[Dict[str, Any]]:
        """Scrape products and return Shopify-normalized dicts.

        Each dict must have:
            handle: str
            title: str
            body_html: str
            variants: [{"price": str}]
            images: [{"src": str}]
            _original_product_url: str (optional, for non-Shopify URLs)
        """
        ...

    @abstractmethod
    def extract_store_context(
        self, products: List[Dict[str, Any]], domain: str
    ) -> Dict[str, Any]:
        """Build store context dict for agent creation.

        Must return: {"store_name", "description", "categories", "price_range"}
        """
        ...

    def get_agent_tags(self, store_id: str) -> List[str]:
        """Tags for the ElevenLabs agent. Override to customize."""
        return ["teampop", self.store_type, store_id]
