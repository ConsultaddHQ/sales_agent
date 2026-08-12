# Agent Handoff Log

> Use this file when ending a session mid-task so another agent can pick up exactly where you left off.
> **Append new handoffs at the top** (newest first).
> Old handoffs (>2 weeks) can be archived or deleted.

---

## Handoff Template

Copy this block and fill it in when handing off:

```markdown
## Handoff — YYYY-MM-DD HH:MM

**From:** [Agent name / tool / session ID]
**To:** [Intended next agent, or "any"]
**Task:** [One-line description of the task]
**Ticket:** HPF-XXX

### Current Progress
- [% complete estimate]
- [Key milestones already done]
- [Last commit hash if applicable]

### What Was Done
- [Bullet list of concrete changes made]
- [Files modified]

### What Remains
1. [Next step — be specific]
2. [Step after that]
3. [...]

### Context the Next Agent Needs
- [Why are we doing this? What problem does it solve?]
- [Any non-obvious decisions made so far?]
- [Gotchas encountered?]

### Attempted Approaches That Failed
- [What was tried and why it didn't work — prevents wasted re-attempts]

### Blockers / Open Questions
- [Anything that needs human input?]
- [Missing credentials, unclear requirements?]

### Key Files
- `path/to/file.py` — [what it does / what needs to change]
- `path/to/component.jsx` — [...]

### Confidence
[ ] High — approach is solid, just needs completion
[ ] Medium — approach works but has tradeoffs worth reviewing
[ ] Low — stuck, next agent should reconsider the approach

### Test Command
```bash
# How to verify this works when done
```
```

---

## Handoff Log

---

## Handoff — 2026-08-13

**From:** Claude (Sonnet 5)
**To:** Human (Gautam) — Lightsail deploy, then any agent for the follow-up latency work
**Task:** Latency-audit reconciliation — find out why the plan felt "lost track of," fix two bugs blocking measurement, align code to live agent drift
**Ticket:** none referenced (pre-existing gap, not this session's doing — flag if a Linear ticket should be opened)

### Current Progress
- Root cause found: latency work (cache, tracking tables, soft-timeout fix) was committed at `03ef0af` (2026-07-21) and pushed, but **never deployed** to `api.teampop.com`. Confirmed via `GET /api/turn-latency` → 404 live (would be 405 if deployed) and 0 rows in `turn_latency`/`search_latency` despite 10 real conversations on 2026-08-06.
- Also found the live ElevenLabs agent (`agent_4901kwna71tve5nbyy85c8v20yre`, "Wrina - Xfused v2") has config drift from the code — looks like manual dashboard edits during testing that were never ported back. See `docs/agents/decisions.md` (2026-08-12 entry) for the full diff.
- Deploy blocker #1 fixed: `/api/latency-summary` 500'd because it resolved `agent_id → store_id` via an `agent_requests` table that **does not exist** in the live Supabase project (`jchigqerypjwmszslzke` — confirmed via schema introspection). Fixed in `onboarding-service/routes/admin.py`: the route now accepts `?store_id=...` directly, and the `agent_requests` lookup is best-effort (logs a warning, never crashes the request).
- Deploy blocker #2 identified (not a code bug, a deploy-config step): `LATENCY_CONFIG_VERSION`/`SEARCH_CONFIG_VERSION` are unset on the live `.env` files, so every row would land under the same `v1-baseline` bucket even after deploying — making before/after comparison impossible. Must be set explicitly at deploy time (see "What Remains" below).
- Code alignment done in `onboarding-service/elevenlabs_agent.py`: `create_agent()` now takes a `language` param (was hardcoded `"en"`) so the live agent's `language="hi"` + `eleven_flash_v2_5` setup is reproducible instead of silently regressable; `soft_timeout_config` default updated to match the live rotating-filler config; stale comments corrected (`optimize_streaming_latency` is now a deprecated ElevenLabs field; the old "English agents must use flash_v2" comment didn't note the `language="hi"` exception).
- Wrote `testing/manual_test_checklist.md` — scenario checklist tied to the 7 client-reported issues + a regression section for future changes.

### What Was Done
- `onboarding-service/routes/admin.py` — `/api/latency-summary/{agent_id}` now takes optional `?store_id=`, `agent_requests` lookup wrapped so it can't 500 the endpoint.
- `onboarding-service/elevenlabs_agent.py` — `create_agent(language="en")` param added and wired into the payload; `soft_timeout_config` defaults updated; stale comment blocks corrected.
- `onboarding-service/.env.example` — added a note on the xfused `language="hi"` exception next to `ELEVENLABS_TTS_MODEL`.
- `docs/agents/decisions.md` — new 2026-08-12 entry documenting the live-vs-code drift and why it's not a contradiction of the 2026-07-04 decision.
- `docs/agents/roadmap.md` — corrected several stale statuses (search cache "done" → "coded, not deployed"; `agent_requests` "done" → not done on this project; Hindi/Tamil pronunciation task → resolved via the `language="hi"` switch; dropped `optimize_streaming_latency` from the re-test item since it's deprecated; region-move item flagged as likely-stale premise given ElevenLabs' Feb 2026 global-routing default).
- `testing/manual_test_checklist.md` — new file.

### What Remains
1. **Deploy to Lightsail** (human step — SSH access needed):
   ```bash
   ssh ubuntu@<lightsail-ip>
   cd /home/ubuntu/sales_agent
   git fetch origin && git checkout release/xfused-pilot && git pull origin release/xfused-pilot

   # Set distinct config-variant tags so before/after is comparable — do this
   # BEFORE restarting, values are just examples, keep them short and unique:
   sed -i 's/^LATENCY_CONFIG_VERSION=.*/LATENCY_CONFIG_VERSION=v2-cache-softtimeout/' onboarding-service/.env
   sed -i 's/^SEARCH_CONFIG_VERSION=.*/SEARCH_CONFIG_VERSION=v2-cache/' search-service/.env
   grep -q SEARCH_CACHE_ENABLED search-service/.env || echo "SEARCH_CACHE_ENABLED=true" >> search-service/.env

   # Python deps (both venvs) — only if requirements changed since last deploy:
   cd onboarding-service && .venv/bin/pip install -r requirements.txt && cd ..
   cd search-service && .venv/bin/pip install -r requirements.txt && cd ..

   sudo systemctl restart tp-onboard tp-search
   sudo systemctl status tp-onboard tp-search --no-pager
   ```
2. **Rebuild + ship the widget** — the per-turn latency POST lives in `AvatarWidget.jsx`, so the *built* widget on the box is also stale. Build locally (the 2GB box + Vite is risky — same reasoning as the embedding-concurrency=2 cap) and copy over:
   ```bash
   # local machine:
   cd www.teampop/frontend && npm ci && npm run build
   scp -r dist/* ubuntu@<lightsail-ip>:/home/ubuntu/sales_agent/www.teampop/frontend/dist/
   ```
3. **Verify the deploy landed**: `curl -s -o /dev/null -w "%{http_code}\n" https://api.teampop.com/api/turn-latency` should now be `405` (route exists, GET not allowed), not `404`.
4. Run a handful of real conversations (see `testing/manual_test_checklist.md` Section A), then pull `GET /api/latency-summary/agent_4901kwna71tve5nbyy85c8v20yre?store_id=9cec7cd0-9252-4aa2-985b-71c2a42018cb` and use those numbers — not guesses — to decide which remaining scorecard item (turn_eagerness re-test, reranker limiting, proxy-hop removal, Lightsail resize) actually matters.
5. Lightsail instance resize and LLM-model change are explicitly **deferred** per user instruction (2026-08-12/13) — do not do either without being asked again.
6. Separately (not blocking the above): `agent_requests` table doesn't exist on this Supabase project at all — the whole client-acquisition admin flow (`/api/requests`, `/api/process`, etc.) is broken for onboarding any *next* client through the public form. Not urgent for xfused (its agent was created directly), but should be fixed before onboarding client #2. See roadmap.md item #1.

### Context the Next Agent Needs
- The live agent's `language`/`tts.model_id`/`voice_id`/soft-timeout filler config no longer matches `create_agent()`'s old hardcoded defaults — this was intentional dashboard tuning, not a bug. Full rationale in `docs/agents/decisions.md` (2026-08-12 entry). Don't "fix" the live agent to match old code; the code was updated to match it instead.
- `update_agent()` (as opposed to `create_agent()`) already only PATCHes the sub-objects it's given (prompt+tools, or tts) — routine prompt/model swaps for xfused do NOT risk overwriting `turn`/`language`/`asr`. The risk is only if `create_agent()` is ever re-run for this store without `language="hi"` explicitly passed.
- Client feedback items #3/#5 (background noise / distraction) have **no server-side lever** — `asr.quality` only accepts `"high"`, no noise-suppression field exists on the agent. The widget also sets no explicit `getUserMedia` constraints (`noiseSuppression`/`echoCancellation`/`autoGainControl` are absent from `AvatarWidget.jsx` entirely). If Section B of the test checklist reproduces real problems, that's the fix path — client-side, not ElevenLabs config.
- Client feedback #2/#6 (more product detail) needs the client's promised files before any real work — description text is currently capped at 300 chars for the rerank doc (`search-service/main.py:407`), so richer data needs a payload-shape decision, not just more scraping.

### Attempted Approaches That Failed
- N/A this session — this was audit + targeted fixes, not exploratory implementation.

### Blockers / Open Questions
- No SSH access to the Lightsail box from this session — deploy steps above are a runbook for the human to execute, not something run directly.
- Whether `language="hi"` (vs. keeping `"en"` + presets) is the right long-term choice for xfused, or was a testing artifact that happened to work, is unverified — it's been live long enough to trust for now (10 real conversations, no reported garbled-English complaints), but flag if English-speaking users start sounding "off."

### Key Files
- `onboarding-service/routes/admin.py` — `/api/latency-summary` fix
- `onboarding-service/elevenlabs_agent.py` — `create_agent()` language param + soft-timeout alignment
- `docs/agents/decisions.md` — 2026-08-12 entry, full drift rationale
- `testing/manual_test_checklist.md` — test scenarios for this round

### Confidence
[x] Medium — approach works but has tradeoffs worth reviewing (the `language="hi"` choice is empirically validated by live usage, not independently re-verified this session)

### Test Command
```bash
curl -s -o /dev/null -w "%{http_code}\n" https://api.teampop.com/api/turn-latency  # expect 404 until deployed, 405 after
```

---

## Handoff — 2026-06-19

**From:** Claude (Sonnet 4.6)
**To:** any
**Task:** Two performance refactors (A: search-service, B: pipeline + products) + enterprise architecture blueprint
**Ticket:** N/A (perf audit follow-up)

### Current Progress
- 40% — audits complete, plan written, code not yet executed

### What Was Done
- Full codebase audit across 3 branches → `docs/audit-2026-06-19.md`
- Performance audit (3 CRITICAL, 6 HIGH, 6 MEDIUM, 6 LOW) → `docs/perf-audit-2026-06-19.md`
- Complete implementation plan for both refactors → `docs/refactor-plan-2026-06-19.md`
- Read all relevant source files: `search-service/main.py`, `onboarding-service/services/products.py`, `onboarding-service/pipeline.py`, `elevenlabs_agent.py`, `error_codes.py`, requirements.txt files

### What Remains — Refactor A (`search-service/main.py`)
1. Write complete file (see `docs/refactor-plan-2026-06-19.md` Section "REFACTOR A" for exact spec)
2. Key additions: `_TTLCache`, `_Metrics`, `GET /metrics`, `_log_search_result()`, `_request_id_ctx` + filter, `_check_webhook_secret` Depends, `ALLOWED_ORIGINS` CORS, Pydantic 422→400 handler, `asyncio.to_thread()` in `/product-details`, semaphore init in startup hook
3. Verify: start search-service, hit `/metrics`, hit `/search` twice (second should log `[CACHE HIT]`), hit `/product-details`

### What Remains — Refactor B (`services/products.py` + `pipeline.py`)
1. Write `onboarding-service/services/products.py`: add `BuildProductsResult`, `_parse_product_metadata`, `_download_images_parallel` (ThreadPoolExecutor max 5), refactor `build_product_rows` into 4-phase pipeline
2. Write `onboarding-service/pipeline.py`: add `_timed_step` context manager, `_create_agent_with_retry` (3 attempts, 2s/4s backoff), wrap each step with `_timed_step`, add structured completion log
3. Verify: run a full onboard against a test store, confirm parallel downloads in logs, confirm step-timing JSON lines, confirm retry log if ElevenLabs fails

### What Remains — Enterprise Architecture Blueprint (interrupted)
The user asked a 4-part architectural question (structural decoupling, state/storage scaling, network/edge optimization, migration roadmap). The request was interrupted at `/compact`. Resume by answering all 4 sections with specifics for: FastAPI + Python, Supabase pgvector, ElevenLabs Conversational AI, React Shadow DOM widget. Target: 50–500 concurrent voice sessions.

### Context the Next Agent Needs
- **No code changes have been made yet** — audits and plan are docs only
- The plan doc (`docs/refactor-plan-2026-06-19.md`) is the authoritative spec — read it before writing code
- `build_product_rows` return type changes from `List[ProductRow]` → `BuildProductsResult` — must update both `products.py` and `pipeline.py` together
- `pipeline.py` remains synchronous — no async needed; parallel downloads use `concurrent.futures.ThreadPoolExecutor`, not asyncio
- `cachetools` is NOT in `search-service/requirements.txt` — the plan uses a pure Python `_TTLCache` class instead (no new dependencies)
- The user prefers seeing the plan before execution ("make plan ready and have doc of that plan")

### Attempted Approaches That Failed
- Direct file write for `search-service/main.py` was rejected by user — user wanted plan doc first before any code is written

### Blockers / Open Questions
- None. Plan is fully specified. User needs to approve before code is executed.

### Key Files
- `docs/refactor-plan-2026-06-19.md` — complete spec for both refactors (READ THIS FIRST)
- `search-service/main.py` — Refactor A target (~534 lines currently)
- `onboarding-service/services/products.py` — Refactor B target part 1 (~194 lines)
- `onboarding-service/pipeline.py` — Refactor B target part 2 (~151 lines)
- `search-service/requirements.txt` — confirm no new deps needed (cachetools not present)

### Confidence
[x] High — approach is solid, plan is detailed, pre-reads complete

### Test Command
```bash
# After Refactor A — verify cache is working
cd search-service && source .venv/bin/activate && python main.py &
curl -s http://localhost:8006/metrics | python3 -m json.tool
curl -s -X POST http://localhost:8006/search \
  -H "Content-Type: application/json" \
  -d '{"store_id":"<valid-uuid>","query":"test"}' | python3 -m json.tool
# Second call should show [CACHE HIT] in logs

# After Refactor B — run onboarding and check logs for step timing
cd onboarding-service && source .venv/bin/activate && python main.py &
curl -X POST http://localhost:8005/onboard \
  -H "Content-Type: application/json" \
  -d '{"url":"<shopify-store-url>"}' | python3 -m json.tool
# Logs should contain pipeline_step JSON lines and onboard_complete summary
```

---

## Handoff — 2026-03-30

**From:** Claude Code (Opus 4.6, session creating docs)
**To:** any
**Task:** Initial documentation setup — `docs/CLAUDE.md` + `docs/COLLABORATIVE.md` + `docs/agents/` folder
**Ticket:** N/A (documentation task)

### Current Progress
- 100% complete for this task

### What Was Done
- Created `docs/CLAUDE.md` — full architecture reference guide for AI agents (architecture, services, DB schema, conventions, gotchas, ADL, changelog)
- Created `docs/COLLABORATIVE.md` — multi-agent coordination hub with onboarding checklist, scope ownership map, cross-reference index
- Created `docs/agents/decisions.md` — append-only architectural decisions log, pre-populated with 7 key decisions
- Created `docs/agents/memory.md` — active WIP state file with template and recent history
- Created `docs/agents/constraints.md` — 14 hard rules covering system integrity, widget, DB, scraper, code quality, process
- Created `docs/agents/handoff.md` — this file

### What Remains
- Nothing from this documentation task. Future agents should keep these files updated.

### Context the Next Agent Needs
- These files are the authoritative agent coordination layer for this project
- `CLAUDE.md` covers static architecture info; `agents/` folder covers dynamic state
- `memory.md` should be updated at the start and end of every significant session
- `decisions.md` is append-only — never delete entries, just mark superseded

### Key Files
- `docs/CLAUDE.md` — architecture, services, gotchas
- `docs/COLLABORATIVE.md` — entry point and coordination hub
- `docs/agents/decisions.md` — architectural decisions
- `docs/agents/memory.md` — live WIP state
- `docs/agents/constraints.md` — hard rules
- `docs/agents/handoff.md` — this file

### Confidence
[x] High — documentation is complete and verified

### Test Command
```bash
# Verify all files exist
ls docs/CLAUDE.md docs/COLLABORATIVE.md docs/agents/decisions.md docs/agents/memory.md docs/agents/constraints.md docs/agents/handoff.md
```
