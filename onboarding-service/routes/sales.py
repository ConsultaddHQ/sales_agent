"""Sales-agent webhooks — the stateful brain + proof retrieval.

These are ElevenLabs *webhook tool* targets (not /api admin routes), hit
directly by ElevenLabs on every turn. URLs must match the tool config in
elevenlabs_agent.py: {brain}/sales/brain and {brain}/sales/proof.

Resilience is the priority: the voice agent must keep talking even if the
DB or LLM is down, so persistence and retrieval failures degrade to a
working-but-stateless turn rather than an error.
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

_REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from shared.db import get_supabase
from shared.llm import make_llm
from services.sales_brain import SalesBrain, DEFAULT_PLAYBOOK_PATH

logger = logging.getLogger("onboarding-service")

router = APIRouter(prefix="/sales")

# Playbook is a committed static file — load once.
try:
    _PLAYBOOK = DEFAULT_PLAYBOOK_PATH.read_text(encoding="utf-8")
except Exception as e:  # pragma: no cover - only if the file is missing
    logger.error(f"Could not read sales playbook: {e}")
    _PLAYBOOK = "Sell consultatively. Discover the problem, quantify impact, then book a meeting."

# Unresolved ElevenLabs dynamic-variable template (means the live API did
# not substitute the conversation id — see decisions.md 2026-05-16).
_UNRESOLVED = "{{system__conversation_id}}"

_DEFAULT_SESSION = {
    "stage": "rapport",
    "pic": [],
    "captured": {},
    "objections": [],
    "proof_shown": [],
    "transcript": [],
    "booked": False,
}


class BrainBody(BaseModel):
    site: str = "teampop"
    conversation_id: str = ""
    message: str = ""


class ProofBody(BaseModel):
    site: str = "teampop"
    query: str = ""
    proof_type: Optional[str] = None


def _load_session(conversation_id: str, site: str) -> dict:
    """Fetch the running session, or a fresh one. Never raises."""
    base = {**_DEFAULT_SESSION, "conversation_id": conversation_id, "site": site}
    if not conversation_id or conversation_id == _UNRESOLVED:
        return base
    try:
        sb = get_supabase()
        rows = (
            sb.table("sales_sessions")
            .select("*")
            .eq("conversation_id", conversation_id)
            .limit(1)
            .execute()
            .data
        )
        if rows:
            row = rows[0]
            return {**base, **{k: row[k] for k in row if k in base or k in (
                "stage", "pic", "captured", "objections", "proof_shown",
                "transcript", "booked", "next_move",
            )}}
    except Exception as e:
        logger.warning(f"sales_sessions load failed ({conversation_id[:12]}…): {e}")
    return base


def _save_session(conversation_id: str, site: str, session: dict) -> None:
    """Upsert session state. Never raises (agent must keep talking)."""
    if not conversation_id or conversation_id == _UNRESOLVED:
        logger.warning(
            "conversation_id unresolved — session not persisted. Verify the "
            "ElevenLabs system dynamic variable substitution (decisions.md 2026-05-16)."
        )
        return
    try:
        sb = get_supabase()
        sb.table("sales_sessions").upsert(
            {
                "conversation_id": conversation_id,
                "site": site,
                "stage": session.get("stage"),
                "pic": session.get("pic", []),
                "captured": session.get("captured", {}),
                "objections": session.get("objections", []),
                "proof_shown": session.get("proof_shown", []),
                "transcript": session.get("transcript", []),
                "next_move": session.get("next_move"),
                "booked": bool(session.get("booked")),
                "updated_at": datetime.now().isoformat(),
            },
            on_conflict="conversation_id",
        ).execute()
    except Exception as e:
        logger.warning(f"sales_sessions save failed ({conversation_id[:12]}…): {e}")


@router.post("/brain")
def sales_brain(body: BrainBody) -> dict:
    """Every-turn AE decision. Returns {stage, say, next_move, directives}."""
    msg = (body.message or "").strip()
    logger.info(
        f"➡️  /sales/brain site={body.site} "
        f"conv={body.conversation_id[:16] if body.conversation_id else '<none>'} "
        f"msg={msg[:80]!r}"
    )
    session = _load_session(body.conversation_id, body.site)

    brain = SalesBrain(llm=make_llm(), playbook=_PLAYBOOK)
    decision, new_session = brain.decide(session, msg or "(visitor was silent)")

    _save_session(body.conversation_id, body.site, new_session)
    logger.info(
        f"⬅️  /sales/brain stage={decision.stage} "
        f"next={decision.next_move!r} directives={[d['tool'] for d in decision.directives]}"
    )
    return decision.to_agent_payload()


@router.post("/proof")
def sales_proof(body: ProofBody) -> dict:
    """Retrieve real proof artifacts (Phase 3 fills the content + admin CRUD).

    Naive keyword/tag relevance over the small curated set — embeddings are
    YAGNI here (the catalog is tiny). Returns {proof: [...]} and never errors.
    """
    try:
        sb = get_supabase()
        q = (
            sb.table("sales_proof")
            .select("type,title,body,metric,tags")
            .eq("site", body.site)
            .eq("active", True)
        )
        if body.proof_type:
            q = q.eq("type", body.proof_type)
        rows = q.execute().data or []
    except Exception as e:
        logger.warning(f"sales_proof query failed: {e}")
        return {"proof": []}

    terms = {t for t in (body.query or "").lower().split() if len(t) > 2}

    def score(r: dict) -> int:
        hay = " ".join(
            [str(r.get("title", "")), str(r.get("body", "")), " ".join(r.get("tags", []) or [])]
        ).lower()
        return sum(1 for t in terms if t in hay)

    ranked = sorted(rows, key=score, reverse=True)
    return {"proof": ranked[:3]}
