# Architectural Decisions Log

> **Append-only.** Never delete entries. If a decision is superseded, mark it `Status: Superseded` and add a new entry.
> **Format:** Follow the structure used in the existing entries below.
> **Purpose:** Prevent agents from re-litigating or unknowingly reversing prior decisions.

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
