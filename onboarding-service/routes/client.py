"""Client-facing endpoints — submit request, send agent delivery."""

import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

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

    # Fire-and-forget notifications
    _bg_executor.submit(send_slack_notification, body.name, body.email, url, request_id)
    _bg_executor.submit(send_client_ack_email, body.name, body.email, url)
    _bg_executor.submit(send_admin_notification_email, body.name, body.email, url, request_id)

    return {"success": True, "request_id": request_id}


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
