"""Phase 3 — pure proof ranking/normalisation (no DB).

routes/sales.py does the Supabase query; THIS decides relevance + the
clean shape the agent receives. Pure → unit-tested.
"""

from services.proof import rank_proof, normalize_proof, PROOF_TYPES, is_valid_proof_type


def test_proof_types_and_validator():
    assert set(PROOF_TYPES) == {"case_study", "roi", "testimonial", "objection_rebuttal"}
    assert is_valid_proof_type("roi") is True
    assert is_valid_proof_type("rm -rf") is False
    assert is_valid_proof_type(None) is False

# NOTE: the term-overlap winner ("ROI vs hiring an SDR") is deliberately
# LAST in input order. rank_proof uses a stable sort, so if scoring were
# broken the testimonial (index 0) would stay #0 — the ordering test only
# passes when ranking actually works (avoids a false-confidence test).
ROWS = [
    {"type": "testimonial", "title": "Founder, DTC brand",
     "body": "feels like a great salesperson on every page", "tags": ["social proof"]},
    {"type": "case_study", "title": "Shopify apparel brand",
     "body": "voice agent on every product page lifted add to cart",
     "metric": "1.9x", "tags": ["ecommerce", "shopify", "conversion"]},
    {"type": "roi", "title": "ROI vs hiring an SDR",
     "body": "one agent is a fraction of one hire", "metric": "pays for itself",
     "tags": ["roi", "expensive", "budget"]},
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
    assert out[0]["title"] != ROWS[0]["title"]  # ranking lifted it past input order


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
