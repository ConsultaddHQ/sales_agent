"""The stateful sales brain — an AI account executive.

This is the "next level" piece: the ElevenLabs voice agent is just the
voice; THIS decides the sale. It reasons over the committed sales playbook
plus the running session state and returns, every turn, the stage, what to
say, and which in-page tools to fire.

Design constraints:
- Import-light and pure: no supabase/httpx/network imports at module load,
  so the decision logic is fully unit-testable with a fake LLM. The route
  (routes/sales.py) owns persistence + the real LLM client.
- The LLM is *advisory*. The brain refuses to be talked backwards out of
  the sale, only emits whitelisted directives, accumulates the Problem
  Identification Chart, and degrades safely if the LLM returns junk.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

# Playbook chapters → the sale's stage machine (forward-biased).
STAGES: List[str] = [
    "rapport",
    "discovery",
    "quantify_gap",
    "demo",
    "pricing",
    "objection",
    "close",
    "booked",
]

# The only tools the brain may instruct the voice agent to fire. Anything
# else the LLM dreams up is dropped (same spirit as the store_id invariant).
ALLOWED_DIRECTIVES = {
    "surface_proof",
    "show_proof",
    "navigate_site",
    "prefill_demo_form",
    "open_booking",
}

_PIC_KEYS = ("technical_problem", "business_impact", "root_cause")

DEFAULT_PLAYBOOK_PATH = Path(__file__).resolve().parent / "sales_playbook.md"


# ── pure helpers (individually unit-tested) ─────────────────────────────────

def parse_decision(raw: str) -> Dict:
    """Best-effort extract a JSON object from an LLM response.

    Handles ```json fences, leading/trailing prose, and pure JSON. Returns
    {} on anything unparseable so callers can fall back safely.
    """
    if not raw or not isinstance(raw, str):
        return {}
    s = re.sub(r"```(?:json)?", "", raw).strip()
    try:
        v = json.loads(s)
        return v if isinstance(v, dict) else {}
    except Exception:
        pass
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            v = json.loads(s[start : end + 1])
            return v if isinstance(v, dict) else {}
        except Exception:
            return {}
    return {}


def advance_stage(current: str, proposed: str) -> str:
    """Forward-biased stage guard.

    The LLM proposes a stage; the brain only honours it if it does not
    abandon progress: forward jumps OK, 'objection' reachable any time,
    at most one step back (re-discovery / post-objection), bigger backward
    jumps and unknown stages are refused.
    """
    if proposed not in STAGES:
        return current
    if proposed == "objection":
        return "objection"
    if current not in STAGES:
        return proposed
    ci, pi = STAGES.index(current), STAGES.index(proposed)
    if pi >= ci:
        return proposed
    if pi == ci - 1:
        return proposed
    return current


def merge_pic(existing: List[Dict], update) -> List[Dict]:
    """Accumulate the Problem Identification Chart.

    Match on technical_problem (case-insensitive): enrich an existing row's
    empty fields, otherwise append. Every row is normalised to all 3 keys.
    """
    if isinstance(update, dict):
        update = [update]
    if not isinstance(update, list):
        update = []

    def norm(row: Dict) -> Dict:
        return {k: str(row.get(k, "") or "").strip() for k in _PIC_KEYS}

    out: List[Dict] = [norm(r) for r in existing if isinstance(r, dict)]
    index = {r["technical_problem"].lower(): r for r in out if r["technical_problem"]}
    for raw in update:
        if not isinstance(raw, dict):
            continue
        row = norm(raw)
        tp = row["technical_problem"]
        if not tp:
            continue
        key = tp.lower()
        if key in index:
            for k in ("business_impact", "root_cause"):
                if not index[key][k] and row[k]:
                    index[key][k] = row[k]
        else:
            out.append(row)
            index[key] = row
    return out


def merge_captured(existing: Dict, update) -> Dict:
    """Shallow-merge discovery fields, ignoring empty/falsy updates."""
    out = dict(existing or {})
    if isinstance(update, dict):
        for k, v in update.items():
            if v not in (None, "", [], {}):
                out[k] = v
    return out


def sanitize_directives(raw) -> List[Dict]:
    """Keep only well-formed, whitelisted {tool, args} directives."""
    out: List[Dict] = []
    if not isinstance(raw, list):
        return out
    for d in raw:
        if not isinstance(d, dict):
            continue
        tool = d.get("tool")
        if tool not in ALLOWED_DIRECTIVES:
            continue
        args = d.get("args")
        out.append({"tool": tool, "args": args if isinstance(args, dict) else {}})
    return out


def fallback_decision(session: Dict) -> Dict:
    """Safe decision when the LLM response is unusable: hold the stage, ask
    one honest discovery question, take no risky actions."""
    return {
        "stage": session.get("stage", "rapport"),
        "say_guidance": (
            "Tell me a bit more about what you're trying to solve — "
            "what does that look like day to day for your team?"
        ),
        "next_move": "discovery",
        "pic_update": [],
        "captured_fields": {},
        "directives": [],
    }


@dataclass
class BrainDecision:
    stage: str
    say_guidance: str
    next_move: str
    directives: List[Dict] = field(default_factory=list)
    pic: List[Dict] = field(default_factory=list)
    captured: Dict = field(default_factory=dict)

    def to_agent_payload(self) -> Dict:
        """What the ElevenLabs sales_brain webhook returns to the voice agent."""
        return {
            "stage": self.stage,
            "say": self.say_guidance,
            "next_move": self.next_move,
            "directives": self.directives,
        }


_SYSTEM_TEMPLATE = """You are the sales brain for {site_name}: a world-class B2B account executive running a live website conversation. You do not speak to the visitor — you instruct a voice agent.

Use ONLY the methodology in this playbook:
<playbook>
{playbook}
</playbook>

Every turn you receive the session state and the visitor's latest message (and any [VISITOR ACTIVITY]). Decide the single best next move per the playbook (Gap Selling: move from technical problem → business impact → root cause; build the gap; quantify; only then price; close to a booked meeting).

Respond with ONLY a JSON object, no prose, no code fence:
{{
  "stage": one of {stages},
  "say_guidance": "one concise, human thing for the agent to say (<25 words)",
  "next_move": "short label of the move you're making",
  "pic_update": [{{"technical_problem": "...", "business_impact": "...", "root_cause": "..."}}],
  "captured_fields": {{"name": "", "email": "", "company": "", "use_case": ""}},
  "directives": [{{"tool": one of {tools}, "args": {{}}}}]
}}

Rules: never invent customers, metrics, or prices — to cite proof, emit a surface_proof directive. Only emit prefill_demo_form/open_booking at the close after value is established. Keep say_guidance honest and specific to what they said."""


class SalesBrain:
    """Stateful AE. `llm` is a callable (system, user) -> raw string."""

    def __init__(self, llm: Callable[[str, str], str], playbook: str, site_name: str = "Team Pop"):
        self.llm = llm
        self.playbook = playbook
        self.site_name = site_name

    @classmethod
    def from_files(
        cls,
        llm: Callable[[str, str], str],
        playbook_path: Path = DEFAULT_PLAYBOOK_PATH,
        site_name: str = "Team Pop",
    ) -> "SalesBrain":
        text = Path(playbook_path).read_text(encoding="utf-8")
        return cls(llm=llm, playbook=text, site_name=site_name)

    def system_prompt(self) -> str:
        return _SYSTEM_TEMPLATE.format(
            site_name=self.site_name,
            playbook=self.playbook,
            stages=STAGES,
            tools=sorted(ALLOWED_DIRECTIVES),
        )

    def _build_user(self, session: Dict, message: str, activity: Optional[str]) -> str:
        transcript = session.get("transcript", [])
        ctx = {
            "stage": session.get("stage", "rapport"),
            "pic": session.get("pic", []),
            "captured": session.get("captured", {}),
            "recent_transcript": transcript[-8:],
            "visitor_message": message,
        }
        if activity:
            ctx["visitor_activity"] = activity
        return json.dumps(ctx, ensure_ascii=False)

    def decide(
        self,
        session: Dict,
        message: str,
        activity: Optional[str] = None,
    ) -> Tuple[BrainDecision, Dict]:
        """Run one AE turn. Returns (decision, updated_session)."""
        try:
            raw = self.llm(self.system_prompt(), self._build_user(session, message, activity))
        except Exception:
            raw = ""
        parsed = parse_decision(raw) or fallback_decision(session)

        stage = advance_stage(session.get("stage", "rapport"), parsed.get("stage", session.get("stage", "rapport")))
        pic = merge_pic(session.get("pic", []), parsed.get("pic_update", []))
        captured = merge_captured(session.get("captured", {}), parsed.get("captured_fields", {}))
        directives = sanitize_directives(parsed.get("directives", []))
        say = str(parsed.get("say_guidance") or fallback_decision(session)["say_guidance"]).strip()
        next_move = str(parsed.get("next_move") or "").strip()

        new_session = {
            **session,
            "stage": stage,
            "pic": pic,
            "captured": captured,
            "next_move": next_move,
            "booked": bool(session.get("booked")) or stage == "booked",
            "transcript": list(session.get("transcript", []))
            + [
                {"role": "visitor", "text": message},
                {"role": "agent", "text": say},
            ],
        }
        decision = BrainDecision(
            stage=stage,
            say_guidance=say,
            next_move=next_move,
            directives=directives,
            pic=pic,
            captured=captured,
        )
        return decision, new_session
