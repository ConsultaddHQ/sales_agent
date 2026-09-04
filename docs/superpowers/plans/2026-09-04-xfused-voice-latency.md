# Xfused Voice-Agent Latency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Xfused voice cycle feel conversational for India shoppers: deploy the already-coded cache/tracking stack, show “heard you” immediately, keep products aligned with speech, surface search failures in the orb UI, and measure every turn against ship-gate B.

**Architecture:** Keep Lightsail Mumbai + local embed/rerank + existing ElevenLabs agent. Phase 0 is a human Lightsail deploy of code already on `release/xfused-pilot`. Phase 1 is widget + agent-tool + search error telemetry. Extra topology/eagerness levers are STOP-gated after `/api/latency-summary` exists. Phase 2 GPT-Pet UI is out of this plan.

**Tech Stack:** React Shadow DOM widget (`AvatarWidget.jsx`, `@elevenlabs/react`), FastAPI onboarding + search, ElevenLabs Conversational AI tools, Caddy, Supabase `turn_latency` / `search_latency`, Node `node:test`, Python `unittest`.

## Global Constraints

- India-only; do not move Supabase or Lightsail overseas in this plan.
- Embedding stays `all-MiniLM-L6-v2` / 384-d; do not change `hybrid_search_products`.
- Voice ack = ElevenLabs `soft_timeout` only (`timeout_seconds: 1.2`, `use_llm_generated_message: false`). No LLM “searching…” before tools.
- UI ack = THINKING on every turn (search and non-search).
- Ship gate B: first useful feedback p95 ≤ 1.2s; User→Products p95 ≤ 3.5–4s; dead-air < 10%; 1002 < 5%; `update_products` miss < 10%. Stretch A is reported, not required.
- Live agent `agent_4901kwna71tve5nbyy85c8v20yre` / store `9cec7cd0-9252-4aa2-985b-71c2a42018cb`. Do not PATCH `language` back to `en`; keep `hi` + `eleven_flash_v2_5`.
- `show_search_error` is xfused `PROMPT_CLAUDE` + shared `_get_tool_config` only — do not port GPT/Gemini/Qwen/GLM templates.
- Never commit `.env` or secrets.
- Bump `LATENCY_CONFIG_VERSION` / `SEARCH_CONFIG_VERSION` on every latency-affecting deploy.
- Phase 2 orb replacement is forbidden in this plan.

## File structure

| File | Responsibility |
|------|----------------|
| `www.teampop/frontend/src/visualState.js` | Pure visual-state + status copy + timing constants (`THINKING_SILENCE_MS`, `SEARCH_FAIL_FALLBACK_MS`) |
| `www.teampop/frontend/src/visualState.test.js` | `node:test` coverage for SEARCH_FAIL vs ERROR vs THINKING |
| `www.teampop/frontend/src/components/AvatarWidget.jsx` | THINKING on transcript, `show_search_error` client tool, 8s fallback, per-cycle latency POST, OrbDock pill |
| `www.teampop/frontend/src/styles/AvatarWidget.css` | SEARCH_FAIL orb glow |
| `onboarding-service/elevenlabs_agent.py` | Register `show_search_error`; PROMPT_CLAUDE error + no-LLM-filler rules; `_verify_agent` expected set |
| `onboarding-service/tests/test_show_search_error_tool.py` | Tool contract tests (no network) |
| `search-service/main.py` | Persist `search_latency` on HTTPException after a real search attempt |
| `search-service/tests/test_search_error_latency.py` | Persist-on-error tests with mocks |
| `testing/manual_test_checklist.md` | Phase 0 pre-flight + SEARCH_FAIL + cache-hit scenarios |
| `deploy/Caddyfile` | Task 7 only (STOP-gated) |
| `testing/latency/set_turn_eagerness.py` | Task 8 only (copy-agent experiment) |

Do not split `AvatarWidget.jsx` beyond extracting `visualState.js`. Do not add vitest.

---

### Task 1: Extract visual-state helpers and add SEARCH_FAIL

**Files:**
- Create: `www.teampop/frontend/src/visualState.js`
- Create: `www.teampop/frontend/src/visualState.test.js`
- Modify: `www.teampop/frontend/src/components/AvatarWidget.jsx` (remove inlined `getVisualState` / `getStatusLabel` / `CONNECTING_MESSAGES` / `CONNECTING_MESSAGE_INTERVAL_MS`; import from `visualState.js`)
- Modify: `www.teampop/frontend/package.json` (add `"test": "node --test src/visualState.test.js"`)

**Interfaces:**
- Consumes: none
- Produces: `getVisualState({ status, interactionMode, isPressActive, vadSubState, searchFailed })` → string token; `getStatusLabel(visualState, connectingMessageIndex)`; `THINKING_SILENCE_MS = 150`; `SEARCH_FAIL_FALLBACK_MS = 8000`; `CONNECTING_MESSAGES`; `CONNECTING_MESSAGE_INTERVAL_MS = 1500`

- [ ] **Step 1: Write the failing test**

Create `www.teampop/frontend/src/visualState.test.js`:

```javascript
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  getVisualState,
  getStatusLabel,
  THINKING_SILENCE_MS,
  SEARCH_FAIL_FALLBACK_MS,
} from "./visualState.js";

describe("getVisualState", () => {
  it("returns SEARCH_FAIL when connected VAD and searchFailed, even if THINKING", () => {
    assert.equal(
      getVisualState({
        status: "connected",
        interactionMode: "vad",
        isPressActive: false,
        vadSubState: "THINKING",
        searchFailed: true,
      }),
      "SEARCH_FAIL",
    );
  });

  it("lets AGENT_SPEAKING override SEARCH_FAIL so the apology is visible", () => {
    assert.equal(
      getVisualState({
        status: "connected",
        interactionMode: "vad",
        isPressActive: false,
        vadSubState: "AGENT_SPEAKING",
        searchFailed: true,
      }),
      "AGENT_SPEAKING",
    );
  });

  it("keeps connection ERROR distinct from SEARCH_FAIL", () => {
    assert.equal(
      getVisualState({
        status: "error",
        interactionMode: "vad",
        isPressActive: false,
        vadSubState: "LISTENING",
        searchFailed: true,
      }),
      "ERROR",
    );
  });

  it("returns THINKING when connected and not failed", () => {
    assert.equal(
      getVisualState({
        status: "connected",
        interactionMode: "vad",
        isPressActive: false,
        vadSubState: "THINKING",
        searchFailed: false,
      }),
      "THINKING",
    );
  });
});

describe("getStatusLabel", () => {
  it("uses dedicated copy for SEARCH_FAIL", () => {
    assert.equal(getStatusLabel("SEARCH_FAIL"), "Couldn't search — try again");
  });
});

describe("timing constants", () => {
  it("cuts silence debounce to 150ms and fallback to cascade 8s", () => {
    assert.equal(THINKING_SILENCE_MS, 150);
    assert.equal(SEARCH_FAIL_FALLBACK_MS, 8000);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd www.teampop/frontend && node --test src/visualState.test.js`

Expected: FAIL with `Cannot find module './visualState.js'` (or ERR_MODULE_NOT_FOUND).

- [ ] **Step 3: Write `visualState.js` and switch AvatarWidget imports**

Create `www.teampop/frontend/src/visualState.js`:

```javascript
export const CONNECTING_MESSAGES = [
  "Connecting...",
  "Setting up your assistant...",
  "Almost ready...",
];
export const CONNECTING_MESSAGE_INTERVAL_MS = 1500;
export const THINKING_SILENCE_MS = 150;
export const SEARCH_FAIL_FALLBACK_MS = 8000;

export function getVisualState({
  status,
  interactionMode,
  isPressActive,
  vadSubState,
  searchFailed = false,
}) {
  if (status === "connecting") return "CONNECTING";
  if (status === "error") return "ERROR";

  if (status === "connected") {
    if (interactionMode === "ptt") {
      if (isPressActive) return "PTT_HOLDING";
      if (searchFailed) return "SEARCH_FAIL";
      return "PTT_MUTED_CONNECTED";
    }
    if (vadSubState === "AGENT_SPEAKING") return "AGENT_SPEAKING";
    if (searchFailed) return "SEARCH_FAIL";
    return vadSubState || "LISTENING";
  }

  return interactionMode === "ptt" ? "PTT_READY" : "IDLE";
}

export function getStatusLabel(visualState, connectingMessageIndex = 0) {
  switch (visualState) {
    case "IDLE":
      return "Talk to AI";
    case "CONNECTING":
      return CONNECTING_MESSAGES[connectingMessageIndex % CONNECTING_MESSAGES.length];
    case "LISTENING":
      return "Listening...";
    case "THINKING":
      return "Thinking...";
    case "AGENT_SPEAKING":
      return "Speaking...";
    case "SEARCH_FAIL":
      return "Couldn't search — try again";
    case "PTT_READY":
      return "Hold to speak";
    case "PTT_MUTED_CONNECTED":
      return "Hold to talk";
    case "PTT_HOLDING":
      return "Listening";
    case "ERROR":
      return "Retry";
    default:
      return "";
  }
}
```

In `AvatarWidget.jsx`, delete the inlined `getVisualState`, `getStatusLabel`, `CONNECTING_MESSAGES`, and `CONNECTING_MESSAGE_INTERVAL_MS`. Add at the top of the file with the other imports:

```javascript
import {
  CONNECTING_MESSAGES,
  CONNECTING_MESSAGE_INTERVAL_MS,
  getStatusLabel,
  getVisualState,
  SEARCH_FAIL_FALLBACK_MS,
  THINKING_SILENCE_MS,
} from "../visualState.js";
```

Update the `getVisualState({...})` call site to pass `searchFailed: false` for now (Task 2 wires the flag):

```javascript
  const visualState = getVisualState({
    status: conversation.status,
    interactionMode,
    isPressActive: ptt.isPressActiveRef.current,
    vadSubState,
    searchFailed: false,
  });
```

Add to `package.json` scripts: `"test": "node --test src/visualState.test.js"`.

- [ ] **Step 4: Run tests and widget import check**

Run: `cd www.teampop/frontend && node --test src/visualState.test.js`

Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add www.teampop/frontend/src/visualState.js www.teampop/frontend/src/visualState.test.js www.teampop/frontend/src/components/AvatarWidget.jsx www.teampop/frontend/package.json
git commit -m "feat(widget): extract visual state and add SEARCH_FAIL token"
```

---

### Task 2: Heard-you THINKING, SEARCH_FAIL UI, and per-turn latency POST

**Files:**
- Modify: `www.teampop/frontend/src/components/AvatarWidget.jsx`
- Modify: `www.teampop/frontend/src/styles/AvatarWidget.css`
- Test: `www.teampop/frontend/src/visualState.test.js` (already covers labels; no new file)

**Interfaces:**
- Consumes: `getVisualState`, `THINKING_SILENCE_MS`, `SEARCH_FAIL_FALLBACK_MS` from Task 1
- Produces: client tool handler `show_search_error`; `searchFailed` React state; `_submitTurnLatency()` posting `{ agent_id, conversation_id, cycle, latency_first_ai_ms, latency_products_ms }` (products_ms omitted/`null` when `update_products` did not fire)

- [ ] **Step 1: Write a failing assertion for the 500ms debounce still in the widget**

Add to `www.teampop/frontend/src/visualState.test.js`:

```javascript
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

describe("AvatarWidget wiring", () => {
  const widgetPath = path.join(path.dirname(fileURLToPath(import.meta.url)), "components/AvatarWidget.jsx");
  const src = fs.readFileSync(widgetPath, "utf8");

  it("uses THINKING_SILENCE_MS instead of a hardcoded 500ms thinking delay", () => {
    assert.equal(src.includes("}, 500);"), false);
    assert.equal(src.includes("THINKING_SILENCE_MS"), true);
  });

  it("registers show_search_error client tool", () => {
    assert.equal(src.includes('useConversationClientTool("show_search_error"'), true);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd www.teampop/frontend && node --test src/visualState.test.js`

Expected: FAIL on the 500ms and/or `show_search_error` assertions.

- [ ] **Step 3: Implement widget wiring**

**A. State.** Next to `vadSubState` add:

```javascript
  const [searchFailed, setSearchFailed] = useState(false);
  const searchFailTimerRef = useRef(null);
```

Pass `searchFailed` into `getVisualState`.

**B. Clear SEARCH_FAIL when the user starts speaking again.** In the rAF loop, when `smoothedIn > INPUT_THRESHOLD` (existing LISTENING branch), also `setSearchFailed(false)` and clear `searchFailTimerRef`.

**C. Immediate THINKING on user transcript.** In `onMessage`, when `source === "user" && text`, after `_startLatencyTimer(text)`:

```javascript
        if (thinkingTimerRef.current) {
          clearTimeout(thinkingTimerRef.current);
          thinkingTimerRef.current = null;
        }
        vadSubStateRef.current = "THINKING";
        setVadSubState("THINKING");
        if (searchFailTimerRef.current) clearTimeout(searchFailTimerRef.current);
        searchFailTimerRef.current = setTimeout(() => {
          searchFailTimerRef.current = null;
          if (!agentIsSpeakingRef.current && !latencyRef.current.productsAt) {
            setSearchFailed(true);
          }
        }, SEARCH_FAIL_FALLBACK_MS);
```

**D. Silence debounce 500 → constant.** In the rAF `setTimeout(..., 500)` change to `THINKING_SILENCE_MS`.

**E. Clear fallback when products arrive or agent speaks.** In `_markProductsArrived`, clear `searchFailTimerRef` and `setSearchFailed(false)`. In the existing `agentIsSpeaking` effect, when speaking starts, clear `searchFailTimerRef` (do not clear `searchFailed` — apology speech uses AGENT_SPEAKING override; after speech, SEARCH_FAIL remains until next LISTENING).

**F. Client tool.** After the `update_products` tool:

```javascript
  useConversationClientTool("show_search_error", () => {
    if (searchFailTimerRef.current) {
      clearTimeout(searchFailTimerRef.current);
      searchFailTimerRef.current = null;
    }
    setSearchFailed(true);
    setAgentSubtitle("Couldn't search — try again");
    if (subtitleTimerRef.current) clearTimeout(subtitleTimerRef.current);
    subtitleTimerRef.current = setTimeout(() => setAgentSubtitle(""), 3000);
    return "search error shown";
  });
```

**G. Per-turn POST on every cycle, including non-search.** Extract from `_markProductsArrived`:

```javascript
  function _submitTurnLatency(firstAiMs, productsMs) {
    const lc = latencyRef.current;
    const apiBase = window.__TEAM_POP_API_URL__ || "";
    fetch(`${apiBase}/api/turn-latency`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        agent_id: agentId,
        conversation_id: conversationIdRef.current,
        cycle: lc.cycle,
        latency_first_ai_ms: firstAiMs,
        latency_products_ms: productsMs,
      }),
    }).catch((e) => console.warn("[latency] Turn sample submission failed (non-blocking):", e));
  }
```

Call `_submitTurnLatency(ms, null)` at the end of `_markFirstAi` (every turn). Keep the existing call from `_markProductsArrived` as `_submitTurnLatency(firstAiMs, totalMs)` so search turns get a second row with `latency_products_ms` set. `_latency_stats` already drops `null` products values, so User→Products p95 is not polluted.

**H. OrbDock pill.** Add to `PILL_STYLES`:

```javascript
    SEARCH_FAIL: "bg-rose-500/20 text-rose-400 border-rose-500/30 shadow-[0_0_10px_rgba(244,63,94,0.2)]",
```

**I. PanelSessionScreen.** After the CONNECTING branch, before the default “I'm listening” block:

```javascript
  if (visualState === "SEARCH_FAIL") {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center bg-zinc-900 pointer-events-auto pt-16">
        <div className="panel-session-orb panel-session-orb--live mb-8" aria-hidden="true" />
        <h2 className="text-xl font-bold text-rose-300 mb-3 tracking-wide">Couldn't search — try again</h2>
        <p className="text-gray-300 text-sm max-w-[260px] mx-auto leading-relaxed">
          I heard you, but product search failed. Say what you want again.
        </p>
      </div>
    );
  }
```

This panel only shows when there are no products (existing ternary). SEARCH_FAIL with an old carousel still uses the pill.

**J. CSS.** In `AvatarWidget.css` after `.orb-wrapper.THINKING`:

```css
.orb-wrapper.SEARCH_FAIL .orb-core {
  animation: searchFailPulse 0.9s ease-in-out infinite alternate;
}
@keyframes searchFailPulse {
  from { filter: drop-shadow(0 0 6px rgba(244, 63, 94, 0.45)); }
  to   { filter: drop-shadow(0 0 18px rgba(244, 63, 94, 0.85)); }
}
```

In the reduced-motion block next to the other `.orb-wrapper.*` lines add:

```css
  .orb-wrapper.SEARCH_FAIL .orb-core { animation: none; filter: drop-shadow(0 0 14px rgba(244,63,94,0.55)); }
```

- [ ] **Step 4: Run tests and widget build**

Run:

```bash
cd www.teampop/frontend && node --test src/visualState.test.js && npm run build
```

Expected: tests PASS; Vite build succeeds (IIFE `dist/widget.js`).

- [ ] **Step 5: Commit**

```bash
git add www.teampop/frontend/src/components/AvatarWidget.jsx www.teampop/frontend/src/styles/AvatarWidget.css www.teampop/frontend/src/visualState.test.js
git commit -m "feat(widget): instant THINKING, SEARCH_FAIL UI, per-turn latency POST"
```

---

### Task 3: Register `show_search_error` on the ElevenLabs agent (PROMPT_CLAUDE)

**Files:**
- Modify: `onboarding-service/elevenlabs_agent.py` (`_get_tool_config` after `update_products` block ~line 748; `PROMPT_CLAUDE` speaking-discipline + `# Error handling`; `_verify_agent` `expected_tool_names` ~line 1016)
- Create: `onboarding-service/tests/__init__.py` (empty)
- Create: `onboarding-service/tests/test_show_search_error_tool.py`

**Interfaces:**
- Consumes: existing `_get_tool_config(search_api_url, store_id) -> List[Dict]`
- Produces: client tool dict `name="show_search_error"`, `type="client"`, `expects_response=False`; `PROMPT_CLAUDE` must contain `show_search_error`

- [ ] **Step 1: Write the failing test**

Create empty `onboarding-service/tests/__init__.py`. Create `onboarding-service/tests/test_show_search_error_tool.py`:

```python
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "onboarding-service"))
os.environ.setdefault("ELEVENLABS_API_KEY", "test-key")

from elevenlabs_agent import PROMPT_CLAUDE, ElevenLabsAgentCreator  # noqa: E402


class ShowSearchErrorToolTests(unittest.TestCase):
    def setUp(self):
        self.creator = ElevenLabsAgentCreator(api_key="test-key")
        self.tools = self.creator._get_tool_config(
            "https://api.example.com", "9cec7cd0-9252-4aa2-985b-71c2a42018cb"
        )
        self.by_name = {t["name"]: t for t in self.tools}

    def test_show_search_error_is_client_tool_without_response(self):
        tool = self.by_name["show_search_error"]
        self.assertEqual(tool["type"], "client")
        self.assertFalse(tool["expects_response"])
        self.assertEqual(tool["execution_mode"], "immediate")

    def test_prompt_claude_calls_show_search_error_only_on_tool_failure(self):
        self.assertIn("show_search_error", PROMPT_CLAUDE)
        self.assertIn("NOT when the catalog is empty", PROMPT_CLAUDE)
        self.assertNotIn(
            'The ONLY allowed process phrase is one short filler before the very first search ("Let me check that.")',
            PROMPT_CLAUDE,
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /workspace && python3 -m unittest onboarding-service.tests.test_show_search_error_tool -v`

If that import path fails, run:

```bash
cd /workspace/onboarding-service && python3 -m unittest tests.test_show_search_error_tool -v
```

Expected: FAIL (`KeyError: 'show_search_error'` and/or assertion on PROMPT_CLAUDE).

- [ ] **Step 3: Implement tool + prompt**

Insert this dict in `_get_tool_config` immediately after the `update_products` client-tool dict (before `update_carousel_main_view`):

```python
            {
                "type": "client",
                "name": "show_search_error",
                "description": (
                    "Call immediately when search_products returns a tool error "
                    "(HTTP 5xx, timeout, or overload). Do NOT call when search "
                    "returns HTTP 200 with an empty products list. This updates "
                    "the shopper UI to a search-failed state."
                ),
                "expects_response": False,
                "execution_mode": "immediate",
                "tool_error_handling_mode": "auto",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
```

In `PROMPT_CLAUDE` `# Speaking discipline`, replace the sentence that allows `"Let me check that."` with:

```
Do not speak a searching filler before tools — the platform already plays a short wait sound. Never narrate search, plans, or tool use.
```

In `# Conversation behavior`, replace `A short filler BEFORE step 1 is fine ("Let me check that."). NEVER speak between step 1 and step 2.` with:

```
Do not speak before step 1. NEVER speak between step 1 and step 2.
```

In `# Error handling` (end of `PROMPT_CLAUDE`), replace `- Tool failure: retry once, then apologize briefly.` with:

```
- Tool failure (search_products HTTP error / timeout — NOT when the catalog is empty): immediately call show_search_error, then apologize briefly. Do NOT call show_search_error when search returned an empty products list.
```

In `_verify_agent`, add `"show_search_error"` to `expected_tool_names`.

- [ ] **Step 4: Run tests**

Run: `cd /workspace/onboarding-service && python3 -m unittest tests.test_show_search_error_tool -v`

Expected: `OK` / all tests PASS.

Also: `python3 -m py_compile elevenlabs_agent.py`

Expected: no output, exit 0.

- [ ] **Step 5: Commit**

```bash
git add onboarding-service/elevenlabs_agent.py onboarding-service/tests/test_show_search_error_tool.py
git commit -m "feat(agent): show_search_error client tool and Claude prompt"
```

---

### Task 4: Persist `search_latency` on search HTTP errors

**Files:**
- Modify: `search-service/main.py` (add `_search_uncached`; `search()` cache-miss calls it)
- Create: `search-service/tests/__init__.py` (empty)
- Create: `search-service/tests/test_search_error_latency.py`

**Interfaces:**
- Consumes: existing `_persist_search_latency(store_id, query, result_count, total_ms, embedding_ms, rpc_ms, queue_wait_ms, cache_hit)`
- Produces: `async def _search_uncached(sb, store_id: str, query: str, t0: float, response: Response) -> tuple` which persists `result_count=0`, `cache_hit=False` on `HTTPException` then re-raises

- [ ] **Step 1: Write the failing test**

Create empty `search-service/tests/__init__.py`. Create `search-service/tests/test_search_error_latency.py`:

```python
import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.responses import Response

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "search-service"))
sys.path.insert(0, str(ROOT))

import main as search_main  # noqa: E402


class SearchErrorLatencyTests(unittest.TestCase):
    def test_persist_called_when_hybrid_search_raises(self):
        persisted = []

        def fake_persist(**kwargs):
            persisted.append(kwargs)

        async def boom(**kwargs):
            raise HTTPException(status_code=503, detail="overloaded")

        response = Response()
        with patch.object(search_main, "_hybrid_search_products", side_effect=boom), \
             patch.object(search_main, "_persist_search_latency", side_effect=fake_persist):
            with self.assertRaises(HTTPException):
                asyncio.run(
                    search_main._search_uncached(
                        sb=object(),
                        store_id="9cec7cd0-9252-4aa2-985b-71c2a42018cb",
                        query="moisturizer",
                        t0=search_main.time.perf_counter(),
                        response=response,
                    )
                )

        self.assertEqual(len(persisted), 1)
        self.assertEqual(persisted[0]["result_count"], 0)
        self.assertFalse(persisted[0]["cache_hit"])
        self.assertEqual(persisted[0]["query"], "moisturizer")
        self.assertEqual(response.headers.get("X-Search-Cache"), "error")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /workspace/search-service && python3 -m unittest tests.test_search_error_latency -v`

Expected: FAIL (`AttributeError: module 'main' has no attribute '_search_uncached'`).

- [ ] **Step 3: Add `_search_uncached` and call it from `search()`**

Add above `search()`:

```python
async def _search_uncached(sb, store_id: str, query: str, t0: float, response: Response):
    try:
        products, queue_wait_ms, embedding_ms, rpc_ms = await _hybrid_search_products(
            sb=sb, store_id=store_id, query=query, final_limit=12
        )
        return products, queue_wait_ms, embedding_ms, rpc_ms
    except HTTPException:
        total_ms = int((time.perf_counter() - t0) * 1000)
        response.headers["X-Search-Duration-Ms"] = str(total_ms)
        response.headers["X-Search-Cache"] = "error"
        logger.error(
            f"⏱  Search failed: total_ms={total_ms} | store_id={store_id} | query={query!r}"
        )
        _persist_search_latency(
            store_id=store_id,
            query=query,
            result_count=0,
            total_ms=total_ms,
            embedding_ms=0,
            rpc_ms=0,
            queue_wait_ms=0,
            cache_hit=False,
        )
        raise
```

In `search()`, replace the cache-miss `_hybrid_search_products(...)` call with:

```python
    products, queue_wait_ms, embedding_ms, rpc_ms = await _search_uncached(
        sb=sb, store_id=req.store_id, query=req.query, t0=t0, response=response
    )
```

Do not persist on the 400 validation branches (empty query / bad UUID).

- [ ] **Step 4: Run tests**

Run:

```bash
cd /workspace/search-service && python3 -m unittest tests.test_search_error_latency -v && python3 -m py_compile main.py
```

Expected: tests PASS; py_compile exit 0.

- [ ] **Step 5: Commit**

```bash
git add search-service/main.py search-service/tests/test_search_error_latency.py
git commit -m "feat(search): persist search_latency on webhook errors"
```

---

### Task 5: Manual checklist + spec status (docs the human uses in Phase 0)

**Files:**
- Modify: `testing/manual_test_checklist.md` (Pre-flight + Section A)
- Modify: `docs/superpowers/specs/2026-09-04-xfused-voice-latency-design.md` (header Status line)

**Interfaces:**
- Consumes: ship-gate numbers from the spec
- Produces: updated checklist the human runs after Lightsail pull

- [ ] **Step 1: Update the spec status line**

Change `**Status:** Draft for human review...` to:

```
**Status:** Approved 2026-09-04. Implementation plan: `docs/superpowers/plans/2026-09-04-xfused-voice-latency.md`.
```

- [ ] **Step 2: Extend `testing/manual_test_checklist.md`**

In Pre-flight, keep the 405 check. Add:

```
4. Confirm env tags on the box (do not commit these):
   grep LATENCY_CONFIG_VERSION onboarding-service/.env
   grep SEARCH_CONFIG_VERSION search-service/.env
   grep SEARCH_CACHE_ENABLED search-service/.env
   Expected for this cutover: LATENCY_CONFIG_VERSION=v3-heardyou-searchfail
   SEARCH_CONFIG_VERSION=v3-error-persist SEARCH_CACHE_ENABLED=true
```

In Section A, add rows:

| # | Scenario | What to watch for |
|---|---|---|
| A7 | Non-search turn (“tell me more about the second one”) | THINKING pill as soon as you stop talking (not ~500ms later). No `/search` proxy log. `turn_latency` row with `latency_products_ms` null. |
| A8 | Repeat the same search 10s later | Second `search_latency` row `cache_hit=true` and `total_ms` much lower. |
| A9 | Empty catalog (“red spaceship”) | Empty carousel / “not carried” speech. Pill is NOT SEARCH_FAIL. |
| A10 | Forced search failure (temporarily stop `tp-search` for one query, then start it) | Pill + panel: “Couldn't search — try again”. Agent calls `show_search_error`. `search_latency` row with `result_count=0` if the request reached search. |

Replace the Section A pass bar with:

```
**Pass bar (ship gate B, Wi-Fi and 4G):** first useful feedback p95 ≤ 1.2s; User→Products p95 ≤ 3.5–4s on search turns; dead-air (User→Products − User→AI > 1.5s) < 10%; 1002 < 5%; update_products miss < 10%. Stretch A (0.8s / 2.5s) is reported, not required.
Pull GET /api/latency-summary/agent_4901kwna71tve5nbyy85c8v20yre?store_id=9cec7cd0-9252-4aa2-985b-71c2a42018cb (admin header required).
```

- [ ] **Step 3: Commit**

```bash
git add testing/manual_test_checklist.md docs/superpowers/specs/2026-09-04-xfused-voice-latency-design.md
git commit -m "docs(latency): approve spec and extend xfused manual checklist"
```

---

### Task 6: Human Phase 0 — deploy and PATCH (no application logic)

**Files:** none in git except what Tasks 1–5 already committed. Human runs this on Lightsail.

**Interfaces:**
- Consumes: Tasks 1–5 on the branch that is deployed
- Produces: live `GET https://api.teampop.com/api/turn-latency` → **405**; rows in `turn_latency` / `search_latency` after a few conversations

- [ ] **Step 1: Confirm current live code is still stale (baseline)**

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://api.teampop.com/api/turn-latency
```

Expected before deploy: `404`. After deploy: `405`. If already `405`, skip the “stale box” narrative but still bump version tags so new widget rows are distinguishable.

- [ ] **Step 2: Pull, tag env, restart, ship widget**

On Lightsail (as `ubuntu`):

```bash
cd /home/ubuntu/sales_agent
git fetch origin
git checkout cursor/voice-latency-design-bcc1   # or release/xfused-pilot after merge
git pull

grep -q '^LATENCY_CONFIG_VERSION=' onboarding-service/.env \
  && sed -i 's/^LATENCY_CONFIG_VERSION=.*/LATENCY_CONFIG_VERSION=v3-heardyou-searchfail/' onboarding-service/.env \
  || echo 'LATENCY_CONFIG_VERSION=v3-heardyou-searchfail' >> onboarding-service/.env
grep -q '^SEARCH_CONFIG_VERSION=' search-service/.env \
  && sed -i 's/^SEARCH_CONFIG_VERSION=.*/SEARCH_CONFIG_VERSION=v3-error-persist/' search-service/.env \
  || echo 'SEARCH_CONFIG_VERSION=v3-error-persist' >> search-service/.env
grep -q '^SEARCH_CACHE_ENABLED=' search-service/.env \
  && sed -i 's/^SEARCH_CACHE_ENABLED=.*/SEARCH_CACHE_ENABLED=true/' search-service/.env \
  || echo 'SEARCH_CACHE_ENABLED=true' >> search-service/.env

sudo systemctl restart tp-onboard tp-search
sudo systemctl status tp-onboard tp-search --no-pager
```

Build widget on a machine with RAM (not the 2GB box if Vite OOMs):

```bash
cd www.teampop/frontend && npm ci && npm run build
scp -r dist/* ubuntu@<lightsail-ip>:/home/ubuntu/sales_agent/www.teampop/frontend/dist/
```

- [ ] **Step 3: PATCH live Wrina with tools + prompt (do not touch language)**

From onboarding-service venv on the box (or laptop with prod `.env`):

```bash
cd /home/ubuntu/sales_agent/onboarding-service && source .venv/bin/activate
python3 -c "
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path('.env'))
from elevenlabs_agent import ElevenLabsAgentCreator
c = ElevenLabsAgentCreator()
print(c.update_agent(
    agent_id='agent_4901kwna71tve5nbyy85c8v20yre',
    store_id='9cec7cd0-9252-4aa2-985b-71c2a42018cb',
    store_context={
        'store_name': 'Xfused',
        'description': 'skincare store',
        'categories': 'facewash, moisturiser, lip balm',
        'price_range': '₹299–₹399',
        'offers': 'Catalog prices are ALREADY the discounted offer prices: facewashes and moisturisers Rs 349 (12% off, regular Rs 399); lip balms Rs 299 (14% off, regular Rs 349). Checkout extras on top: extra 10% off first order, free shipping on orders ₹499+.',
    },
))
"
```

Expected: `success: True`. Verify tools include `show_search_error` in the ElevenLabs dashboard or via GET agent. Confirm `language` is still `hi`.

- [ ] **Step 4: Pre-flight + Section A (human mic, India Wi-Fi then 4G)**

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://api.teampop.com/api/turn-latency
# expect 405
```

Run checklist A1–A10. Then pull latency-summary (admin password header). Record `by_config_variant.v3-heardyou-searchfail`.

**STOP.** If ship gate B fails, do **not** start Task 7 or 8. Inspect whether `search_ms` / `cache_hit` / User→AI is the bottleneck and only then continue.

- [ ] **Step 5: No code commit.** Paste summary numbers into the PR or `docs/agents/memory.md` in a follow-up commit if desired:

```bash
git add docs/agents/memory.md
git commit -m "docs(latency): record v3-heardyou-searchfail baseline numbers"
```

---

### Task 7: Caddy `/search*` shortcut (STOP-gated)

**Files:**
- Modify: `deploy/Caddyfile`

**Interfaces:**
- Consumes: Phase 0 logs showing `proxy_total_ms - search_ms` as a real cost (not ~1ms localhost)
- Produces: Caddy routes `/search*` and `/product-details*` to `:8006`, everything else to `:8005`

- [ ] **Step 1: STOP unless measurement says so**

If onboarding logs show `proxy_total_ms − search_ms` typically **< 20ms**, skip this task entirely. Localhost proxy is not the India problem.

- [ ] **Step 2: Replace the `api.teampop.com` site block**

```caddy
api.teampop.com {
	encode zstd gzip
	handle /search* {
		reverse_proxy localhost:8006
	}
	handle /product-details* {
		reverse_proxy localhost:8006
	}
	handle {
		reverse_proxy localhost:8005
	}
}
```

CORS on search-service must already allow the widget origin (it does via `ALLOWED_ORIGINS`). ElevenLabs calls `/search` server-to-server; CORS does not apply. Widget does **not** call `/search` directly.

- [ ] **Step 3: Reload Caddy on the box**

```bash
sudo cp /home/ubuntu/sales_agent/deploy/Caddyfile /etc/caddy/Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
curl -s -o /dev/null -w "%{http_code}\n" -X POST https://api.teampop.com/search \
  -H 'Content-Type: application/json' \
  -d '{"store_id":"9cec7cd0-9252-4aa2-985b-71c2a42018cb","query":"moisturizer"}'
```

Expected: `200` (or `422`/`400` if body validation differs — not `502`). Bump `SEARCH_CONFIG_VERSION=v4-caddy-direct`.

- [ ] **Step 4: Commit**

```bash
git add deploy/Caddyfile
git commit -m "perf(caddy): send /search and /product-details to search-service"
```

Rollback: restore the single `reverse_proxy localhost:8005` site block and `systemctl reload caddy`.

---

### Task 8: Copy-agent eagerness experiment (STOP-gated)

**Files:**
- Create: `testing/latency/set_turn_eagerness.py`

**Interfaces:**
- Consumes: `ElevenLabsAgentCreator.api_key`, PATCH `/v1/convai/agents/{id}`
- Produces: a **new** agent or a PATCH of a copy — never the live Wrina id unless the copy already passed interruption tests

- [ ] **Step 1: STOP unless User→AI p95 is the bottleneck after Task 6**

If `turn.first_ai_ms.p95_ms` is already ≤ 1200 on v3, skip. If interruptions were the prior regression, this task is an experiment, not a live rollout.

- [ ] **Step 2: Write the script**

Create `testing/latency/set_turn_eagerness.py`:

```python
#!/usr/bin/env python3
"""PATCH turn_eagerness / speculative_turn on one agent. Default is dry-run."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / "onboarding-service" / ".env")

LIVE_WRINA = "agent_4901kwna71tve5nbyy85c8v20yre"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--agent-id", required=True)
    p.add_argument("--eagerness", choices=("normal", "eager", "patient"), default="eager")
    p.add_argument("--speculative", action="store_true")
    p.add_argument("--apply", action="store_true", help="actually PATCH; default prints payload")
    p.add_argument("--allow-live-wrina", action="store_true")
    args = p.parse_args()

    if args.agent_id == LIVE_WRINA and not args.allow_live_wrina:
        print("Refusing to PATCH live Wrina without --allow-live-wrina", file=sys.stderr)
        return 2

    payload = {
        "conversation_config": {
            "turn": {
                "turn_eagerness": args.eagerness,
                "speculative_turn": bool(args.speculative),
            }
        }
    }
    print(json.dumps(payload, indent=2))
    if not args.apply:
        print("dry-run; pass --apply to PATCH")
        return 0

    key = os.environ["ELEVENLABS_API_KEY"]
    url = f"https://api.elevenlabs.io/v1/convai/agents/{args.agent_id}"
    r = requests.patch(url, headers={"xi-api-key": key, "Content-Type": "application/json"}, json=payload, timeout=30)
    print(r.status_code, r.text[:500])
    r.raise_for_status()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Dry-run then copy-agent only**

```bash
./onboarding-service/.venv/bin/python testing/latency/set_turn_eagerness.py \
  --agent-id <COPY_AGENT_ID> --eagerness eager --speculative
```

Expected: prints payload, exit 0, no PATCH.

Then `--apply` on the copy. Demo URL: `https://<host>/demo/test_<store>.html?agent=<COPY_AGENT_ID>`. Listen for false interruptions (checklist Section B4). Rollback: `--eagerness normal` without `--speculative --apply`.

- [ ] **Step 4: Commit the script only after dry-run works**

```bash
git add testing/latency/set_turn_eagerness.py
git commit -m "feat(latency): copy-agent turn_eagerness PATCH helper"
```

Do **not** pass `--allow-live-wrina` in this plan.

---

### Task 9: Mic constraints (STOP-gated)

**Files:**
- Modify: `www.teampop/frontend/src/components/AvatarWidget.jsx` (`conversation.startSession` ~line 1360)

**Interfaces:**
- Consumes: existing `startSession({ agentId, connectionType, dynamicVariables })`
- Produces: same call plus `audioInputConstraints` only if the installed `@elevenlabs/react` documents that key — verify in `node_modules/@elevenlabs/react` / client types before adding

- [ ] **Step 1: STOP unless checklist B2/B3 fail after Task 6**

If ASR is fine in a noisy room, skip.

- [ ] **Step 2: Confirm the SDK option name**

```bash
rg -n "noiseSuppression|audioConstraints|getUserMedia" www.teampop/frontend/node_modules/@elevenlabs/client www.teampop/frontend/node_modules/@elevenlabs/react --glob '*.d.ts' | head
```

If a documented `startSession` field exists (e.g. constraints object), pass:

```javascript
    conversation.startSession({
      agentId,
      connectionType: CONNECTION_TYPE,
      dynamicVariables: { session_context: sessionContextText },
      // Use the exact key the installed SDK types declare — do not invent a second getUserMedia.
    });
```

If the SDK has **no** input-constraint field, stop. Do not call `getUserMedia` yourself (double-capture / permission prompt). Record that finding in `docs/agents/memory.md` and leave the widget unchanged.

- [ ] **Step 3: Rebuild widget and re-run B2/B3**

```bash
cd www.teampop/frontend && npm run build
```

- [ ] **Step 4: Commit only if the SDK key was real**

```bash
git add www.teampop/frontend/src/components/AvatarWidget.jsx
git commit -m "fix(widget): enable browser noise suppression on session start"
```

---

## Out of this plan (explicit)

- GPT-Pet UI rewrite (Phase 2)
- Lightsail instance resize
- LLM / TTS model swap
- Moving Supabase or requesting ElevenLabs India residency
- Porting `show_search_error` to GPT/Gemini/Qwen/GLM prompts
- Creating `agent_requests` on this Supabase project
