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
