"""ElevenLabs post-call webhook — the server-side record of every conversation.

ElevenLabs POSTs here once a call ends (workspace setting: ElevenAgents →
Settings → Post-call webhook → URL `https://api.teampop.com/webhooks/elevenlabs`,
transcript format JSON). We:

1. verify the HMAC signature (`elevenlabs-signature: t=<ts>,v0=<hex>` over
   "<ts>.<raw body>", SHA-256, 30-min tolerance — same as the official SDK),
2. ack 200 immediately (ElevenLabs auto-disables a webhook after repeated
   failures — never make it wait on Supabase),
3. in the background: upsert one `conversations` row (outcome, evaluation +
   data-collection results, cost, latency roll-ups) and one
   `conversation_turns` row per transcript turn (LLM TTFB, tool latency,
   tool errors, interruptions),
4. optionally fetch the call's OpenTelemetry trace from ElevenLabs and push it
   to Grafana Cloud Tempo, so each call is a browsable trace.

Everything is keyed on `conversation_id`, the same ID the widget, webhook
tools and Sentry carry — that's what makes per-conversation RCA possible.

Env vars:
  ELEVENLABS_WEBHOOK_SECRET  HMAC secret shown when the webhook is created (required)
  ELEVENLABS_API_KEY         used to fetch the OTel trace
  ELEVENLABS_API_BASE        default https://api.elevenlabs.io/v1 (change for residency)
  GRAFANA_OTLP_ENDPOINT      e.g. https://otlp-gateway-prod-ap-south-1.grafana.net/otlp
  GRAFANA_OTLP_INSTANCE_ID   Grafana Cloud OTLP instance ID (numeric)
  GRAFANA_OTLP_TOKEN         Grafana Cloud access-policy token with traces:write
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from fastapi import APIRouter, HTTPException, Request

_REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from shared.db import insert_tolerant
from shared.observability import bind_conversation, capture_exception, log_event

logger = logging.getLogger("onboarding-service")

router = APIRouter(prefix="/webhooks")

_executor = ThreadPoolExecutor(max_workers=2)

SIGNATURE_TOLERANCE_SECS = 30 * 60
MAX_MESSAGE_CHARS = 2000


def verify_signature(raw_body: bytes, sig_header: Optional[str], secret: str) -> bool:
    if not sig_header or not secret:
        return False
    timestamp, signature = None, None
    for part in sig_header.split(","):
        part = part.strip()
        if part.startswith("t="):
            timestamp = part[2:]
        elif part.startswith("v0="):
            signature = part
    if not timestamp or not signature or not timestamp.isdigit():
        return False
    if int(timestamp) < time.time() - SIGNATURE_TOLERANCE_SECS:
        return False
    message = f"{timestamp}.{raw_body.decode('utf-8')}"
    expected = "v0=" + hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/elevenlabs")
async def elevenlabs_webhook(request: Request):
    raw = await request.body()
    secret = os.getenv("ELEVENLABS_WEBHOOK_SECRET", "")
    if not secret:
        log_event(logger, "webhook.misconfigured", logging.ERROR, reason="ELEVENLABS_WEBHOOK_SECRET not set")
        raise HTTPException(status_code=503, detail="webhook not configured")
    if not verify_signature(raw, request.headers.get("elevenlabs-signature"), secret):
        log_event(logger, "webhook.bad_signature", logging.WARNING)
        raise HTTPException(status_code=401, detail="invalid signature")

    try:
        event = json.loads(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid JSON")

    event_type = event.get("type")
    data = event.get("data") or {}
    conversation_id = data.get("conversation_id")
    bind_conversation(conversation_id)
    log_event(logger, "webhook.received", event_type=event_type, agent_id=data.get("agent_id"))

    if event_type == "post_call_transcription":
        _executor.submit(_process_transcription, data)
    # post_call_audio / call_initiation_failure: acknowledged, nothing stored.
    # Audio replay lives in the ElevenLabs dashboard (30-day retention).
    return {"ok": True}


# ── Parsing ────────────────────────────────────────────────────────────────

def _metric_ms(turn_metrics: Optional[dict], key: str) -> Optional[int]:
    metrics = (turn_metrics or {}).get("metrics") or {}
    rec = metrics.get(key)
    if isinstance(rec, dict) and rec.get("elapsed_time") is not None:
        return int(float(rec["elapsed_time"]) * 1000)
    return None


def _parse_turns(conversation_id: str, transcript: List[dict]) -> List[Dict[str, Any]]:
    rows = []
    for idx, t in enumerate(transcript or []):
        tool_calls = [
            {"tool_name": c.get("tool_name"), "params": (c.get("params_as_json") or "")[:500]}
            for c in (t.get("tool_calls") or [])
        ]
        tool_results = [
            {
                "tool_name": r.get("tool_name"),
                "latency_ms": int(float(r["tool_latency_secs"]) * 1000) if r.get("tool_latency_secs") is not None else None,
                "is_error": bool(r.get("is_error")),
            }
            for r in (t.get("tool_results") or [])
        ]
        tool_latencies = [r["latency_ms"] for r in tool_results if r["latency_ms"] is not None]
        tm = t.get("conversation_turn_metrics")
        rows.append({
            "conversation_id": conversation_id,
            "turn_index": idx,
            "role": t.get("role"),
            "message": (t.get("message") or "")[:MAX_MESSAGE_CHARS] or None,
            "time_in_call_secs": t.get("time_in_call_secs"),
            "interrupted": bool(t.get("interrupted")),
            "llm_ttfb_ms": _metric_ms(tm, "convai_llm_service_ttfb"),
            "llm_ttf_sentence_ms": _metric_ms(tm, "convai_llm_service_ttf_sentence"),
            "tool_calls": tool_calls or None,
            "tool_results": tool_results or None,
            "max_tool_latency_ms": max(tool_latencies) if tool_latencies else None,
            "has_tool_error": any(r["is_error"] for r in tool_results),
            "turn_metrics": tm or None,
        })
    return rows


def _p95(values: List[int]) -> Optional[int]:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]


def build_conversation_row(data: dict, turns: List[Dict[str, Any]]) -> Dict[str, Any]:
    meta = data.get("metadata") or {}
    analysis = data.get("analysis") or {}
    ttfbs = [t["llm_ttfb_ms"] for t in turns if t["llm_ttfb_ms"] is not None]
    tool_lat = [t["max_tool_latency_ms"] for t in turns if t["max_tool_latency_ms"] is not None]
    start = meta.get("start_time_unix_secs")
    return {
        "conversation_id": data.get("conversation_id"),
        "agent_id": data.get("agent_id"),
        "branch_id": data.get("branch_id") or meta.get("branch_id"),
        "version_id": data.get("version_id") or meta.get("version_id"),
        "status": data.get("status"),
        "started_at": datetime.fromtimestamp(start, tz=timezone.utc).isoformat() if start else None,
        "duration_secs": meta.get("call_duration_secs"),
        "termination_reason": meta.get("termination_reason"),
        "main_language": meta.get("main_language"),
        "cost": meta.get("cost"),
        "call_successful": analysis.get("call_successful"),
        "transcript_summary": analysis.get("transcript_summary"),
        "evaluation_results": analysis.get("evaluation_criteria_results") or None,
        "data_collection": analysis.get("data_collection_results") or None,
        "turn_count": len(turns),
        "user_turns": sum(1 for t in turns if t["role"] == "user"),
        "interruptions": sum(1 for t in turns if t["interrupted"]),
        "tool_error_count": sum(1 for t in turns if t["has_tool_error"]),
        "llm_ttfb_p50_ms": int(statistics.median(ttfbs)) if ttfbs else None,
        "llm_ttfb_p95_ms": _p95(ttfbs),
        "tool_latency_p95_ms": _p95(tool_lat),
        "tool_latency_max_ms": max(tool_lat) if tool_lat else None,
        "error": (meta.get("error") or None) if isinstance(meta.get("error"), (dict, str)) else None,
    }


def _process_transcription(data: dict) -> None:
    conversation_id = data.get("conversation_id")
    if not conversation_id:
        return
    try:
        turns = _parse_turns(conversation_id, data.get("transcript") or [])
        conv = build_conversation_row(data, turns)
        insert_tolerant("conversations", conv, logger, upsert_on="conversation_id")
        # Upsert (not insert) so ElevenLabs retries don't duplicate turns.
        for row in turns:
            insert_tolerant("conversation_turns", row, logger, upsert_on="conversation_id,turn_index")
        log_event(
            logger, "conversation.stored",
            conversation_id=conversation_id, turns=len(turns),
            duration_secs=conv["duration_secs"], call_successful=conv["call_successful"],
            llm_ttfb_p95_ms=conv["llm_ttfb_p95_ms"], tool_latency_p95_ms=conv["tool_latency_p95_ms"],
            tool_errors=conv["tool_error_count"], termination_reason=conv["termination_reason"],
        )
    except Exception as e:
        log_event(logger, "conversation.store_failed", logging.ERROR, conversation_id=conversation_id, error=repr(e))
        capture_exception(e, conversation_id=conversation_id, stage="post_call_webhook")

    _forward_otel_trace(conversation_id)


# ── Grafana Tempo forwarding ───────────────────────────────────────────────

def _forward_otel_trace(conversation_id: str) -> None:
    endpoint = os.getenv("GRAFANA_OTLP_ENDPOINT", "").rstrip("/")
    instance = os.getenv("GRAFANA_OTLP_INSTANCE_ID", "")
    token = os.getenv("GRAFANA_OTLP_TOKEN", "")
    api_key = os.getenv("ELEVENLABS_API_KEY", "")
    if not (endpoint and instance and token and api_key):
        return
    api_base = os.getenv("ELEVENLABS_API_BASE", "https://api.elevenlabs.io/v1").rstrip("/")
    try:
        r = requests.get(
            f"{api_base}/convai/conversations/{conversation_id}",
            params={"format": "opentelemetry"},
            headers={"xi-api-key": api_key},
            timeout=15,
        )
        r.raise_for_status()
        traces = r.json().get("otlp_traces")
        if not traces:
            log_event(logger, "otel.no_trace", logging.WARNING, conversation_id=conversation_id)
            return
        auth = base64.b64encode(f"{instance}:{token}".encode()).decode()
        push = requests.post(
            f"{endpoint}/v1/traces",
            data=json.dumps(traces),
            headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
            timeout=15,
        )
        push.raise_for_status()
        log_event(logger, "otel.forwarded", conversation_id=conversation_id)
    except Exception as e:
        log_event(logger, "otel.forward_failed", logging.WARNING, conversation_id=conversation_id, error=repr(e))
