"""
create_test_agents.py — STEP 3 of the voice-agent latency plan.

Creates 6 parallel ElevenLabs agents for one already-onboarded store, each
pinned to a different `llm` value. This lets you A/B-test latency and tool
reliability across candidate models without re-running the scraping pipeline.

Why this exists:
    `POST /onboard` creates ONE agent using ELEVENLABS_LLM_MODEL env var.
    To compare 6 models fairly we need 6 agents, same store, same prompts,
    same voice — only the LLM changes. This script does that in one shot.

Usage:
    # Run from repo root using the onboarding-service venv:
    ./onboarding-service/.venv/bin/python testing/latency/create_test_agents.py \
        --store-id <uuid>
    ./onboarding-service/.venv/bin/python testing/latency/create_test_agents.py \
        --store-id <uuid> --dry-run
    ./onboarding-service/.venv/bin/python testing/latency/create_test_agents.py \
        --store-id <uuid> --only claude-haiku-4-5

Output:
    Writes latency_test_agents.json (or --out path) with {model: {agent_id, ...}}
    and prints a table with agent IDs + ready-to-use demo URLs.

Related:
    Plan:            ~/.claude/plans/synchronous-churning-sky.md (§11 STEP 3)
    Test protocol:   testing/latency/README.md
    Prompt contract: docs/agents/decisions.md (2026-04-17 entries)
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
# File lives at testing/latency/create_test_agents.py; go up 2 levels for repo root.
_THIS = Path(__file__).resolve()
_REPO_ROOT = _THIS.parent.parent.parent            # sales_agent/
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
logger = logging.getLogger("create-test-agents")

# ---------------------------------------------------------------------------
# Candidate LLMs for the 6-model A/B matrix.
#
# The `llm` string is what ElevenLabs' convai API accepts in the agent
# prompt config. Names are best-effort per the decisions log (2026-04-08)
# and may need adjustment — run with --dry-run first, and if a creation
# fails with "invalid llm", update the string below.
#
# Order: control first, then ranked by expected latency (fastest first).
# ---------------------------------------------------------------------------
CANDIDATES: List[Dict[str, str]] = [
    {
        "id": "gemini-2.5-flash",
        "label": "Gemini 2.5 Flash (CONTROL)",
        "notes": "Current production default. Baseline for comparison.",
    },
    {
        "id": "qwen3-30b-a3b",
        "label": "Qwen3-30B-A3B",
        "notes": "ElevenLabs-hosted, ~187ms; tool reliability is the risk.",
    },
    {
        "id": "gpt-4.1-nano",
        "label": "GPT-4.1 Nano",
        "notes": "OpenAI, ~504ms, very reliable native function calling.",
    },
    {
        "id": "gemini-2.5-flash-lite",
        "label": "Gemini 2.5 Flash Lite",
        "notes": "Fastest Gemini tier; simpler reasoning.",
    },
    {
        "id": "glm-45-air-fp8",
        "label": "GLM-4.5 Air",
        "notes": "ElevenLabs-hosted, ~634ms, agentic.",
    },
    {
        "id": "claude-haiku-4-5",
        "label": "Claude Haiku 4.5",
        "notes": "Anthropic, ~686ms; strongest instruction-following.",
    },
]


def build_store_context(store_id: str, override_name: Optional[str] = None) -> Dict:
    """Pull store context from Supabase so test agents feel like production.

    Falls back to sensible defaults if the store row is missing — the latency
    test doesn't actually need perfect context, just non-empty values so the
    prompt template renders cleanly.
    """
    context = {
        "store_name": override_name or "this store",
        "description": "online store",
        "categories": "various products",
        "price_range": "affordable to premium pricing",
    }

    try:
        sb = get_supabase()
        # The `stores` table may not exist in every deploy; products do.
        # Try stores first, fall back to deriving from products.
        try:
            stores = sb.table("stores").select("*").eq("id", store_id).limit(1).execute()
            if stores.data:
                row = stores.data[0]
                if not override_name:
                    context["store_name"] = row.get("name") or context["store_name"]
                context["description"] = row.get("description") or context["description"]
        except Exception:
            pass  # stores table may not exist; keep going

        products = (
            sb.table("products")
            .select("name, price")
            .eq("store_id", store_id)
            .limit(20)
            .execute()
        )
        if products.data:
            prices = [float(p["price"]) for p in products.data if p.get("price") is not None]
            if prices:
                lo, hi = min(prices), max(prices)
                context["price_range"] = f"{lo:.0f} to {hi:.0f}"
        else:
            logger.warning(
                "Store %s has no products. Are you sure this is the right store_id?",
                store_id,
            )
    except Exception as e:
        logger.warning("Could not enrich store context from Supabase: %s", e)

    return context


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Create 6 test ElevenLabs agents for latency A/B testing.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--store-id", required=True, help="Target store UUID (must be already onboarded)")
    p.add_argument("--store-name", help="Override store_name in prompt context")
    p.add_argument("--out", default="latency_test_agents.json", help="Write mapping JSON here")
    p.add_argument(
        "--only",
        action="append",
        metavar="LLM_ID",
        help="Restrict to these model ids (repeatable). Default: all 6.",
    )
    p.add_argument("--dry-run", action="store_true", help="Show what would be created without calling the API")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    # Filter candidates if --only given
    selected = CANDIDATES
    if args.only:
        wanted = set(args.only)
        selected = [c for c in CANDIDATES if c["id"] in wanted]
        missing = wanted - {c["id"] for c in CANDIDATES}
        if missing:
            logger.warning("Ignoring unknown models: %s", sorted(missing))
        if not selected:
            logger.error("No matching candidates. Valid ids: %s", [c["id"] for c in CANDIDATES])
            return 2

    context = build_store_context(args.store_id, override_name=args.store_name)
    logger.info("Store context: %s", context)

    if args.dry_run:
        print("\nDRY RUN — would create these agents:\n")
        for c in selected:
            print(f"  • {c['label']:30s}  llm={c['id']:26s}  name=latency-test-{c['id']}")
        print(f"\nWould write → {args.out}")
        return 0

    creator = ElevenLabsAgentCreator()
    results: Dict[str, Dict] = {}

    print(f"\nCreating {len(selected)} agents for store {args.store_id}...\n")
    for c in selected:
        model_id = c["id"]
        label = c["label"]
        print(f"→ {label}  (llm={model_id})")
        try:
            resp = creator.create_agent(
                store_id=args.store_id,
                store_context=context,
                llm_model=model_id,
                agent_name=f"latency-test-{model_id}-{args.store_id[:8]}",
                tags=["latency-test", model_id, args.store_id],
            )
            results[model_id] = {
                "label": label,
                "agent_id": resp.get("agent_id"),
                "agent_url": resp.get("agent_url"),
                "notes": c["notes"],
            }
            print(f"   ✅ agent_id={resp.get('agent_id')}")
        except Exception as e:
            logger.exception("Failed to create agent for %s", model_id)
            results[model_id] = {
                "label": label,
                "error": str(e),
                "notes": c["notes"],
            }
            print(f"   ❌ {e}")

    out_path = Path(args.out).resolve()
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\n✅ Wrote {out_path}\n")

    print("=" * 72)
    print(f"{'MODEL':30s}  {'AGENT_ID':42s}")
    print("=" * 72)
    for model_id, info in results.items():
        if "agent_id" in info:
            print(f"{model_id:30s}  {info['agent_id']}")
        else:
            print(f"{model_id:30s}  ERROR: {info.get('error', '?')[:40]}")
    print("=" * 72)
    print("\nNext: follow testing/latency/README.md to run the 10-prompt test")
    print("against each agent_id. Paste the widget + server logs back per model.\n")

    # Exit non-zero if ANY agent failed, so CI or shells see the signal.
    return 1 if any("error" in v for v in results.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
