"""
add_conversation_id_to_tools.py — surgically add `conversation_id` to a live
agent's webhook tools (search_products, get_product_details).

Why: the body param `conversation_id` (filled by ElevenLabs from the
`system__conversation_id` dynamic variable) is what lets search_latency rows,
server logs and Sentry events be joined to one shopper's call. New agents get
it from elevenlabs_agent._get_tool_config(); this script back-fills LIVE agents.

Safety: it GETs the live agent and changes ONLY the request_body_schema of the
webhook tools that don't already carry the param. Prompt, voice, TTS, language,
turn settings, other tools — untouched (the live xfused agent has dashboard
hand-edits that must not be overwritten; see decisions.md 2026-08-12).
Handles both inline `prompt.tools` and standalone tools referenced by `tool_ids`.

Dry run by default — prints what it would change. Pass --apply to write.

Usage:
    python3 testing/monitoring/add_conversation_id_to_tools.py --agent-id agent_4901kwna71tve5nbyy85c8v20yre
    python3 testing/monitoring/add_conversation_id_to_tools.py --agent-id agent_... --apply

Requires ELEVENLABS_API_KEY (read from onboarding-service/.env if not exported).
Optional ELEVENLABS_API_BASE for residency endpoints.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from pathlib import Path

import requests

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TARGET_TOOLS = {"search_products", "get_product_details"}
PARAM = {"type": "string", "dynamic_variable": "system__conversation_id"}


def _load_env() -> None:
    env = _REPO_ROOT / "onboarding-service" / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _patch_tool_config(tool: dict) -> bool:
    """Mutates a webhook tool config in place. Returns True if changed."""
    if tool.get("type") != "webhook" or tool.get("name") not in TARGET_TOOLS:
        return False
    schema = (tool.get("api_schema") or {}).get("request_body_schema") or {}
    props = schema.setdefault("properties", {})
    if "conversation_id" in props:
        return False
    props["conversation_id"] = dict(PARAM)
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent-id", required=True)
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    args = ap.parse_args()

    _load_env()
    key = os.getenv("ELEVENLABS_API_KEY")
    if not key:
        print("ELEVENLABS_API_KEY not set", file=sys.stderr)
        return 2
    base = os.getenv("ELEVENLABS_API_BASE", "https://api.elevenlabs.io/v1").rstrip("/")
    h = {"xi-api-key": key, "Content-Type": "application/json"}

    agent = requests.get(f"{base}/convai/agents/{args.agent_id}", headers=h, timeout=20)
    agent.raise_for_status()
    prompt = agent.json()["conversation_config"]["agent"]["prompt"]

    changed_any = False

    # 1) Inline tools — only for agents that don't use standalone tools. When
    # tool_ids is set, the GET echoes the resolved tools inline too; PATCHing
    # that list would duplicate/convert them, so patch the tool objects instead.
    inline = prompt.get("tools") or []
    if inline and not prompt.get("tool_ids"):
        new_tools = copy.deepcopy(inline)
        changed = [t["name"] for t in new_tools if _patch_tool_config(t)]
        if changed:
            changed_any = True
            print(f"inline tools to patch: {changed}")
            if args.apply:
                r = requests.patch(
                    f"{base}/convai/agents/{args.agent_id}", headers=h, timeout=30,
                    json={"conversation_config": {"agent": {"prompt": {"tools": new_tools}}}},
                )
                print(f"  PATCH agent → {r.status_code} {r.text[:300] if not r.ok else ''}")
                r.raise_for_status()

    # 2) Standalone tools referenced by id
    for tool_id in prompt.get("tool_ids") or []:
        t = requests.get(f"{base}/convai/tools/{tool_id}", headers=h, timeout=20)
        t.raise_for_status()
        cfg = copy.deepcopy(t.json().get("tool_config") or {})
        if _patch_tool_config(cfg):
            changed_any = True
            print(f"standalone tool to patch: {cfg.get('name')} ({tool_id})")
            print(json.dumps(cfg["api_schema"]["request_body_schema"], indent=2))
            if args.apply:
                r = requests.patch(f"{base}/convai/tools/{tool_id}", headers=h, timeout=30,
                                   json={"tool_config": cfg})
                print(f"  PATCH tool → {r.status_code} {r.text[:300] if not r.ok else ''}")
                r.raise_for_status()

    if not changed_any:
        print("nothing to change — webhook tools already send conversation_id (or none found)")
    elif not args.apply:
        print("\nDry run only. Re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
