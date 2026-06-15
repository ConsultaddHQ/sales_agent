"""Pure lead-enrichment for the assisted close.

Maps a sales_sessions row into the extra columns attached to the
agent_requests lead (source, transcript, discovery, pic). No DB import
→ unit-tested. routes/client.py does the fetch + insert.
"""

from typing import Dict, Optional


def build_lead_enrichment(session_row: Optional[Dict], source: str = "sales_agent") -> Dict:
    """Return the agent_requests fields to merge for an assisted-close lead.

    With no session (manual visit / session lookup failed) we still tag the
    source so the funnel is attributable, but add no empty transcript noise.
    """
    if not session_row or not isinstance(session_row, dict):
        return {"source": source}
    return {
        "source": source,
        "transcript": list(session_row.get("transcript") or []),
        "discovery": dict(session_row.get("captured") or {}),
        "pic": list(session_row.get("pic") or []),
    }
