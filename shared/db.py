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


def insert_tolerant(table: str, row: dict, logger=None, upsert_on: Optional[str] = None) -> None:
    """Insert (or upsert) a row, dropping any column PostgREST says is missing.

    Telemetry tables often lag behind code (a migration not yet run on the live
    project — see the 2026-07-16 session_feedback incident). Losing one column
    beats losing the whole row. Raises on any other error.
    """
    import re

    row = dict(row)
    sb = get_supabase()
    for _ in range(len(row) + 1):
        try:
            q = sb.table(table)
            (q.upsert(row, on_conflict=upsert_on) if upsert_on else q.insert(row)).execute()
            return
        except Exception as err:
            m = re.search(r"Could not find the '([^']+)' column", str(err))
            if not m or m.group(1) not in row:
                raise
            if logger:
                logger.warning(f"{table} missing column '{m.group(1)}' — retrying without it (run the migration)")
            row.pop(m.group(1))
