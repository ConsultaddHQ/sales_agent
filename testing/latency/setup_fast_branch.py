"""
setup_fast_branch.py — configure an ElevenLabs BRANCH for the Phase 2 "fast flow".

Fast flow: `search_products` and `get_product_details` become CLIENT tools run by
the widget (AvatarWidget.jsx). The widget calls our Mumbai API directly, paints the
carousel immediately, and returns a compact summary to the LLM. This removes:
  - the LLM re-typing every product into `update_products` (~2.5–3s/turn, measured
    2026-09-30 on conv_3001m3qepcw0fwa8tgpd802cm8j2),
  - per-product `update_carousel_main_view` round-trips (carousel follows the voice),
  - the ElevenLabs(US) → Mumbai webhook hop.

What this script does (idempotent; safe to re-run):
  1. Creates/updates two standalone client tools (ids cached in fast_branch_tools.json).
  2. Takes the MAIN branch's live prompt and rewrites only the tool-flow sentences.
     Every replacement is asserted, so a changed live prompt fails loudly instead
     of producing a half-edited prompt.
  3. PATCHes the target BRANCH only (?branch_id=...). Main is never modified.

Usage:
    python3 testing/latency/setup_fast_branch.py --branch-id agtbrch_... [--pre-tool-speech auto|force|off] [--dry-run]

Rollback: the branch has 0% traffic until deployed; to undo a rollout, set Main
back to 100% (deployments API / dashboard). Main's config is untouched.
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
TOOL_CACHE = Path(__file__).with_name("fast_branch_tools.json")

# Main tools that the fast flow replaces (by name). Everything else is kept.
REPLACED_TOOL_NAMES = {"search_products", "get_product_details", "update_products"}


def _key() -> str:
    if os.getenv("ELEVENLABS_API_KEY"):
        return os.environ["ELEVENLABS_API_KEY"]
    for line in (REPO / "onboarding-service" / ".env").read_text().splitlines():
        if line.startswith("ELEVENLABS_API_KEY="):
            return line.split("=", 1)[1].strip().strip("\"'")
    sys.exit("ELEVENLABS_API_KEY not found")


def search_tool(pre_tool_speech: str) -> dict:
    return {
        "type": "client",
        "name": "search_products",
        "description": (
            "Search the store's product catalog AND show the matching products on the shopper's "
            "screen in one step. ALWAYS call this before naming any product, price, variant or "
            "availability — even if you think you already know the answer from the store summary; the "
            "shopper can only see products this tool returns. Returns JSON: "
            "{count, products: [{index, id, name, price, about}]}. "
            "Expand vague queries: 'something for dry skin' → 'moisturiser dry skin', 'show me stuff' "
            "→ 'bestseller products', 'a gift' → 'gift set'. If count is 0, follow the No results rule. "
            "If the result starts with 'Error:', call show_search_error and apologise briefly."
        ),
        "expects_response": True,
        "response_timeout_secs": 10,
        "execution_mode": "immediate",
        "pre_tool_speech": pre_tool_speech,
        "tool_error_handling_mode": "auto",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The shopper's search query — product name, type, concern, or natural-language request.",
                }
            },
            "required": ["query"],
        },
    }


def details_tool() -> dict:
    return {
        "type": "client",
        "name": "get_product_details",
        "description": (
            "Fetch the FULL details of a specific product: ingredients, benefits, claims, certifications, "
            "comparisons, usage, variants, and the complete description. The 'about' text from "
            "search_products is only a short summary — call this tool for ANY product question beyond "
            "name/price, and answer only from what it returns. It also brings that product into focus on "
            "the shopper's screen automatically, so no update_carousel_main_view call is needed afterwards."
        ),
        "expects_response": True,
        "response_timeout_secs": 10,
        "execution_mode": "immediate",
        "pre_tool_speech": "auto",
        "tool_error_handling_mode": "auto",
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {
                    "type": "string",
                    "description": "The product's id from the search_products result.",
                }
            },
            "required": ["product_id"],
        },
    }


# (old, new) pairs applied to the Main prompt. Each `old` must appear exactly once.
PROMPT_EDITS = [
    (
        "The customer only sees products after update_products runs.",
        "search_products shows the results on the customer's screen automatically.",
    ),
    (
        "1. search_products\n2. update_products with the full returned products array — BEFORE saying any words about the results\n3. Give a SHORT spoken summary:",
        "1. search_products — this ALSO shows the results on the shopper's screen; there is no separate display step.\n2. Give a SHORT spoken summary from its result:",
    ),
    (
        "CRITICAL — the carousel must FOLLOW YOUR VOICE product by product: for EVERY product you mention in the summary, call update_carousel_main_view with that product's zero-based index immediately BEFORE saying its name, so the shopper is always looking at the product you're talking about. Go in array order (index 0 first, then 1, 2, ...): tool call → speak that product's name and price → next tool call → next product. Never name a product without focusing it first — the screen showing product A while you describe product B confuses the shopper.",
        "Go in result order (index 0 first, then 1, 2, ...) and say each product's name as it appears in the result — the carousel follows your voice and moves to each product when you say its name, so do NOT call update_carousel_main_view while walking through results.",
    ),
    (
        "call get_product_details for that specific product (and update_carousel_main_view to focus it), then share its specifics.",
        "call get_product_details for that specific product (it also focuses it on screen), then share its specifics.",
    ),
    (
        "Do not speak before step 1. NEVER speak between step 1 and step 2. The customer must see the carousel update on screen BEFORE hearing you describe what you found. This step is important.",
        "Never describe products before search_products returns — the shopper sees them on screen the moment it does. This step is important.",
    ),
    (
        "## search_products\nUse for all product discovery and browse intent.\n",
        "## search_products\nUse for all product discovery and browse intent. It searches AND displays the results on screen.\n",
    ),
    (
        "## update_products\nUse immediately after search_products.\nPass the complete products array from the result.\nThis is required for UI rendering.\n\n",
        "",
    ),
    (
        "The description you received from search_products is a TRUNCATED 200-character summary;",
        "The 'about' text you received from search_products is a short summary;",
    ),
    (
        "After the result arrives, call update_carousel_main_view with that product's zero-based index BEFORE speaking. This step is important.",
        "It also brings that product into focus on screen automatically — no update_carousel_main_view call is needed afterwards.",
    ),
    (
        "Use when: customer references a product by position (e.g. \"the second one\"). Also call this immediately after every get_product_details result. Pass zero-based index.",
        "Use ONLY when the customer references a product by position (e.g. \"the second one\") and you are NOT about to call get_product_details for it. Pass zero-based index.",
    ),
    (
        "CRITICAL — the product you SPEAK about must be the product SHOWN on screen: before describing any specific product in detail, call this tool with that product's index and check the product_name it returns. If the returned name is NOT the product you were about to describe, you have the wrong index — correct it and call again BEFORE speaking. Never describe product A while product B is focused on screen.",
        "The product you speak about in detail must be the one on screen: get_product_details focuses it automatically; otherwise call this tool first and check the product_name it returns.",
    ),
    (
        "- After a search_products result arrives, your very next action must be update_products. Do not speak between the tool result and the update_products call — the UI must update BEFORE the customer hears you describe products. This step is important.\n",
        "",
    ),
    (
        "- After a get_product_details result arrives, your very next action must be update_carousel_main_view with that product's zero-based index. Do not speak between the tool result and the carousel update. This step is important.\n",
        "",
    ),
    (
        "- Never describe product options before search_products + update_products.",
        "- Never describe product options before search_products returns. Any product request — "
        "\"what X do you have\", \"show me X\", \"do you have X\" — means call search_products FIRST, "
        "even when the Categories/Prices line already seems to answer it: the shopper sees nothing "
        "on screen until search_products runs. Reply in the language the shopper is using. This step is important.",
    ),
    (
        "call search_products + update_products as usual.",
        "call search_products as usual.",
    ),
]


# 2026-10-02 voice-test fixes (conv_4501m3ye0v…: Haiku answered English in Hindi;
# conv_6301m3ye4x…: GPT said "taking you to your cart now!" twice without calling
# go_to_cart, and answered a Hindi request in English).
PROMPT_EDITS += [
    (
        "English is the DEFAULT. Greet in English and stay in English unless the customer clearly speaks another language.",
        "English is the DEFAULT. Greet in English and stay in English unless the customer clearly speaks another language. "
        "Decide the reply language from the shopper's LAST message only: if its meaningful words are English, reply in English — "
        "never answer an English sentence in Hindi or Devanagari, even though the voice is configured for Hindi. "
        "If its meaningful words include Hindi/Hinglish, you MUST call language_detection with \"hi\" in that same turn and reply in Hinglish. This step is important.",
    ),
    (
        "Say a brief warm closing line FIRST (e.g. \"Great choice — taking you to your cart now!\"), THEN call go_to_cart. This step is important: calling this tool navigates away and ends the conversation, so the closing line must come first.",
        "Call go_to_cart FIRST, then say a brief warm closing line (e.g. \"Great choice — taking you to your cart now!\") in the SAME response — "
        "the screen waits for your closing line to finish before it moves to the cart. "
        "Never say you are taking them to the cart without calling go_to_cart — the words alone do nothing and the shopper stays stuck. This step is important.",
    ),
]


def rewrite_prompt(prompt: str) -> str:
    for old, new in PROMPT_EDITS:
        n = prompt.count(old)
        if n != 1:
            sys.exit(f"Prompt edit anchor found {n}x (expected 1) — live prompt changed?\n  anchor: {old[:120]!r}")
        prompt = prompt.replace(old, new)
    if "update_products" in prompt:
        sys.exit("Rewritten prompt still mentions update_products — refusing to apply")
    return prompt


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--branch-id", required=True)
    ap.add_argument("--pre-tool-speech", default="auto", choices=["auto", "force", "off"])
    ap.add_argument("--filler", default="off", choices=["off", "on"],
                    help="ElevenLabs soft-timeout filler lines ('Let me see'); off for the fast flow (2026-10-02 voice test)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    h = {"xi-api-key": _key(), "Content-Type": "application/json"}
    main_agent = requests.get(f"{API}/convai/agents/{AGENT_ID}", headers=h, timeout=30)
    main_agent.raise_for_status()
    main_prompt = main_agent.json()["conversation_config"]["agent"]["prompt"]
    new_prompt = rewrite_prompt(main_prompt["prompt"])

    # Keep every Main tool except the ones the fast flow replaces.
    kept_ids = []
    for tid in main_prompt.get("tool_ids") or []:
        t = requests.get(f"{API}/convai/tools/{tid}", headers=h, timeout=30).json()["tool_config"]
        if t["name"] not in REPLACED_TOOL_NAMES:
            kept_ids.append(tid)

    cache = json.loads(TOOL_CACHE.read_text()) if TOOL_CACHE.exists() else {}
    wanted = {"search_products": search_tool(args.pre_tool_speech), "get_product_details": details_tool()}
    if args.dry_run:
        print(f"[dry-run] would upsert tools {list(wanted)}; keep {len(kept_ids)} Main tools")
        print(f"[dry-run] prompt {len(main_prompt['prompt'])} → {len(new_prompt)} chars")
        return 0

    for name, cfg in wanted.items():
        if name in cache:
            r = requests.patch(f"{API}/convai/tools/{cache[name]}", headers=h, json={"tool_config": cfg}, timeout=30)
        else:
            r = requests.post(f"{API}/convai/tools", headers=h, json={"tool_config": cfg}, timeout=30)
        if not r.ok:
            sys.exit(f"tool {name}: HTTP {r.status_code} {r.text[:300]}")
        cache[name] = cache.get(name) or r.json()["id"]
        print(f"tool {name}: {cache[name]}")
    TOOL_CACHE.write_text(json.dumps(cache, indent=2) + "\n")

    soft = dict(main_agent.json()["conversation_config"]["turn"].get("soft_timeout_config") or {})
    soft["timeout_seconds"] = -1 if args.filler == "off" else 0.8
    body = {"conversation_config": {
        "agent": {"prompt": {
            "prompt": new_prompt,
            "tool_ids": [cache["search_products"], cache["get_product_details"], *kept_ids],
        }},
        "turn": {"soft_timeout_config": soft},
    }}
    r = requests.patch(f"{API}/convai/agents/{AGENT_ID}", headers=h, params={"branch_id": args.branch_id}, json=body, timeout=60)
    if not r.ok:
        sys.exit(f"branch PATCH: HTTP {r.status_code} {r.text[:400]}")

    check = requests.get(f"{API}/convai/agents/{AGENT_ID}", headers=h, params={"branch_id": args.branch_id}, timeout=30).json()
    bp = check["conversation_config"]["agent"]["prompt"]
    names = [requests.get(f"{API}/convai/tools/{t}", headers=h, timeout=30).json()["tool_config"]["name"] for t in bp["tool_ids"]]
    print("branch tools:", names)
    print("branch prompt has update_products:", "update_products" in bp["prompt"],
          "| filler timeout:", check["conversation_config"]["turn"]["soft_timeout_config"]["timeout_seconds"],
          "| llm:", bp.get("llm"))
    main_after = requests.get(f"{API}/convai/agents/{AGENT_ID}", headers=h, timeout=30).json()
    print("Main untouched:", main_after["conversation_config"]["agent"]["prompt"]["prompt"] == main_prompt["prompt"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
