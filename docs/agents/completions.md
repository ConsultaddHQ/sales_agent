# Completed Work Log

> Use this file for meaningful completed tasks that future humans or agents may want to review.
> Purpose: preserve implementation summaries, reasoning, tradeoffs, and verification in one durable place.
> Add newest entries at the top.

---

## 2026-09-06 — N/A — Wrina GET verification + SEARCH_FAIL widget rebuild (Lightsail still blocked)

- **Status:** Wrina verified live; widget rebuilt locally; Lightsail pull/copy **not done**
- **Owner:** Cloud agent (secrets-backed personal env)
- **Summary:** Started from the secrets-injected env on `release/xfused-pilot`. Confirmed the 2026-09-04 Wrina `update_agent` PATCH is still live: `language="hi"`, `show_search_error` is a client tool, webhook `store_id` is still the xfused constant. Did not re-PATCH and did not call `create_agent`. Rebuilt `www.teampop/frontend/dist/widget.js` (1,436,292 bytes, contains `SEARCH_FAIL`). Live `$WIDGET_SCRIPT_URL` is still the 12 Aug 2026 bundle without `SEARCH_FAIL`. SSH to `ubuntu@13.232.36.194` is `Permission denied (publickey)`.
- **Why:** The 2026-09-04 handoff’s first job (Lightsail pull + widget copy + Wrina PATCH) was blocked on keys in the previous pod. This env has the ElevenLabs/Supabase/OpenRouter secrets; it still lacks an SSH key, so only the PATCH half can be confirmed.
- **Files:** `docs/agents/{memory,handoff,completions}.md` (this session). Live ElevenLabs agent `agent_4901kwna71tve5nbyy85c8v20yre` unchanged this session.
- **Tradeoffs:** Skipped a redundant `update_agent` so dashboard-tuned voice/TTS/`language=hi` cannot drift. Widget `dist/` stays gitignored; next agent must rebuild or scp from a machine with the key.
- **Verification:** GET agent → `language=hi`, tools include `show_search_error`, store_id `constant_value` matches `9cec7cd0-9252-4aa2-985b-71c2a42018cb`. `node --test src/visualState.test.js` 8/8. `python3 -m unittest tests.test_show_search_error_tool` 2/2. `npm install && npm run build` → `SEARCH_FAIL` in dist. Live widget GET: 1,302,202 bytes, `SEARCH_FAIL` absent. `GET /api/turn-latency` → 405. SSH → publickey denied.
- **Related Decisions:** 2026-08-12 live Wrina `language=hi` + multilingual TTS; 2026-09-04 perceived-latency UI
- **Notes:** Next step is only SSH. Do not pass `voice_id`/`tts_overrides` if a later PATCH is required.

---

## 2026-09-04 — N/A — Xfused voice latency: perceived-latency UI, search-failure surfacing, per-turn measurement

- **Status:** Completed on `cursor/voice-latency-design-bcc1` — **not deployed**
- **Owner:** Claude Opus 5
- **Summary:** Tasks 1–6 of the approved latency plan. THINKING now shows the instant the user stops talking (`THINKING_SILENCE_MS` 500→150ms); a failed search surfaces as a distinct `SEARCH_FAIL` state instead of silently looking like listening; the agent gets a `show_search_error` client tool; every turn POSTs its own `turn_latency` row; and `search-service` persists a `search_latency` row on the error path too. Whole-branch review then fixed four real defects: `_markProductsArrived` was POSTing the first-AI leg a second time (double-counting it in `/api/latency-summary`), `searchFailed` leaked across sessions, the `SEARCH_FAIL` fallback was permanently cancelled by soft-timeout filler audio, and the search-error timing headers were written to a `Response` object FastAPI discards.
- **Why:** The client's "feels slow" report had no numbers behind it, and the two obvious ElevenLabs knobs were already tried and reverted (decisions.md 2026-07-20). Measure per turn, and stop the two failure modes that read as slowness but aren't: dead air while thinking, and a search that fails without ever saying so.
- **Files:** `www.teampop/frontend/src/visualState.js` + `.test.js`, `www.teampop/frontend/src/components/AvatarWidget.jsx`, `onboarding-service/elevenlabs_agent.py` + `tests/test_show_search_error_tool.py`, `search-service/main.py` + `tests/test_search_error_latency.py`, `testing/manual_test_checklist.md`.
- **Tradeoffs:** `searchFailed` resets only on the connect edge, not whenever agent audio stops — otherwise the apology would clear the error pill the moment the agent finished saying it. The 8s fallback is re-armed after filler instead of during, so a slow-but-successful search is never mislabelled as a failure. First-AI and products are separate rows rather than one wide row, which keeps `_latency_stats` null-dropping correct at the cost of two POSTs per search turn.
- **Verification:** `node --test src/visualState.test.js` (8/8), `python3 -m unittest tests.test_show_search_error_tool` (2/2), `.venv/bin/python -m unittest tests.test_search_error_latency` (1/1). `https://api.teampop.com/api/turn-latency` already returns 405, so the 2026-08-13 deploy did land — but **this branch is not on the box**, so none of the above is live. No measurement is meaningful until the handoff runbook is executed.
- **Related Decisions:** builds on 2026-07-20 per-turn latency tracking; spec at `docs/superpowers/specs/2026-09-04-xfused-voice-latency-design.md`.
- **Notes:** Tasks 7–9 are deliberately gated on the deployed A1–A10 numbers. Do not pick a further optimisation without them.

---

## 2026-07-20 — N/A — Voice-agent latency: per-turn tracking infra + search cache + soft-timeout tuning

- **Status:** Completed
- **Owner:** Claude Opus 4.6
- **Summary:** Xfused client feedback: the agent "feels slow." Built per-turn latency tracking (two new tables, an admin summary endpoint, `config_variant` tagging) so future latency changes are measurable instead of anecdotal, and shipped two safe wins: a 5-minute TTL search-result cache in `search-service`, and `soft_timeout_config.timeout_seconds` 2.5s→1.2s (filler phrase now "One sec..." instead of "Let me see...").
- **Why:** Prior investigation found the two most obvious "quick wins" (`turn_eagerness: "eager"` + `speculative_turn: true`, and `optimize_streaming_latency: 3`) had already been tried live and reverted for real regressions (premature interruptions; audible TTS dropouts) — see decisions.md 2026-07-20 entry and `[[elevenlabs-latency-reverts]]` memory. Rather than guess again, built measurement infra first so any future re-test of those settings (or new ones) has real before/after data instead of repeating the same trial-and-error.
- **Files:** `create_latency_tracking_table.sql` (new — run in Supabase before use), `onboarding-service/routes/client.py` (`POST /api/turn-latency`, `LATENCY_CONFIG_VERSION`), `onboarding-service/routes/admin.py` (`GET /api/latency-summary/{agent_id}`), `search-service/main.py` (in-memory FIFO cache keyed on `(store_id, normalized_query)`, `SEARCH_CACHE_TTL_SECONDS`/`SEARCH_CACHE_MAX_ENTRIES`/`SEARCH_CACHE_ENABLED` env vars, `SEARCH_CONFIG_VERSION`, `_persist_search_latency`), `www.teampop/frontend/src/components/AvatarWidget.jsx` (`_markProductsArrived` now POSTs each cycle immediately), `onboarding-service/elevenlabs_agent.py` (soft timeout + comment documenting why eagerness/streaming-latency were left alone).
- **Tradeoffs:** Search cache trades a few minutes of product-catalog staleness for latency — fine for a single-store pilot catalog that doesn't change minute-to-minute; would need revisiting for a high-churn multi-tenant catalog. Cache is FIFO-bounded (200 entries), not true LRU — acceptable at this scale, dependency-free. Did not touch `turn_eagerness`/`optimize_streaming_latency`/prompt length in this pass — flagged in roadmap as re-test candidates now that tracking exists.
- **Verification:** `python3 -m py_compile` on all 4 changed Python files; `npm run build` on the widget (506 modules, no errors). Not yet verified against a live Supabase instance — `create_latency_tracking_table.sql` must be run manually first (same manual-migration pattern as `create_feedback_table.sql`).
- **Related Decisions:** 2026-07-20 "Per-turn latency tracking via config_variant tagging" (decisions.md).
- **Notes:** Bump `LATENCY_CONFIG_VERSION` (onboarding-service env) and `SEARCH_CONFIG_VERSION` (search-service env) on every future latency-affecting deploy so `/latency-summary` can distinguish before/after. This closes roadmap fast-follow "search cache (#1)" from the 2026-07-03 pilot-launch entry.

---

## 2026-07-03 — N/A — Xfused pilot launch: search relevance UX + domain-neutral agent

- **Status:** Completed
- **Owner:** Claude Opus 4.8
- **Summary:** Launched the first real client (Xfused — goxfused.com, 6-product skincare) on an isolated `release/xfused-pilot` branch deployed to AWS Lightsail Mumbai. Fixed a chain of search/agent issues so the demo behaves: full small catalog surfaced, agent talks like a skincare (not clothing) advisor, and the carousel matches what the agent narrates.
- **Why:** The generic prompt was apparel-specific ("size/fabric/fashion pairing"), search truncated a 6-product catalog to 5, then over-corrected — a relevance cutoff hid products on "show me everything." Each broke the pilot demo.
- **Files:** `onboarding-service/elevenlabs_agent.py` (`PROMPT_CLAUDE` → domain-neutral + search-first/clarify guardrails), `search-service/main.py` (`final_limit` 5→12 at call site; rerank relevance cutoff + browse-intent bypass), `shared/config.py` (`RERANK_SCORE_MARGIN`), `testing/load/loadtest.py` + `latency_report.sh`, `testing/monitoring/monitor_agent_cost.py`, `deploy/` (Caddyfile + systemd units).
- **Tradeoffs:** Prompt neutralized only for `PROMPT_CLAUDE` (the model in use); other 4 templates deferred. Currency (₹) fixed via UI-pasted prompt + the widget's hardcoded ₹, not yet detected from the store — deferred. Onboarding run on the box (Shopify needs no Chromium) after a laptop `.env` `STORE_IMAGES_PATH` pointed at a non-existent path, nulling images.
- **Verification:** `curl /search` — "moisturizer"→2, "lip balm"→2, "show me everything"→6 (verified via `Reranked … browse=… kept N` logs); load test (~5.6 req/s CPU-bound ceiling on 2 vCPU); voice conversation on the test page confirmed skincare-appropriate narration matching the carousel.
- **Related Decisions:** 2026-07-03 relevance cutoff + browse bypass (see decisions.md); builds on 2026-06-25 search-quality overhaul.
- **Notes:** `RERANK_SCORE_MARGIN` (default 4.0) is env-tunable from the `kept_scores` logs; set high (~999) to disable. Post-pilot fast-follows tracked in roadmap: search cache (#1), currency-awareness, neutralize other 4 prompt templates, full production-hardening merge.

## 2026-06-29 — N/A — Context-aware dock button: carousel ↔ chat navigation

- **Status:** Completed
- **Owner:** Claude Sonnet 4.6
- **Summary:** The OrbDock's right-side button now reads "Chat" when in PRODUCTS view, and "← Products" when products exist in CHAT or NONE view, letting users navigate back to the carousel without losing session state.
- **Why:** Previously, closing the carousel or switching to chat had no way back — both X buttons dropped to NONE. Users needed a way to re-open the carousel after dismissing it or after reading the chat transcript.
- **Files:** `www.teampop/frontend/src/components/AvatarWidget.jsx` — `OrbDock` component (added `rightLabel` prop, line ~296) and `sharedDockProps` block (dynamic action/label based on `activeView` + `latestProducts.length`, line ~1289)
- **Tradeoffs:** Kept change minimal — no new components, no CSS, no new state. Label changes are derived entirely from existing `activeView` and `latestProducts` values already in scope. The `←` arrow gives directional cue without adding a separate back button.
- **Verification:** `npm run build` passed (1,286 kB). Manual flow: products appear → dock says "Chat" → click → chat opens → dock says "← Products" → click → carousel reopens. Closing carousel from NONE → dock shows "← Products" to reopen.
- **Related Decisions:** None
- **Notes:** Research confirmed contextual toggle beats a dedicated back button for occasional view switching in overlay widgets (Baymard, Entropik/Decode). The `←` prefix follows Smashing Magazine back-button UX guidance: users need to know *what* they're returning to.

---

## 2026-06-26 — False "we don't carry X" refusal fix + category extraction overhaul

- **Status:** Complete. Re-onboard stores to apply.
- **Owner:** Claude (Sonnet 4.6)
- **Root cause:** Two bugs compounded. (1) `adapters/shopify.py:extract_store_context` only scanned `products[:50]` and capped at 10 categories — so bottoms/pants never appeared in the Categories hint for stores where those products fell after index 50. (2) All 5 prompts had a hard guardrail "never search for a category the store doesn't sell" — the agent trusted an incomplete list and refused without searching, bypassing the "never reject on first miss" rule entirely.
- **Fix:**
  - All 5 prompts (`PROMPT_GEMINI/QWEN/GLM/CLAUDE/GPT`, lines ~114/201/282/371/459): changed guardrail from hard wall → search-first: "Categories is only a HINT — ALWAYS call search_products first; only say not carried if search returns nothing."
  - `adapters/shopify.py`: scan ALL products; priority: `product_type` → tags (parsed from Shopify comma-string; matched against clothing taxonomy) → title-word nouns. Cap raised to 20 (from 10). Fallback activates when <3 distinct types.
  - `adapters/universal.py`: same pattern — scan ALL products; prefer `product_type`, fall back to title nouns; cap raised to 20.
- **Tradeoff:** Prompt now allows the agent to search for anything plausibly related before saying "not carried" — this is correct because the Categories hint was always advisory, not exhaustive. Anti-hallucination is preserved: agent still can't describe or promise a product before `search_products` confirms it.
- **Also:** Created GitHub issue #41 (ConsultaddHQ/sales_agent) to park the multi-product cart feature design.
- **Action required:** Re-onboard stores (`POST /onboard`) after this deploy. Categories baked into the ElevenLabs agent prompt at creation time — won't update until re-onboard.

---

## 2026-06-19 — N/A — Codebase + Performance Audit; Refactor Plan (A + B)

- **Status:** Audits complete. Refactor code pending execution.
- **Owner:** Claude (Sonnet 4.6)
- **Summary:** Full read-only audit of all three branches (`version/v2`, `feature/ui-enhancements-v2`, `production-hardening`). Produced a general audit (`docs/audit-2026-06-19.md`) covering security, CORS, currency, and test gaps; a structured performance audit (`docs/perf-audit-2026-06-19.md`) with 3 CRITICAL / 6 HIGH / 6 MEDIUM / 6 LOW findings; and a detailed implementation plan (`docs/refactor-plan-2026-06-19.md`) for two targeted refactors.
- **Why:** Alpha-stage performance profile: zero result caching (every ElevenLabs utterance hits Supabase), serial image downloads (~400s for 200 products), no retry on ElevenLabs agent creation, no metrics endpoint, no structured per-request logging. Audit surfaced concrete impact estimates and priority order before any code changes.
- **Files:** `docs/audit-2026-06-19.md` (created), `docs/perf-audit-2026-06-19.md` (created), `docs/refactor-plan-2026-06-19.md` (created)
- **Key findings:**
  - CRITICAL C2: Serial image downloads + per-product embedding are the dominant onboarding latency driver (200 products ≈ 400s → 20s after fix)
  - CRITICAL C3: Zero search result cache — 50–100 req/s at 500 voice sessions would saturate Supabase
  - HIGH H2: No retry on ElevenLabs agent creation (`requests.post`, 30s timeout, single attempt)
  - Production-hardening branch (WEBHOOK_SECRET, ALLOWED_ORIGINS, request-ID, test suite) not merged into current working branch
- **Tradeoffs:** Audit is read-only; no code changed. Refactor plan ready for execution (see handoff.md).
- **Verification:** N/A — audit only. Code refactors have their own verification gates in the plan doc.
- **Related Decisions:** None created — refactor details are implementation-level, not architectural.
- **Notes:** Enterprise architecture blueprint (50–500 concurrent sessions) was requested but interrupted before delivery. Resume from `docs/agents/handoff.md`.

---

## 2026-06-19 — N/A — Fix: Enforce get_product_details → update_carousel_main_view chain; Disable carousel click-to-agent

- **Status:** Completed
- **Owner:** Antigravity
- **Summary:** Two product behaviour fixes. (1) When the agent fetches product details via `get_product_details`, it now always focuses the carousel on that product via `update_carousel_main_view` before speaking — enforced at three levels: tool description, `## Tools` section, and `# Guardrails` in all five model-specific system prompts (Gemini, Qwen, GLM, Claude, GPT). (2) Clicking a carousel thumbnail no longer sends a `[CAROUSEL UPDATE]` context message to the agent. The visual carousel update (`setActiveIndex`) still fires; only the agent narration trigger is removed.
- **Why:** (1) The agent was calling `get_product_details` but narrating without focusing the carousel, so the main frame lagged behind what the agent was describing — especially as conversation context grew. (2) Carousel click-to-agent caused the agent to interrupt itself or start an unwanted narration whenever the user browsed thumbnails.
- **Files:** `onboarding-service/elevenlabs_agent.py` (tool descriptions + all 5 system prompts), `www.teampop/frontend/src/components/AvatarWidget.jsx` (`syncMainProduct` call commented out in thumbnail `onClick`)
- **Pattern used:** Same triple-reinforcement proven for `search_products → update_products`: (a) tool `description` field, (b) `## ToolName` in system prompt, (c) `# Guardrails` rule. This makes the chain robust even as context grows.
- **Verification:** `npm run build` ✓ — 496 modules, 1313 kB bundle, 0 errors, 3.18s.
- **Re-enable carousel click:** Uncomment `syncMainProduct(latestProducts[idx])` in `AvatarWidget.jsx` onClick handler (search for "disabled — re-enable to have agent narrate clicked product").

---

## 2026-06-12 — N/A — Fix: Product images 404 in the running voice agent (4-layer root cause)

- **Status:** Completed
- **Owner:** Claude
- **Summary:** Product cards in the voice widget showed broken images (404). The root cause was four independent defects stacked along the image path; fixed all four so a freshly-built image URL flows search → agent → widget.
- **Why:** Images are core to the shopping UX; the carousel was rendering the dummy fallback (which itself 404'd) on every result.
- **Defects & fixes:**
  1. **Search dropped the good URL.** `search-service/main.py` computed `local_image_url` (current host + `local_image_path`) but `ProductOut` only returned the stale DB `image_url`. → `main.py:360` now returns `p.local_image_url or p.image_url`.
  2. **Stale absolute host in DB + missing config.** `image_url` is baked at onboarding time (`products.py:109`) as an absolute URL; ngrok subdomains rotate, so the stored host goes dead. `search-service/.env` had no `IMAGE_SERVER_URL`, so `IMAGE_SERVER_URL()` defaulted to `http://localhost:8000` (nothing runs there). → Added `IMAGE_SERVER_URL` (current ngrok → onboarding `:8005`) to `search-service/.env`. Search now rebuilds the host at query time, decoupling from the stale DB value.
  3. **LLM dropped image_url at the agent hop.** The `update_products` client tool used an opaque `items: {type: object}` schema, so the ElevenLabs LLM relayed a reconstructed array and dropped the long `image_url` (same failure class as the `store_id` truncation rule in constraints.md). → Gave `update_products.products.items` an explicit property schema with `image_url` required and "copy verbatim" wording, then pushed it to the live agent `agent_6501kpdsw9…` via `update_agent()` (re-pushes the tools config, no re-scrape).
  4. **Wrong fallback path.** `DUMMY_IMAGE = "/image.png"` resolves to the host root and 404s; the asset is served at `/widget/image.png`. → Changed to `/widget/image.png` and rebuilt the widget.
- **Files:** `search-service/main.py`, `search-service/.env`, `onboarding-service/elevenlabs_agent.py` (`_get_tool_config`), `www.teampop/frontend/src/components/AvatarWidget.jsx`.
- **Tradeoffs:** Search still reads `local_image_path` from the DB; the absolute `image_url` write in `products.py:109` is now redundant for search but left in place (durable follow-up: store only the relative path). `IMAGE_SERVER_URL` in `search-service/.env` must be re-pointed whenever the free ngrok tunnel restarts (or use a reserved domain).
- **Verification:** `/search` returns live-host URLs; `curl -I` on a product image → 200; `/widget/image.png` → 200; `update_agent` returned `success`; widget rebuilt clean (`npm run build`). Requires a hard-refresh of the demo page (stale `widget.js` cache) and a fresh conversation (schema change applies to new conversations).
- **Related Decisions:** 2026-06-12 — Voice-agent image URLs are composed at read time and relayed via explicit tool schema.
- **Notes:** The agent in question runs `gemini-2.5-flash`, which the 2026-04-17 A/B disqualified; upgrade is a separate task (`testing/latency/upgrade_agent_model.py`).

## 2026-04-17 — N/A — Voice-Agent Latency STEP 3: 6-Model A/B Test + Claude Haiku 4.5 as New Default

- **Status:** Completed (closes the voice-agent latency plan STEPS 1–4)
- **Owner:** Claude
- **Summary:** Ran the 6-model A/B latency protocol against one real store (see `testing/latency/README.md`), compiled results, and flipped the codebase default from Gemini 2.5 Flash to Claude Haiku 4.5. Also relocated the test harness into a durable `testing/latency/` folder with a new `upgrade_agent_model.py` helper so the experiment is re-runnable.
- **Why:** After STEPs 1/2/4 shipped earlier in the day, search was at its ~1s India↔Supabase network floor but voice cycles were still 3–15s with occasional `closeCode 1002` session kills on Gemini 2.5 Flash. The only remaining lever big enough to matter was the LLM choice; a disciplined measurement prevented making the swap on vibes.
- **Files:**
  - `onboarding-service/elevenlabs_agent.py` — default fallback changed to `claude-haiku-4-5` in `create_agent`, `update_agent`, and `_build_system_prompt`; `_verify_agent` now warns when it sees an agent still running gemini-2.5-flash and points to the upgrade script; docstring example updated.
  - `onboarding-service/.env.example` — `ELEVENLABS_LLM_MODEL=claude-haiku-4-5` with the full ranking (DQ reasons included).
  - `testing/latency/create_test_agents.py` — moved from `onboarding-service/scripts/` and sys.path fixed; creates 6 parallel test agents for one store.
  - `testing/latency/upgrade_agent_model.py` — NEW. Calls `update_agent` via the ElevenLabs PATCH endpoint to swap `llm` on a live agent. Supports single `--agent-id` or batch `--from-json` from the test harness output.
  - `testing/latency/README.md` — moved from `docs/latency-test-protocol.md` and reframed as a reusable harness doc (not a one-off STEP 3 doc).
  - `testing/README.md` — NEW. Short convention doc for future test harnesses.
  - `.personal/learning/LEARNING_PATH.md` — path references updated to the new `testing/latency/` location (section 6A).
- **Tradeoffs:**
  - The Gemini 2.5 Flash default was left reachable via env var for emergency rollback; it wasn't deleted from the prompt map or the model comparison table.
  - The 5 losing test agents were kept on the ElevenLabs dashboard per user request (they can be re-used or deleted manually). The `latency_test_agents.json` output file is gitignored-by-convention — not committed.
  - Claude Haiku 4.5 costs slightly more per call than Gemini 2.5 Flash, but the net-net is probably cheaper because there are no more retry loops, 1002 cascades, or failed tool calls burning tokens.
  - The harness is designed for one store at a time. Multi-store A/B isn't wired up; we can add it when/if model selection becomes store-dependent.
- **Verification:**
  - Compile: `python3 -m py_compile` passes on all three touched Python files.
  - Functional: `./onboarding-service/.venv/bin/python testing/latency/create_test_agents.py --help` and `…upgrade_agent_model.py --help` both render cleanly under argparse.
  - Empirical (from STEP 3 live run, one store, 10 cycles per model):

    | Model | Tool reliability | User→Products p50 | 1002 kills | Verdict |
    |---|---|---|---|---|
    | claude-haiku-4-5 | 7/7 = 100% | 3.4 s | 0 | ✅ WINNER |
    | gemini-2.5-flash-lite | 6/9 ≈ 67% | 2.0 s when fires | 0 | ✅ 2nd |
    | glm-45-air-fp8 | 7/9 ≈ 78% | 5.6 s | 0 | 🟡 backup |
    | gemini-2.5-flash | ~60% | 6.4 s + 18 s outlier | 1 | ❌ DQ |
    | qwen3-30b-a3b | 2/10 = 20% | N/A (no carousel) | 0 | ❌ DQ |
    | gpt-4.1-nano | 0/10 = 0% | N/A (no carousel) | 0 | ❌ DQ |

    User's own subjective read matched: *"Claude conversation was good in flow more like human… latency too good."*
- **Related Decisions:** 2026-04-17: Default ElevenLabs LLM = Claude Haiku 4.5 (winner of 6-model A/B test)
- **Notes:**
  - **Existing production agents are NOT upgraded automatically.** ElevenLabs bakes `llm` in at agent creation. Run `testing/latency/upgrade_agent_model.py --agent-id <id> --store-id <uuid>` per agent, or `--from-json` to batch. Human must decide which agents to upgrade and when.
  - Rerun the harness whenever ElevenLabs adds a new hosted model or Anthropic/Google ship a next-tier small model.
  - Product description is currently truncated to 200 chars before going to the LLM (`_truncate_for_voice` in `search-service/main.py`). For richer catalogs, consider a dedicated `voice_description` column generated at ingestion (see roadmap).

---

## 2026-04-17 — N/A — Voice-Agent Latency Tuning: Startup Warmup + Index-Aware Search RPC + Tool-First Prompt Rule

- **Status:** Completed (STEP 1, 2, 4 of the latency plan; STEP 3 — 6-model A/B matrix — still pending)
- **Owner:** Claude
- **Summary:** Shipped three coordinated changes that took measured `search_ms` from 2100–3100 ms down to ~1000 ms (network floor, India↔Supabase) and partially closed the "agent speaks about products before carousel updates" UX gap. Full plan lives at `/Users/consultadd/.claude/plans/synchronous-churning-sky.md`.
- **Why:** User reported 3–14 s end-to-end latency with frequent ElevenLabs `closeCode 1002 "Generating the LLM response took too long"` session kills. Baseline telemetry showed three root causes: (a) embedder cold-start stacking 1.5–3 s onto the first request of each session, (b) the `hybrid_search_products` RPC not using its own indexes so every call scanned all of a store's products, (c) Gemini speaking about search results before calling `update_products`, leaving the carousel 3–12 s behind the voice.
- **Files:**
  - `search-service/main.py` — added `@app.on_event("startup")` warmup that pre-loads `all-MiniLM-L6-v2` and opens the Supabase connection in a worker thread; added `X-Search-Duration-Ms` response header + correlated info log (`⏱ search_ms=… store_id=… query=… results=…`); CORS `expose_headers` so downstream can read the header.
  - `onboarding-service/main.py` — hoisted `httpx.AsyncClient` to module scope with keepalive pool; `/search` proxy now forwards the `X-Search-Duration-Ms` header and emits a one-line summary log per request (`⏱ /search proxy | store_id=… | query=… | search_ms=… | proxy_total_ms=… | status=…`). Added matching startup/shutdown hooks.
  - `onboarding-service/elevenlabs_agent.py` — tightened 5 model prompt templates (Gemini, Qwen, GLM, Claude, GPT) with one explicit rule in both the numbered procedure and `# Guardrails`: *"After a tool result, your very next action must be the next tool call. Do not speak between the result and the next tool. Filler before the first tool is fine."*
  - Supabase schema — new `products_fts_idx` GIN on `to_tsvector('english', coalesce(name,'') || ' ' || coalesce(description,''))`; `hybrid_search_products` function body rewritten to use `ORDER BY embedding <=> p_query_embedding LIMIT 50` (HNSW-friendly) and `@@ plainto_tsquery(...)` filter (GIN-friendly). Same signature, same weighting.
- **Tradeoffs:**
  - Kept Supabase region as-is (~1 s network floor from India). Moving region or adding a result cache is the next lever if needed.
  - Did not edit `start_services.sh` per user preference — they run services manually.
  - Did not change TTS model (`eleven_flash_v2` kept; English-only, fastest).
  - Prompt rule is advisory: LLMs that ignore it (Gemini 2.5 Flash does, sometimes) will still produce filler speech. Model swap (STEP 3) is the hard fix.
- **Verification:**
  - `python3 -m py_compile` passes on all three touched Python files.
  - Measured `search_ms` per widget cycle in live onboarding log: 347, 718, 798, 1003, 1041, 1050, 1065, 1153, 1237, 1335, 1575, 1650 ms (avg ~1.1 s, median ~1.04 s).
  - `EXPLAIN ANALYZE` on `hybrid_search_products(...)` shows 51.9 ms DB execution with the new function — confirmed HNSW and GIN are hit in the plan.
  - Fresh-session Cycle 1 dropped from baseline ~18 s to ~283–380 ms to first AI — warmup verified.
  - Remaining bottleneck confirmed as Gemini 2.5 Flash's 2nd-turn reasoning: Cycle 4 in last test showed `update_products` firing at 3047 ms but AI speech not starting until 17983 ms.
- **Related Decisions:**
  - 2026-04-17: Voice-Agent Prompt Contract — Tool-First-After-Result Rule Across All Models
  - 2026-04-17: Supabase `hybrid_search_products` Rewritten to Use HNSW and GIN Indexes
- **Notes:**
  - STEP 3 scaffolding is the natural next piece of work: create 6 test agents under one store, run a fixed 10-prompt protocol against each, compare `User→AI` p95 and tool-call reliability. Candidates: `claude-haiku-4-5`, `gpt-4.1-nano`, `gemini-2.5-flash-lite`, `glm-45-air-fp8`, `qwen3-30b-a3b`, and `gemini-2.5-flash` as control. Exact ElevenLabs model strings should be verified against their `/v1/convai/agents/supported_llms` (or equivalent) endpoint before creating agents.
  - New stores onboarded after this change inherit the fast-search path automatically (schema-level change).
  - `@app.on_event` usage raises DeprecationWarning under current FastAPI — harmless; migrate to `lifespan` context manager in a future cleanup pass if desired.

---

## 2026-04-14 — Phase 3: Push-to-Talk (PTT) orb mode

**What was done:**
Added push-to-talk as a plug-and-play interaction mode alongside the existing VAD mode.

**File structure:**
- `src/hooks/useVoiceMode.js` — NEW: VAD/PTT mode state + localStorage persistence key `team-pop-voice-mode`
- `src/hooks/usePttInteraction.js` — NEW: all PTT logic isolated; exposes `beginPress`, `endPress`, `onConnected`, `onDisconnected`, `syncStatus`
- `src/styles/ptt.css` — NEW: CSS for `PTT_READY`, `PTT_MUTED_CONNECTED`, `PTT_HOLDING`, `CONNECTING` states + mode toggle + End button
- `src/components/AvatarWidget.jsx` — MODIFIED: integrated above hooks; extracted `OrbDock` sub-component shared by NONE and PRODUCTS views; `getVisualState()` and `getStatusLabel()` pure helpers

**SDK surface used:**
`conversation.setMuted` from `@elevenlabs/react` `useConversation` (v1.x). Session stays open between PTT presses; only mic gate is toggled.

**Key tradeoffs:**
- PTT hook takes `setMuted` as its only SDK dependency — can swap SDK mic API without touching widget logic
- `syncStatus` + `onConnected`/`onDisconnected` pattern avoids stale closures while keeping hook portable
- Pointer capture (`setPointerCapture`) ensures release fires even when pointer leaves the orb element

**Verification:** `npm run build` passes, 1,178 kB bundle, 0 errors.

---

## 2026-04-14 — N/A — Phase 1: Tool Reduction + Prompt/Flow Overhaul

- **Status:** Completed
- **Owner:** Codex
- **Summary:** Completed Phase 1 of the multi-user/tool-reduction UX plan by reducing ElevenLabs to two tools (`search_products`, `update_products`), rewriting all model prompts for natural conversation and one-turn context gathering before search, and simplifying the widget to client-side carousel context handling only.
- **Why:** The previous 4-tool setup and scripted filler behavior added complexity and made interactions feel robotic, especially during first-turn search latency.
- **Files:** `onboarding-service/elevenlabs_agent.py`, `www.teampop/frontend/src/components/AvatarWidget.jsx`, `docs/agents/{decisions,completions,roadmap}.md`
- **Tradeoffs:** Agent-side explicit carousel-navigation tooling was removed; references like "the second one" now rely on model reasoning over latest shown results context. This keeps UX simpler but increases prompt dependence for ordinal reference handling.
- **Verification:** `python3 -m py_compile onboarding-service/elevenlabs_agent.py` passed. Confirmed removed tool names are absent from agent config and widget tool registrations via grep checks. Frontend `npm run build` and `npm run lint` could not run because local toolchain binaries (`vite`, `eslint`) are not installed in this workspace.
- **Related Decisions:** 2026-04-14: Phase 1 Voice UX — Two-Tool Contract + One-Turn Context-First Search
- **Notes:** `first_message` now uses store name context, and `soft_timeout_config.message` changed to "Let me see...".

---

## 2026-04-14 — N/A — Phase 2 Infrastructure: Search-Service Concurrency + Rate Limiting

- **Status:** Completed
- **Owner:** Codex
- **Summary:** Hardened the search service for simultaneous usage by converting `POST /search` to an async endpoint, offloading embedding generation and Supabase RPC execution to worker threads, adding `slowapi` request limiting, and documenting current ElevenLabs concurrency and pricing constraints in a new operational note.
- **Why:** The widget already supports multiple independent browser sessions, so the next scaling bottleneck was the backend search path and the external ElevenLabs workspace limits. The previous synchronous search endpoint could block under concurrent traffic, and the repo did not have one durable source summarizing ElevenLabs concurrency/cost constraints for planning.
- **Files:** `search-service/main.py`, `search-service/{requirements.txt,.env.example,README.md}`, `shared/{db,embeddings}.py`, `docs/elevenlabs-limits.md`, `docs/agents/{decisions,memory,roadmap}.md`
- **Tradeoffs:** Kept the synchronous Supabase client instead of migrating to an async stack. This reduces risk and scope, but it means concurrency still depends on thread offload plus Uvicorn workers rather than a fully async DB/client path. The default rate limit (`30/minute`) is intentionally conservative and may need adjustment for trusted internal traffic or deployments behind a proxy.
- **Verification:** `python3 -m py_compile search-service/main.py shared/db.py shared/embeddings.py` succeeded. Manual diff review confirmed the search endpoint is now async, `slowapi` is wired into the app and `/search`, singleton initialization is lock-protected, the default `python main.py` port now aligns with port `8006`, and `docs/elevenlabs-limits.md` includes official source links plus explicit notes where conclusions are inference rather than published hard limits.
- **Related Decisions:** 2026-04-14: Search Service Scaling via Async Endpoint + Thread Offload + Worker Processes; 2026-04-08: Remove Pitch LLM from Search Service
- **Notes:** I did not find an official published hard cap for maximum conversation duration or a separate browser-WebSocket session limit in ElevenLabs docs. The new limits doc calls those gaps out explicitly instead of implying certainty.

## 2026-04-10 — N/A — Human-Facing Knowledge Base Handbook

- **Status:** Completed
- **Owner:** Codex
- **Summary:** Added a new canonical human-facing KT hub under `docs/knowledge-base/` with layered docs for system overview, repo map, core flows, architecture decisions, technology rationale, risks, roadmap, and glossary. Added lightweight pointers from `README.md` and `AGENTS.md`, and updated personal learning notes to point back to the new handbook instead of older shared-study paths.
- **Why:** The repo already had durable agent-oriented source docs, but it lacked one readable handbook that helps humans understand the current system, flows, contracts, tradeoffs, and risks without depending on chat history or tribal memory.
- **Files:** `docs/knowledge-base/*.md`, `README.md`, `AGENTS.md`, `.personal/learning/{LEARNING_PATH,ENGINEERING_OPERATING_SYSTEM}.md`, `docs/agents/{memory,roadmap}.md`
- **Tradeoffs:** The new handbook intentionally summarizes and links to `docs/agents/*` instead of copying long sections. Some “why this tech” explanations are marked as informed inference where the codebase/history implies rationale more strongly than it states it outright.
- **Verification:** Audited `AGENTS.md`, `docs/agents/{constraints,memory,decisions,completions,roadmap}.md`, live backend/frontend code paths, and current service READMEs before writing. Confirmed the KT docs call out the main stable contracts: `hybrid_search_products`, `all-MiniLM-L6-v2` + `vector(384)`, `<team-pop-agent>`, onboarding response shape, and ElevenLabs tool-name consistency. Confirmed root docs now point to `docs/knowledge-base/README.md`.
- **Related Decisions:** 2026-04-07: Monorepo Refactoring — Shared Library + Adapter Registry + Universal Scraping; 2026-04-08: Single-Tunnel Architecture — All Services Through One ngrok Tunnel; 2026-04-03: Widget Served from Onboarding Service, Not Vite Dev Server
- **Notes:** The handbook is intentionally human-facing and should stay synchronized with the underlying source docs in `docs/agents/`. `.personal/learning/` remains optional and non-canonical.

---

## 2026-04-10 — N/A — Conservative Repo Cleanup Audit

- **Status:** Completed
- **Owner:** Codex
- **Summary:** Removed two detached legacy onboarding adapter modules, deleted the stale `WidgetZIndexFix.jsx` helper after inlining its only live wrapper usage into `AvatarWidget.jsx`, removed unreferenced website starter assets, and trimmed low-risk dead comments/imports in the frontend.
- **Why:** The repo still contained duplicated adapter-era files, placeholder widget helper code, and starter assets/comments that no longer matched the live architecture. Keeping them added confusion during maintenance without providing runtime value.
- **Files:** `onboarding-service/threadless_adapter.py`, `onboarding-service/supermicro_adapter.py`, `www.teampop/frontend/src/components/{AvatarWidget,WidgetZIndexFix}.jsx`, `www.teampop/frontend/{index.html,src/App.jsx,src/main.jsx,vite.config.js}`, `www.teampop/website/src/components/VoiceOrb.jsx`, `docs/Engineering Standards.md`
- **Tradeoffs:** Historical docs mentioning the old adapter files were preserved unless they would become misleading as current guidance. Existing unrelated lint issues in the website were not addressed as part of this conservative cleanup.
- **Verification:** Repo-wide `rg` checks confirmed no live code references to the removed adapters, widget helper, or website assets. `python3` adapter smoke test confirmed `detect_store_type()` and `get_adapter()` still resolve both Threadless and Supermicro through `onboarding-service/adapters/`. `npm run build` succeeded in both `www.teampop/frontend/` and `www.teampop/website/`. `npm run lint` in `www.teampop/frontend/` now reports only one `react-hooks/exhaustive-deps` warning in `AvatarWidget.jsx`; `npm run lint` in `www.teampop/website/` still reports pre-existing `react-hooks/set-state-in-effect` errors in `FAQ.jsx` and `AdminPage.jsx`.
- **Related Decisions:** 2026-04-07: Monorepo Refactoring — Shared Library + Adapter Registry + Universal Scraping
- **Notes:** `docs/Engineering Standards.md` was updated to point to `AvatarWidget.jsx` for z-index isolation guidance after removing `WidgetZIndexFix.jsx`.

## Entry Template

Copy this block for meaningful completed work:

```markdown
## YYYY-MM-DD — [Ticket or N/A] — [Short title]

- **Status:** Completed
- **Owner:** [Agent / engineer]
- **Summary:** [What changed in 1-2 sentences]
- **Why:** [Why this work mattered]
- **Files:** [Key files only]
- **Tradeoffs:** [Important tradeoffs or constraints accepted]
- **Verification:** [Tests, manual checks, screenshots, commands]
- **Related Decisions:** [Decision date/title or "None"]
- **Notes:** [Anything future readers should know]
```

---

## 2026-04-09 — N/A — Agent Conversation Cycle Reference + WebSocket Diagnostic Logging

- **Status:** Completed
- **Owner:** Claude Code
- **Summary:** Added an `onDisconnect` callback to the widget's `useConversation` hook to capture WebSocket close code/reason (previously silent), and documented the complete end-to-end agent conversation cycle (user speech → VAD/ASR → Gemini LLM → search webhook → widget client tool → TTS) with file paths and line numbers. This entry is the single source of truth for debugging agent conversation flow.
- **Why:** Three observed problems needed better visibility: (1) WebSocket closes mid-conversation with `WebSocket is already in CLOSING or CLOSED state` at `sendMessage` (widget tries to send `client_tool_result` after server killed WS) — no diagnostic info was captured. (2) Reliability varies 3-4s vs 10s because Gemini sometimes generates filler speech before calling `update_products` after receiving webhook results. (3) No end-to-end doc existed, so agents debugging had to trace AvatarWidget.jsx + elevenlabs_agent.py + search-service/main.py + SDK source every time.
- **Files:** `www.teampop/frontend/src/components/AvatarWidget.jsx` (added `onDisconnect` after `onError` at ~line 242).
- **Tradeoffs:** Diagnostic-only change — does not fix the WebSocket close, just logs the close code + reason so the real cause can be identified from real data instead of guessing. Actual fix requires analyzing a few captured closes.
- **Verification:** Widget built with `npm run build` in `www.teampop/frontend/`. After a search triggers a close, check browser console for `[ElevenLabs] Disconnected: reason=... closeCode=... closeReason=...`. Close code 1000 = clean agent end; any other code = server error.
- **Related Decisions:** 2026-04-09: Tools-First Gemini Prompt + Latency/Interruption Settings Overhaul
- **Notes:** The agent settings in `elevenlabs_agent.py` (lines 699-745) were verified against the working agent `agent_6501knschbgtf98sp1cawz6b1hza` via GET API — `soft_timeout_config` (2.5s, "Hhmmmm...yeah.", LLM=false) and all 5 `client_events` (audio, user_transcript, interruption, agent_response, agent_response_correction) already match exactly. No settings code changes were needed.

### Complete Agent Conversation Cycle Reference

End-to-end trace of a single user query from speech to products on carousel. Line numbers match current state as of 2026-04-09.

#### STEP 1 — User clicks orb → WebSocket opens
- **File:** `www.teampop/frontend/src/components/AvatarWidget.jsx:368-384` (`handleInteraction`)
- Calls `conversation.startSession({ agentId, connectionType: "websocket" })`
- **SDK internals** (`node_modules/@elevenlabs/client/dist/utils/WebSocketConnection.js`): `WebSocketConnection.create()` opens `wss://api.elevenlabs.io/...`, waits for `"conversation_initiation_metadata"` event containing `conversation_id`, `user_input_audio_format`, `agent_output_audio_format`
- Status transitions: `disconnected → connecting → connected`
- Agent plays `first_message` via TTS immediately (configured in `onboarding-service/elevenlabs_agent.py:711-715`)

#### STEP 2 — User speaks → VAD → ASR → Transcript
- SDK captures microphone via `getUserMedia()`, streams `"user_audio"` frames over WS
- Server runs VAD (voice activity detection) → ASR (Automatic Speech Recognition) → sends transcript event
- **File:** `AvatarWidget.jsx:181-217` (`onMessage({source:"user", text})`)
- Calls `_startLatencyTimer(text)` → records `performance.now()` as `userSpeechAt` (line 147-151)
- Adds to `chatHistory` state (line 203)

#### STEP 3 — Gemini LLM processes (~1s)
- Server passes transcript to Gemini 2.5 Flash with system prompt + conversation history
- Per the tools-first prompt (`elevenlabs_agent.py:43-91`): Gemini says a short phrase like "On it!" or "Let me check!" (step 1 of the 4-step procedure)
- **File:** `AvatarWidget.jsx:220-240` (`onMessage({source:"ai", text})`)
- Calls `_markFirstAi()` → records `firstAiAt` (line 153-160)
- **Soft timeout fallback:** If Gemini takes >2.5s before any speech, `soft_timeout_config` fires (configured in `elevenlabs_agent.py:736-740`) — TTS plays static message `"Hhmmmm...yeah."` (NOT an LLM response, it is platform-level filler)

#### STEP 4 — `search_products` webhook fires
- **Tool config:** `onboarding-service/elevenlabs_agent.py:427-456`
  - `type: "webhook"`, `execution_mode: "immediate"`, `response_timeout_secs: 5`
  - `store_id` is a `constant_value` (NOT LLM-generated, to prevent UUID truncation)
  - `query` is LLM-expanded from user utterance
- Server sends `POST {SEARCH_API_URL}/search` with `Content-Type: application/json`
- **File:** `search-service/main.py:253-299` (`search()` endpoint)
  - Validates `store_id` (UUID format) + `query` (non-empty)
  - Calls `_hybrid_search_products()` at `search-service/main.py:123-245`
  - Encodes query with `all-MiniLM-L6-v2` → 384-dim embedding (loaded from `shared/embeddings.py`)
  - Calls Supabase RPC `hybrid_search_products` with `p_store_id`, `p_query`, `p_query_embedding`, `p_limit=5`, `p_min_score=0.25`
- Returns `SearchResponse`: `{ "products": [{id, name, price, description, image_url, product_url}, ...], "pitch": "Found N products." }`
- **Typical latency:** 500ms-1.5s (measured in production)

#### STEP 5 — Gemini receives results → Calls `update_products` ⚠️ BOTTLENECK
- Server passes webhook response back to Gemini as tool result
- Gemini decides to call `update_products` (client tool) with the products array
- **Three observed failure modes:**
  - **FAST (3-4s total):** Gemini immediately calls `update_products` → speaks about results
  - **SLOW (8-10s total):** Gemini generates filler speech first (e.g., "I found some great options, let me pull those up"), THEN calls `update_products` — the intermediate speech adds 3-5s
  - **BROKEN:** Gemini speaks about products WITHOUT calling `update_products` → carousel stays blank. Prompt reinforcement with "This step is important." mitigates but does not eliminate this.
- Server sends `"client_tool_call"` event over WS to widget:
  ```json
  {
    "type": "client_tool_call",
    "client_tool_call": {
      "tool_call_id": "...",
      "tool_name": "update_products",
      "parameters": { "products": [...] }
    }
  }
  ```

#### STEP 6 — Widget executes `update_products` client tool
- **SDK internals** (`node_modules/@elevenlabs/client/dist/BaseConversation.js`): routes `"client_tool_call"` to the handler registered via `useConversationClientTool("update_products", ...)`
- **File:** `AvatarWidget.jsx:246-262`
  - Calls `_markProductsArrived(products.length)` → records `productsAt`, logs latency breakdown (line 162-177)
  - `setLatestProducts(products)` + `latestProductsRef.current = products`
  - `setActiveView("PRODUCTS")` → carousel view appears
  - `setActiveIndex(0)` → first product focused
  - Returns string `"UI updated successfully"`
- **SDK sends result back over WS:**
  ```json
  {
    "type": "client_tool_result",
    "tool_call_id": "...",
    "result": "UI updated successfully",
    "is_error": false
  }
  ```
- ⚠️ **This is where the `WebSocket is already in CLOSING or CLOSED state` error originates.** If the server killed the WS during step 5 (e.g., LLM timeout, orchestrator error), the SDK's `connection.sendMessage()` at `widget.js:472` throws because the socket is already closed. The new `onDisconnect` callback now captures the close code + reason to diagnose *why*.

#### STEP 7 — Gemini speaks about results
- Gemini generates product descriptions, TTS converts to speech, streamed via `"audio"` events over WS
- **File:** `AvatarWidget.jsx:220-240` (`onMessage({source:"ai", text})`)
- `setAgentSubtitle(text)` → user sees subtitle
- Price keyword detection (line 226-239): if text contains "price", "₹", "rupees", or "cost", triggers `setHighlightPrice(true)` for 2.5s
- User sees carousel + hears agent describing products
- **Cycle complete.** Next user query returns to STEP 2.

#### Other client tools in the cycle
- **`update_carousel_main_view`** (`AvatarWidget.jsx:264-286`): Agent-triggered carousel navigation. Takes `index` (preferred) or `product_id`. Sets `isAgentTriggeredRef.current = true` so the scroll `useEffect` at line 351-366 distinguishes agent vs. manual scroll.
- **`product_desc_of_main_view`** (`AvatarWidget.jsx:288-304`): Called **only** by the frontend (never by the agent) when user manually scrolls the carousel. Agent prompt explicitly forbids calling this tool.
- **`syncMainProduct`** (`AvatarWidget.jsx:317-348`): On manual thumbnail click, debounces 600ms, then sends `sendContextualUpdate("[CAROUSEL UPDATE] ...")` + `sendUserMessage("Tell me about this one")` to trigger agent narration. `isSyntheticMessageRef` prevents the synthetic "Tell me about this one" from appearing in chat history.

#### WebSocket message types (SDK → server)
| Type | Purpose | Trigger |
|------|---------|---------|
| `user_audio` | Raw mic audio frames | Continuous while mic active |
| `user_message` | Text input | `sendUserMessage(text)` |
| `contextual_update` | Inject context without interrupting | `sendContextualUpdate(text)` |
| `client_tool_result` | Tool execution result | After each client tool runs |
| `pong` | Response to server ping | Server `ping` event |
| `feedback` | Like/dislike | `sendFeedback()` |

#### WebSocket event types (server → client)
Configured in `elevenlabs_agent.py:728-731` via `client_events`:
- `audio` — TTS audio chunks
- `user_transcript` — Final ASR result
- `interruption` — User interrupted agent speech
- `agent_response` — Agent message text
- `agent_response_correction` — Agent message edit

---

## 2026-04-08 — N/A — ElevenLabs API Migration + Latency Optimization + Single-Tunnel Sharing

- **Status:** Completed
- **Owner:** Claude Code
- **Summary:** Migrated ElevenLabs agent creation to current API format (`conversation_config.agent` nesting), fixed tool config validation errors, added `ignore_default_personality`, switched to low-latency ElevenLabs-hosted LLM (`glm-45-air-fp8`), optimized TTS/turn settings, consolidated all services behind single ngrok tunnel, and added widget-side latency instrumentation.
- **Why:** Agent creation was silently failing to store prompt/tools due to API format changes. Agent was behaving as generic chatbot (missing personality). Latency was high due to external API LLM. Sharing demos required 3 ngrok tunnels (impossible on free tier).
- **Files:** `onboarding-service/elevenlabs_agent.py` (major rewrite — API format, tool config, latency settings, verification), `onboarding-service/main.py` (added `/images` static mount + `/search` proxy), `image_server.py` (fixed default images path), `www.teampop/frontend/src/components/AvatarWidget.jsx` (latency timing instrumentation), `onboarding-service/routes/admin.py` + `client.py` (error logging), `onboarding-service/.env.example` (new LLM/TTS defaults)
- **Tradeoffs:** (1) `glm-45-air-fp8` is faster but less proven than `gpt-4o-mini` for complex tool-calling — fallback via env var. (2) `optimize_streaming_latency: 3` trades slight audio quality for speed. (3) Search proxy adds one local hop but eliminates need for separate ngrok tunnel. (4) `eager` turn mode may occasionally interrupt user — acceptable for shopping assistant.
- **Verification:** Agent verification log confirms prompt stored (3800+ chars with "Sam"), 4 tools configured, `ignore_default_personality: true`, `llm=glm-45-air-fp8`. Browser console shows colored latency breakdown per conversation cycle. Single ngrok tunnel serves demo pages, widget JS, images, and search webhook.
- **Related Decisions:** 2026-04-08: ElevenLabs API format migration, 2026-04-08: Latency-optimized agent config
- **Notes:** Key API discoveries: (1) `agent_config` as top-level key is silently ignored — must nest under `conversation_config.agent`. (2) `constant_value` and `description` cannot coexist on same webhook param. (3) Array-type tool params require `items` field. (4) Default `ignore_default_personality: false` injects generic ElevenLabs personality that overrides custom prompt.

---

## 2026-04-07 — N/A — Monorepo Refactoring: Plug-and-Play Adapters + Universal Scraping

- **Status:** Completed
- **Owner:** Claude Code
- **Summary:** Decomposed the 1,251-line onboarding main.py into a plug-and-play adapter registry, shared library, unified pipeline, route modules, and service modules. Added a 6-tier universal scraping chain (JSON-LD, microdata, OG tags, platform CSS selectors, Playwright rendering, LLM fallback) with platform auto-detection for WooCommerce, Magento, PrestaShop, OpenCart, Wix, and others.
- **Why:** Adding a 4th store type previously required ~140 lines of copy-paste, a new endpoint, and a new elif branch. Now it requires 1 class implementing StoreAdapter + 1 line in the registry. The universal adapter enables scraping ~90-95% of e-commerce sites without any platform-specific code.
- **Files:** `shared/{config,db,embeddings,parsing}.py`, `onboarding-service/{main,pipeline}.py`, `onboarding-service/adapters/{base,registry,shopify,threadless,supermicro,universal}.py`, `onboarding-service/routes/{onboard,admin,client}.py`, `onboarding-service/services/{products,test_page,agent_creator}.py`, `onboarding-service/scraping/{platform_detect,renderer,llm_fallback}.py`, `onboarding-service/scraping/extractors/{json_ld,open_graph,microdata,sitemap,platform_selectors}.py`, `search-service/main.py`
- **Tradeoffs:** Used `sys.path.insert` for shared/ imports instead of `pip install -e .` — appropriate for alpha stage, upgrade when team grows. Old adapter files (`threadless_adapter.py`, `supermicro_adapter.py`) kept for now as the new adapters import their scrapers. Backward-compatible `/onboard-threadless` and `/onboard-supermicro` endpoints delegate to unified handler.
- **Verification:** All imports verified via `python -c "from main import app"` in both services. All routes registered: `/onboard`, `/onboard-threadless`, `/onboard-supermicro`, `/api/*`. Adapter registry auto-detects: shopify, threadless, supermicro, universal.
- **Related Decisions:** 2026-04-03 Adapter Pattern for Non-Shopify, 2026-04-07 Monorepo Refactoring Architecture
- **Notes:** The `main.py` went from 1,251 lines to ~80 lines. The universal adapter's fallback chain has not been tested against live sites yet — integration testing needed. Platform CSS selectors defined for WooCommerce, Magento 2, PrestaShop, and OpenCart.

---

## 2026-04-07 — N/A — Marketing Website Redesign + Client Acquisition Frontend

- **Status:** Completed
- **Owner:** Claude Code
- **Summary:** Complete redesign of the marketing website (`www.teampop/website/`) from an AI-generic indigo/purple theme to a Resend.com-inspired black/white monochrome design. Replaced Three.js 3D orb with CSS + GSAP orb (74% bundle reduction). Built full client acquisition frontend: request form, admin dashboard, and confirmation flow. Added Winterfell-style enhanced step cards with scroll-driven animation, 3D hover tilt, tag pills, and accent dots. Added 2-column FAQ section with accordion.
- **Why:** The original design looked too "AI-generated" and wouldn't convert real clients. The monochrome redesign gives a premium, professional feel. The client acquisition flow (form → notifications → admin processing → delivery) is the core business workflow for Hyperflex.
- **Files:**
  - `www.teampop/website/src/index.css` — Full design system: CSS variables, orb classes (voice-orb, orb-glow, orb-shimmer, voice-ring), card/button/input utilities
  - `www.teampop/website/src/components/VoiceOrb.jsx` — CSS radial-gradient orb with GSAP idle animations, canvas particles, mouse proximity glow, hover escalation, click effect (push-back + shockwave ring)
  - `www.teampop/website/src/components/HowItWorks.jsx` — 3-col equal grid with scroll-driven entrance (translateY + scale + rotation like Winterfell), 3D tilt on hover, tag pills, colored accent dots
  - `www.teampop/website/src/components/FAQ.jsx` — **NEW**: 2-column layout (large heading + CTA left, accordion right), Plus icon rotates to × on open, smooth height animation
  - `www.teampop/website/src/components/Hero.jsx` — 2-col hero with staggered text animation
  - `www.teampop/website/src/components/CTA.jsx`, `Navbar.jsx`, `Footer.jsx` — Monochrome styling
  - `www.teampop/website/src/pages/RequestPage.jsx` — Form (name, email, URL) + confirmation with Calendly embed
  - `www.teampop/website/src/pages/AdminPage.jsx` — Password-gated dashboard with request table, process/send dialogs, 30s auto-refresh
  - `www.teampop/website/src/lib/api.js` — 6 API functions (submitRequest, adminLogin, getRequests, processRequest, updateRequest, sendAgent)
  - `www.teampop/website/src/pages/Landing.jsx` — Composes Navbar → Hero → HowItWorks → FAQ → CTA → Footer
  - `www.teampop/website/package.json` — Removed three/r3f/postprocessing, added @gsap/react
- **Tradeoffs:**
  - Removed Three.js entirely — no 3D orb, but 74% smaller bundle (1,458KB → 379KB) and no WebGL compatibility issues
  - GSAP ScrollTrigger replaced with vanilla scroll listeners + IntersectionObserver — GSAP ScrollTrigger was unreliable in headless preview and some browser contexts
  - Admin auth is simple password header (X-Admin-Password), not JWT — acceptable for internal tool, should upgrade before production
  - Dark-on-dark monochrome (#111 cards on #000 bg) has low contrast in JPEG screenshots but looks correct in real browsers
- **Verification:**
  - `npm run build` succeeds at 379KB (down from 1,458KB)
  - All components render correctly (verified via accessibility tree snapshots and DOM inspection)
  - 3-col card grid: each card 379px wide, equal height
  - FAQ: 2-column grid (560px + 560px), 6 accordion items functional
  - Card scroll animation: cards enter from bottom with staggered rotation
  - Orb: idle breathing + shimmer + ring ripples + mouse tilt + click shockwave all working
- **Related Decisions:** None (design choices, not architectural)
- **Notes:**
  - Backend endpoints for client acquisition are in `onboarding-service/main.py` (6 new endpoints added in same session)
  - `notifications.py` handles Resend emails + Slack webhooks (fire-and-forget via ThreadPoolExecutor)
  - Manual setup required before testing: Supabase `agent_requests` table, Resend API key, Slack webhook, Calendly link, ADMIN_PASSWORD env var
  - 2s fallback timer on scroll animations ensures cards always appear even if scroll listeners don't fire

---

## 2026-04-07 — N/A — Client Acquisition Backend (Request Pipeline + Notifications)

- **Status:** Completed
- **Owner:** Claude Code
- **Summary:** Added 6 API endpoints to onboarding-service for the full client acquisition workflow: submit-request, admin login, list requests, process request, update request, send agent. Added multi-channel notifications via Resend (email) and Slack (webhooks).
- **Why:** Core business flow — clients submit their store URL, team gets notified, admin processes and delivers the voice agent demo.
- **Files:**
  - `onboarding-service/main.py` — 6 new endpoints with Pydantic models, ThreadPoolExecutor for background tasks
  - `onboarding-service/notifications.py` — **NEW**: send_slack_notification, send_client_ack_email, send_admin_notification_email, send_delivery_email
  - `onboarding-service/.env.example` — Added RESEND_API_KEY, FROM_EMAIL, ADMIN_EMAIL, ADMIN_PASSWORD, SLACK_WEBHOOK_URL, CALENDLY_URL
  - `onboarding-service/requirements.txt` — Added `resend`
- **Tradeoffs:**
  - Notifications are fire-and-forget (ThreadPoolExecutor, errors logged not raised) — acceptable for non-critical alerts
  - Admin auth via X-Admin-Password header — simple but not production-grade
  - No rate limiting on submit-request — needs adding before public launch
- **Verification:**
  - Build compiles, all imports resolve
  - Endpoint signatures match frontend api.js calls
  - Error handling uses error_codes.py for user-facing responses
- **Related Decisions:** None
- **Notes:**
  - Requires `agent_requests` table in Supabase (SQL provided in project docs)
  - Resend free tier: 100 emails/day, requires domain verification for custom FROM address
  - Status flow: pending → processing → ready → sent (or failed → retry)

---

## 2026-04-06 — N/A — Repo Cleanup: Removed Dashboard, Dead Code, Stale Scripts

- **Status:** Completed
- **Owner:** Claude Code
- **Summary:** Removed the unused merchant onboarding dashboard (`www.teampop/dashboard/`), dead frontend pages/components (Home, Docs, GetStarted, Header), stale startup scripts (`scripts/`), and miscellaneous artifacts. Updated all documentation references.
- **Why:** The dashboard was a standalone React app no longer in active use. The frontend widget contained ~40% dead code from an abandoned multi-page routing attempt. The `scripts/` directory referenced the deleted `image-service/`. All of this was clutter adding confusion for agents and engineers.
- **Files:**
  - Deleted: `www.teampop/dashboard/` (15 files), `scripts/` (2 files), `test_shopify_flow.py`, `www.teampop/index.html`, `www.teampop/test_widget.html`, `www.teampop/demo_click_pattern.md`, stray JPG
  - Deleted from frontend: `src/pages/` (Home, Docs, GetStarted), `src/components/Header.jsx`, `src/styles/` (Header.css, GetStarted.css), `src/App.css` (entirely dead)
  - Modified: `src/App.jsx` (removed App.css import), `package.json` (removed `react-router-dom`)
  - Updated docs: `AGENTS.md`, `README.md`, `www.teampop/README.md`, `SHOPIFY_FLOW_COMPLETE.md`, `docs/agents/constraints.md`
  - Updated scripts: `start_services.sh` (4 steps instead of 5), `stop_services.sh` (removed dashboard)
- **Tradeoffs:**
  - Dashboard deletion means onboarding must happen via API calls (curl/Postman) until a replacement UI is built
  - `SHOPIFY_FLOW_COMPLETE.md` still has some dashboard references in deeper sections — kept as historical context rather than rewriting the entire doc
- **Verification:**
  - `npm run build` in `www.teampop/frontend/` succeeds — widget builds cleanly without deleted files
  - `grep` confirms no remaining imports of deleted components in frontend source
  - `git status` shows only intended deletions and modifications
- **Related Decisions:** 2026-04-06 — Dashboard removed in favor of API-first onboarding
- **Notes:**
  - `www.teampop/website/` (untracked React + Three.js project) was intentionally kept — it's the new marketing website in active development
  - `react-router-dom` was removed from frontend dependencies since no routing is configured in the widget

---

## 2026-04-05 — N/A — Supermicro GPU Server Onboarding Pipeline

- **Status:** Completed
- **Owner:** Claude Code
- **Summary:** Built end-to-end onboarding pipeline for Supermicro's enterprise GPU server catalog (82 products). Includes two-phase scraper (JSON API + detail page enrichment), adapter, API endpoint, and fixes to ElevenLabs agent config and search service debugging.
- **Why:** Supermicro is the first B2B enterprise catalog (no prices, hardware specs instead of fashion). Required a different scraping strategy (internal JSON API discovery) and exposed bugs in the ElevenLabs tool config.
- **Files:**
  - `universal-scraper/scripts/supermicro_scraper.py` — **NEW**: Two-phase scraper. Phase 1 fetches 82 products from Supermicro's internal JSON API (`/en/structuredbapi/ps2/system/gpu/all`). Phase 2 enriches each product from its detail page (core count, memory capacity, PCIe config, key features, cooling, dimensions, weight).
  - `onboarding-service/supermicro_adapter.py` — **NEW**: Adapter normalizing scraper output to Shopify-compatible format, filesystem-safe handle sanitization for SKUs with spaces/`+`/parentheses, store context builder, test page generator.
  - `onboarding-service/main.py` — Added `POST /onboard-supermicro` endpoint (7-step pipeline).
  - `onboarding-service/elevenlabs_agent.py` — Updated to current ElevenLabs API format (`conversational_config`, tools inside `agent.prompt`, `type: "client"` not `"client_tool"`), changed `store_id` from `value_type: "llm_prompt"` to `"constant"`, added UUID validation at creation time.
  - `onboarding-service/error_codes.py` — Added `SCRAPING_BLOCKED` error code.
  - `search-service/main.py` — Added `RequestLoggingMiddleware` for debugging 400 errors, improved UUID validation error messages with truncation detection.
  - `image-service/` — **DELETED**: Duplicate of `image_server.py`.
- **Tradeoffs:**
  - All specs flattened into `description` field instead of adding new DB columns — avoids migration, relies on embedding search for filtering
  - Phase 2 detail page scraping adds ~3-5 min for 82 products but provides richer embeddings (key features, memory capacity, core count)
  - Handle sanitization replaces `+` with `-plus` and removes parentheses — lossy but URL/filesystem safe
- **Verification:**
  - Standalone scraper test: 82 products fetched from API, 3 detail pages enriched successfully with ~1400-1700 char descriptions
  - ElevenLabs agent created and connected, search webhook called with correct constant store_id
  - Products found in search results after onboarding
- **Bugs Found & Fixed:**
  - **ElevenLabs `store_id` as `llm_prompt`**: The LLM was copying a 36-char UUID from the system prompt and truncating it (dropped one `5`), causing 400 on every search. Fixed by setting `value_type: "constant"`.
  - **SKU handle sanitization**: Supermicro SKUs like `AS -4124GO-NART+` broke image filenames. Fixed with sanitization.
  - **Dead ngrok tunnel**: Identified expired tunnel as cause of webhook failures.
- **Related Decisions:** 2026-04-05 — API-based scraping for Supermicro; Constant store_id in ElevenLabs webhooks
- **Notes:**
  - Supermicro's internal API at `/en/structuredbapi/ps2/system/gpu/all` is undocumented — if they change it, the scraper breaks. Fallback: scrape HTML directly.
  - Basic HTTP returns 403 for supermicro.com — Playwright is required.
  - B2B catalog has no prices — agent responds with "contact sales for quote".

---

## 2026-04-03 — N/A — Threadless (NurdLuv) Store Integration with Supabase Pipeline

- **Status:** Completed
- **Owner:** Claude Code
- **Summary:** Integrated the standalone nurdluv.threadless.com scraper into the full onboarding pipeline — scraping, embedding, Supabase storage, ElevenLabs agent creation, and demo page generation. Also upgraded `@elevenlabs/react` from v0.14.3 to v1.0.1 and migrated the widget to the new SDK API.
- **Why:** The Threadless scraper existed as standalone code with no DB storage, no agent creation, and no demo page. This integration makes the full voice shopping experience work end-to-end for non-Shopify stores.
- **Files:**
  - `onboarding-service/threadless_adapter.py` — **NEW**: adapter that normalizes Threadless scraper output to Shopify-compatible format, Playwright-based page fetching for demo pages, store context builder
  - `onboarding-service/main.py` — added `POST /onboard-threadless` endpoint, import adapter, fixed product_url to use `_original_product_url` for non-Shopify stores
  - `onboarding-service/elevenlabs_agent.py` — added optional `tags` parameter to `create_agent()` and `create_agent_for_store()`
  - `onboarding-service/requirements.txt` — added `playwright`
  - `www.teampop/frontend/src/App.jsx` — wrapped app in `<ConversationProvider>` for ElevenLabs SDK v1.0
  - `www.teampop/frontend/src/components/AvatarWidget.jsx` — migrated from `useConversation` with inline `clientTools` to `useConversationClientTool` hooks, fixed `startSession` to sync (v1.0), fixed `connectionType: "websocket"`, fixed `<img> onError` undefined `product` bug
  - `search-service/main.py` — added `local_image_url` field to `ProductResult` dataclass
- **Tradeoffs:**
  - Adapter pattern (normalize to Shopify format) instead of refactoring `build_product_rows()` — avoids breaking existing Shopify flow, acceptable duplication for 2 store types
  - Strips ALL scripts and HTML comments from demo pages — necessary because Cloudflare challenge scripts and commented-out `<script>` blocks break browser parsing when served from localhost
  - Uses `connectionType: "websocket"` instead of default WebRTC — installed `livekit-client@2.18.1` doesn't have ElevenLabs' patch for their RTC server, causing WebRTC connections to drop
  - Widget served from onboarding service (`/widget/widget.js`) instead of Vite dev server — Vite injects React Fast Refresh globals that break the IIFE on external pages
- **Verification:**
  - `POST /onboard-threadless` creates store, scrapes products, stores in Supabase, creates ElevenLabs agent, generates demo page
  - Demo page loads real NurdLuv store HTML with widget overlay
  - Agent connects via WebSocket, responds to voice, calls search_products webhook via ngrok, updates product carousel via client tools
  - Product images served correctly from image server
  - Search service returns products with correct URLs (`/designs/` not `/products/`)
- **Related Decisions:** 2026-04-03 — Adapter pattern for non-Shopify stores; ElevenLabs SDK v1.0 migration
- **Notes:**
  - ElevenLabs tools must be configured via dashboard (API PATCH for tools has validation issues with `constant_value` + `description` conflict)
  - Tool names must match exactly between: ElevenLabs dashboard, agent system prompt, and widget `useConversationClientTool` registrations (e.g., `search_products` not `search_product`)
  - ngrok URL for search webhook changes on restart — must update agent's tool config each time
  - Image server expects images at repo-root `./images/`, but onboarding service saves to `onboarding-service/images/` — needs copy or symlink
  - `build_product_rows()` now checks `product.get("_original_product_url")` before falling back to Shopify `/products/{handle}` format

---

## 2026-04-02 — N/A — Added durable completed-work log and clarified doc ownership

- **Status:** Completed
- **Owner:** Codex
- **Summary:** Added a permanent completed-work log for future learning and review, and clarified which collaboration files should be updated during and after a task.
- **Why:** The existing system captured active work and architecture decisions well, but it did not have one durable place to review completed implementation work, tradeoffs, and verification history.
- **Files:** `AGENTS.md`, `CLAUDE.md`, `docs/agents/completions.md`, `docs/agents/decisions.md`, `docs/agents/memory.md`, `docs/COLLABORATIVE.md`, `docs/AGENT_DOCS_GUIDE.md`
- **Tradeoffs:** Kept both human-facing docs, but reduced overlap by making `COLLABORATIVE.md` a lightweight explainer and `AGENT_DOCS_GUIDE.md` the maintainer guide. This avoids deleting helpful context while still enforcing single ownership.
- **Verification:** Reviewed the full doc set for ownership overlap and updated the canonical workflow so start-of-task, decision logging, completion logging, and handoffs each have a single home.
- **Related Decisions:** 2026-04-02 — Durable completed-work summaries live in `docs/agents/completions.md`
- **Notes:** Future task summaries should go here only when the work is meaningful enough to be useful for later review or onboarding.

---

## 2026-04-02 — N/A — Moved personal learning notes to local-only ignored storage

- **Status:** Completed
- **Owner:** Codex
- **Summary:** Removed personal learning documents from tracked repo docs, added a gitignored `.personal/` location for local-only files, and removed shared references to those personal materials.
- **Why:** Personal growth notes and individual learning systems should not live in an organization repo when they are not required for shared agent workflow or team reference.
- **Files:** `.gitignore`, `AGENTS.md`, `docs/COLLABORATIVE.md`, `docs/AGENT_DOCS_GUIDE.md`, `docs/agents/memory.md`, `docs/agents/completions.md`
- **Tradeoffs:** This keeps the shared repo cleaner and more private, but it also means personal notes are no longer discoverable through repo docs and need to be managed locally by the user.
- **Verification:** Added `.personal/` and `.claude/` to `.gitignore`, moved the learning files under `.personal/learning/`, and verified that tracked docs no longer reference the personal file names.
- **Related Decisions:** None
- **Notes:** Future personal notes should stay under `.personal/` or another gitignored local folder, not under tracked `docs/`.
