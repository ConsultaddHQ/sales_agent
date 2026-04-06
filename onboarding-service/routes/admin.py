"""Admin endpoints — login, list/process/update requests."""

import logging
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
from pipeline import pipeline

logger = logging.getLogger("onboarding-service")

router = APIRouter(prefix="/api")

_bg_executor = ThreadPoolExecutor(max_workers=4)


def _verify_admin(x_admin_password: str = Header(...)):
    if x_admin_password != ADMIN_PASSWORD():
        raise HTTPException(status_code=401, detail="Unauthorized")


class ProcessRequestBody(BaseModel):
    scrape_url: str
    store_type: str = "auto"


class UpdateRequestBody(BaseModel):
    notes: Optional[str] = None
    calendly_booked: Optional[bool] = None


@router.post("/admin/login")
def admin_login(body: dict):
    """Validate admin password."""
    if body.get("password") != ADMIN_PASSWORD():
        raise HTTPException(status_code=401, detail="Invalid password")
    return {"authenticated": True}


@router.get("/requests")
def list_requests(x_admin_password: str = Header(...)):
    """Admin: list all client requests."""
    _verify_admin(x_admin_password)
    sb = get_supabase()
    result = sb.table("agent_requests").select("*").order("created_at", desc=True).execute()
    return result.data


@router.post("/process-request/{request_id}")
def process_request(request_id: str, body: ProcessRequestBody, x_admin_password: str = Header(...)):
    """Admin: start the onboarding pipeline."""
    _verify_admin(x_admin_password)
    sb = get_supabase()

    row = sb.table("agent_requests").select("*").eq("id", request_id).single().execute().data
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")
    if row["status"] not in ("pending", "failed"):
        raise HTTPException(status_code=400, detail=f"Cannot process request in status '{row['status']}'")

    scrape_url = body.scrape_url.strip()
    if not scrape_url.startswith("http"):
        scrape_url = f"https://{scrape_url}"

    sb.table("agent_requests").update({
        "status": "processing",
        "scrape_url": scrape_url,
        "error_message": None,
        "updated_at": datetime.now().isoformat(),
    }).eq("id", request_id).execute()

    _bg_executor.submit(pipeline.run_background, request_id, scrape_url, body.store_type)

    return {"success": True, "message": "Processing started"}


@router.post("/update-request/{request_id}")
def update_request(request_id: str, body: UpdateRequestBody, x_admin_password: str = Header(...)):
    """Admin: update request metadata."""
    _verify_admin(x_admin_password)
    sb = get_supabase()

    updates = {"updated_at": datetime.now().isoformat()}
    if body.notes is not None:
        updates["notes"] = body.notes
    if body.calendly_booked is not None:
        updates["calendly_booked"] = body.calendly_booked

    sb.table("agent_requests").update(updates).eq("id", request_id).execute()
    return {"success": True}
