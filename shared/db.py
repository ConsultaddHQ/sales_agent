"""Supabase client singleton shared across services."""

from typing import Optional
from supabase import Client, create_client

from shared.config import SUPABASE_URL, SUPABASE_KEY

_supabase: Optional[Client] = None


def get_supabase() -> Client:
    """Get or create the Supabase client (lazy singleton)."""
    global _supabase
    if _supabase is not None:
        return _supabase
    _supabase = create_client(SUPABASE_URL().rstrip("/"), SUPABASE_KEY())
    return _supabase
