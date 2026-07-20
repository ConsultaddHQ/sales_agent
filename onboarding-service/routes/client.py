"""Client-facing endpoints — submit request, send agent delivery, session feedback."""

import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

_REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from shared.config import ADMIN_PASSWORD
from shared.db import get_supabase
from notifications import (
    send_slack_notification,
    send_client_ack_email,
    send_admin_notification_email,
    send_delivery_email,
)

logger = logging.getLogger("onboarding-service")

router = APIRouter(prefix="/api")

_bg_executor = ThreadPoolExecutor(max_workers=4)

# Bump this string (and redeploy) every time a latency-affecting config
# changes in elevenlabs_agent.py — soft_timeout, turn_eagerness, TTS
# streaming settings, prompt length, etc. It's stamped server-side (never
# client-supplied) onto every turn_latency/session_feedback row so
# /latency-summary can group "did change X actually help?" by variant
# instead of eyeballing timestamps.
LATENCY_CONFIG_VERSION = os.getenv("LATENCY_CONFIG_VERSION", "v1-baseline")


class SubmitRequestBody(BaseModel):
    name: str
    email: str
    url: str


class SendAgentBody(BaseModel):
    base_url: str


def _verify_admin(x_admin_password: str = Header(...)):
    if x_admin_password != ADMIN_PASSWORD():
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.post("/submit-request")
def submit_request(body: SubmitRequestBody):
    """Public: client submits interest. Triggers Slack + email notifications."""
    logger.info(f"New request: name={body.name}, email={body.email}, url={body.url}")
    try:
        sb = get_supabase()
        url = body.url.strip()
        if not url.startswith("http"):
            url = f"https://{url}"

        result = sb.table("agent_requests").insert({
            "name": body.name.strip(),
            "email": body.email.strip().lower(),
            "url": url,
            "status": "pending",
        }).execute()

        request_id = result.data[0]["id"]
        logger.info(f"Request created: {request_id}")

        # Fire-and-forget notifications
        _bg_executor.submit(send_slack_notification, body.name, body.email, url, request_id)
        _bg_executor.submit(send_client_ack_email, body.name, body.email, url)
        _bg_executor.submit(send_admin_notification_email, body.name, body.email, url, request_id)

        return {"success": True, "request_id": request_id}
    except Exception as e:
        logger.error(f"Failed to submit request: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to submit request: {str(e)}")


@router.post("/send-agent/{request_id}")
def send_agent(request_id: str, body: SendAgentBody, x_admin_password: str = Header(...)):
    """Admin: send the delivery email with test link to the client."""
    _verify_admin(x_admin_password)
    sb = get_supabase()

    row = sb.table("agent_requests").select("*").eq("id", request_id).single().execute().data
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")
    if row["status"] != "ready":
        raise HTTPException(status_code=400, detail=f"Agent not ready (status: {row['status']})")

    base = body.base_url.rstrip("/")
    full_test_url = f"{base}{row['test_url']}"

    send_delivery_email(
        name=row["name"],
        email=row["email"],
        test_url=full_test_url,
        calendly_booked=row.get("calendly_booked", False),
    )

    sb.table("agent_requests").update({
        "status": "sent",
        "test_url": full_test_url,
        "updated_at": datetime.now().isoformat(),
    }).eq("id", request_id).execute()

    return {"success": True, "test_url": full_test_url}


class SessionFeedbackBody(BaseModel):
    agent_id: str
    duration_seconds: Optional[int] = None
    rating: Optional[str] = None        # "positive" | "neutral" | "negative" | "none"
    feedback_tag: Optional[str] = None  # e.g. "found_product", "too_slow"
    products_shown: int = 0
    products_clicked: int = 0
    shop_now_clicked: bool = False
    chat_messages: int = 0
    end_reason: Optional[str] = None
    conversation_id: Optional[str] = None
    latency_first_ai_ms: Optional[int] = None
    latency_products_ms: Optional[int] = None
    tool_calls: int = 0
    interruption_count: int = 0
    # Business/funnel metrics (2026-07-16) — require the matching session_feedback
    # columns (see docs/agents/xfused-lightsail-deploy-checklist.md for the SQL).
    searches: int = 0
    products_focused: int = 0
    cart_adds: int = 0
    cart_add_failures: int = 0
    cart_value_paise: int = 0
    checkout_initiated: bool = False
    resumed_session: bool = False


@router.post("/session-feedback")
def submit_session_feedback(body: SessionFeedbackBody):
    """Public: store post-session feedback and implicit signals. No auth — no PII stored."""
    try:
        sb = get_supabase()
        valid_ratings = {"positive", "neutral", "negative", "none"}
        rating = body.rating if body.rating in valid_ratings else "none"
        row = {
            "agent_id": body.agent_id,
            "duration_seconds": body.duration_seconds,
            "rating": rating,
            "feedback_tag": body.feedback_tag,
            "products_shown": body.products_shown,
            "products_clicked": body.products_clicked,
            "shop_now_clicked": body.shop_now_clicked,
            "chat_messages": body.chat_messages,
            "end_reason": body.end_reason,
            "conversation_id": body.conversation_id,
            "latency_first_ai_ms": body.latency_first_ai_ms,
            "latency_products_ms": body.latency_products_ms,
            "tool_calls": body.tool_calls,
            "interruption_count": body.interruption_count,
            "searches": body.searches,
            "products_focused": body.products_focused,
            "cart_adds": body.cart_adds,
            "cart_add_failures": body.cart_add_failures,
            "cart_value_paise": body.cart_value_paise,
            "checkout_initiated": body.checkout_initiated,
            "resumed_session": body.resumed_session,
            "config_variant": LATENCY_CONFIG_VERSION,
        }
        # Schema-drift tolerance: if the table is missing a column (migration not
        # applied, or created from an older base schema — the 2026-07-16 xfused
        # incident lost every row over 'interruption_count'), PostgREST names the
        # missing column in the error. Drop exactly that column and retry, so a
        # partial row is stored instead of losing the feedback entirely.
        import re as _re
        for _ in range(len(row)):
            try:
                sb.table("session_feedback").insert(row).execute()
                break
            except Exception as col_err:
                m = _re.search(r"Could not find the '([^']+)' column", str(col_err))
                if not m or m.group(1) not in row:
                    raise
                logger.warning(f"session_feedback missing column '{m.group(1)}' — retrying without it (run the migration in the deploy checklist)")
                row.pop(m.group(1))
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to store session feedback: {e}", exc_info=True)
        # Never surface errors to the widget — feedback is non-critical
        return {"success": False}


class TurnLatencyBody(BaseModel):
    agent_id: str
    conversation_id: Optional[str] = None
    cycle: Optional[int] = None
    latency_first_ai_ms: Optional[int] = None
    latency_products_ms: Optional[int] = None


@router.post("/turn-latency")
def submit_turn_latency(body: TurnLatencyBody):
    """Public: per-turn latency sample, sent immediately after each voice cycle
    (not just once at session end). No auth — no PII stored."""
    try:
        sb = get_supabase()
        row = {
            "agent_id": body.agent_id,
            "conversation_id": body.conversation_id,
            "cycle": body.cycle,
            "latency_first_ai_ms": body.latency_first_ai_ms,
            "latency_products_ms": body.latency_products_ms,
            "config_variant": LATENCY_CONFIG_VERSION,
        }
        # Same schema-drift tolerance as /session-feedback: drop whatever
        # column PostgREST reports missing and retry, so a partial row is
        # stored instead of losing the sample entirely.
        import re as _re
        for _ in range(len(row)):
            try:
                sb.table("turn_latency").insert(row).execute()
                break
            except Exception as col_err:
                m = _re.search(r"Could not find the '([^']+)' column", str(col_err))
                if not m or m.group(1) not in row:
                    raise
                logger.warning(f"turn_latency missing column '{m.group(1)}' — retrying without it (run create_latency_tracking_table.sql)")
                row.pop(m.group(1))
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to store turn latency: {e}", exc_info=True)
        # Never surface errors to the widget — telemetry is non-critical
        return {"success": False}
