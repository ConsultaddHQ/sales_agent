"""Embedding model singleton shared across services."""

import logging
from typing import Optional

from sentence_transformers import SentenceTransformer

from shared.config import EMBEDDING_MODEL

logger = logging.getLogger(__name__)

_model: Optional[SentenceTransformer] = None


def get_embedder() -> SentenceTransformer:
    """Get or load the embedding model (lazy singleton)."""
    global _model
    if _model is None:
        logger.info(f"Loading embedding model {EMBEDDING_MODEL}...")
        _model = SentenceTransformer(EMBEDDING_MODEL)
        logger.info("Embedding model loaded")
    return _model
