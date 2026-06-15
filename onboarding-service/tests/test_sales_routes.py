"""Phase 7 — route-layer tests for the §8 load-bearing risk path.

DESIGN §8 Q2 names `{{system__conversation_id}}` the program's
load-bearing unverified assumption. The degradation logic in
routes/sales.py (`_load_session`/`_save_session`) was previously only
"correct by inspection" — this makes it a tested contract.

`supabase` isn't installed in the unit env, so we stub it in sys.modules
before importing the route, then inject fakes for the DB + LLM.
"""

import sys
import types

import pytest

# Stub `supabase` so `from shared.db import get_supabase` imports headless.
if "supabase" not in sys.modules:
    _stub = types.ModuleType("supabase")
    _stub.Client = object
    _stub.create_client = lambda *a, **k: None
    sys.modules["supabase"] = _stub

from routes import sales as sales_route  # noqa: E402


class _BoomClient:
    """Any DB use explodes — proves the unresolved path never touches it."""

    def table(self, *_a, **_k):
        raise AssertionError("DB must not be called for an unresolved conversation_id")


@pytest.fixture(autouse=True)
def _fakes(monkeypatch):
    # LLM returns a valid decision so the brain path is exercised without network.
    monkeypatch.setattr(
        sales_route, "make_llm",
        lambda: (lambda system, user: '{"stage":"discovery","say_guidance":"tell me more"}'),
    )
    yield


@pytest.mark.parametrize("conv", ["", "{{system__conversation_id}}"])
def test_load_session_unresolved_id_returns_base_and_never_hits_db(conv, monkeypatch):
    monkeypatch.setattr(sales_route, "get_supabase", lambda: _BoomClient())
    s = sales_route._load_session(conv, "teampop")
    assert s["stage"] == "rapport"
    assert s["pic"] == [] and s["captured"] == {} and s["transcript"] == []
    assert s["site"] == "teampop"


@pytest.mark.parametrize("conv", ["", "{{system__conversation_id}}"])
def test_save_session_unresolved_id_is_noop_and_never_raises(conv, monkeypatch):
    monkeypatch.setattr(sales_route, "get_supabase", lambda: _BoomClient())
    # Must not raise even though the DB client would explode if touched.
    sales_route._save_session(conv, "teampop", {"stage": "discovery"})


def test_load_session_db_down_degrades_to_base(monkeypatch):
    def boom():
        raise RuntimeError("supabase unreachable")

    monkeypatch.setattr(sales_route, "get_supabase", boom)
    s = sales_route._load_session("a-real-conversation-id", "teampop")
    assert s["stage"] == "rapport"          # resilient: fresh session, no crash
    assert s["conversation_id"] == "a-real-conversation-id"


def test_brain_endpoint_works_statelessly_on_unresolved_id(monkeypatch):
    monkeypatch.setattr(sales_route, "get_supabase", lambda: _BoomClient())
    body = sales_route.BrainBody(
        site="teampop", conversation_id="{{system__conversation_id}}", message="hi there"
    )
    out = sales_route.sales_brain(body)
    # HTTP 200-shaped payload even with no persistence + a "boom" DB.
    assert set(out) == {"stage", "say", "next_move", "directives"}
    assert out["stage"] in (
        "rapport", "discovery", "quantify_gap", "demo",
        "pricing", "objection", "close", "booked",
    )
    assert isinstance(out["directives"], list)
