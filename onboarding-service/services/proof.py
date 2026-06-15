"""Pure proof ranking + normalisation for /sales/proof.

routes/sales.py owns the Supabase query; this owns relevance and the
clean shape the voice agent receives. No DB import → unit-testable.
Embeddings are YAGNI here (the curated set is tiny) — keyword/tag
overlap is enough.
"""

from typing import Dict, List, Optional

# The only proof categories the agent + admin understand.
PROOF_TYPES = ("case_study", "roi", "testimonial", "objection_rebuttal")


def is_valid_proof_type(t) -> bool:
    return t in PROOF_TYPES


def normalize_proof(row: Dict) -> Dict:
    """Coerce a DB row into the exact shape the agent expects."""
    r = row if isinstance(row, dict) else {}
    metric = r.get("metric")
    return {
        "type": str(r.get("type") or ""),
        "title": str(r.get("title") or ""),
        "body": str(r.get("body") or ""),
        "metric": metric if metric not in ("", None) else None,
        "tags": list(r.get("tags") or []),
    }


def rank_proof(
    rows,
    query: str,
    proof_type: Optional[str] = None,
    limit: int = 3,
) -> List[Dict]:
    """Rank curated proof by keyword/tag overlap with the query.

    Stable: ties and empty queries preserve input order (so the most
    recently curated/active rows win by default).
    """
    items = [normalize_proof(r) for r in (rows or []) if isinstance(r, dict)]
    if proof_type:
        items = [r for r in items if r["type"] == proof_type]

    terms = {t for t in str(query or "").lower().split() if len(t) > 2}

    def score(r: Dict) -> int:
        hay = " ".join([r["title"], r["body"], " ".join(r["tags"])]).lower()
        return sum(1 for t in terms if t in hay)

    ranked = sorted(items, key=score, reverse=True)  # stable sort
    return ranked[: max(0, limit)]
