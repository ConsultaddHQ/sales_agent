# Completed Work Log

> Use this file for meaningful completed tasks that future humans or agents may want to review.
> Purpose: preserve implementation summaries, reasoning, tradeoffs, and verification in one durable place.
> Add newest entries at the top.

---

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
