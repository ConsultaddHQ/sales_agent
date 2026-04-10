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
from elevenlabs_agent import update_agent_model, MODEL_PROMPT_MAP

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
    try:
        sb = get_supabase()
        result = sb.table("agent_requests").select("*").order("created_at", desc=True).execute()
        return result.data
    except Exception as e:
        logger.error(f"Failed to list requests: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.post("/process-request/{request_id}")
def process_request(request_id: str, body: ProcessRequestBody, x_admin_password: str = Header(...)):
    """Admin: start the onboarding pipeline."""
    _verify_admin(x_admin_password)
    logger.info(f"Processing request {request_id}: scrape_url={body.scrape_url}, store_type={body.store_type}")

    try:
        sb = get_supabase()
        row = sb.table("agent_requests").select("*").eq("id", request_id).single().execute().data
    except Exception as e:
        logger.error(f"Failed to fetch request {request_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    if not row:
        raise HTTPException(status_code=404, detail="Request not found")
    if row["status"] not in ("pending", "failed"):
        raise HTTPException(status_code=400, detail=f"Cannot process request in status '{row['status']}'")

    scrape_url = body.scrape_url.strip()
    if not scrape_url.startswith("http"):
        scrape_url = f"https://{scrape_url}"

    try:
        sb.table("agent_requests").update({
            "status": "processing",
            "scrape_url": scrape_url,
            "error_message": None,
            "updated_at": datetime.now().isoformat(),
        }).eq("id", request_id).execute()
    except Exception as e:
        logger.error(f"Failed to update request status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database update error: {str(e)}")

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


class SwitchModelBody(BaseModel):
    agent_id: str
    store_id: str
    llm_model: str


@router.post("/switch-model")
def switch_agent_model(body: SwitchModelBody, x_admin_password: str = Header(...)):
    """Admin: hot-swap an agent's LLM model + prompt. No re-scraping needed.

    curl -X POST http://localhost:8005/api/switch-model \\
      -H "Content-Type: application/json" \\
      -H "x-admin-password: YOUR_PASSWORD" \\
      -d '{"agent_id":"abc123","store_id":"c5a0c8a1-...","llm_model":"gemini-2.5-flash"}'
    """
    _verify_admin(x_admin_password)
    logger.info(f"Switching agent {body.agent_id} to model {body.llm_model}")
    try:
        result = update_agent_model(
            agent_id=body.agent_id,
            store_id=body.store_id,
            llm_model=body.llm_model,
        )
        # Persist the active model so the dashboard can show it
        try:
            sb = get_supabase()
            sb.table("agent_requests").update({
                "llm_model": body.llm_model,
            }).eq("agent_id", body.agent_id).execute()
        except Exception as db_err:
            logger.warning(f"Could not persist llm_model to DB: {db_err}")
        return result
    except Exception as e:
        logger.error(f"Failed to switch model: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
