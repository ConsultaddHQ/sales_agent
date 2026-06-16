# Voice Agent Latency Test Harness

> **Purpose:** Compare candidate LLMs for the ElevenLabs agent on a fixed,
> repeatable set of prompts so decisions are made from data, not hunches.
> **Created:** 2026-04-17 for STEP 3 of the latency plan.
> **Kept here for future re-runs** — whenever ElevenLabs adds a new hosted
> model, when Anthropic/OpenAI/Google ship a new Haiku/Nano/Flash tier, or
> when any latency regression shows up in production.

---

## Files

| File | What it does |
|------|--------------|
| `create_test_agents.py` | Spins up N parallel ElevenLabs agents for one store, one per candidate `llm` value. |
| `upgrade_agent_model.py` | Swaps the `llm` model on one existing agent without re-onboarding (uses `update_agent` under the hood). |
| `README.md` | This file — test protocol and runbook. |
| `latency_test_agents.json` | Output of `create_test_agents.py`. Gitignore or re-create as needed. |

---

## Related

- Plan: `~/.claude/plans/synchronous-churning-sky.md` (§11 STEP 3).
- Prompt contract: `docs/agents/decisions.md` (2026-04-17 entries).
- Winner on 2026-04-17: **Claude Haiku 4.5** (see `docs/agents/decisions.md`).

---

## What this test measures

Per conversation cycle the widget logs two numbers (see
`www.teampop/frontend/src/components/AvatarWidget.jsx` lines 265–297):

- `User→AI` — ms from user stopping speech to the first AI text arriving.
- `User→Products` — ms from user stopping speech to `update_products` firing.

The onboarding-service proxy logs one more number per search (added in
STEP 1):

- `search_ms` — ms for the search webhook round-trip (embed + Supabase RPC).

The gap we're hunting is **`User→Products − User→AI`**. When it exceeds
~1500 ms the user hears the agent describing products before the carousel
updates — the UX problem that motivated this test.

---

## Prerequisites

1. STEP 2 Supabase changes are live (`products_fts_idx` GIN + rewritten
   `hybrid_search_products`). Verify with `EXPLAIN ANALYZE`.
2. STEP 1 code is running (startup warmup, `X-Search-Duration-Ms` header,
   proxy client reuse). Verify by restarting search-service and checking
   for the `🔥 Warmup: embedder ready` log line.
3. A store has been onboarded with products. Note its `store_id`.

---

## Step-by-step

### 1. Create the 6 test agents

```bash
# from repo root
./onboarding-service/.venv/bin/python testing/latency/create_test_agents.py \
    --store-id <your-store-uuid>
```

Output: `latency_test_agents.json` (in whatever directory you ran it from)
with one entry per model. Example row:

```json
"claude-haiku-4-5": {
  "label": "Claude Haiku 4.5",
  "agent_id": "agent_abc123...",
  "agent_url": "https://elevenlabs.io/app/conversational-ai/agent_abc123..."
}
```

If any model errors out with "invalid llm", note the string ElevenLabs
rejected and update `CANDIDATES` in `testing/latency/create_test_agents.py`.
The test can still proceed with the remaining models; just note which
one you had to drop.

### 2. Run the fixed 10-prompt script against each agent

For every agent in `latency_test_agents.json`:

1. Open the demo page in Chrome with the agent override in the URL:
   ```
   https://<your-tunnel>/demo/test_<store_id>.html?agent=<agent_id_from_json>
   ```
   For example:
   ```
   https://garth-quare-nonequably.ngrok-free.dev/demo/test_75eb8b55.html?agent=agent_abc123
   ```
   The override is logged in the console so you can confirm which agent is
   active (`[TeamPop] Widget config loaded — agent: agent_abc123 (URL override)`).
   No edits to the HTML file or re-onboarding needed.
2. Open DevTools → Console.
3. Speak these prompts **in this exact order**, one per session cycle.
   Wait for the agent to finish speaking (or the carousel to settle)
   before speaking the next one.

```
1.  "Show me some 80s or 90s movie inspired designs."
2.  "What about something horror themed?"
3.  "Show me sledgehammer designs."
4.  "The second one — tell me more."
5.  "Okay, show me Crocs inspired designs."
6.  "Show me something sci-fi under 30 dollars."
7.  "Surprise me with a bestseller."
8.  "Show me the Game Over design."
9.  "Anything with a weathered look?"
10. "Okay, show me more movie-inspired."
```

Notes on the prompt set:
- #1, #2, #5, #6 — broad category searches.
- #3, #8 — specific name searches.
- #4 — ordinal reference to test "resolve from latest shown results".
- #7 — tests fallback behaviour when intent is vague.
- #9, #10 — follow-up refinements that test context carry-over.

Do **not** deviate from this list during the test — we want same-input
comparison. If the agent misunderstands a prompt, that counts too.

### 3. Capture the logs

From the widget console copy every line that matches:

```
⏱ [Cycle N] ...
[ElevenLabs] Disconnected: ...
```

From the onboarding-service terminal copy every line that matches:

```
⏱  /search proxy | ...
```

Paste both sets back to the agent (or save locally) under a clear label:

```
=== latency-test-claude-haiku-4-5 ===
<widget console lines>

<server log lines>
```

### 4. Repeat for each of the 6 models

Same store, same 10 prompts, same order. Ideally within the same 30-minute
window so network conditions are comparable.

---

## How the winner is picked

For each model we compute from the pasted logs:

| Metric | Definition | Weight |
|---|---|---|
| `User→Products p95` | 95th percentile of the 10 cycles | **primary** |
| `Dead-air rate` | % of cycles where `User→Products − User→AI > 1500 ms` | **primary** |
| `Tool-call failure rate` | % of cycles where `update_products` never fired | hard fail if >10% |
| `1002 timeout rate` | ElevenLabs session kills with "LLM response took too long" | hard fail if >5% |
| `Ordinal reference handling` | Did #4 ("the second one") describe the right product? | tie-breaker |
| `User→AI median` | How fast the agent starts responding | tie-breaker |

A model is disqualified if any hard-fail threshold is breached, regardless
of how fast it is otherwise. Among survivors the lowest `User→Products p95`
wins; dead-air rate is the tie-breaker.

Target: **p95 under 4 s, dead-air rate under 10 %.**

---

## Cleanup

After the winner is chosen, keep one agent as the new production agent and
delete the other five from the ElevenLabs dashboard (or via API). The
`latency_test_agents.json` file can be deleted or archived.

Update `ELEVENLABS_LLM_MODEL` in `onboarding-service/.env` to the winning
model so future onboardings use it automatically.

Record the winner in `docs/agents/decisions.md` as an append-only entry
(Decision: "Default ElevenLabs LLM for voice agent = X") with the measured
numbers as rationale.
