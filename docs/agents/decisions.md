# Architectural Decisions Log

> **Append-only.** Never delete entries. If a decision is superseded, mark it `Status: Superseded` and add a new entry.
> **Format:** Follow the structure used in the existing entries below.
> **Purpose:** Prevent agents from re-litigating or unknowingly reversing prior decisions.

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
