import os
import logging
from threading import Lock
from typing import Optional

# Limit PyTorch CPU threads early, before model load to prevent CPU thrashing
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

import torch
torch.set_num_threads(1)
torch.set_num_interop_threads(1)

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
