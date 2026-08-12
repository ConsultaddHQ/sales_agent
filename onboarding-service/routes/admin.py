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


@router.get("/feedback-summary/{agent_id}")
def get_feedback_summary(agent_id: str, x_admin_password: str = Header(...)):
    """Admin: aggregated session feedback stats for an agent."""
    _verify_admin(x_admin_password)
    try:
        sb = get_supabase()
        rows = (
            sb.table("session_feedback")
            .select("*")
            .eq("agent_id", agent_id)
            .order("created_at", desc=True)
            .limit(200)
            .execute()
            .data
        )
        total = len(rows)
        if total == 0:
            return {"agent_id": agent_id, "total_sessions": 0}

        positive = sum(1 for r in rows if r.get("rating") == "positive")
        neutral  = sum(1 for r in rows if r.get("rating") == "neutral")
        negative = sum(1 for r in rows if r.get("rating") == "negative")
        avg_dur  = sum(r.get("duration_seconds") or 0 for r in rows) / total
        shop_rate = sum(1 for r in rows if r.get("shop_now_clicked")) / total

        # Tally feedback tags
        tag_counts: dict = {}
        for r in rows:
            tag = r.get("feedback_tag")
            if tag:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        return {
            "agent_id": agent_id,
            "total_sessions": total,
            "ratings": {"positive": positive, "neutral": neutral, "negative": negative, "no_rating": total - positive - neutral - negative},
            "avg_duration_seconds": round(avg_dur, 1),
            "shop_now_click_rate": round(shop_rate, 3),
            "top_feedback_tags": [{"tag": t, "count": c} for t, c in top_tags],
            "recent": rows[:10],
        }
    except Exception as e:
        logger.error(f"Failed to fetch feedback summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _percentile(sorted_values: list, pct: float) -> Optional[float]:
    """Nearest-rank percentile over an already-sorted list. pct in [0, 100]."""
    if not sorted_values:
        return None
    idx = min(len(sorted_values) - 1, int(round(pct / 100 * (len(sorted_values) - 1))))
    return sorted_values[idx]


def _latency_stats(values: list) -> dict:
    clean = sorted(v for v in values if v is not None)
    if not clean:
        return {"count": 0, "avg_ms": None, "p50_ms": None, "p95_ms": None, "max_ms": None}
    return {
        "count": len(clean),
        "avg_ms": round(sum(clean) / len(clean), 1),
        "p50_ms": _percentile(clean, 50),
        "p95_ms": _percentile(clean, 95),
        "max_ms": clean[-1],
    }


@router.get("/latency-summary/{agent_id}")
def get_latency_summary(
    agent_id: str,
    store_id: Optional[str] = None,
    x_admin_password: str = Header(...),
):
    """Admin: per-turn and per-search latency stats, grouped by config_variant —
    the running answer to "is the latency work actually helping?" Pulls from
    two vantage points: turn_latency (widget-reported, per voice cycle) and
    search_latency (search-service-reported, per query — server truth,
    unaffected by whether the widget's own POST ever lands).

    store_id: pass explicitly (recommended) since turn_latency has no
    store_id column and the agent_requests table this used to resolve it
    from does not exist in every Supabase project (confirmed missing on the
    xfused pilot project, 2026-08-12) — that made this endpoint 500 for
    every request. Falls back to the agent_requests lookup if store_id is
    omitted, but that lookup is now best-effort and never fails the request.
    """
    _verify_admin(x_admin_password)
    try:
        sb = get_supabase()

        turn_rows = (
            sb.table("turn_latency")
            .select("*")
            .eq("agent_id", agent_id)
            .order("created_at", desc=True)
            .limit(1000)
            .execute()
            .data
        )

        if not store_id:
            try:
                req_row = (
                    sb.table("agent_requests")
                    .select("store_id")
                    .eq("agent_id", agent_id)
                    .limit(1)
                    .execute()
                    .data
                )
                if req_row:
                    store_id = req_row[0].get("store_id")
            except Exception as lookup_err:
                logger.warning(
                    f"agent_requests lookup failed for {agent_id} (table may not "
                    f"exist in this project) — pass ?store_id=... explicitly. "
                    f"Error: {lookup_err}"
                )

        search_rows = []
        if store_id:
            search_rows = (
                sb.table("search_latency")
                .select("*")
                .eq("store_id", store_id)
                .order("created_at", desc=True)
                .limit(1000)
                .execute()
                .data
            )

        def _group_by_variant(rows: list) -> dict:
            groups: dict = {}
            for r in rows:
                groups.setdefault(r.get("config_variant") or "unknown", []).append(r)
            return groups

        turn_by_variant = _group_by_variant(turn_rows)
        search_by_variant = _group_by_variant(search_rows)

        variants = sorted(set(turn_by_variant) | set(search_by_variant))
        by_variant = {}
        for variant in variants:
            t_rows = turn_by_variant.get(variant, [])
            s_rows = search_by_variant.get(variant, [])
            by_variant[variant] = {
                "turn": {
                    "first_ai_ms": _latency_stats([r.get("latency_first_ai_ms") for r in t_rows]),
                    "products_ms": _latency_stats([r.get("latency_products_ms") for r in t_rows]),
                },
                "search": {
                    "total_ms": _latency_stats([r.get("total_ms") for r in s_rows]),
                    "embedding_ms": _latency_stats([r.get("embedding_ms") for r in s_rows]),
                    "rpc_ms": _latency_stats([r.get("rpc_ms") for r in s_rows]),
                    "queue_wait_ms": _latency_stats([r.get("queue_wait_ms") for r in s_rows]),
                },
            }

        return {
            "agent_id": agent_id,
            "store_id": store_id,
            "total_turns_sampled": len(turn_rows),
            "total_searches_sampled": len(search_rows),
            "by_config_variant": by_variant,
        }
    except Exception as e:
        logger.error(f"Failed to fetch latency summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

