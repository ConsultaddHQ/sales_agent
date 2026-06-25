"""Cross-encoder reranker — lazy thread-safe singleton, mirrors shared/embeddings.py."""

import logging
import os
from threading import Lock
from typing import Optional

from sentence_transformers import CrossEncoder

from shared.config import RERANK_MODEL

logger = logging.getLogger(__name__)

_reranker: Optional[CrossEncoder] = None
_reranker_lock = Lock()


def get_reranker() -> CrossEncoder:
    """Get or load the cross-encoder model (lazy singleton)."""
    global _reranker
    if _reranker is not None:
        return _reranker
    with _reranker_lock:
        if _reranker is None:
            logger.info(f"Loading reranker model {RERANK_MODEL}...")
            _reranker = CrossEncoder(RERANK_MODEL)
            logger.info("Reranker model loaded")
    return _reranker


def rerank(query: str, docs: list[str]) -> list[float]:
    """Score (query, doc) pairs; returns a relevance score per doc (higher = better)."""
    if not docs:
        return []
    pairs = [(query, d) for d in docs]
    scores = get_reranker().predict(pairs)
    return scores.tolist() if hasattr(scores, "tolist") else list(scores)
