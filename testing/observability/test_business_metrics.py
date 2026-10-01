"""Tests for the Shopify orders/create webhook (Phase 3 business metrics)."""

import base64
import hashlib
import hmac
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from test_observability import FakeSupabase, fake_sb  # noqa: F401  (fixture re-export)

SECRET = "shpss_test"


def _sig(body: str, secret: str = SECRET) -> str:
    return base64.b64encode(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()).decode()


def _order(attrs):
    return {"id": 99, "total_price": "499.00", "currency": "INR", "created_at": "2026-10-01T10:00:00+05:30",
            "note_attributes": attrs, "line_items": [{"product_id": 1, "title": "Face Wash", "quantity": 1, "price": "499.00"}]}


@pytest.fixture
def client(fake_sb, monkeypatch):
    import routes.shopify as sh

    class SyncExec:
        def submit(self, fn, *a):
            fn(*a)

    monkeypatch.setenv("SHOPIFY_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(sh, "_executor", SyncExec())
    app = FastAPI()
    app.include_router(sh.router)
    return TestClient(app)


def _post(client, body, sig):
    return client.post("/webhooks/shopify/orders-create", content=body,
                       headers={"x-shopify-hmac-sha256": sig, "x-shopify-shop-domain": "goxfused.myshopify.com"})


def test_valid_hmac_stores_row_with_conversation(client, fake_sb):
    body = json.dumps(_order([{"name": "TeamPop Conversation", "value": "conv_42"}]))
    r = _post(client, body, _sig(body))
    assert r.status_code == 200
    row = fake_sb.rows["assisted_orders"][0]
    assert row["order_id"] == "99" and row["conversation_id"] == "conv_42"
    assert row["total_price"] == 499.0 and row["shop_domain"] == "goxfused.myshopify.com"


def test_assisted_flag_without_conversation_is_stored(client, fake_sb):
    body = json.dumps(_order([{"name": "TeamPop Assisted", "value": "yes"}]))
    assert _post(client, body, _sig(body)).status_code == 200
    assert fake_sb.rows["assisted_orders"][0]["conversation_id"] is None


def test_bad_hmac_401(client, fake_sb):
    body = json.dumps(_order([{"name": "TeamPop Conversation", "value": "conv_42"}]))
    assert _post(client, body, _sig(body, "wrong")).status_code == 401
    assert "assisted_orders" not in fake_sb.rows


def test_order_without_teampop_attrs_not_stored(client, fake_sb):
    body = json.dumps(_order([{"name": "gift", "value": "yes"}]))
    assert _post(client, body, _sig(body)).status_code == 200
    assert "assisted_orders" not in fake_sb.rows


def test_missing_secret_503(client, monkeypatch):
    monkeypatch.delenv("SHOPIFY_WEBHOOK_SECRET")
    body = json.dumps(_order([]))
    assert _post(client, body, _sig(body)).status_code == 503
