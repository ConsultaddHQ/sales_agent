"""
benchmark_flows.py — measure real voice-turn latency against the live agent or a branch.

Runs real ElevenLabs conversations over the WebSocket API. A typed shopper message
stands in for speech (ASR time is excluded — identical across variants). Client tools
are answered exactly as the widget does, including the fast-flow client tools
(search_products / get_product_details hit our real API).

Per turn it records, relative to sending the shopper's message:
  first_audio_ms   first agent audio chunk (what the shopper first HEARS)
  first_text_ms    first agent text
  products_ms      products on screen (update_products call, or client search done)
  done_ms          last agent response of the turn
  tool_calls       client + server tool calls in the turn

Usage:
  python3 testing/latency/benchmark_flows.py --runs 5                     # Main
  python3 testing/latency/benchmark_flows.py --runs 5 --branch agtbrch_... # a branch
  (macOS python.org builds: prefix SSL_CERT_FILE=$(python3 -m certifi))

Each run is a real (short) conversation billed to the agent — keep --runs small.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

import requests
import websockets

AGENT_ID = "agent_4901kwna71tve5nbyy85c8v20yre"
STORE_ID = "9cec7cd0-9252-4aa2-985b-71c2a42018cb"
API_BASE = "https://api.teampop.com"
QUERIES = [
    "Show me a face wash for oily skin",
    "Do you have a moisturiser for dry skin?",
    "What lip balms do you have?",
]


def api(path: str, body: dict) -> dict:
    r = requests.post(f"{API_BASE}{path}", json={"store_id": STORE_ID, **body}, timeout=15)
    r.raise_for_status()
    return r.json()


async def run_once(query: str, branch: str | None, verbose: bool, followup: str | None = None) -> dict:
    url = f"wss://api.elevenlabs.io/v1/convai/conversation?agent_id={AGENT_ID}"
    if branch:
        url += f"&branch_id={branch}"
    res = {"query": query, "first_audio_ms": None, "first_text_ms": None, "products_ms": None,
           "done_ms": None, "tool_calls": [], "conversation_id": None, "error": None,
           "followup_first_text_ms": None, "followup_tools": []}
    fu_sent_at = None
    shown: list = []
    async with websockets.connect(url, max_size=None) as ws:
        await ws.send(json.dumps({"type": "conversation_initiation_client_data",
                                  "dynamic_variables": {"session_context": ""}}))
        sent_at = None
        greeted = False
        last_audio = 0.0   # wall time of the latest audio chunk (greeting tail must finish first)
        last_event = time.perf_counter()
        deadline = time.time() + 45
        ms = lambda: int((time.perf_counter() - sent_at) * 1000) if sent_at else None

        async def reply(call_id: str, result: str, is_error: bool = False):
            await ws.send(json.dumps({"type": "client_tool_result", "tool_call_id": call_id,
                                      "result": result, "is_error": is_error}))

        while time.time() < deadline:
            waiting_to_send = greeted and sent_at is None
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=0.3 if waiting_to_send else (6 if res["products_ms"] else 15))
            except asyncio.TimeoutError:
                if not waiting_to_send:
                    break  # turn finished (no events for a while)
                raw = None
            if waiting_to_send and time.perf_counter() - last_audio > 1.5:
                # Greeting audio has gone quiet — now send, so "first audio" is the reply's.
                sent_at = time.perf_counter()
                await ws.send(json.dumps({"type": "user_message", "text": query}))
            if raw is None:
                continue
            ev = json.loads(raw)
            t = ev.get("type")
            last_event = time.perf_counter()
            if t == "conversation_initiation_metadata":
                res["conversation_id"] = ev["conversation_initiation_metadata_event"]["conversation_id"]
            elif t == "ping":
                await ws.send(json.dumps({"type": "pong", "event_id": ev["ping_event"]["event_id"]}))
            elif t == "audio":
                last_audio = time.perf_counter()
                if sent_at and res["first_audio_ms"] is None:
                    res["first_audio_ms"] = ms()
            elif t == "agent_response":
                text = ev["agent_response_event"]["agent_response"]
                if not greeted:
                    greeted = True
                    last_audio = max(last_audio, time.perf_counter())
                    continue
                if fu_sent_at:
                    if res["followup_first_text_ms"] is None:
                        res["followup_first_text_ms"] = int((time.perf_counter() - fu_sent_at) * 1000)
                    if verbose:
                        print(f"    [follow-up +{res['followup_first_text_ms']}ms] AGENT: {text[:110]}")
                    continue
                if res["first_text_ms"] is None:
                    res["first_text_ms"] = ms()
                res["done_ms"] = ms()
                if verbose:
                    print(f"    +{ms()}ms AGENT: {text[:110]}")
                if followup and res["products_ms"] and not fu_sent_at:
                    await asyncio.sleep(2.5)  # let the summary finish streaming
                    fu_sent_at = time.perf_counter()
                    await ws.send(json.dumps({"type": "user_message", "text": followup}))
            elif t == "agent_tool_response" and sent_at:
                r = ev["agent_tool_response"]
                if r.get("tool_type") != "client":
                    res["tool_calls"].append(f"{r.get('tool_name')}{'!' if r.get('is_error') else ''}@{ms()}")
            elif t == "client_tool_call":
                c = ev["client_tool_call"]
                name, params, cid = c["tool_name"], c.get("parameters") or {}, c["tool_call_id"]
                (res["followup_tools"] if fu_sent_at else res["tool_calls"]).append(f"{name}@{ms()}")
                try:
                    if name == "update_products":
                        shown = params.get("products") or []
                        res["products_ms"] = res["products_ms"] or ms()
                        await reply(cid, "UI updated successfully")
                    elif name == "search_products":  # fast flow — same contract as AvatarWidget.jsx
                        data = await asyncio.to_thread(api, "/search", {"query": params.get("query", ""),
                                                                        "conversation_id": res["conversation_id"]})
                        shown = data.get("products") or []
                        if shown:
                            res["products_ms"] = res["products_ms"] or ms()
                        await reply(cid, json.dumps({
                            "count": len(shown),
                            "note": "Already shown on screen; the carousel follows your voice when you say each product's name.",
                            "products": [{"index": i, "id": str(p["id"]), "name": p["name"], "price": p.get("price"),
                                          "about": (p.get("description") or "")[:110] or None} for i, p in enumerate(shown)],
                        }))
                    elif name == "get_product_details":
                        data = await asyncio.to_thread(api, "/product-details", {"product_id": params.get("product_id", ""),
                                                                                 "conversation_id": res["conversation_id"]})
                        await reply(cid, json.dumps(data))
                    elif name == "update_carousel_main_view":
                        i = int(params.get("index", 0))
                        p = shown[i] if 0 <= i < len(shown) else None
                        await reply(cid, json.dumps({"product_name": p["name"], "product_id": str(p["id"])}) if p else "ok")
                    else:
                        await reply(cid, "ok")
                except Exception as e:  # report like the widget would
                    res["error"] = repr(e)
                    await reply(cid, f"Error: {e}", True)
    return res


def summarize(rows: list, label: str) -> dict:
    def med(k):
        vals = [r[k] for r in rows if r[k] is not None]
        return int(statistics.median(vals)) if vals else None
    out = {k: med(k) for k in ("first_audio_ms", "first_text_ms", "products_ms", "done_ms", "followup_first_text_ms")}
    out["products_missing"] = sum(1 for r in rows if r["products_ms"] is None)
    out["runs"] = len(rows)
    print(f"\n== {label}: median of {len(rows)} → {json.dumps(out)}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--branch")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--label", default=None)
    ap.add_argument("--out", default=None, help="append JSON results to this file")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--query", action="append", help="shopper message(s) to cycle through (default: built-in set)")
    ap.add_argument("--followup", help="second shopper message sent after products are shown (tests details flow)")
    args = ap.parse_args()
    label = args.label or (args.branch or "main")
    queries = args.query or QUERIES
    rows = []
    for i in range(args.runs):
        q = queries[i % len(queries)]
        r = asyncio.run(run_once(q, args.branch, args.verbose, args.followup))
        rows.append(r)
        print(f"[{label} {i+1}/{args.runs}] audio={r['first_audio_ms']} text={r['first_text_ms']} "
              f"products={r['products_ms']} done={r['done_ms']} tools={r['tool_calls']} "
              + (f"followup_text={r['followup_first_text_ms']} followup_tools={r['followup_tools']} " if args.followup else "")
              + f"{r['conversation_id']}"
              + (f" ERROR={r['error']}" if r["error"] else ""))
    summary = summarize(rows, label)
    if args.out:
        with open(args.out, "a") as f:
            f.write(json.dumps({"label": label, "ts": time.time(), "summary": summary, "runs": rows}) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
