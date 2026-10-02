"""
set_en_preset.py — align the agent's English language preset with the base agent.

Why (2026-10-02): the widget now starts every session in English
(conversation_config_override.agent.language="en") because the base language is
"hi" (required for the multilingual flash_v2_5 voice) and Haiku answered English
shoppers in Hindi. Sessions in English use `language_presets.en`, which had drifted:
  - first_message: old "Hi, welcome to Goxfused! … AI shopping companion" text
  - soft-timeout filler: Hindi "मुझे देखने दो..." spoken to English shoppers
This copies the base first_message into the en preset and sets an English filler.
Nothing else in the preset or agent changes. Dry run by default.

Usage: python3 testing/latency/set_en_preset.py [--branch agtbrch_...]... [--main] [--apply]
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[2]
AGENT_ID = "agent_4901kwna71tve5nbyy85c8v20yre"
API = os.getenv("ELEVENLABS_API_BASE", "https://api.elevenlabs.io/v1").rstrip("/")
EN_FILLER = "One second."


def _key() -> str:
    for line in (REPO / "onboarding-service" / ".env").read_text().splitlines():
        if line.startswith("ELEVENLABS_API_KEY="):
            return line.split("=", 1)[1].strip().strip("\"'")
    sys.exit("ELEVENLABS_API_KEY not found")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--branch", action="append", default=[])
    ap.add_argument("--main", action="store_true", help="also update the Main branch")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    h = {"xi-api-key": _key(), "Content-Type": "application/json"}
    url = f"{API}/convai/agents/{AGENT_ID}"
    targets = ([None] if args.main else []) + args.branch
    for br in targets:
        params = {"branch_id": br} if br else {}
        cc = requests.get(url, headers=h, params=params, timeout=30).json()["conversation_config"]
        presets = copy.deepcopy(cc.get("language_presets") or {})
        en = presets.setdefault("en", {"overrides": {}})
        ov = en.setdefault("overrides", {}) or {}
        en["overrides"] = ov
        agent = ov.get("agent") or {}
        agent["first_message"] = cc["agent"]["first_message"]
        ov["agent"] = agent
        turn = ov.get("turn") or {}
        st = turn.get("soft_timeout_config") or {}
        st["message"] = EN_FILLER
        turn["soft_timeout_config"] = st
        ov["turn"] = turn
        en.pop("first_message_translation", None)  # stale translation of the old text
        label = br or "Main"
        if not args.apply:
            print(f"[dry-run] {label}: en.first_message → {agent['first_message'][:60]!r}, filler → {EN_FILLER!r}")
            continue
        r = requests.patch(url, headers=h, params=params, json={"conversation_config": {"language_presets": presets}}, timeout=30)
        if not r.ok:
            sys.exit(f"{label}: HTTP {r.status_code} {r.text[:300]}")
        after = requests.get(url, headers=h, params=params, timeout=30).json()["conversation_config"]
        en_after = after["language_presets"]["en"]["overrides"]
        print(f"{label}: en greeting={en_after['agent']['first_message'][:50]!r} filler={en_after['turn']['soft_timeout_config']['message']!r} "
              f"| other presets kept: {sorted(after['language_presets'])} | base language={after['agent']['language']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
