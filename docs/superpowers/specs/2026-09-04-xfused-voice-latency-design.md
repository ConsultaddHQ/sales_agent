# Xfused voice-agent latency — design

**Date:** 2026-09-04  
**Branch basis:** `release/xfused-pilot`  
**Status:** Approved 2026-09-04. Implementation plan: `docs/superpowers/plans/2026-09-04-xfused-voice-latency.md`.  
**Audience:** India-only shoppers (north / south / central). Not overseas.

---

## 1. Problem

The live Xfused voice agent is too slow to take to production as a conversational experience. The target feel is a human conversation: the shopper stops speaking, the agent shows it heard them, search/reply starts immediately, products and speech stay aligned.

Constraints from the live system:

- ElevenLabs Conversational AI region is not something we can pick in-dashboard for this account (global routing since Feb 2026; India residency is Enterprise-only).
- App + search run on AWS Lightsail Mumbai (`api.teampop.com`). Supabase project `jchigqerypjwmszslzke` is used by that stack. Do not move services overseas “to get closer to ElevenLabs” without a measured webhook RTT bottleneck — that would hurt India.
- A latency package (search cache, 1.2s soft-timeout, per-turn `turn_latency` / `search_latency`) is **already on this branch** (`03ef0af` and follow-ups) but was **never deployed** to `api.teampop.com` as of 2026-08-13. Live still looked like pre-`03ef0af` (turn-latency 404; tracking tables empty despite traffic). Further tuning without that deploy produces meaningless numbers.

GPT-Pet-style full UI rewrite is **out of this spec**. It is Phase 2, gated on latency ship-gate below.

---

## 2. Goals and non-goals

### Goals

- Cut perceived request–response latency as far as the India topology allows.
- **Heard-you:** UI shows listening → thinking as soon as the user stops speaking; voice uses platform soft-timeout filler only (no LLM “searching…” chatter before tools).
- Search turns: carousel updates **before** product speech (`search_products` → `update_products` → speak).
- Measure every turn so each lever has a before/after `config_variant`.
- Failed search: dedicated UI state, not a stuck “Thinking…” orb.

### Non-goals (this spec)

- Replacing the orb with a GPT-Pet-inspired UI (Phase 2).
- Re-enabling `turn_eagerness: eager` / `speculative_turn: true` / `optimize_streaming_latency: 3` on the **live** Xfused agent without a copy-agent experiment (those were reverted for real regressions).
- Moving Supabase or Lightsail to US/EU by default.
- Changing the embedding model (`all-MiniLM-L6-v2` / 384-d) or `hybrid_search_products` contract.
- Onboarding the next merchant via `agent_requests` (table missing on this Supabase project; separate roadmap item).

---

## 3. Success metrics

Instrument: widget `User→AI` / `User→Products`; search-service `search_ms` breakdown; `GET /api/latency-summary/{agent_id}?store_id=…` grouped by `config_variant`.

Live Xfused ids (pilot):

- Agent: `agent_4901kwna71tve5nbyy85c8v20yre`
- Store: `9cec7cd0-9252-4aa2-985b-71c2a42018cb`

**Dead-air:** `User→Products − User→AI > 1500 ms` on a search turn (voice describing products before carousel).

| Bar | First useful feedback (filler or speech) | User→Products (search turns) | Dead-air | 1002 kills | `update_products` miss |
|-----|------------------------------------------|------------------------------|----------|------------|-------------------------|
| **Ship gate (B)** | p95 ≤ 1.2s | p95 ≤ 3.5–4s | < 10% | < 5% | < 10% |
| **Stretch (A)** | p95 ≤ 0.8s | p95 ≤ 2.5s | same | same | same |

Go-live is **B**. **A** is the directional target, not a blocker if B holds and A is close.

India mix: Wi‑Fi **and** 4G. Same numeric gate for both; 4G may miss A while still passing B. Do not loosen B for 4G — if 4G fails B, that is a real ship blocker (client users are on mobile).

Historical context (not the live scoreboard): 2026-04-17 Haiku A/B median User→Products ~3.4s; search_ms after indexes ~1s (India↔Supabase floor at the time). Re-measure after Phase 0; do not treat those as current production truth.

---

## 4. Architecture

Keep Mumbai colocation. Shopper (India) ↔ ElevenLabs (unknown POP, global routing) ↔ `https://api.teampop.com` (Caddy → onboarding `:8005` → search `:8006`) ↔ Supabase. Embed + cross-encoder rerank stay **on the Lightsail box**.

### Phase 0 — Deploy what is already coded (prerequisite)

Human on Lightsail (this cloud workspace has no SSH and no `.env` files):

1. `git checkout release/xfused-pilot` (or this spec’s follow-up branch once merged) and pull.
2. Set distinct tags **before** restart, e.g. `LATENCY_CONFIG_VERSION=v2-cache-softtimeout`, `SEARCH_CONFIG_VERSION=v2-cache`, `SEARCH_CACHE_ENABLED=true`.
3. Restart `tp-onboard` / `tp-search`. Rebuild widget (`dist/`) and copy to the box if Vite is too heavy on 2GB.
4. PATCH the live agent via existing `update_agent()` so prompt/tools/soft-timeout match code. Do **not** wipe live `language=hi` + `eleven_flash_v2_5` (intentional dashboard tuning; code already accepts `create_agent(language=…)`).
5. Pre-flight: `GET https://api.teampop.com/api/turn-latency` → **405** (not 404). Then a few real conversations must produce rows in `turn_latency` / `search_latency`.

Until step 5 is true, do not spend time on region moves or extra levers.

### Phase 1 — Cut perceived cycle time against numbers

Order of work after a baseline `config_variant`:

1. Confirm cache hits on repeat queries (`search_latency.cache_hit`).
2. Widget “heard you”: THINKING on **every** turn (search and non-search), faster than today’s **500 ms** silence timer in `AvatarWidget.jsx`.
3. Dedicated **SEARCH_FAIL** UI when the search webhook errors (not empty catalog).
4. Optional Caddy `handle /search*` → `localhost:8006` if proxy overhead shows in `proxy_total_ms − search_ms` (local hop is expected to be tiny; only do this if logs justify it).
5. Extra levers, **one tagged experiment + rollback each** (see §6). Region/Supabase move only if ElevenLabs→Mumbai webhook RTT dominates after 1–4.

### Phase 2 — UI rewrite (gated)

New GPT-Pet-inspired UI instead of the orb. Starts only after ship gate B is met (or explicitly waived in writing). Not designed in this document.

---

## 5. Components

| Unit | Responsibility | Depends on |
|------|----------------|------------|
| Widget (`AvatarWidget.jsx`) | Mic, orb states, `update_products`, fire-and-forget `POST /api/turn-latency` every cycle | ElevenLabs SDK, `api.teampop.com` |
| ElevenLabs agent | STT, LLM, TTS, webhook `search_products`, client `update_products`, soft-timeout filler | `SEARCH_API_URL` baked at create/update |
| Onboarding `:8005` | Widget/static, `/search` proxy, `/api/turn-latency`, `/api/latency-summary` | Search `:8006`, Supabase |
| Search `:8006` | Cache, embed, `hybrid_search_products`, rerank, `search_latency` insert | Supabase, local models |
| Caddy | TLS + route all of `api.teampop.com` to `:8005` today | systemd units |
| Human / Lightsail | Deploy, `.env`, live voice tests (Wi‑Fi + 4G) | SSH (not this cloud agent) |

**Heard-you (locked):**

- Voice: `soft_timeout_config.timeout_seconds = 1.2`, static/rotating fillers, `use_llm_generated_message: false`, `max_soft_timeouts_per_generation: 2`. No LLM ack before tools.
- UI: LISTENING while user is speaking; THINKING as soon as they stop (search **and** non-search). Today’s 500ms debounce is too slow for “instant”; Phase 1 should cut it (target: on `user_transcript` / speech-end, or ≤150ms silence) without flickering on brief pauses.

**Telemetry (locked):**

- Every turn: POST User→AI when first AI audio/text arrives.
- User→Products only when `update_products` fires.
- POST is non-blocking; conversation never waits on it.
- Server stamps `config_variant` from env, never from the client.

---

## 6. Extra levers (in scope, experiment-gated)

Not a bundle. One `LATENCY_CONFIG_VERSION` / `SEARCH_CONFIG_VERSION` bump per change. Rollback if interruption complaints, 1002 spike, dead-air >10%, or User→Products p95 worse than the previous variant.

| Lever | How | Default |
|-------|-----|---------|
| Caddy `/search*` → `:8006` | Commented pattern in `deploy/Caddyfile` | Off until logs show proxy waste |
| `turn_eagerness` / `speculative_turn` | **Copy agent**, not live Wrina first | Off on live until copy passes listening/interruption check |
| Lightsail resize | If `queue_wait_ms` / embed timeout is high | Off until search_latency proves CPU queue |
| LLM / TTS swap | Only if User→AI still far from A after search is at network floor | Off; Haiku remains default |
| Prompt trim | Last; quality risk | Off until measured |
| Region / EL India residency | Only if webhook RTT is the proven bottleneck | Off; keep Mumbai |
| Mic constraints | `getUserMedia` noiseSuppression / echoCancellation / autoGainControl | Optional if Section B noise tests fail |

---

## 7. Data flow (one search turn)

```
User speaking          → widget LISTENING
User stops             → widget THINKING immediately (UI ack)
ElevenLabs STT → LLM
Silence > ~1.2s        → static filler TTS (“One second, Looking that up.” / rotate)
LLM search_products    → POST https://api.teampop.com/search
                         Caddy → :8005 proxy → :8006
                         cache hit? else embed → RPC → rerank
                         persist search_latency
                         JSON back to ElevenLabs
LLM update_products    → carousel; POST turn-latency (AI + products)
LLM speaks products    → widget AGENT_SPEAKING
```

**Alignment rule:** no product speech between search result and `update_products`.

**Non-search turns** (e.g. “tell me more about the second one”, add to cart, greeting): no webhook. Still THINKING on speech-end. Still POST User→AI. No User→Products unless `update_products` runs. These turns do **not** skip UI ack or telemetry — skipping neither saves milliseconds (THINKING is not a wait; POST is fire-and-forget).

---

## 8. Error handling

| Failure | Behavior |
|---------|----------|
| Search webhook 5xx / timeout / embed fail | ElevenLabs `tool_error_handling_mode: auto`. Agent says a short honest miss. Widget shows **SEARCH_FAIL** (see trigger below). Persist `search_latency` on error when possible. |
| Zero catalog hits (successful 200, empty list) | Existing prompt: one silent reinterpret + one retry, then “not carried.” UI: empty results, **not** SEARCH_FAIL (that state is for infrastructure failure). |
| Soft-timeout / long tools | Filler at 1.2s, max 2 per generation. `cascade_timeout_seconds: 8` unchanged. |
| ElevenLabs 1002 | Hard fail in the test scoreboard. Roll back the last lever if rate rises. |
| `POST /api/turn-latency` fails | Log/warn; never block speech. |
| Stale cache | 5 min TTL OK for xfused. Restart search-service clears in-memory cache. Set `SEARCH_CACHE_ENABLED=false` if a catalog change must show immediately. |
| Widget disconnect | Existing session resume. Do not retry-stack searches. |

**SEARCH_FAIL (Phase 1, orb-era):** new visual state next to LISTENING / THINKING / AGENT_SPEAKING / ERROR. Distinct copy (e.g. “Couldn’t search — try again”). User retries by speaking again (clears SEARCH_FAIL on next LISTENING). Connection-level ERROR stays separate (WebSocket down).

**SEARCH_FAIL trigger (single path):** webhook failures are visible to the LLM, not to the widget. On the **error path only**, the LLM must immediately call a new client tool `show_search_error` (`expects_response: false`) before or instead of product speech. The widget handler sets SEARCH_FAIL. Happy-path search does not gain a tool hop. Fallback if the LLM skips the tool: THINKING with no `update_products` and no agent audio for `cascade_timeout_seconds` (8s) → SEARCH_FAIL. Empty 200 results must **not** call `show_search_error`.

---

## 9. Testing

**Split of work**

- Human: live mic on xfused, India Wi‑Fi and 4G; Lightsail pull/restart.
- Agent session: HTTP checks and `/api/latency-summary` after human sync. This cloud workspace currently has only `.env.example` — no keys. Do not commit secrets.

**Pre-flight (every run):** `GET /api/turn-latency` → 405. If 404, stop.

**Scenarios** (extend `testing/manual_test_checklist.md` Section A):

- A1 cold first search vs A2 repeat query (must show `cache_hit` if cache is live).
- Narrow first-hit search (full embed→RPC→rerank).
- Non-search turn: THINKING still, no `/search` log line.
- Zero hits vs **forced search 5xx**: SEARCH_FAIL vs empty-results, not stuck THINKING.
- 5+ turn session: p95 must not collapse on later cycles.
- Copy-agent eagerness slice only after Phase 0 baseline exists.

**Automated after code changes:** `python3 -m py_compile` on touched Python; widget `npm run build` if `AvatarWidget.jsx` changes; add focused tests if search cache or `/api/turn-latency` behavior is edited. Full voice e2e stays manual (ElevenLabs + mic).

**Pass:** ship gate B on the post-lever `config_variant`, both networks, plus SEARCH_FAIL UX check. Stretch A is reported, not required to close Phase 1.

---

## 10. Env and human setup

Human-configured (gitignored). Examples already in `.env.example`:

**Onboarding:** `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `ELEVENLABS_TTS_MODEL`, `ELEVENLABS_LLM_MODEL`, `SEARCH_API_URL` / public URLs = `https://api.teampop.com` in prod, `SUPABASE_*`, `LATENCY_CONFIG_VERSION`.

**Search:** `SUPABASE_*`, `SEARCH_CACHE_*`, `SEARCH_CONFIG_VERSION`, `RERANK_*`, `SEARCH_EMBEDDING_CONCURRENCY`.

This cloud agent will not invent Lightsail SSH. After the human deploys, verification is curl + summary API + their conversation samples.

---

## 11. Implementation notes (for the later plan, not this PR’s code)

When implementation starts (after spec approval + implementation plan):

- Prefer existing patterns: `soft_timeout_config` in `elevenlabs_agent.py`, cache in `search-service/main.py`, `_markProductsArrived` in `AvatarWidget.jsx`.
- SEARCH_FAIL: extend `getVisualState` / status pill; register client tool `show_search_error`; add the same call to `PROMPT_CLAUDE` (xfused) only — do not port other prompt templates in this spec.
- Do not PATCH live agent `language` back to `en`.
- Bump version env vars on each deploy.
- Keep `all-MiniLM-L6-v2` and `hybrid_search_products` unchanged.

---

## 12. Open questions (resolved in brainstorming)

| Topic | Decision |
|-------|----------|
| Optimize for | Overall snappy feel + carousel alignment + fast hear→ack→search→speak |
| Geography | India only |
| Bars | B ship, A stretch |
| Heard-you | Soft-timeout voice + UI thinking; no LLM pre-tool chatter |
| Non-search turns | Still THINKING + User→AI telemetry |
| Failed search UI | Dedicated SEARCH_FAIL |
| Extra levers | In scope, experiment-gated, not default-on |
| Live access | Human pulls Lightsail; no SSH required for this agent |
| GPT-Pet UI | Phase 2 after B |
