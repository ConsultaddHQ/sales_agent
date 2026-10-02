"""Offline tests for the observability layer — no Supabase, no models, no network.

Run (any venv with fastapi, httpx, requests, python-dotenv, slowapi, supabase,
sentry-sdk, psutil, pytest):

    python -m pytest testing/observability -q

sentence-transformers is stubbed so the ML models never load; Supabase is
replaced with an in-memory fake that records inserts.
"""

import hashlib
import hmac
import importlib
import json
import logging
import sys
import time
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for p in (str(REPO), str(REPO / "onboarding-service"), str(REPO / "search-service")):
    if p not in sys.path:
        sys.path.insert(0, p)


# ── stubs ──────────────────────────────────────────────────────────────────

class _FakeVec(list):
    def tolist(self):
        return list(self)


class _FakeST:
    def __init__(self, *a, **k):
        pass

    def encode(self, text, normalize_embeddings=True):
        return _FakeVec([0.1] * 384)


class _FakeCE:
    def __init__(self, *a, **k):
        pass

    def predict(self, pairs):
        return _FakeVec([float(len(pairs) - i) for i in range(len(pairs))])


st = types.ModuleType("sentence_transformers")
st.SentenceTransformer = _FakeST
st.CrossEncoder = _FakeCE
sys.modules["sentence_transformers"] = st
torch_stub = types.ModuleType("torch")
torch_stub.set_num_threads = lambda n: None
torch_stub.set_num_interop_threads = lambda n: None
sys.modules.setdefault("torch", torch_stub)


class _Resp:
    def __init__(self, data):
        self.data = data


class FakeSupabase:
    """Records inserts/upserts; optionally rejects named columns like PostgREST."""

    def __init__(self, rpc_rows=None, missing_columns=()):
        self.rows = {}
        self.rpc_rows = rpc_rows or []
        self.missing = set(missing_columns)

    def table(self, name):
        sb = self

        class Q:
            def __init__(self):
                self._op = None

            def insert(self, row):
                self._op = ("insert", row)
                return self

            def upsert(self, row, on_conflict=None):
                self._op = ("upsert", row)
                return self

            def select(self, *a, **k):
                self._op = ("select", None)
                return self

            def eq(self, *a):
                return self

            def limit(self, *a):
                return self

            def execute(self):
                kind, row = self._op
                if kind == "select":
                    return _Resp([{"id": "x", "name": "Face Wash", "metadata": {"variants": [{"id": 1}]}}])
                for col in row:
                    if col in sb.missing:
                        raise Exception(f"Could not find the '{col}' column of '{name}' in the schema cache")
                sb.rows.setdefault(name, []).append(row)
                return _Resp([row])

        return Q()

    def rpc(self, name, params):
        sb = self

        class R:
            def execute(self):
                return _Resp(sb.rpc_rows)

        return R()


@pytest.fixture
def fake_sb(monkeypatch):
    import shared.db as db

    fake = FakeSupabase(rpc_rows=[
        {"id": "11111111-1111-1111-1111-111111111111", "store_id": "s", "name": "Rose Face Wash",
         "description": "Gentle cleanser", "price": 299, "image_url": "http://img/a.jpg",
         "local_image_path": None, "product_url": "http://p/a", "similarity": 0.8, "metadata": {}},
        {"id": "22222222-2222-2222-2222-222222222222", "store_id": "s", "name": "Aloe Gel",
         "description": "Soothing", "price": 199, "image_url": "http://img/b.jpg",
         "local_image_path": None, "product_url": "http://p/b", "similarity": 0.6, "metadata": {}},
    ])
    monkeypatch.setattr(db, "_supabase", fake)
    return fake


# ── shared.db.insert_tolerant ──────────────────────────────────────────────

def test_insert_tolerant_drops_missing_column(fake_sb):
    from shared.db import insert_tolerant

    fake_sb.missing = {"rerank_ms"}
    insert_tolerant("search_latency", {"store_id": "s", "rerank_ms": 5})
    assert fake_sb.rows["search_latency"] == [{"store_id": "s"}]


def test_insert_tolerant_reraises_other_errors(fake_sb, monkeypatch):
    from shared.db import insert_tolerant

    def boom(name):
        raise RuntimeError("network down")

    monkeypatch.setattr(fake_sb, "table", boom)
    with pytest.raises(RuntimeError):
        insert_tolerant("t", {"a": 1})


# ── shared.observability ───────────────────────────────────────────────────

def test_json_log_carries_conversation_id(capsys):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from shared import observability as obs

    obs.setup_logging("test-svc")
    app = FastAPI()
    app.add_middleware(obs.CorrelationMiddleware)

    @app.post("/x")
    async def x(body: dict):
        obs.bind_conversation(body.get("conversation_id"))
        obs.log_event(logging.getLogger("test-svc"), "x.done", n=1)
        return {"ok": True}

    r = TestClient(app).post("/x", json={"conversation_id": "conv_abc"}, headers={"X-Request-Id": "rid123"})
    assert r.status_code == 200
    assert r.headers["x-request-id"] == "rid123"
    lines = [json.loads(l) for l in capsys.readouterr().err.strip().splitlines() if l.startswith("{")]
    done = next(l for l in lines if l.get("event") == "x.done")
    access = next(l for l in lines if l.get("event") == "http.request")
    assert done["conversation_id"] == "conv_abc" and done["request_id"] == "rid123" and done["n"] == 1
    # conversation bound inside the endpoint is visible on the access line too
    assert access["conversation_id"] == "conv_abc" and access["status"] == 200


# ── post-call webhook ──────────────────────────────────────────────────────

SECRET = "whsec_test"

SAMPLE = {
    "type": "post_call_transcription",
    "event_timestamp": 1790000000,
    "data": {
        "agent_id": "agent_1",
        "conversation_id": "conv_1",
        "status": "done",
        "transcript": [
            {"role": "agent", "message": "Hi! What are you looking for?", "time_in_call_secs": 0,
             "conversation_turn_metrics": {"metrics": {"convai_llm_service_ttfb": {"elapsed_time": 0.4}}}},
            {"role": "user", "message": "face wash for oily skin", "time_in_call_secs": 4},
            {"role": "agent", "message": "", "time_in_call_secs": 6,
             "tool_calls": [{"tool_name": "search_products", "params_as_json": "{\"query\":\"face wash oily\"}"}],
             "tool_results": [{"tool_name": "search_products", "tool_latency_secs": 1.25, "is_error": False}],
             "conversation_turn_metrics": {"metrics": {"convai_llm_service_ttfb": {"elapsed_time": 0.9},
                                                       "convai_llm_service_ttf_sentence": {"elapsed_time": 1.4}}}},
            {"role": "agent", "message": "Here are some options", "time_in_call_secs": 8, "interrupted": True,
             "tool_results": [{"tool_name": "get_product_details", "tool_latency_secs": 5.0, "is_error": True}]},
        ],
        "metadata": {"start_time_unix_secs": 1790000000, "call_duration_secs": 42,
                     "termination_reason": "client disconnected", "cost": 120},
        "analysis": {"call_successful": "success", "transcript_summary": "Shopper wanted face wash.",
                     "evaluation_criteria_results": {"found_product": {"result": "success"}},
                     "data_collection_results": {"unmet_need": {"value": None}}},
    },
}


def _sign(body: str, ts: int = None) -> str:
    ts = ts or int(time.time())
    return f"t={ts},v0=" + hmac.new(SECRET.encode(), f"{ts}.{body}".encode(), hashlib.sha256).hexdigest()


def test_signature_verification():
    from routes.webhooks import verify_signature

    body = json.dumps(SAMPLE)
    assert verify_signature(body.encode(), _sign(body), SECRET)
    assert not verify_signature(body.encode(), _sign(body + "x"), SECRET)
    assert not verify_signature(body.encode(), _sign(body, ts=int(time.time()) - 3600), SECRET)
    assert not verify_signature(body.encode(), None, SECRET)


def test_parse_and_rollup():
    from routes.webhooks import _parse_turns, build_conversation_row

    turns = _parse_turns("conv_1", SAMPLE["data"]["transcript"])
    assert [t["llm_ttfb_ms"] for t in turns] == [400, None, 900, None]
    assert turns[2]["llm_ttf_sentence_ms"] == 1400
    assert turns[2]["max_tool_latency_ms"] == 1250
    assert turns[3]["has_tool_error"] and turns[3]["interrupted"]
    conv = build_conversation_row(SAMPLE["data"], turns)
    assert conv["turn_count"] == 4 and conv["user_turns"] == 1
    assert conv["tool_error_count"] == 1 and conv["interruptions"] == 1
    assert conv["llm_ttfb_p50_ms"] == 650 and conv["tool_latency_max_ms"] == 5000
    assert conv["call_successful"] == "success" and conv["duration_secs"] == 42
    assert conv["started_at"].startswith("2026-")


def test_webhook_endpoint_stores_rows(fake_sb, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import routes.webhooks as wh

    monkeypatch.setenv("ELEVENLABS_WEBHOOK_SECRET", SECRET)

    class SyncExec:
        def submit(self, fn, *a):
            fn(*a)

    monkeypatch.setattr(wh, "_executor", SyncExec())
    app = FastAPI()
    app.include_router(wh.router)
    client = TestClient(app)
    body = json.dumps(SAMPLE)

    bad = client.post("/webhooks/elevenlabs", content=body, headers={"elevenlabs-signature": "t=1,v0=nope"})
    assert bad.status_code == 401

    ok = client.post("/webhooks/elevenlabs", content=body, headers={"elevenlabs-signature": _sign(body)})
    assert ok.status_code == 200
    assert fake_sb.rows["conversations"][0]["conversation_id"] == "conv_1"
    assert len(fake_sb.rows["conversation_turns"]) == 4


# ── search-service ─────────────────────────────────────────────────────────

@pytest.fixture
def search_app(fake_sb, monkeypatch):
    monkeypatch.setenv("SYSTEM_STATS_INTERVAL_SECONDS", "0")
    monkeypatch.setenv("SEARCH_CACHE_ENABLED", "true")
    if "main" in sys.modules:
        del sys.modules["main"]
    spec = importlib.util.spec_from_file_location("search_main", REPO / "search-service" / "main.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._search_cache.clear()
    return mod


def test_search_logs_timing_and_persists_conversation(search_app, fake_sb, caplog):
    from fastapi.testclient import TestClient

    caplog.set_level(logging.DEBUG)
    with TestClient(search_app.app) as client:
        body = {"store_id": "75eb8b55-70de-42fb-ae38-813af27022d3", "query": "face wash",
                "conversation_id": "conv_9"}
        r = client.post("/search", json=body)
        assert r.status_code == 200, r.text
        assert r.headers["x-search-cache"] == "miss"
        r2 = client.post("/search", json=body)
        assert r2.headers["x-search-cache"] == "hit"
        time.sleep(0.2)  # fire-and-forget inserts

    rows = fake_sb.rows["search_latency"]
    assert rows and all(r["conversation_id"] == "conv_9" for r in rows)
    assert {"rerank_ms", "request_id", "endpoint"} <= set(rows[0])
    assert "p_query_embedding" not in caplog.text  # the 384-float dump is gone
    completed = [r for r in caplog.records if r.getMessage() == "search.completed"]
    assert completed and completed[0].conversation_id == "conv_9"
    assert "rerank_ms" in completed[0].fields and completed[1].fields["cache"] == "hit"


def test_product_details_and_deep_health(search_app, fake_sb):
    from fastapi.testclient import TestClient

    with TestClient(search_app.app) as client:
        r = client.post("/product-details", json={
            "store_id": "75eb8b55-70de-42fb-ae38-813af27022d3",
            "product_id": "11111111-1111-1111-1111-111111111111", "conversation_id": "conv_9"})
        assert r.status_code == 200 and r.json()["product_name"] == "Face Wash"
        h = client.get("/health?deep=1")
        assert h.status_code == 200 and h.json()["supabase"] is True
        assert client.get("/health").json() == {"status": "ok"}


def test_low_confidence_query_is_trimmed_not_browsed(search_app, fake_sb, monkeypatch):
    """Unknown brand + product type: top rerank score < 0 must still apply the margin
    cutoff (only explicit browse phrases return everything)."""
    import asyncio
    rows = [dict(fake_sb.rpc_rows[0], id=f"{i}" * 8 + "-1111-1111-1111-111111111111", name=n)
            for i, n in enumerate(["Drench Facewash", "Detox Face Wash", "Soothe Lip Balm", "Dwell Moisturiser"], 1)]
    fake_sb.rpc_rows = rows
    scores = {"Drench Facewash": -1.2, "Detox Face Wash": -1.6, "Soothe Lip Balm": -9.7, "Dwell Moisturiser": -10.9}
    monkeypatch.setattr(search_app, "rerank", lambda q, docs: [next(v for k, v in scores.items() if d.startswith(k)) for d in docs])
    products, *_ = asyncio.run(search_app._hybrid_search_products(fake_sb, "s", "xiaomi face wash"))
    assert [p.name for p in products] == ["Drench Facewash", "Detox Face Wash"]
    browse, *_ = asyncio.run(search_app._hybrid_search_products(fake_sb, "s", "show me everything"))
    assert len(browse) == 4
