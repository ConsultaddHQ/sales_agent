"""Smoke + contract tests for search-service.

Covered: /health, /search (happy / empty query / bad store_id / no results),
/product-details (happy / 404 / bad uuid), webhook-secret auth (401 paths),
and the _truncate_for_voice helper. All hermetic via fakes — no DB, no model.

Run from the search-service dir:
    .venv/bin/python -m pytest -q
"""
import pytest
from fastapi.testclient import TestClient

import main

STORE = "11111111-1111-1111-1111-111111111111"
PROD = "22222222-2222-2222-2222-222222222222"
BAD_UUID = "not-a-uuid"


# --------------------------------------------------------------------------
# Fakes — stand in for Supabase + the embedding model.
# --------------------------------------------------------------------------
class _Resp:
    def __init__(self, data):
        self.data = data


class _Query:
    """Any chained builder call (select/eq/limit/order/...) returns self."""
    def __init__(self, resp):
        self._resp = resp

    def __getattr__(self, _name):
        return lambda *a, **k: self

    def execute(self):
        return self._resp


class FakeSupabase:
    def __init__(self, rpc_data=None, table_data=None):
        self._rpc = [] if rpc_data is None else rpc_data
        self._table = [] if table_data is None else table_data

    def rpc(self, *a, **k):
        return _Query(_Resp(self._rpc))

    def table(self, *a, **k):
        return _Query(_Resp(self._table))


class _Vec(list):
    def tolist(self):
        return list(self)


class FakeEmbedder:
    def encode(self, *a, **k):
        return _Vec([0.1] * 384)


def make_client(monkeypatch, rpc_data=None, table_data=None, secret=""):
    monkeypatch.setattr(main, "get_embedder", lambda: FakeEmbedder())
    monkeypatch.setattr(main, "get_supabase", lambda: FakeSupabase(rpc_data, table_data))
    monkeypatch.setattr(main, "WEBHOOK_SECRET", secret)
    return TestClient(main.app)


def _rpc_row(**over):
    row = {
        "id": PROD, "store_id": STORE, "name": "Cotton Tee",
        "description": "A soft tee", "price": 2749, "image_url": None,
        "local_image_path": f"{STORE}/cotton-tee.jpg",
        "product_url": "https://sensesindia.in/products/cotton-tee", "score": 0.9,
    }
    row.update(over)
    return row


# --------------------------------------------------------------------------
# /health
# --------------------------------------------------------------------------
def test_health(monkeypatch):
    with make_client(monkeypatch) as c:
        r = c.get("/health")
        assert r.status_code == 200 and r.json() == {"status": "ok"}


# --------------------------------------------------------------------------
# /search
# --------------------------------------------------------------------------
def test_search_happy(monkeypatch):
    with make_client(monkeypatch, rpc_data=[_rpc_row()]) as c:
        r = c.post("/search", json={"store_id": STORE, "query": "cotton tee"})
        assert r.status_code == 200
        body = r.json()
        assert len(body["products"]) == 1
        p = body["products"][0]
        assert p["id"] == PROD and p["name"] == "Cotton Tee"
        assert p["image_url"] and p["product_url"]
        # correlation id is echoed back
        assert r.headers.get("X-Request-ID")


def test_search_empty_query(monkeypatch):
    with make_client(monkeypatch) as c:
        r = c.post("/search", json={"store_id": STORE, "query": "   "})
        assert r.status_code == 400


def test_search_bad_store_id(monkeypatch):
    with make_client(monkeypatch) as c:
        r = c.post("/search", json={"store_id": BAD_UUID, "query": "shirt"})
        assert r.status_code == 400


def test_search_no_results(monkeypatch):
    with make_client(monkeypatch, rpc_data=[]) as c:
        r = c.post("/search", json={"store_id": STORE, "query": "nothing"})
        assert r.status_code == 200
        assert r.json()["products"] == []


# --------------------------------------------------------------------------
# /product-details
# --------------------------------------------------------------------------
def _detail_row():
    return {
        "name": "Cotton Tee",
        "metadata": {
            "options": [{"name": "Size", "values": ["S", "M", "L"]}],
            "variants": [
                {"id": 1, "title": "S", "price": "2749.00", "available": True, "sku": "T-S"},
                {"id": 2, "title": "L", "price": "2749.00", "available": False, "sku": "T-L"},
            ],
            "full_description_html": "<p>Double Mercerised Cotton</p>",
        },
    }


def test_product_details_happy(monkeypatch):
    with make_client(monkeypatch, table_data=[_detail_row()]) as c:
        r = c.post("/product-details", json={"store_id": STORE, "product_id": PROD})
        assert r.status_code == 200
        body = r.json()
        assert body["product_name"] == "Cotton Tee"
        assert "Double Mercerised Cotton" in body["full_description"]
        assert len(body["variants"]) == 2
        assert body["available_options"][0]["name"] == "Size"


def test_product_details_not_found(monkeypatch):
    with make_client(monkeypatch, table_data=[]) as c:
        r = c.post("/product-details", json={"store_id": STORE, "product_id": PROD})
        assert r.status_code == 404


def test_product_details_bad_uuid(monkeypatch):
    with make_client(monkeypatch) as c:
        r = c.post("/product-details", json={"store_id": STORE, "product_id": BAD_UUID})
        assert r.status_code == 400


# --------------------------------------------------------------------------
# Webhook-secret auth
# --------------------------------------------------------------------------
def test_auth_rejected_without_header(monkeypatch):
    with make_client(monkeypatch, rpc_data=[_rpc_row()], secret="topsecret") as c:
        r = c.post("/search", json={"store_id": STORE, "query": "tee"})
        assert r.status_code == 401


def test_auth_accepted_with_header(monkeypatch):
    with make_client(monkeypatch, rpc_data=[_rpc_row()], secret="topsecret") as c:
        r = c.post(
            "/search",
            json={"store_id": STORE, "query": "tee"},
            headers={"X-TeamPop-Secret": "topsecret"},
        )
        assert r.status_code == 200


def test_product_details_auth_rejected(monkeypatch):
    with make_client(monkeypatch, table_data=[_detail_row()], secret="topsecret") as c:
        r = c.post("/product-details", json={"store_id": STORE, "product_id": PROD})
        assert r.status_code == 401


# --------------------------------------------------------------------------
# _truncate_for_voice helper
# --------------------------------------------------------------------------
def test_truncate_short_passthrough():
    assert main._truncate_for_voice("short", 200) == "short"
    assert main._truncate_for_voice(None) is None


def test_truncate_long_adds_ellipsis():
    long = "word " * 100
    out = main._truncate_for_voice(long, 50)
    assert len(out) <= 51 and out.endswith("…")
