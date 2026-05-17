"""Phase 3 — pure proof ranking/normalisation (no DB).

routes/sales.py does the Supabase query; THIS decides relevance + the
clean shape the agent receives. Pure → unit-tested.
"""

from services.proof import rank_proof, normalize_proof

ROWS = [
    {"type": "roi", "title": "ROI vs hiring an SDR",
     "body": "one agent is a fraction of one hire", "metric": "pays for itself",
     "tags": ["roi", "expensive", "budget"]},
    {"type": "case_study", "title": "Shopify apparel brand",
     "body": "voice agent on every product page lifted add to cart",
     "metric": "1.9x", "tags": ["ecommerce", "shopify", "conversion"]},
    {"type": "testimonial", "title": "Founder, DTC brand",
     "body": "feels like a great salesperson on every page", "tags": ["social proof"]},
]


def test_normalize_fills_defaults_and_coerces_types():
    n = normalize_proof({"title": "T"})
    assert n == {"type": "", "title": "T", "body": "", "metric": None, "tags": []}
    n2 = normalize_proof({"type": "roi", "title": "x", "body": "y", "metric": "m", "tags": ["a"]})
    assert n2["metric"] == "m" and n2["tags"] == ["a"]
    # unknown keys dropped
    assert "secret" not in normalize_proof({"title": "t", "secret": 1})


def test_rank_orders_by_term_overlap():
    out = rank_proof(ROWS, "expensive budget for an SDR", proof_type=None, limit=3)
    assert out[0]["title"] == "ROI vs hiring an SDR"  # most term hits


def test_rank_respects_limit():
    assert len(rank_proof(ROWS, "agent", None, limit=1)) == 1


def test_rank_filters_by_type():
    out = rank_proof(ROWS, "agent", proof_type="testimonial", limit=5)
    assert len(out) == 1 and out[0]["type"] == "testimonial"


def test_empty_query_returns_up_to_limit_normalized():
    out = rank_proof(ROWS, "", None, limit=2)
    assert len(out) == 2
    assert set(out[0].keys()) == {"type", "title", "body", "metric", "tags"}


def test_tags_contribute_to_score():
    out = rank_proof(ROWS, "shopify", None, limit=1)
    assert out[0]["title"] == "Shopify apparel brand"


def test_bad_rows_do_not_crash():
    rows = [None, "nope", {"title": "ok", "body": "agent"}]
    out = rank_proof(rows, "agent", None, limit=5)
    assert out and out[0]["title"] == "ok"
