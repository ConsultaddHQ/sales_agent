# Architectural Decisions Log

> **Append-only.** Never delete entries. If a decision is superseded, mark it `Status: Superseded` and add a new entry.
> **Format:** Follow the structure used in the existing entries below.
> **Purpose:** Prevent agents from re-litigating or unknowingly reversing prior decisions.

---

## 2026-07-20: Per-turn latency tracking via `config_variant` tagging, not ad-hoc log-scraping

- **Decision:** Added two new Supabase tables — `turn_latency` (widget-reported: per-voice-cycle `latency_first_ai_ms`/`latency_products_ms`, sent immediately via `POST /api/turn-latency` rather than only once at session end) and `search_latency` (search-service-reported: `total_ms`/`embedding_ms`/`rpc_ms`/`queue_wait_ms`/`cache_hit`, persisted server-side so it doesn't depend on the widget's own POST landing). Both carry a `config_variant` text column, stamped server-side from a `LATENCY_CONFIG_VERSION` / `SEARCH_CONFIG_VERSION` env var — never client-supplied. `session_feedback` also got a `config_variant` column for the same reason. Added `GET /api/latency-summary/{agent_id}` (admin-gated) returning avg/p50/p95/max grouped by `config_variant`, resolving `store_id` from `agent_id` via `agent_requests` to join the two tables' different keys.
- **Context:** Client reported the agent "feels slow" and asked specifically to be able to tell, with data, whether each latency fix actually helps. Existing instrumentation (`AvatarWidget.jsx` `_markProductsArrived`) only console.log'd per-cycle numbers and persisted just the *last* cycle's value to `session_feedback` at session end — no history, no way to compare before/after a config change.
- **Rationale:** A version tag stamped server-side (not inferred from timestamps) is the only way to reliably answer "did change X help?" after the fact, especially once multiple changes ship close together. Two tables instead of one because the widget-reported and search-service-reported numbers answer different questions (perceived latency vs. backend truth) and the widget's POST can fail to arrive (network, ad blockers) while the search-service's own insert cannot.
- **Alternatives considered:** (a) Parse production `journalctl` logs for `X-Search-Duration-Ms` — already exists (`testing/load/latency_report.sh`) but is a manual pull, not a live dashboard, and doesn't capture widget-side (STT+LLM+TTS) time at all. (b) Extend `session_feedback` with a JSON array of per-cycle timings — rejected, breaks the existing one-row-per-session shape and every existing query against that table.
- **Consequences:** `create_latency_tracking_table.sql` must be run in Supabase before these columns/tables exist — same schema-drift-tolerant insert pattern as `session_feedback` is used, so a missing column degrades gracefully instead of losing the whole row. Any future latency-affecting change (prompt trims, model swaps, TTS/turn settings) should bump `LATENCY_CONFIG_VERSION` (and `SEARCH_CONFIG_VERSION` if backend-side) on deploy so its rows are distinguishable in `/latency-summary`.
- **Status:** Active
- **Agent/Author:** Claude (Opus 4.6)

---

## 2026-07-04: Multilingual agents use language_presets + language_detection, not a multilingual base TTS model

- **Decision:** English-primary agents keep `tts.model_id = eleven_flash_v2` (never `eleven_flash_v2_5` or `eleven_multilingual_v2`). Hindi/Tamil support is added via two confirmed-API-settable fields on `create_agent()`: `additional_languages` (populates `conversation_config.language_presets`, a sibling of `agent`, each with a translated `first_message` override) and `hinglish_mode` (boolean on `conversation_config.agent`, blends Hindi-English when the active language is Hindi). Both also proved safe to send at `create_agent()` time without touching `update_agent()`.
- **Context:** The 2026-04-17 latency A/B test picked `eleven_flash_v2_5` as the TTS default and a comment claimed it was needed for "32 languages incl. Hindi + Tamil" — this was never actually validated against a live English-primary agent. Attempting to PATCH an English agent's `tts.model_id` to `eleven_flash_v2_5` got a hard 400: `"English Agents must use turbo or flash v2"`. Also corrected a prior wrong assumption (roadmap 2026-07-03 entry) that `language_presets` was UI-only — it is API-settable on both create and update, per ElevenLabs docs (`docs/eleven-agents/customization/tools/system-tools/language-detection`, `.../voice/customization/language`).
- **Rationale:** The base TTS model choice and the multilingual capability are orthogonal — language switching is handled by `language_presets` + the `language_detection` system tool at the conversation level, not by picking a "multilingual" base model (which the platform disallows for English-primary agents anyway).
- **Alternatives considered:** (a) Set agent's primary `language` to something other than `en` — rejected, the store's default customer is English-speaking. (b) Per-language TTS override via `tts.supported_voices[].model_family` — plausible per the multi-voice-support docs but unverified schema; not attempted, flagged for a future pass if Hindi/Tamil pronunciation quality on `eleven_flash_v2` turns out to be poor in live testing.
- **Consequences:** `.env.example`, `ELEVENLABS_TTS_MODEL` default, and the `elevenlabs_agent.py` comment block were all corrected to `eleven_flash_v2`. Telugu remains unsupported by any of ElevenLabs' real-time conversational models (`eleven_flash_v2`, `eleven_flash_v2_5`, `eleven_multilingual_v2` all exclude it; only the non-realtime "Eleven v3" lists it) — not offered until the user provides contrary evidence they mentioned having (an ElevenLabs "v3 conversation" claim) or ElevenLabs ships real-time Telugu support.
- **Status:** Active
- **Agent/Author:** Claude

---

## 2026-07-03: Rerank relevance cutoff with browse-intent bypass

- **Decision:** After the cross-encoder rerank in `search-service/main.py`, `/search` no longer returns a fixed top-N; it applies a **relevance cutoff** — keep only results whose score is within `RERANK_SCORE_MARGIN` (default 4.0, env-tunable) of the top score — **except for browse/broad queries**, which bypass the cutoff and return the full ranked set. Browse intent is detected by phrase (`_BROWSE_TERMS`: "everything", "all product", "full range", …) or a very low top score (`< 0`). Always keeps ≥1; the reranker-disabled/error fallback paths are unchanged.
- **Context:** On small catalogs a specific query ("moisturizer") returned every product (recall-favoring RRF returns all; the reranker sorted but never cut), so the carousel showed 6 while the agent narrated 2 — a UX mismatch. A naive cutoff then over-corrected: the agent expands "show me everything" into queries like `"all products facewash moisturiser lip balm"` (middling scores), and the margin trimmed the tail → only 4 of 6 shown.
- **Rationale:** A **relative** margin (not an absolute threshold) adapts without query classification — specific queries have a score gap (tail dropped), vague queries have clustered scores (all kept). The browse bypass handles the case that breaks it: enumerated/expanded browse queries that score middling but must return everything. This makes `/search` results (and thus what `update_products` renders) match user intent.
- **Alternatives considered:** (a) Fixed top-N — doesn't distinguish relevant from filler. (b) Absolute score threshold — brittle; zeroes out vague queries. (c) Agent-side subsetting of `update_products` — rejected; agents subset unreliably and it desyncs narration from the carousel; the prompt requires the full array.
- **Consequences:** `/search` now returns a variable count. Tune `RERANK_SCORE_MARGIN` from the `Reranked … browse=… kept N … kept_scores=[…]` log line; set very high (~999) to restore old "return all ranked" behavior. Known edge: a browse request expanded with **no** browse keyword *and* a positive top score could still trim — the durable fix (tracked in roadmap) is an explicit agent-passed browse flag. `RERANK_SCORE_MARGIN` documented in `search-service/.env.example`.
- **Status:** Active
- **Agent/Author:** Claude Opus 4.8

## 2026-06-25: Search-quality overhaul — enriched search_text + RRF hybrid RPC + cross-encoder reranker

- **Decision:** Three coordinated changes to fix attribute-precision failures (e.g. "white polo shirt" returning wrong colors). (1) **Enriched `search_text`**: onboarding now embeds and indexes `name + product_type + color/size/material/style option values + tags + description` (`_build_search_text()` in `onboarding-service/services/products.py`), persisted to a new `products.search_text` column. (2) **RRF hybrid RPC**: `hybrid_search_products` rewritten (`migrations/2026-06-25_search_text_and_fts.sql`) to fuse a vector CTE (HNSW top-50) and an FTS CTE (`websearch_to_tsquery` over `search_text`) via Reciprocal Rank Fusion (k=60); keeps all keyword hits + vector hits above a low `p_min_score` (0.15) to favor recall; returns `metadata` + `local_image_path`. (3) **Cross-encoder reranker**: `shared/reranker.py` (lazy `CrossEncoder` singleton, default `cross-encoder/ms-marco-MiniLM-L-6-v2`); search-service fetches `RERANK_CANDIDATES` (30) then reranks to top-5, with graceful fallback to Stage-1 order on error/timeout and a `RERANK_ENABLED` kill-switch.
- **Context:** Color/type/variant attributes lived only in `metadata` JSONB — invisible to both the embedding (`name + description` only) and the FTS index. all-MiniLM-L6-v2 is too coarse to separate "white" from "black" pants. The old RPC used `plainto_tsquery` (AND-ed all tokens → one stray word zeroed the text side). No reranker existed.
- **Rationale:** Two-stage retrieve-then-rerank is the 2026 standard (+15–30% accuracy). Enriching `search_text` makes attributes retrievable at all; RRF + `websearch_to_tsquery` fixes recall; the cross-encoder reads (query, product) jointly to recover precision. Self-hosted reranker chosen over a managed API to avoid India→US latency, per-call cost, a new secret, and data leaving infra. **No embedding-model change** — stays all-MiniLM/384, honoring constraint #1.
- **Alternatives considered:** (a) Upgrade the embedding model (BGE-M3/text-embedding-3) — deferred; triggers a 384→N dimension migration + full re-embed (constraint #1), not needed once enrichment + rerank land. (b) Managed rerank API (Cohere/Jina) — rejected for latency/cost/secret/data-egress. (c) Switch to a dedicated vector DB — rejected; pgvector is fine at ~250 products/store.
- **Consequences:** Requires running `migrations/2026-06-25_search_text_and_fts.sql` (drops prior overloads, adds column + GIN index + new function) **and re-onboarding stores** to populate enriched `search_text`/embeddings (existing rows are backfilled with `name + description` so they keep working). The committed migration is now the **source of truth** for the RPC; the `SHOPIFY_FLOW_COMPLETE.md` block is marked superseded. RPC `similarity` is cast to `float` to match the return type. `search-service` first start downloads the ~80MB reranker; warmup loads it off the hot path. `RERANK_*` env vars documented in `search-service/.env.example`.
- **Status:** Active
- **Agent/Author:** Claude

---

## 2026-06-19: Carousel click-to-agent context disabled by default

- **Decision:** Clicking a carousel thumbnail no longer sends a `[CAROUSEL UPDATE]` message to the ElevenLabs voice agent. The visual update (`setActiveIndex`) still fires, but `syncMainProduct()` is not called. The function is kept in the codebase with a comment — re-enable by uncommenting one line in `AvatarWidget.jsx` `onClick`.
- **Context:** When users browsed carousel thumbnails by clicking, the agent would interrupt its current turn and narrate the newly clicked product. This was reported as intrusive — users want to visually browse without triggering an agent response each time.
- **Rationale:** Carousel clicks are a browse gesture, not a "tell me about this" intent signal. The agent already narrates products when it calls `get_product_details` and focuses the carousel. Separating visual navigation from agent narration gives users control.
- **Alternatives considered:** (a) Keep the feature with a longer debounce — rejected, even 600ms was too short; clicks felt like they hijacked the conversation. (b) Only trigger if the user holds the click — rejected, adds undiscoverable UX friction. (c) Add a separate "info" button per thumbnail — deferred, may be added as an explicit CTA later.
- **Consequences:** Users can scroll/click through carousel thumbnails without triggering agent speech. To re-enable the feature, uncomment `syncMainProduct(latestProducts[idx])` in the `onClick` of the thumbnail map in `AvatarWidget.jsx`.
- **Status:** Active
- **Agent/Author:** Antigravity

---

## 2026-06-19: get_product_details must be followed by update_carousel_main_view (triple-lock enforcement)

- **Decision:** When the agent calls `get_product_details` to fetch product specifics, it MUST immediately follow up with `update_carousel_main_view` (using the product's zero-based index) BEFORE speaking. This is enforced at three levels: (a) the `get_product_details` tool `description` field, (b) the `## get_product_details` and `## update_carousel_main_view` sections in all five model system prompts, and (c) a new `# Guardrails` rule in all five prompts.
- **Context:** The agent was fetching product details and narrating them correctly, but the carousel main frame was not always focused on the described product — especially as conversation context grew and the LLM had to juggle more state. Users saw the agent describe a product while the carousel showed a different one.
- **Rationale:** Same pattern as the proven `search_products → update_products` chain: the LLM's tool-calling reliability under context pressure is best ensured by redundant, multi-level reinforcement. The tool description is seen at every call site; `## Tools` is read in context; `# Guardrails` receives highest model attention per ElevenLabs prompting guidance. Triple-locking means any one level alone can carry the rule if the others are missed.
- **Alternatives considered:** (a) Rely on the system prompt alone — rejected; this was the failing behavior for `update_products` too, before triple-lock was introduced. (b) Client-side hook: detect `get_product_details` tool call from websocket event and auto-fire `update_carousel_main_view` client-side — viable but adds complexity and couples frontend to backend tool names. (c) Make `get_product_details` a client-side compound tool — rejected; it's a webhook and must stay server-side.
- **Consequences:** All new agents created via `create_agent()` inherit this rule automatically. Existing agents need to be re-created to get the updated prompts and tool descriptions. The `update_carousel_main_view` tool description no longer says "fire-and-forget" — it's a required step after `get_product_details`.
- **Status:** Active
- **Agent/Author:** Antigravity

---

## 2026-06-12: Product image URLs are composed at read time and relayed via an explicit tool schema

- **Decision:** Two standing rules for product image URLs end-to-end:
  1. **Search composes the image URL at query time** from `local_image_path` + the service's configured `IMAGE_SERVER_URL`, and returns it as the canonical `image_url` (`search-service/main.py:360`, `p.local_image_url or p.image_url`). The absolute `image_url` baked into the DB at onboarding (`onboarding-service/services/products.py:109`) is treated as a fallback only — never the source of truth for the host.
  2. **Anything the ElevenLabs LLM must relay verbatim needs an explicit JSON-schema property.** The `update_products` client tool defines per-product `items.properties` (incl. `image_url`, required) so the model cannot drop long URLs. Opaque `items: {type: object}` is banned for data the UI depends on.
- **Context:** Product images 404'd in the voice widget. Root cause spanned four layers, but the durable lessons are these two: an absolute host stored in the DB goes stale (ngrok rotates), and the LLM silently drops long fields when a tool schema is opaque — the same failure class as the existing `store_id` UUID-truncation invariant.
- **Rationale:** Composing at read time means the image host follows whatever tunnel/domain the search service is configured with, with no DB migration or re-onboard. An explicit tool schema is the only reliable way to force the hosted LLM to forward exact values.
- **Alternatives considered:** (a) Re-onboard to rewrite DB URLs — rejected, fragile and repeats every tunnel change. (b) Trust the prompt to tell the LLM "pass the full array" — rejected, that was the failing behavior. (c) Pass only product IDs and have the widget re-fetch details — viable but a larger widget+endpoint change; deferred.
- **Consequences:** `search-service/.env` must set `IMAGE_SERVER_URL` (defaults to `localhost:8000` otherwise, which serves nothing in the single-tunnel setup). Future tools that feed the widget must schematize every field the UI reads. Follow-up: stop writing the absolute `image_url` at onboarding and store only the relative path.
- **Status:** Active
- **Agent/Author:** Claude

## 2026-04-17: Default ElevenLabs LLM = Claude Haiku 4.5 (winner of 6-model A/B test)

- **Decision:** The default value of `ELEVENLABS_LLM_MODEL` (used by every new ElevenLabs agent created via `ElevenLabsAgentCreator.create_agent` and `update_agent`) is now `claude-haiku-4-5`. Fallback hardcoded in `onboarding-service/elevenlabs_agent.py` in three spots (`create_agent`, `update_agent`, `_build_system_prompt`) and advertised in `onboarding-service/.env.example` with the full ranking.
- **Context:** After STEP 1/2/4 (warmup, HNSW+GIN indexes, tool-first prompt rule) landed, search was already at its India↔Supabase network floor of ~1s, but voice cycles still ran 3–15s on Gemini 2.5 Flash because of 2nd-turn reasoning lag and intermittent `closeCode 1002 "Generating the LLM response took too long"` session kills. STEP 3 of the plan (`~/.claude/plans/synchronous-churning-sky.md`) spun up six parallel agents — one per candidate LLM — against the same store and ran a fixed 10-prompt protocol (`testing/latency/README.md`).
- **Rationale:** Measured results, 10 cycles per model, same 10 prompts:
  - **claude-haiku-4-5: 100% tool reliability, median User→Products 3.4 s, 0 timeouts.** Winner on every axis of the three-axis frame.
  - gemini-2.5-flash-lite: close 2nd on speed (~2 s when it fires) but only ~67% tool reliability.
  - glm-45-air-fp8: 78% tool reliability, acceptable but slower (~5–8 s first cycle, ~3 s warm).
  - **gemini-2.5-flash (previous default): DQ** — 1 session hit the 1002 timeout, had an 18 s dead-air outlier.
  - **qwen3-30b-a3b: DQ** — only 2/10 `update_products` calls despite fast speech.
  - **gpt-4.1-nano: DQ** — 0/10 `update_products` calls. Searched, spoke, but never updated the carousel. Surprising given its strong tool-calling reputation on direct OpenAI API; appears to be an ElevenLabs-hosted-tier quirk.
  - Claude also handled the ordinal reference ("tell me more about the second one") correctly without triggering an unnecessary search — the only model to do so cleanly. User's subjective read ("more human, less silence") matched the numbers.
- **Alternatives considered:** (1) Keep Gemini 2.5 Flash and increase ElevenLabs `cascade_timeout` — rejected; it would just turn 1002 kills into longer waits rather than fixing the root cause. (2) Ship Qwen for speed — rejected by the protocol's hard-fail threshold (>10% tool misses). (3) Stay on Gemini and add client-side "wait for update_products before TTS" gating — rejected because fighting the model is worse than picking a model that behaves.
- **Consequences:**
  - Every new store onboarded via `POST /onboard` immediately gets Claude Haiku 4.5. Existing agents keep their baked-in model until upgraded via `testing/latency/upgrade_agent_model.py`.
  - Cost model shifts slightly: Claude Haiku 4.5 per-call cost is close to Gemini 2.5 Flash but the workload changes — no more retries or cascaded timeouts means fewer wasted tokens.
  - Prompt templates in `elevenlabs_agent.py` already route `PROMPT_CLAUDE` for any model string containing "claude" via `MODEL_PROMPT_MAP`.
  - `_verify_agent` now emits a warning when an agent is seen still running `gemini-2.5-flash`, pointing to the upgrade script.
  - Re-run the A/B matrix whenever ElevenLabs adds a new hosted model or an existing model is deprecated. The harness lives in `testing/latency/` and is designed for reuse.
- **Status:** Active
- **Agent/Author:** Claude

---

## 2026-04-17: Voice-Agent Prompt Contract — Tool-First-After-Result Rule Across All Models

- **Decision:** Every model prompt template (`PROMPT_GEMINI`, `PROMPT_QWEN`, `PROMPT_GLM`, `PROMPT_CLAUDE`, `PROMPT_GPT`) now carries one explicit rule in both the numbered procedure and the `# Guardrails` block: *"After a tool result arrives, the very next action must be the next tool call. Do not speak any words between the tool result and the next tool call. Filler BEFORE the first tool is fine."*
- **Context:** Even after STEP 2 dropped search to ~1s, widget logs showed 3–15s gaps between `User→AI` and `User→Products` on many cycles. The cause was Gemini calling `update_products` AFTER speaking a product description, so the carousel lagged the voice by 3–12 seconds. The old prompts said "search → update_products → describe" but did not explicitly forbid speech between the search result and `update_products`.
- **Rationale:** This rule is the minimal, model-agnostic change that aligns spoken output with UI state. It preserves natural conversation (filler before tools is still encouraged) while making the forbidden gap unambiguous. Putting the same text in both the procedure and `# Guardrails` matches ElevenLabs' prompting guidance — Guardrails are weighted higher, the procedure is what the model follows turn-by-turn.
- **Alternatives considered:** (1) Add a client-side timer that withholds agent audio until `update_products` fires — rejected because it adds UX complexity and fights the model instead of guiding it. (2) Reduce `soft_timeout` below 2.5s — rejected; the static filler is a safety net, not a fix. (3) Use two separate tools with `expects_response: true` to force sequencing — rejected because the current client-tool shape is correct and changing it risks regressions.
- **Consequences:**
  - Every new agent created via `create_agent()` picks up the new rule automatically; existing agents need to be re-created to inherit it.
  - The rule is consistent across all 6 candidate LLMs in the upcoming STEP 3 A/B matrix, so model comparison will be fair.
  - Prompts grew by ~150–300 chars each; all still under ElevenLabs' ~8 KB limit.
- **Status:** Active
- **Agent/Author:** Claude

---

## 2026-04-17: Supabase `hybrid_search_products` Rewritten to Use HNSW and GIN Indexes

- **Decision:** Replace the body of `public.hybrid_search_products(uuid, text, vector, numeric, int, float)` with a version that uses the canonical pgvector top-K pattern (`ORDER BY embedding <=> $query LIMIT 50`) for the vector CTE and a `to_tsvector(...) @@ plainto_tsquery(...)` filter for the text CTE. Add `products_fts_idx` — a GIN index on `to_tsvector('english', coalesce(name,'') || ' ' || coalesce(description,''))` — so the FTS filter actually uses an index. Function signature and return shape are unchanged.
- **Context:** The previous function body scanned all rows for a given `store_id` to compute cosine distances in the `SELECT` list (which bypasses HNSW) and built tsvectors at query time for every row (no GIN usage). Measured `search_ms` was 2100–3100 ms for a single store's ~250 products; `EXPLAIN ANALYZE` after the fix shows DB execution at 52 ms. Remaining ~1s is India↔Supabase network, which is outside DB control.
- **Rationale:** This is the smallest change that makes the existing indexes effective. It preserves the function's signature, its 0.6/0.4 hybrid weighting, and its FULL OUTER JOIN logic, so no service code changes are required. HNSW + GIN are now the durable contract: any future change to the RPC must keep them in use.
- **Alternatives considered:** (1) Add a result cache in search-service — deferred; would reduce repeat-query cost but not first-query cost. (2) Move Supabase to a closer region (Mumbai) — deferred; bigger ops change, affects every service. (3) Switch to a managed vector DB (Pinecone, Weaviate) — rejected for alpha; introduces a second datastore.
- **Consequences:**
  - Every future store onboarded automatically inherits the fast path — the indexes and function are schema-level, no per-store code change.
  - The tsvector expression in the GIN index and in the function body must stay identical; changing one without the other silently breaks the index match.
  - `p_min_score` default was kept at 0.2 in the new function (old default); callers passing 0.25 continue to work.
  - Products whose embedding is NULL are now excluded from the vector-matches CTE explicitly; previously they contributed 0 vector-score rows that got filtered later. Net output is the same but planning is cleaner.
- **Status:** Active
- **Agent/Author:** Claude

---

## 2026-04-14: Search Service Scaling via Async Endpoint + Thread Offload + Worker Processes

- **Decision:** Keep the existing synchronous Supabase Python client and sentence-transformer model, but make `POST /search` an async FastAPI endpoint that offloads embedding generation and the Supabase RPC call to `asyncio.to_thread()`. Add request rate limiting with `slowapi`, use thread-safe singleton initialization for shared clients/models, and run search-service with multiple Uvicorn workers outside reload mode.
- **Context:** Phase 2 infrastructure work needed better multi-user behavior. The widget already supports separate browser sessions, but the search service was still a synchronous single-process bottleneck: model inference and Supabase RPC calls both blocked the event loop, and the lazy shared singletons were not safe once requests started moving through worker threads.
- **Rationale:** This is the smallest reliable change that improves concurrency without forcing a risky async-Supabase migration in an early-alpha repo. `asyncio.to_thread()` keeps the FastAPI event loop responsive, worker processes add process-level concurrency, and thread-safe singleton creation prevents duplicate cold-start initialization under concurrent load.
- **Alternatives considered:** (1) Migrate to an async Supabase/client stack immediately. Rejected for now because it expands scope and would need wider validation across services. (2) Only add more Uvicorn workers. Rejected because each worker would still block internally on embedding/RPC work. (3) Add rate limiting only. Rejected because it protects the service but does not remove the core blocking path.
- **Consequences:**
  - `search-service/main.py` now requires `Request` in the search endpoint for `slowapi`.
  - Default local protection is `SEARCH_RATE_LIMIT=30/minute`; trusted/proxied deployments may need a different value or forwarded-IP handling.
  - `shared/db.py` and `shared/embeddings.py` now protect singleton initialization with locks.
  - Production-style runs should use `uvicorn main:app --workers 4` or `RELOAD=false` with `UVICORN_WORKERS=4`.
- **Status:** Active
- **Agent/Author:** Codex

---

## 2026-04-14: Phase 1 Voice UX — Two-Tool Contract + One-Turn Context-First Search

- **Decision:** Reduce ElevenLabs tool contract to exactly two tools (`search_products`, `update_products`) and shift prompting to a context-first flow: one natural clarifying turn before search by default, with immediate-search exceptions for specific or impatient requests.
- **Context:** The prior 4-tool setup (`update_carousel_main_view`, `product_desc_of_main_view`) created extra coordination complexity and scripted behavior. First-turn search also surfaced a 4-6s latency gap that felt robotic.
- **Rationale:** UI carousel navigation and product card display can be handled fully client-side from `latestProducts` and `activeIndex`, so dedicated agent tools are unnecessary. A single clarifying exchange makes openings feel human and improves query quality while masking search latency. Immediate search is still preserved when user intent is already specific or explicitly impatient.
- **Consequences:**
  - `onboarding-service/elevenlabs_agent.py` now publishes two tools only.
  - All model prompt templates now enforce `search_products -> update_products -> describe`.
  - Agents resolve "the second one" style references from latest shown results context instead of calling a carousel-nav tool.
  - Widget removed `update_carousel_main_view` and `product_desc_of_main_view` handlers and now auto-updates subtitle from active product state.
- **Status:** Active
- **Agent/Author:** Codex

---

## 2026-04-09: Tools-First Gemini Prompt + Latency/Interruption Settings Overhaul

- **Decision:** Rewrote `PROMPT_GEMINI` to remove "say a brief phrase first" step. Agent now calls tools immediately (search_products → update_products → speak). Updated conversation settings: `turn_eagerness: "high"`, expanded `client_events` to include `interruption`, `agent_response`, `agent_response_correction`. Bumped TTS speed to 1.08. Shortened first_message.
- **Context:** Three UX problems: (1) agent said filler ("okay", "I am finding") before executing tools, adding 2-3s latency; (2) filler speech caused Gemini to lose context and forget tool chain; (3) agent didn't yield to user interruptions. The 2.5s soft timeout with pre-set message "Hhmmmm...yeah." handles silence during tool execution.
- **Rationale:** Gemini drops instructions mid-prompt, so the "say something first" step was competing with tool execution. Tools-first eliminates the distraction. "high" eagerness makes agent respond faster after user pauses. Client `interruption` event enables proper interrupt handling in the widget. TTS speed 1.08 makes responses snappier and easier to interrupt.
- **Consequences:** Agents created with Gemini model will execute tools silently before speaking. Soft timeout message fills the gap. Must test that Gemini reliably calls both tools before speaking. Supersedes the Gemini-specific prompt from 2026-04-08 decision.
- **Status:** Active
- **Agent/Author:** Claude Code (prompt + latency optimization for NurdLuv testing)

---

## 2026-04-08: Model-Specific System Prompts for ElevenLabs Agent

- **Decision:** Use three separate system prompt templates optimized per LLM model family (Gemini, Qwen, GLM), auto-selected based on `ELEVENLABS_LLM_MODEL`.
- **Context:** Agent was inconsistently following the tool chain (search_products → update_products → speak). The 79-line / 7-rule prompt was too complex for smaller models. Research showed each model family responds to different prompt strategies.
- **Rationale:**
  - **Gemini 2.5 Flash:** Positive framing only (negatives get dropped mid-prompt), critical constraints at END in `# Guardrails`. Google docs say avoid broad negatives.
  - **Qwen3-30B-A3B:** Aggressive reinforcement, one-shot example of correct tool sequence, repeat critical rules. Known to omit tool calls without explicit examples.
  - **GLM-4.5-Air:** Must-haves at TOP (too many instructions cause competing asks to get dropped). `# Guardrails` heading goes first for special model attention.
  - All prompts use ElevenLabs-recommended markdown headings (`# Personality`, `# Goal`, `# Guardrails`, `# Tools`) and append "This step is important." to critical lines per ElevenLabs prompting guide.
- **Consequences:**
  - `_select_prompt_for_model()` in `elevenlabs_agent.py` maps model name → prompt template
  - Changing `ELEVENLABS_LLM_MODEL` env var auto-selects the matching prompt
  - Unknown models fall back to GLM prompt
  - Agent must be re-created after changing the model to pick up the new prompt
- **Status:** Active
- **Agent/Author:** Claude agent (latency + tool reliability optimization sprint)

---

## 2026-04-08: Remove Pitch LLM from Search Service

- **Decision:** Remove the synchronous OpenRouter LLM call (`_build_pitch()`) from search-service and replace with a static string.
- **Context:** End-to-end voice agent latency was 24-26 seconds. ElevenLabs model latency was only 634ms. Investigation found `_build_pitch()` was calling `xai/grok-beta` via OpenRouter on every search request, taking 8-15 seconds — 67-83% of total latency.
- **Rationale:** The pitch field was redundant: the ElevenLabs agent generates its own speech from product data. No frontend or agent code reads the `pitch` field. The SearchResponse schema keeps the field with a static string to avoid breaking the API contract.
- **Consequences:**
  - Search endpoint latency dropped from ~10-17s to ~500-800ms
  - `openai`, `requests` imports removed from search-service
  - `OPENROUTER_API_KEY` no longer needed by search-service (still used by scraper)
  - Webhook timeout reduced from 10s to 5s
- **Status:** Active
- **Agent/Author:** Claude agent (latency optimization sprint)

---

## 2026-04-08: Single-Tunnel Architecture — All Services Through One ngrok Tunnel

- **Decision:** Route all external traffic through the onboarding service (port 8005) instead of requiring separate tunnels for image server, search service, and widget. Added `/images` StaticFiles mount, `/search` proxy route (forwards to localhost:8006), and widget served from `/widget/widget.js` (built IIFE).
- **Context:** ngrok free tier allows only 1 tunnel per account. Sharing demos externally required 3 tunnels (onboarding, images, search webhook). This blocked demo sharing without paid ngrok.
- **Rationale:** Proxy pattern keeps services independently deployable while consolidating external access. Search proxy adds <1ms local overhead. Images served directly via StaticFiles (no separate server needed for dev). Widget already built as IIFE in dist/.
- **Alternatives considered:** (1) 3 ngrok accounts — messy, fragile. (2) Cloudflare Tunnel — requires account setup. (3) Deploy to Railway — premature for alpha. (4) Combine all services into one — violates separation of concerns.
- **Consequences:** `IMAGE_SERVER_URL`, `SEARCH_API_URL`, and `WIDGET_SCRIPT_URL` all point to same ngrok URL. Must re-onboard after ngrok restart. Image server (`image_server.py`) still works standalone for local dev.
- **Status:** Active
- **Agent/Author:** Claude Code

---

## 2026-04-08: ElevenLabs API Format — conversation_config.agent Nesting + Latency Config

- **Decision:** Use `conversation_config.agent.prompt.tools` nesting (not top-level `agent_config`). Set `ignore_default_personality: true`. Use ElevenLabs-hosted LLM `glm-45-air-fp8` as default. Enable `turn_eagerness: "eager"`, `speculative_turn: true`, `optimize_streaming_latency: 3`.
- **Context:** ElevenLabs API silently ignores `agent_config` as a top-level key — verified by GET response showing empty prompt. Their docs show `agent_config` but the actual API expects it nested inside `conversation_config.agent`. Additionally, `ignore_default_personality` defaults to `false`, causing ElevenLabs' generic personality to override custom prompts. Latency was 2-3s per turn due to external API LLM calls.
- **Rationale:** Nesting confirmed by GET response inspection. `glm-45-air-fp8` is ElevenLabs-hosted (no external API hop, ~634ms vs ~1-2s) and labeled "great for agentic use cases". Eager turn + speculative turn reduce perceived latency by 300-500ms. LLM configurable via `ELEVENLABS_LLM_MODEL` env var for easy fallback.
- **Alternatives considered:** (1) `qwen3-30b-a3b` (~187ms) — faster but uncertain tool-calling reliability. (2) `gpt-4o-mini` — reliable but 2-3x slower due to external API. (3) `gpt-4o` — best quality but slowest.
- **Consequences:** Must test `glm-45-air-fp8` with complex tool-calling prompts. Webhook `constant_value` cannot coexist with `description` on same param. Array tool params require `items` field.
- **Status:** Active
- **Agent/Author:** Claude Code

---

## 2026-04-07: Monorepo Refactoring — Shared Library + Adapter Registry + Universal Scraping

- **Decision:** Decomposed onboarding-service into `shared/` (cross-service), `adapters/` (StoreAdapter ABC + registry), `routes/`, `services/`, `scraping/` (6-tier universal extraction chain), and `pipeline.py` (unified flow). Search-service imports from `shared/` instead of duplicating Supabase/embedding code.
- **Context:** The onboarding main.py had grown to 1,251 lines with 3 near-identical pipeline branches. Adding a new store type required copy-pasting ~140 lines. Only Shopify, Threadless, and Supermicro were supported — ~50% of e-commerce sites couldn't be scraped.
- **Rationale:** Adapter pattern with registry enables plug-and-play: new store = 1 class + 1 registry line. Shared library eliminates duplication of embedding model name (constraint #1 risk), Supabase client, and price parsing. Universal adapter with 6-tier fallback chain (JSON-LD > microdata > platform CSS > Playwright > sitemap > LLM) covers ~90-95% of e-commerce sites.
- **Alternatives considered:** (1) Separate microservices per store type — over-engineering for alpha. (2) Plugin system with entry points — too complex for 4 adapters. (3) Keep monolithic main.py, just add functions — doesn't solve duplication or plug-and-play.
- **Consequences:** `sys.path.insert` used for shared imports (upgrade to `pip install -e .` when team grows). Old adapter files kept as legacy references. All existing endpoints preserved via backward-compatible aliases.
- **Status:** Active
- **Agent/Author:** Claude Code

---

## 2026-04-07: Three.js Replaced with CSS + GSAP Orb (74% Bundle Reduction)

- **Decision:** Remove `three`, `@react-three/fiber`, `@react-three/drei`, and `@react-three/postprocessing` from the marketing website. Replace the 3D orb with a CSS radial-gradient + GSAP animation + Canvas particles approach.
- **Context:** The Three.js orb was the single largest dependency in the website bundle (1,458KB total). It required WebGL support, added significant load time, and was overkill for what is essentially a decorative animated sphere.
- **Rationale:** CSS radial-gradient produces a visually identical sphere appearance. GSAP handles idle animations (breathing, shimmer rotation, ring ripples), mouse interactions (proximity glow, tilt), and click effects (push-back, shockwave). Canvas API handles floating particles. Total bundle: 379KB (74% reduction).
- **Alternatives considered:** Keep Three.js with lighter shaders (still large), use Lottie animation (extra dependency), static image (no interactivity).
- **Consequences:**
  - No WebGL requirement — works on all devices including low-end mobile
  - GSAP is already used for page animations, so no new dependency for orb
  - Canvas particles disabled on touch devices via `matchMedia('(hover: hover)')` for performance
  - Future 3D effects would require re-adding Three.js
- **Status:** Active
- **Agent/Author:** Claude Code

---

## 2026-04-06: Dashboard Removed — API-First Onboarding

- **Decision:** Remove the `www.teampop/dashboard/` React app entirely. Onboarding is now API-first (via curl/Postman or future replacement UI).
- **Context:** The dashboard was a standalone merchant-facing React app that called `POST /onboard`. It was not actively used or maintained — all recent onboarding testing used direct API calls. The new marketing website (`www.teampop/website/`) is being developed separately.
- **Rationale:** The dashboard added maintenance burden (referenced in 5+ docs, startup scripts) without active use. Removing it simplifies the repo, reduces agent confusion, and allows the team to build a proper replacement when needed.
- **Alternatives considered:** Keep dashboard as-is (unused baggage), merge dashboard into website (different tech stacks and purposes).
- **Consequences:**
  - Merchants must onboard via API calls until a replacement UI exists
  - `start_services.sh` now has 4 steps instead of 5 (no port 5174)
  - Constraint #14 updated to reference "external consumers" instead of dashboard specifically
  - All doc references to dashboard updated or removed
- **Status:** Active
- **Agent/Author:** Claude Code

---

## 2026-04-02: Durable Completed-Work Summaries Live in `docs/agents/completions.md`

- **Decision:** Add `docs/agents/completions.md` as the canonical place for meaningful completed-task summaries, tradeoffs, and verification notes.
- **Context:** The repo already had good homes for hard rules, active work, architectural decisions, and unfinished handoffs, but it lacked a durable place to review completed implementation work for learning or historical reference.
- **Rationale:** Humans and agents need one place to answer "what changed, why did we do it this way, what tradeoffs did we accept, and how was it verified?" without searching through temporary memory or mixing implementation logs into architectural decision records.
- **Alternatives considered:** Expanding `memory.md` to keep long history; adding more detail to `decisions.md`; using `handoff.md` for completed work.
- **Consequences:**
  - `memory.md` stays short and temporary.
  - `decisions.md` stays focused on durable architecture and process choices, not every finished task.
  - `completions.md` becomes the main review and learning reference for meaningful shipped work.
  - Completed entries should summarize key files, rationale, tradeoffs, and verification, but should not turn into a raw changelog.
- **Status:** Active
- **Agent/Author:** Codex

---

## 2026-03-30: Canonical Agent Instructions Live in `AGENTS.md`

- **Decision:** Use repo-root `AGENTS.md` as the canonical shared instruction file, with `docs/agents/` as the specialized state layer.
- **Context:** The repo had multiple overlapping agent-facing docs (`docs/CLAUDE.md`, `docs/COLLABORATIVE.md`, `docs/codex.md`) with duplicated architecture and workflow guidance.
- **Rationale:** A single root entry point is easier for tools to discover, while separate state files prevent the canonical instructions from turning into a noisy session log.
- **Alternatives considered:** Single giant collaboration file; `docs/COLLABORATIVE.md` as the main entry point; keeping per-tool full handbooks in parallel.
- **Consequences:**
  - `AGENTS.md` owns shared instructions and read order.
  - `docs/agents/constraints.md`, `memory.md`, `decisions.md`, and `handoff.md` own specialized state by stability.
  - Root `CLAUDE.md` becomes a thin wrapper that imports/references `AGENTS.md`.
- **Status:** Active
- **Agent/Author:** Codex

---

## 2026-03-30: Remove Duplicate Wrapper Files Under `docs/`

- **Decision:** Keep `AGENTS.md` and `CLAUDE.md` only at repo root and remove duplicate wrapper files from `docs/`.
- **Context:** After standardizing the hybrid system, `docs/CLAUDE.md` and `docs/codex.md` no longer owned any information and only added extra discovery paths.
- **Rationale:** Removing duplicate wrappers lowers ambiguity and reinforces the rule that each piece of guidance should have one owner.
- **Alternatives considered:** Keeping legacy pointer files indefinitely.
- **Consequences:**
  - Root remains the only place for machine-discoverable agent entry files.
  - Human-oriented guidance stays in `docs/COLLABORATIVE.md` and `docs/AGENT_DOCS_GUIDE.md`.
  - Agents should be instructed to start from `AGENTS.md`, not from tool-specific files in subfolders.
- **Status:** Active
- **Agent/Author:** Codex

---

## 2026-04-05: API-Based Scraping for Supermicro (Internal JSON API Discovery)

- **Decision:** Scrape Supermicro's GPU catalog via their internal JSON API (`/en/structuredbapi/ps2/system/gpu/all`) instead of parsing HTML.
- **Context:** Supermicro's product listing page uses a React product selector that loads data dynamically. The static HTML only contains a loading spinner. Basic HTTP returns 403 (bot protection). Playwright bypasses bot protection and can call the API via `page.evaluate(fetch(...))`.
- **Rationale:** The JSON API returns all 82 products with structured fields (SKU, form factor, GPU count, CPU type, etc.) in a single call. This is more reliable, faster, and provides richer data than HTML scraping with fragile CSS selectors.
- **Alternatives considered:** HTML scraping with Playwright + BeautifulSoup (fragile selectors, JS-rendered content), sitemap discovery (sitemap also returns 403).
- **Consequences:**
  - Phase 1 (API) gives ~80% of data; Phase 2 (detail pages) enriches with remaining 20% (core count, memory capacity, key features)
  - If Supermicro changes their internal API, the scraper breaks — but it will fail loudly (no data returned) rather than silently (wrong selectors returning partial data)
  - Playwright is required even for the API call because session cookies from the initial page visit are needed to bypass bot protection
- **Status:** Active
- **Agent/Author:** Claude Code

---

## 2026-04-05: ElevenLabs Webhook store_id Must Be Constant, Not LLM-Generated

- **Decision:** Set `store_id` as `value_type: "constant"` in ElevenLabs webhook tool config, not `"llm_prompt"`.
- **Context:** The ElevenLabs agent was configured with `store_id` as an `llm_prompt` field, meaning the LLM had to read the 36-character UUID from the system prompt and type it into every tool call. The LLM consistently truncated the UUID (dropped 1 character), causing 400 errors from the search service.
- **Rationale:** UUIDs are deterministic values that never change per agent. The LLM has no business generating them. Setting `value_type: "constant"` hardcodes the value at agent creation time — the LLM never touches it.
- **Alternatives considered:** Adding the store_id to enum values (still LLM-selected), putting it in dynamic variables, adding retry logic in search service for near-miss UUIDs.
- **Consequences:**
  - `store_id` is frozen at agent creation time — correct by construction
  - If store_id needs to change, the agent must be re-created
  - Added UUID validation in `elevenlabs_agent.py` to catch truncated IDs at creation time
  - Search service now logs truncated UUID detection in error messages
- **Status:** Active
- **Agent/Author:** Claude Code

---

## 2026-04-05: Flatten Supermicro Specs into Description Field (No DB Schema Change)

- **Decision:** Store all Supermicro-specific specs (form factor, GPU count, CPU type, memory capacity, PCIe config, etc.) in the existing `description` text field rather than adding new columns to the `products` table.
- **Context:** Supermicro products have ~20 spec fields not present in consumer stores (form factor, DIMM slots, cooling type, TDP, etc.). Adding columns would require a Supabase migration and search service changes.
- **Rationale:** The embedding model (`all-MiniLM-L6-v2`) generates vectors from the description text. A rich natural-language description containing all specs enables semantic search for queries like "4U server with H100 GPUs" without any DB schema changes. The existing pipeline (`build_product_rows` → `store_products_in_supabase`) works unchanged.
- **Alternatives considered:** Add spec columns (requires migration), add a `specs JSONB` column (one migration but enables exact filtering).
- **Consequences:**
  - No exact-match filtering (e.g., `WHERE form_factor = '4U'`) — all filtering is via semantic search
  - Description text is ~1400-1700 chars per product — well within embedding model limits
  - If exact filtering is needed later, a JSONB column can be added alongside the description
- **Status:** Active
- **Agent/Author:** Claude Code

---

## 2026-04-03: Adapter Pattern for Non-Shopify Store Onboarding

- **Decision:** Use an adapter module (`threadless_adapter.py`) that normalizes store-specific scraper output to Shopify-compatible dicts, rather than modifying `build_product_rows()` or creating a parallel pipeline.
- **Context:** The Threadless scraper returns different field names and formats (e.g., `name` vs `title`, price as `"$24.99"` string vs variant object, `/designs/` vs `/products/` URLs). The existing onboarding pipeline functions (`build_product_rows`, `store_products_in_supabase`, `create_agent_for_store`) are store-agnostic at the data level.
- **Rationale:** Normalizing at the adapter layer means zero changes to existing pipeline functions. A new endpoint (`POST /onboard-threadless`) keeps Shopify and Threadless flows independently testable. If a 3rd store type is added, extract shared pipeline into `pipeline.py`.
- **Alternatives considered:** Modifying `build_product_rows()` to accept multiple formats; creating a completely separate pipeline; extracting a shared `pipeline.py` module immediately.
- **Consequences:**
  - Each non-Shopify store type needs an adapter module and a new endpoint
  - `_original_product_url` field preserves the real URL when Shopify's `/products/{handle}` pattern doesn't apply
  - Demo page generation uses Playwright (not `requests.get`) to bypass Cloudflare on non-Shopify stores
  - All existing scripts and HTML comments are stripped from demo pages to prevent browser parsing issues
- **Status:** Active
- **Agent/Author:** Claude Code

---

## 2026-04-03: ElevenLabs React SDK v1.0 Migration

- **Decision:** Upgrade `@elevenlabs/react` from v0.14.x to v1.0.1 and use WebSocket connection type.
- **Context:** ElevenLabs deprecated the LiveKit `/rtc/v1` WebRTC endpoint. The old SDK version couldn't connect to their servers. The new SDK v1.0 has breaking API changes.
- **Rationale:** Required upgrade to maintain ElevenLabs voice agent functionality.
- **Alternatives considered:** Staying on v0.14.x (broken), downgrading livekit-client (no control over bundled version).
- **Consequences:**
  - `<ConversationProvider>` wrapper required around all conversation hooks
  - `clientTools` moved from `useConversation` options to individual `useConversationClientTool()` hooks (auto-register/unregister, always-fresh closures)
  - `startSession()` is now synchronous (returns void, errors go to `onError` callback)
  - `connectionType: "websocket"` must be set explicitly — default WebRTC path fails because installed `livekit-client@2.18.1` lacks ElevenLabs' RTC server patch
  - Widget must be served as raw built IIFE (`/widget/widget.js` from onboarding service), NOT through Vite dev server (which injects React Fast Refresh globals that break on external pages)
- **Status:** Active
- **Agent/Author:** Claude Code

---

## 2026-04-03: Widget Served from Onboarding Service, Not Vite Dev Server

- **Decision:** Demo pages reference `http://localhost:8005/widget/widget.js` (pre-built IIFE served by onboarding service) instead of `http://localhost:5173/dist/widget.js` (Vite dev server).
- **Context:** Vite dev server injects React Fast Refresh globals (`$RefreshSig$`, `$RefreshReg$`) into every JS file it serves. These globals only exist on pages loaded through Vite itself (port 5173). Demo pages served from port 8005 don't have these globals, causing `ReferenceError` and the entire widget IIFE dying silently.
- **Rationale:** The onboarding service already mounts `www.teampop/frontend/dist/` at `/widget/`. Using this path serves the raw built file without Vite transformations.
- **Alternatives considered:** Running Vite in preview mode, disabling Fast Refresh in Vite config.
- **Consequences:**
  - `WIDGET_SCRIPT_URL` env var must point to `http://localhost:8005/widget/widget.js`
  - `npm run build` must be run after any widget code changes before testing demo pages
  - Vite dev server (port 5173) is only needed for widget development with HMR, not for demo page testing
- **Status:** Active
- **Agent/Author:** Claude Code

---

## 2026-03: Shadow DOM for Widget Isolation

- **Decision:** The embeddable widget uses Shadow DOM via a `<team-pop-agent>` custom element.
- **Context:** Widget is embedded on merchant Shopify storefronts. Host page CSS was bleeding into widget styles causing visual inconsistency across stores.
- **Rationale:** Shadow DOM provides complete style encapsulation without needing CSS-in-JS or complex specificity overrides. React renders into the shadow root.
- **Alternatives considered:** CSS Modules with high-specificity selectors; iframe embedding; CSS-in-JS (styled-components).
- **Consequences:**
  - `@import` rules don't work inside Shadow DOM — fonts must be injected via `<link>` appended to shadow root
  - Host page cannot style widget internals (intentional)
  - CSS is injected via `window.__TEAM_POP_CSS__` using `vite-plugin-css-injected-by-js`
  - Widget build output is an IIFE (`dist/widget.js`), not a standard module
- **Status:** Active
- **Agent/Author:** Engineering team

---

## 2026-03: Embedding Model — all-MiniLM-L6-v2 (384 dimensions)

- **Decision:** Use `sentence-transformers/all-MiniLM-L6-v2` for product text embeddings.
- **Context:** Need to embed product names + descriptions for semantic search against Supabase pgvector.
- **Rationale:** Fast inference (~14ms/sentence), small model (~90MB), 384-dimensional output (compact vector storage), strong performance on short product text.
- **Alternatives considered:** `text-embedding-ada-002` (OpenAI, paid, 1536d), `all-mpnet-base-v2` (larger, slower), `paraphrase-MiniLM-L6-v2`.
- **Consequences:**
  - **CRITICAL:** Both `onboarding-service` and `search-service` MUST use this exact model. A mismatch silently breaks similarity search (wrong or zero results).
  - Supabase `products.embedding` column is `vector(384)` — changing model requires full column migration and re-embedding of all product data.
  - First-request latency: model downloads (~90MB) on first use if not cached.
- **Status:** Active
- **Agent/Author:** Engineering team

---

## 2026-03: ElevenLabs for Voice Interaction

- **Decision:** Use ElevenLabs Conversational AI for per-store voice agents.
- **Context:** Voice-first AI shopping assistant requires text-to-speech + speech-to-text + conversational AI in a single SDK.
- **Rationale:** ElevenLabs provides `@elevenlabs/react` SDK with built-in conversation state management. Per-store agents allow custom system prompts with store-specific product context.
- **Alternatives considered:** OpenAI Realtime API, Deepgram + OpenAI TTS, Vapi.
- **Consequences:**
  - Each store gets a dedicated ElevenLabs agent ID stored in Supabase
  - `ELEVENLABS_API_KEY` required in onboarding-service env
  - SDK connection state must be tracked manually (`conversation.status`) — no built-in `onConnectionChange` event as of SDK 0.14.1
  - Agent creation happens in `onboarding-service/elevenlabs_agent.py`
- **Status:** Active
- **Agent/Author:** Engineering team

---

## 2026-03: OpenRouter for LLM Access

- **Decision:** Use OpenRouter as the LLM gateway, accessed via the OpenAI SDK (`openai` Python package).
- **Context:** Need LLM for product pitch generation in search service and LLM-based extraction fallback in scraper.
- **Rationale:** OpenRouter provides a single API key for multiple models, OpenAI SDK compatibility (drop-in base URL change), and model switching via env var.
- **Alternatives considered:** Direct OpenAI API, Anthropic API, AWS Bedrock.
- **Consequences:**
  - Default model: `xai/grok-beta` (set via `OPENROUTER_MODEL` env var)
  - Model can be swapped without code changes
  - `OPENROUTER_API_KEY` required in search-service and universal-scraper
- **Status:** Active
- **Agent/Author:** Engineering team

---

## 2026-03: Supabase for Database + Vector Search

- **Decision:** Use Supabase (PostgreSQL + pgvector) for product storage and hybrid search.
- **Context:** Need persistent storage for product embeddings with fast vector similarity search.
- **Rationale:** Supabase provides pgvector extension, built-in RPC functions, free tier, and Python/JS clients. `hybrid_search_products` RPC combines cosine similarity + PostgreSQL full-text search in a single call.
- **Alternatives considered:** Pinecone (vector only, separate DB needed), Weaviate, Redis with RedisSearch.
- **Consequences:**
  - Requires `vector` extension enabled in Supabase project
  - `hybrid_search_products` RPC must be deployed to Supabase SQL before system works
  - HNSW index on `embedding` column required for performance
  - `SUPABASE_URL` + `SUPABASE_KEY` (service role) required in onboarding and search services
  - Full SQL in `SHOPIFY_FLOW_COMPLETE.md`
- **Status:** Active
- **Agent/Author:** Engineering team

---

## 2026-03: Multi-Strategy Scraping with Fallback Chain

- **Decision:** Implement a fallback chain for web scraping: Basic HTTP → Playwright → LLM extraction.
- **Context:** Shopify stores vary widely — some are static HTML, some are JS-heavy SPAs, some block simple scrapers.
- **Rationale:** Maximizes coverage across store types. Basic HTTP is fastest; Playwright handles JS rendering; LLM extraction is the last-resort fallback for complex/unusual layouts.
- **Alternatives considered:** Scrapy (overkill), Selenium only (slow), paid scraping APIs.
- **Consequences:**
  - Playwright requires `playwright install` for browser binaries (not in requirements.txt)
  - LLM extraction uses OpenRouter, adding latency + cost for fallback cases
  - Strategy logic in `universal-scraper/scripts/scraping_strategies.py`
- **Status:** Active
- **Agent/Author:** Engineering team

---

## 2026-03: Error Codes for User-Friendly Onboarding Errors

- **Decision:** Use structured error codes (`ErrorCodes` class) instead of raw exception messages.
- **Context:** Onboarding flow failed with cryptic Python tracebacks surfaced to the user in the dashboard.
- **Rationale:** User-facing errors must be actionable. Error codes allow frontend to display localized, contextual messages.
- **Alternatives considered:** Generic HTTP status codes only, logging to Sentry.
- **Consequences:**
  - All onboarding errors must go through `error_codes.py` using `get_error_response()` helper
  - New error conditions need a new entry in `ErrorCodes` before being raised
  - Error code format: `ONBOARDING_XXX` pattern
- **Status:** Active
- **Agent/Author:** Engineering team

---

## 2026-03: IIFE Widget Build (Not Standard SPA)

- **Decision:** Build the frontend widget as a single IIFE file (`dist/widget.js`) rather than a standard SPA bundle.
- **Context:** Widget must be embeddable on any merchant storefront with a single `<script>` tag.
- **Rationale:** IIFE (Immediately Invoked Function Expression) bundles everything (JS + CSS) into one self-contained file with no external dependencies.
- **Alternatives considered:** Web Components with separate CSS, iframe approach, npm package.
- **Consequences:**
  - Entire widget bundle loads at once (no code splitting or tree-shaking)
  - Vite config sets `build.lib.entry` + `build.lib.formats = ['iife']`
  - CSS injected at runtime via `vite-plugin-css-injected-by-js` into `window.__TEAM_POP_CSS__`
  - Widget dev server runs on port 5173; `npm run build` outputs `dist/widget.js`
  - Onboarding service mounts `www.teampop/frontend/dist/` — build must be run before demo pages work
- **Status:** Active
- **Agent/Author:** Engineering team

---

## 2026-06-18: Client Tool Synchronous Sequencing (`expects_response` = True)

- **Decision:** Set `"expects_response": True` for client-side tools (`update_products`, `update_carousel_main_view`) in the ElevenLabs agent configuration.
- **Context:** The product carousel updated after a 1-3s delay while the agent was already narrating the results.
- **Rationale:** Forcing the agent to wait for the client tool to complete execution guarantees that the carousel mounts and renders *before* the user hears the spoken descriptions.
- **Consequences:** The LLM pauses speech generation until the client returns a status value (which happens instantly). This eliminates the voice-UI rendering lag.
- **Status:** Active
- **Agent/Author:** Antigravity (Gemini)

---

## 2026-06-18: WebSocket Manual Selection Event Consolidation

- **Decision:** Consolidated the manual thumbnail selection in `syncMainProduct` (`AvatarWidget.jsx`) into a single `sendUserMessage` call instead of sending `sendContextualUpdate` followed by `sendUserMessage`.
- **Context:** Thumbnail clicks triggered duplicate AI responses where the agent spoke the exact same description twice consecutively.
- **Rationale:** Sending both messages over WebSocket in the same tick created a race condition on the ElevenLabs server, causing it to queue and generate two separate responses. Combining them into a single string ensures exactly one event is processed.
- **Consequences:** WebSocket traffic is halved for thumbnail selection, and the race condition is completely prevented.
- **Status:** Active
- **Agent/Author:** Antigravity (Gemini)


---

## 2026-08-12: Live xfused agent diverged from code — dashboard hand-edits treated as source of truth

- **Decision:** For the live pilot agent (`agent_4901kwna71tve5nbyy85c8v20yre`, "Wrina - Xfused (v2, multilingual)"), the ElevenLabs dashboard's current live config is authoritative over `elevenlabs_agent.py`'s hardcoded defaults where they conflict. Code was updated to make the divergent fields reproducible instead of silently overwriting them.
- **Context:** A latency audit compared the code in this repo against the live agent via `GET /v1/convai/agents/{id}` and found real drift, most likely from manual dashboard edits during live testing that were never ported back:
  - `agent.language`: code hardcoded `"en"`; live is `"hi"` (base language), with `hinglish_mode=true` and `language_presets` for `en`/`ta`.
  - `tts.model_id`: code/decisions.md (2026-07-04 entry) mandate `eleven_flash_v2` for English-primary agents; live runs `eleven_flash_v2_5`. This is **not a contradiction** — the 400 ElevenLabs throws on `eleven_flash_v2_5` is keyed on `agent.language == "en"`, and live is no longer `"en"`. Switching the base language is what unlocked the multilingual TTS model.
  - `tts.voice_id`: live is `o6qTxWUeRyzRYZyUNDVJ`, not the `.env.example` default `xoV6iGVuOGYHLWjXhVC7` (Muskaan).
  - `turn.soft_timeout_config`: live has 2 rotating fillers (`randomize_fillers=true`, `max_soft_timeouts_per_generation=2`) vs. code's single static filler — an undocumented refinement of the 2026-07-20 latency fix.
- **Rationale:** Reproducing exactly what's proven live in production (10 real conversations through 2026-08-06) is lower-risk than re-deriving these settings from the 2026-07-04 decision, which was correct for an English-primary agent but doesn't apply once the base language changed.
- **Consequences:** `create_agent()` gained a `language: str = "en"` param (elevenlabs_agent.py) so this setup is reproducible instead of hardcoded — pass `language="hi"` + `ELEVENLABS_TTS_MODEL=eleven_flash_v2_5` to match Wrina v2. The soft-timeout defaults in `create_agent()` were updated to the rotating-filler version. The 2026-07-04 decision is **not reversed** — `eleven_flash_v2` + `language="en"` remains correct for any future English-primary store; this entry documents a store-specific exception, not a new global default. `update_agent()` was not touched — it already patches only the sub-objects it's asked to (prompt, tts), so routine prompt/model updates for xfused do not risk overwriting `turn`/`language`/`asr`, which live only in `create_agent()`'s payload.
- **Open risk:** If xfused's agent is ever re-created (not just updated) without passing `language="hi"` explicitly, it will silently regress to the English defaults. There is no guardrail against this beyond this doc entry and the code comments at `elevenlabs_agent.py` create_agent().
- **Status:** Active
- **Agent/Author:** Claude
