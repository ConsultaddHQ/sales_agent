"""Shopify `orders/create` webhook — links orders back to TeamPop conversations.

The widget tags the cart with note attributes ("TeamPop Conversation" =
<conversation_id>, "TeamPop Assisted" = "yes"). When the order is placed Shopify
POSTs it here; orders carrying a TeamPop attribute are upserted into
`assisted_orders`, which feeds the purchase-lag / assisted-revenue metrics
(create_business_metrics.sql). Other orders are acknowledged and ignored.

Env vars:
  SHOPIFY_WEBHOOK_SECRET  the app/store webhook signing secret (required)
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request

_REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from shared.db import insert_tolerant
from shared.observability import bind_conversation, capture_exception, log_event

logger = logging.getLogger("onboarding-service")

router = APIRouter(prefix="/webhooks/shopify")

_executor = ThreadPoolExecutor(max_workers=2)

CONVERSATION_ATTR = "TeamPop Conversation"
ASSISTED_ATTR = "TeamPop Assisted"


def verify_hmac(raw_body: bytes, header: Optional[str], secret: str) -> bool:
    if not header or not secret:
        return False
    expected = base64.b64encode(hmac.new(secret.encode(), raw_body, hashlib.sha256).digest()).decode()
    return hmac.compare_digest(expected, header.strip())


def build_order_row(order: Dict[str, Any], shop_domain: Optional[str]) -> Optional[Dict[str, Any]]:
    """Return the assisted_orders row, or None when the order has no TeamPop attribute."""
    attrs = {}
    for a in order.get("note_attributes") or []:
        if isinstance(a, dict) and a.get("name"):
            attrs[str(a["name"]).strip()] = a.get("value")
    conversation_id = (str(attrs.get(CONVERSATION_ATTR) or "").strip()) or None
    assisted = str(attrs.get(ASSISTED_ATTR) or "").strip().lower() == "yes"
    if not conversation_id and not assisted:
        return None
    try:
        total = float(order.get("total_price")) if order.get("total_price") is not None else None
    except (TypeError, ValueError):
        total = None
    line_items = [
        {k: li.get(k) for k in ("product_id", "variant_id", "title", "quantity", "price", "sku")}
        for li in (order.get("line_items") or []) if isinstance(li, dict)
    ]
    return {
        "order_id": str(order.get("id")),
        "shop_domain": shop_domain,
        "conversation_id": conversation_id,
        "total_price": total,
        "currency": order.get("currency"),
        "line_items": line_items,
        "created_at": order.get("created_at"),
    }


def _store(row: Dict[str, Any]) -> None:
    try:
        insert_tolerant("assisted_orders", row, logger, upsert_on="order_id")
        log_event(logger, "shopify.order_stored", order_id=row["order_id"],
                  conversation_id=row.get("conversation_id"), total_price=row.get("total_price"))
    except Exception as e:
        capture_exception(e, order_id=row.get("order_id"))
        log_event(logger, "shopify.order_store_failed", logging.ERROR, order_id=row.get("order_id"))


@router.post("/orders-create")
async def orders_create(request: Request):
    raw = await request.body()
    secret = os.getenv("SHOPIFY_WEBHOOK_SECRET", "")
    if not secret:
        log_event(logger, "shopify.misconfigured", logging.ERROR, reason="SHOPIFY_WEBHOOK_SECRET not set")
        raise HTTPException(status_code=503, detail="webhook not configured")
    if not verify_hmac(raw, request.headers.get("x-shopify-hmac-sha256"), secret):
        log_event(logger, "shopify.bad_signature", logging.WARNING)
        raise HTTPException(status_code=401, detail="invalid signature")
    try:
        order = json.loads(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid JSON")

    row = build_order_row(order, request.headers.get("x-shopify-shop-domain"))
    log_event(logger, "shopify.order_received", order_id=order.get("id"), assisted=row is not None)
    if row:
        bind_conversation(row.get("conversation_id"))
        _executor.submit(_store, row)
    return {"ok": True}
