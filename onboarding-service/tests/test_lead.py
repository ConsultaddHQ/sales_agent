"""Phase 4 — pure lead enrichment (no DB).

Turns a sales_sessions row into the fields attached to the agent_requests
lead on the assisted close. Pure → unit-tested.
"""

from services.lead import build_lead_enrichment


def test_full_session_maps_transcript_discovery_pic():
    row = {
        "transcript": [{"role": "visitor", "text": "hi"}],
        "captured": {"email": "jane@acme.com", "use_case": "outreach"},
        "pic": [{"technical_problem": "manual", "business_impact": "20h/wk"}],
    }
    out = build_lead_enrichment(row)
    assert out["source"] == "sales_agent"
    assert out["transcript"] == row["transcript"]
    assert out["discovery"] == row["captured"]
    assert out["pic"] == row["pic"]


def test_no_session_still_marks_source_only():
    assert build_lead_enrichment(None) == {"source": "sales_agent"}
    assert build_lead_enrichment({}) == {"source": "sales_agent"}


def test_missing_subfields_are_safe_defaults():
    out = build_lead_enrichment({"captured": {"email": "x@y.com"}})
    assert out["discovery"] == {"email": "x@y.com"}
    assert out["transcript"] == []
    assert out["pic"] == []


def test_explicit_source_is_respected():
    assert build_lead_enrichment(None, source="website")["source"] == "website"
    assert build_lead_enrichment({"pic": []}, source="campaign")["source"] == "campaign"
