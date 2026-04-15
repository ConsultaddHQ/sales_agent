"""Supabase client singleton shared across services."""

from threading import Lock
from typing import Optional
from supabase import Client, create_client

from shared.config import SUPABASE_URL, SUPABASE_KEY

_supabase: Optional[Client] = None
_supabase_lock = Lock()


def get_supabase() -> Client:
    """Get or create the Supabase client (lazy singleton)."""
    global _supabase
    if _supabase is not None:
        return _supabase
    with _supabase_lock:
        if _supabase is None:
            _supabase = create_client(SUPABASE_URL().rstrip("/"), SUPABASE_KEY())
    return _supabase
