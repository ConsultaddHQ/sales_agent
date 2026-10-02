"""
scenario_test.py — scripted multi-turn regression test against the live agent / a branch.

Replays the 2026-10-02 voice-test flow and checks behaviour per turn (pass/fail):
  1. English product request      → search_products called, reply in English
  2. Hinglish follow-up for details → get_product_details called, reply NOT English-only
                                      (language_detection 'hi' or Hindi/Hinglish words)
  3. "Add this one to the cart"     → add_to_cart called
  4. "Checkout"                     → go_to_cart called (not just "taking you to your cart")
Also records per-turn latency (first agent audio / text after the shopper's message).

Client tools are answered like the widget (search/details hit the real API).
Usage:
  python3 testing/latency/scenario_test.py --branch agtbrch_... --runs 2
  (macOS python.org builds: SSL_CERT_FILE=$(python3 -m certifi))
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time

import requests
import websockets

AGENT_ID = "agent_4901kwna71tve5nbyy85c8v20yre"
STORE_ID = "9cec7cd0-9252-4aa2-985b-71c2a42018cb"
API_BASE = "https://api.teampop.com"

DEVANAGARI = re.compile(r"[ऀ-ॿ]")
HINGLISH = re.compile(r"\b(hai|hain|aap|aapki|aapke|ke liye|mein|yeh|ye|wala|wali|bahut|accha|acha|kar|karo|dijiye|chahiye|nahi)\b", re.I)

SCENARIO = [
    ("Show me a face wash for oily skin", "english_search"),
    ("Mujhe second wale ki details chahiye", "hinglish_details"),
    ("Add this one to the cart", "add_to_cart"),
    ("Checkout", "checkout"),
]


def api(path: str, body: dict) -> dict:
    r = requests.post(f"{API_BASE}{path}", json={"store_id": STORE_ID, **body}, timeout=15)
    r.raise_for_status()
    return r.json()


def judge(kind: str, turn: dict) -> tuple[bool, str]:
    tools, text = turn["tools"], turn["text"]
    if kind == "english_search":
        ok = "search_products" in tools and not DEVANAGARI.search(text)
        return ok, "searched + English" if ok else f"tools={tools} devanagari={bool(DEVANAGARI.search(text))}"
    if kind == "hinglish_details":
        hindi = "language_detection" in tools or DEVANAGARI.search(text) or HINGLISH.search(text)
        ok = "get_product_details" in tools and bool(hindi)
        return ok, "details + Hindi/Hinglish" if ok else f"tools={tools} hindi_reply={bool(hindi)}"
    if kind == "add_to_cart":
        ok = "add_to_cart" in tools
        return ok, "add_to_cart called" if ok else f"tools={tools}"
    if kind == "checkout":
        ok = "go_to_cart" in tools
        return ok, "go_to_cart called" if ok else f"tools={tools} (said: {text[:60]!r})"
    return False, "unknown"


async def run(branch: str | None, verbose: bool, start_lang: str | None = None) -> dict:
    url = f"wss://api.elevenlabs.io/v1/convai/conversation?agent_id={AGENT_ID}" + (f"&branch_id={branch}" if branch else "")
    turns, shown, cid = [], [], None
    cur = None
    async with websockets.connect(url, max_size=None) as ws:
        init = {"type": "conversation_initiation_client_data", "dynamic_variables": {"session_context": ""}}
        if start_lang:  # same override the widget sends (AvatarWidget.jsx startSession)
            init["conversation_config_override"] = {"agent": {"language": start_lang}}
        await ws.send(json.dumps(init))
        step, last_activity, greeted = 0, time.perf_counter(), False
        deadline = time.time() + 120

        async def reply(call_id, result):
            await ws.send(json.dumps({"type": "client_tool_result", "tool_call_id": call_id,
                                      "result": result, "is_error": False}))

        while time.time() < deadline and step <= len(SCENARIO):
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=0.3)
            except asyncio.TimeoutError:
                raw = None
            except websockets.ConnectionClosed:
                break
            now = time.perf_counter()
            if raw:
                ev = json.loads(raw)
                t = ev.get("type")
                if t == "conversation_initiation_metadata":
                    cid = ev["conversation_initiation_metadata_event"]["conversation_id"]
                elif t == "ping":
                    await ws.send(json.dumps({"type": "pong", "event_id": ev["ping_event"]["event_id"]}))
                elif t == "audio":
                    last_activity = now
                    if cur and cur["first_audio_ms"] is None:
                        cur["first_audio_ms"] = int((now - cur["sent"]) * 1000)
                elif t == "agent_response":
                    last_activity = now
                    greeted = True
                    text = ev["agent_response_event"]["agent_response"]
                    if cur:
                        cur["text"] += " " + text
                        if cur["first_text_ms"] is None:
                            cur["first_text_ms"] = int((now - cur["sent"]) * 1000)
                    if verbose and cur:
                        print(f"      AGENT: {text[:120]}")
                elif t == "agent_tool_response" and cur:
                    last_activity = now
                    name = ev["agent_tool_response"].get("tool_name")
                    if name not in cur["tools"]:
                        cur["tools"].append(name)
                elif t == "client_tool_call":
                    last_activity = now
                    c = ev["client_tool_call"]
                    name, params = c["tool_name"], c.get("parameters") or {}
                    if cur and name not in cur["tools"]:
                        cur["tools"].append(name)
                    if name == "search_products":
                        data = await asyncio.to_thread(api, "/search", {"query": params.get("query", ""), "conversation_id": cid})
                        shown = data.get("products") or []
                        await reply(c["tool_call_id"], json.dumps({"count": len(shown), "products": [
                            {"index": i, "id": str(p["id"]), "name": p["name"], "price": p.get("price"),
                             "about": (p.get("description") or "")[:110]} for i, p in enumerate(shown)]}))
                    elif name == "get_product_details":
                        data = await asyncio.to_thread(api, "/product-details", {"product_id": params.get("product_id", ""), "conversation_id": cid})
                        await reply(c["tool_call_id"], json.dumps(data))
                    elif name == "update_products":
                        shown = params.get("products") or []
                        await reply(c["tool_call_id"], "UI updated successfully")
                    elif name == "update_carousel_main_view":
                        i = int(params.get("index", 0))
                        p = shown[i] if 0 <= i < len(shown) else None
                        await reply(c["tool_call_id"], json.dumps({"product_name": p["name"], "product_id": str(p["id"])}) if p else "ok")
                    elif name == "add_to_cart":
                        p = next((x for x in shown if str(x["id"]) == str(params.get("product_id"))), None)
                        await reply(c["tool_call_id"], f"Added {p['name'] if p else 'item'} to cart!")
                    else:
                        await reply(c["tool_call_id"], "ok")
            # Agent idle (no audio/text/tool for 2.5s) → judge current turn, send the next message.
            if greeted and now - last_activity > 2.5:
                if cur:
                    cur["ok"], cur["why"] = judge(cur["kind"], cur)
                    turns.append(cur)
                    cur = None
                if step == len(SCENARIO):
                    break
                msg, kind = SCENARIO[step]
                step += 1
                cur = {"msg": msg, "kind": kind, "sent": time.perf_counter(), "tools": [], "text": "",
                       "first_audio_ms": None, "first_text_ms": None}
                if verbose:
                    print(f"    USER: {msg}")
                await ws.send(json.dumps({"type": "user_message", "text": msg}))
                last_activity = time.perf_counter()
        if cur:  # e.g. go_to_cart tool + socket closed
            cur["ok"], cur["why"] = judge(cur["kind"], cur)
            turns.append(cur)
    return {"conversation_id": cid, "turns": turns}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--branch")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--label", default=None)
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--start-lang", help="session language override, e.g. en (what the widget sends)")
    args = ap.parse_args()
    label = args.label or args.branch or "main"
    passed = total = 0
    results = []
    for i in range(args.runs):
        r = asyncio.run(run(args.branch, args.verbose, args.start_lang))
        results.append(r)
        print(f"[{label} run {i+1}] {r['conversation_id']}")
        for t in r["turns"]:
            total += 1
            passed += t["ok"]
            print(f"   {'PASS' if t['ok'] else 'FAIL'} {t['kind']:<17} audio={t['first_audio_ms']} text={t['first_text_ms']} — {t['why']}")
    print(f"== {label}: {passed}/{total} checks passed")
    if args.out:
        with open(args.out, "a") as f:
            f.write(json.dumps({"label": label, "passed": passed, "total": total, "runs": results}) + "\n")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
