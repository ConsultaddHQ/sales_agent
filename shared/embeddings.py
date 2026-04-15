"""Embedding model singleton shared across services."""

import logging
from threading import Lock
from typing import Optional

from sentence_transformers import SentenceTransformer

from shared.config import EMBEDDING_MODEL

logger = logging.getLogger(__name__)

_model: Optional[SentenceTransformer] = None
_model_lock = Lock()


def get_embedder() -> SentenceTransformer:
    """Get or load the embedding model (lazy singleton)."""
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is None:
            logger.info(f"Loading embedding model {EMBEDDING_MODEL}...")
            _model = SentenceTransformer(EMBEDDING_MODEL)
            logger.info("Embedding model loaded")
    return _model
