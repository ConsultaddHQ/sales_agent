"""
upgrade_agent_model.py — swap the LLM model on an existing ElevenLabs agent
without re-scraping or re-onboarding the store.

Background:
    ElevenLabs bakes the `llm` field in at agent creation time. To change
    the LLM on a live agent you must PATCH it. The onboarding service
    already has this helper: `ElevenLabsAgentCreator.update_agent(...)`.
    This script is the human-facing wrapper.

Use cases:
    1. After the latency A/B test picks a winner, upgrade production agents
       to the winning model (currently Claude Haiku 4.5 per the 2026-04-17
       decision).
    2. Experiment with a new ElevenLabs-hosted model on one live agent
       before changing the default for future onboardings.
    3. Roll back quickly if a model is misbehaving.

Usage:
    # Upgrade one agent to the env-var default (ELEVENLABS_LLM_MODEL):
    ./onboarding-service/.venv/bin/python testing/latency/upgrade_agent_model.py \
        --agent-id agent_abc123 --store-id 75eb8b55-70de-42fb-ae38-813af27022d3

    # Upgrade to a specific model (overrides the env var for this call only):
    ./onboarding-service/.venv/bin/python testing/latency/upgrade_agent_model.py \
        --agent-id agent_abc123 --store-id 75eb8b55-70de-42fb-ae38-813af27022d3 \
        --llm claude-haiku-4-5

    # Batch-upgrade from a JSON file produced by create_test_agents.py
    # (only the row you want to keep — delete the rest from the file):
    ./onboarding-service/.venv/bin/python testing/latency/upgrade_agent_model.py \
        --from-json latency_test_agents.json --store-id 75eb8b55-...

Notes:
    - This only touches prompt + llm + tools. Voice, TTS, turn settings,
      and the baked-in constant store_id are preserved.
    - Prompts are re-rendered from the current templates in
      onboarding-service/elevenlabs_agent.py, so agents will pick up any
      prompt changes shipped since the agent was last created/updated.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

# --- repo path wiring --------------------------------------------------------
_THIS = Path(__file__).resolve()
_REPO_ROOT = _THIS.parent.parent.parent
_SERVICE_DIR = _REPO_ROOT / "onboarding-service"
for _p in (str(_REPO_ROOT), str(_SERVICE_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from dotenv import load_dotenv
load_dotenv(_SERVICE_DIR / ".env")

from elevenlabs_agent import ElevenLabsAgentCreator  # noqa: E402
from shared.db import get_supabase                    # noqa: E402

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(levelname)s %(message)s",
)
logger = logging.getLogger("upgrade-agent-model")


def build_store_context(store_id: str) -> Dict:
    """Re-derive store context from Supabase so the re-rendered prompt has
    the same store_name / price_range as a freshly onboarded agent would.
    """
    ctx = {
        "store_name": "this store",
        "description": "online store",
        "categories": "various products",
        "price_range": "affordable to premium pricing",
    }
    try:
        sb = get_supabase()
        try:
            stores = sb.table("stores").select("*").eq("id", store_id).limit(1).execute()
            if stores.data:
                row = stores.data[0]
                ctx["store_name"] = row.get("name") or ctx["store_name"]
                ctx["description"] = row.get("description") or ctx["description"]
        except Exception:
            pass

        products = (
            sb.table("products")
            .select("price")
            .eq("store_id", store_id)
            .limit(20)
            .execute()
        )
        if products.data:
            prices = [float(p["price"]) for p in products.data if p.get("price") is not None]
            if prices:
                ctx["price_range"] = f"{min(prices):.0f} to {max(prices):.0f}"
    except Exception as e:
        logger.warning("Could not enrich store context: %s", e)
    return ctx


def upgrade_one(creator: ElevenLabsAgentCreator, agent_id: str, store_id: str,
                llm: Optional[str], ctx: Dict) -> Dict:
    logger.info("→ Upgrading %s (store=%s) to llm=%s", agent_id, store_id, llm or "<env default>")
    return creator.update_agent(
        agent_id=agent_id,
        store_id=store_id,
        store_context=ctx,
        llm_model=llm,
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Swap the LLM on an existing ElevenLabs agent (PATCH, not create).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--store-id", required=True, help="Store UUID that owns the agent(s).")
    p.add_argument("--agent-id", help="Single agent id to upgrade.")
    p.add_argument(
        "--from-json",
        help=(
            "Path to a JSON file shaped like create_test_agents.py output "
            "({model: {agent_id: ...}}). Every entry with an agent_id is upgraded."
        ),
    )
    p.add_argument(
        "--llm",
        help=(
            "ElevenLabs `llm` string to switch to. If omitted, uses "
            "ELEVENLABS_LLM_MODEL from onboarding-service/.env."
        ),
    )
    p.add_argument("--dry-run", action="store_true", help="Print plan without PATCHing.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if not args.agent_id and not args.from_json:
        logger.error("Provide either --agent-id or --from-json")
        return 2

    ctx = build_store_context(args.store_id)
    logger.info("Store context: %s", ctx)

    targets: List[Dict[str, str]] = []
    if args.agent_id:
        targets.append({"agent_id": args.agent_id, "label": "cli"})
    if args.from_json:
        data = json.loads(Path(args.from_json).read_text())
        for key, info in data.items():
            aid = info.get("agent_id") if isinstance(info, dict) else None
            if aid:
                targets.append({"agent_id": aid, "label": key})

    if not targets:
        logger.error("No valid agent ids found in inputs")
        return 2

    if args.dry_run:
        for t in targets:
            print(f"[DRY] Would PATCH {t['agent_id']} ({t['label']}) "
                  f"→ llm={args.llm or '<env default>'}")
        return 0

    creator = ElevenLabsAgentCreator()
    results = {}
    for t in targets:
        try:
            resp = upgrade_one(creator, t["agent_id"], args.store_id, args.llm, ctx)
            results[t["agent_id"]] = {"ok": True, "model": resp.get("llm_model")}
            print(f"✅ {t['agent_id']} → {resp.get('llm_model')}")
        except Exception as e:
            logger.exception("Failed to upgrade %s", t["agent_id"])
            results[t["agent_id"]] = {"ok": False, "error": str(e)}
            print(f"❌ {t['agent_id']}: {e}")

    return 0 if all(r["ok"] for r in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
