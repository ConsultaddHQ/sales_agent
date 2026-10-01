"""
configure_agent_analysis.py — post-call analysis config for the Wrina agent.

Sets, on Main and any given branches (post-call only — zero runtime latency):
  • data collection  — business signals extracted from every call (feeds the
    v_bi_* views via the post-call webhook → conversations.data_collection)
  • evaluation criteria — per-call quality checks used for RCA
  • privacy retention — 30 days (agreed with the user 2026-09-29)

Idempotent; dry run by default. Usage:
    python3 testing/monitoring/configure_agent_analysis.py --branch agtbrch_... [--branch ...] [--apply]
The ids below are a contract with create_business_metrics.sql — rename both together.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[2]
AGENT_ID = "agent_4901kwna71tve5nbyy85c8v20yre"
API = os.getenv("ELEVENLABS_API_BASE", "https://api.elevenlabs.io/v1").rstrip("/")
CATEGORIES = ["facewash", "moisturiser", "lip balm", "other", "none"]

DATA_COLLECTION = {
    "shopper_need": {"type": "string", "description": (
        "What the shopper was looking for, in their own words, translated to short English "
        "(e.g. 'face wash for oily skin'). Empty string if they never asked for a product.")},
    "product_category": {"type": "string", "enum": CATEGORIES, "description": (
        "The store category the shopper's main request belongs to. 'other' if it is a product type "
        "the store does not carry; 'none' if they never asked for a product.")},
    "need_met": {"type": "boolean", "description": (
        "True if the agent showed at least one product that genuinely fits the shopper's request. "
        "False if nothing suitable was found or shown.")},
    "unmet_need": {"type": "string", "description": (
        "If the shopper wanted something the store did not have, or the results did not fit "
        "(size, variant, concern, ingredient, bundle, price), describe it in short English. "
        "Empty string if the need was met.")},
    "shopper_terms": {"type": "string", "description": (
        "Comma-separated key words and phrases the shopper used to describe what they want, in "
        "romanized form exactly as said (e.g. 'chipchipa, oily, pimple wala facewash').")},
    "budget_mentioned": {"type": "boolean", "description": "True if the shopper mentioned a budget, price limit, or asked for something cheaper."},
    "budget_amount_inr": {"type": "number", "description": "The budget in rupees if the shopper stated a number (e.g. 'under 300' → 300); otherwise leave empty."},
    "price_objection": {"type": "boolean", "description": "True if the shopper said a price was too high, hesitated over price, or asked for discounts."},
    "drop_off_reason": {"type": "string", "enum": [
        "purchase_intent", "got_answer", "no_suitable_product", "price", "agent_confusion",
        "technical_issue", "left_without_reason"], "description": (
        "Why the conversation ended: purchase_intent (added to cart / went to checkout), got_answer "
        "(question answered, left satisfied), no_suitable_product, price, agent_confusion (agent "
        "misunderstood or repeated itself), technical_issue (errors, silence), left_without_reason.")},
}

EVALUATION = [
    ("search_before_answering", "Search before answering",
     "The agent called search_products before naming any product, price or availability. Fail if it named products or prices without a search result in this conversation."),
    ("grounded_answers", "Grounded answers",
     "Every product fact the agent stated (ingredients, benefits, suitability, price) came from a tool result. Fail if anything looks invented or contradicts the tool results."),
    ("language_match", "Language match",
     "The agent replied in the language the shopper used (English, Hindi/Hinglish, or Tamil). Fail if it answered in a different language than the shopper's last message."),
    ("concise_replies", "Concise replies",
     "Agent replies were short (one or two sentences) unless the shopper asked for detail. Fail if it gave long monologues unprompted."),
    ("need_resolved", "Need resolved",
     "The shopper's need was addressed: relevant products were shown, their question was answered, or the agent honestly said the item is not carried. Fail if the shopper left with the need unaddressed due to the agent."),
]


def _key() -> str:
    if os.getenv("ELEVENLABS_API_KEY"):
        return os.environ["ELEVENLABS_API_KEY"]
    for line in (REPO / "onboarding-service" / ".env").read_text().splitlines():
        if line.startswith("ELEVENLABS_API_KEY="):
            return line.split("=", 1)[1].strip().strip("\"'")
    sys.exit("ELEVENLABS_API_KEY not found")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--branch", action="append", default=[], help="branch ids to configure besides Main")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    h = {"xi-api-key": _key(), "Content-Type": "application/json"}
    url = f"{API}/convai/agents/{AGENT_ID}"

    for branch in [None, *args.branch]:
        params = {"branch_id": branch} if branch else {}
        cur = requests.get(url, headers=h, params=params, timeout=30).json()["platform_settings"]
        privacy = dict(cur.get("privacy") or {})
        privacy.update({"retention_days": 30, "apply_to_existing_conversations": False})
        body = {"platform_settings": {
            "data_collection": DATA_COLLECTION,
            "evaluation": {"criteria": [
                {"id": i, "name": n, "type": "prompt", "conversation_goal_prompt": p} for i, n, p in EVALUATION]},
            "privacy": privacy,
        }}
        label = branch or "Main"
        if not args.apply:
            print(f"[dry-run] {label}: {len(DATA_COLLECTION)} data-collection items, {len(EVALUATION)} criteria, retention 30d")
            continue
        r = requests.patch(url, headers=h, params=params, json=body, timeout=60)
        if not r.ok:
            sys.exit(f"{label}: HTTP {r.status_code} {r.text[:400]}")
        after = requests.get(url, headers=h, params=params, timeout=30).json()
        ps = after["platform_settings"]
        print(f"{label}: data_collection={sorted(ps.get('data_collection') or {})} "
              f"criteria={[c['id'] for c in (ps.get('evaluation') or {}).get('criteria', [])]} "
              f"retention_days={ps['privacy'].get('retention_days')} "
              f"webhook_override={((ps.get('workspace_overrides') or {}).get('webhooks') or {}).get('post_call_webhook_id')}")
    if not args.apply:
        print("Dry run only — re-run with --apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
