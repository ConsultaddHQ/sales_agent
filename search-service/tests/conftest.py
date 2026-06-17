"""Pytest bootstrap for search-service tests.

Keeps the suite hermetic: no real Supabase, no model download, no webhook
enforcement by default, and a high rate limit so repeated calls don't 429.
These env vars must be set BEFORE `main` is imported (the rate limit and
secret are read at module import time).
"""
import os
import sys
from pathlib import Path

# Make `import main` resolve to search-service/main.py.
SEARCH_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SEARCH_DIR))

os.environ.setdefault("WEBHOOK_SECRET", "")          # no enforcement by default
os.environ.setdefault("SEARCH_RATE_LIMIT", "1000/minute")
os.environ.setdefault("ALLOWED_ORIGINS", "*")
os.environ.setdefault("RELOAD", "false")
