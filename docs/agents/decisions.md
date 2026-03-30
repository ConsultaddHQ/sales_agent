# Architectural Decisions Log

> **Append-only.** Never delete entries. If a decision is superseded, mark it `Status: Superseded` and add a new entry.
> **Format:** Follow the structure used in the existing entries below.
> **Purpose:** Prevent agents from re-litigating or unknowingly reversing prior decisions.

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
