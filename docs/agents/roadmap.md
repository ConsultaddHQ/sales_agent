# Roadmap — Tasks, Improvements & Pending Work

> **Purpose:** Single source of truth for what needs to be done, by whom, and priority.
> **Updated:** 2026-07-03
> **Rule:** Agents update this after completing work or discovering new tasks. Remove done items, add new ones.

---

## Manual Steps (Human Required)

These cannot be done by an agent — they require account access, credentials, or external service setup.

| # | Task | Status | Notes |
|---|------|--------|-------|
| 1 | Create `agent_requests` table in Supabase | ✅ Done | SQL provided and executed |
| 2 | Sign up for Resend → get API key | ✅ Done | Free tier, sends from `@resend.dev` |
| 3 | Create Slack incoming webhook | ⏭️ Skipped | Deferred — not needed for demo |
| 4 | Get Calendly booking link | ✅ Done | Free account created |
| 5 | Fill `.env` in `onboarding-service/` | ✅ Done | All keys set including ElevenLabs, Resend, Calendly |
| 6 | Fill `.env` in `www.teampop/website/` | ✅ Done | VITE_API_URL, VITE_CALENDLY_URL set |
| 7 | `pip install resend` in onboarding venv | ✅ Done | Already in requirements.txt |
| 8 | End-to-end test of full flow | ⬜ In Progress | Agent + onboarding works; admin flow has 422 issue under investigation |
| 9 | Merge PR after testing | ⬜ Pending | After full flow verified |

---

## High Priority Improvements

| Task | Owner | Status | Effort | Notes |
|------|-------|--------|--------|-------|
| **⭐ [Post-pilot #1] Search-result cache (subset of Refactor A)** | Agent | ⬜ Ready | 30 min | **Validated by 2026-07-03 Xfused load test:** search-service is CPU-bound at ~5.6 req/s; under concurrent load `queue_wait_ms` dominates (~1.6s waiting for embed slots) while `rpc_ms` stays healthy (~250ms). A TTL cache serves repeat queries in ~0ms, removing the embed+rerank CPU cost — the **highest-leverage scaling fix, no hardware change**. Do this before any box upgrade (a Lightsail RAM bump keeps the same 2 vCPUs, so it won't raise the ceiling). |
| **[Refactor A] Rewrite search-service/main.py** | Agent | ⬜ Ready | 1 hr | Plan at `docs/refactor-plan-2026-06-19.md`. Adds: TTLCache (512/300s), /metrics endpoint, structured logging, WEBHOOK_SECRET, ALLOWED_ORIGINS CORS, request-ID correlation, asyncio.to_thread() in /product-details, semaphore init in startup |
| **[Refactor B] Parallel image downloads + batch embedding + pipeline timing** | Agent | ⬜ Ready | 1–2 hrs | Plan at `docs/refactor-plan-2026-06-19.md`. Rewrites: `services/products.py` (4-phase batch pipeline) + `pipeline.py` (step timing, ElevenLabs retry, structured completion log) |
| Upgrade existing production agents to Claude Haiku 4.5 | Human | ⬜ Pending | 15 min per agent | Run `./onboarding-service/.venv/bin/python testing/latency/upgrade_agent_model.py --agent-id <id> --store-id <uuid>` for each live agent that should inherit the 2026-04-17 winner. `--from-json` for batch. |
| Product-description strategy for larger catalogs | Agent | ⬜ Pending | 3–4 hrs | Today we truncate to 200 chars in `_truncate_for_voice`. As descriptions grow, consider: (a) pre-generate a 150-char `voice_description` column at ingestion and send that instead of truncation; or (b) add a `get_product_details(product_id)` tool the agent calls only when the user asks for more. Keep the full description in DB for the carousel card. |
| Add search-service result cache (LRU+TTL) | Agent | ⬜ Ready | 30 min | Covered in Refactor A above. ~1s network floor per search; 300s cache TTL eliminates repeat utterance cost entirely. |
| Rate limiting on `/api/submit-request` | Agent | ⬜ Pending | 1 hr | Prevent spam submissions before public launch |
| CORS restriction from `*` to actual domains | Agent | ⬜ Pending | 30 min | Covered in Refactor A (ALLOWED_ORIGINS env var). Both services currently use wildcard. |
| Production deployment + custom domain + SSL | Human + Agent | ⬜ Pending | 1 day | Needed before sharing with real clients |
| Request deduplication (same email/URL) | Agent | ⬜ Pending | 30 min | Prevent duplicate submissions |
| Fix send_delivery_email not fire-and-forget (H3) | Agent | ⬜ Pending | 30 min | `routes/client.py:send_agent()` calls `send_delivery_email()` synchronously in request thread — blocks response. Move to executor submit. |
| Add index on agent_requests.agent_id (H4) | Human | ⬜ Pending | 15 min | `admin.py:switch_agent_model()` filters by unindexed `agent_id` field → full table scan. Add Supabase index. |
| Add LIMIT to admin list query (H5) | Agent | ⬜ Pending | 15 min | `admin.py:list_requests()` does unbounded `select("*")` — will OOM/timeout as table grows. Add `.limit(200)` or pagination. |
| Unify two ThreadPoolExecutors into shared module (L2) | Agent | ⬜ Pending | 30 min | `admin.py` and `client.py` each have `_bg_executor = ThreadPoolExecutor(max_workers=4)` — no shared state, unbounded queues. Consolidate into `shared/executor.py`. |
| Voice-test Hindi/Tamil pronunciation quality on `eleven_flash_v2` (not the multilingual model) | Human | ⬜ Pending | 15 min | 2026-07-04: shipped a fresh Xfused agent (`agent_4901kwna71tve5nbyy85c8v20yre`, store `9cec7cd0-...`) via `create_agent(additional_languages=["hi","ta"], hinglish_mode=True)` — new params now support this on any store. Verified live via GET: `language_presets` has `hi`/`ta` with translated `first_message`, `hinglish_mode=True`, `tts.model_id=eleven_flash_v2` (the **only** valid choice for an English-primary agent — see [[decisions.md 2026-07-04]] entry, `eleven_flash_v2_5` gets a hard 400). Demo page generated locally (`onboarding-service/demo_pages/test_9cec7cd0.html`) but not yet on the box — needs copying/regenerating there before it's reachable at the public `/demo/...` URL. **Open question**: since the base model is `eleven_flash_v2` (not a multilingual model), voice-test whether Hindi/Tamil pronunciation is acceptable; if not, investigate `tts.supported_voices[].model_family` per-language override (unverified schema, see decision doc). Telugu still has no supported real-time voice model — user says they have proof it works via an ElevenLabs "v3 conversation" mode; pending that evidence before adding. |

---

## Medium Priority Improvements

| Task | Owner | Status | Effort | Notes |
|------|-------|--------|--------|-------|
| Email template polish (branded HTML) | Agent | ⬜ Pending | 2 hrs | Current templates are functional but plain |
| Conversion analytics (form submissions, completion rate) | Agent | ⬜ Pending | 2 hrs | No tracking on the funnel yet |
| Widget integration/docs page for merchants | Agent | ⬜ Pending | 3 hrs | Show how to embed `<team-pop-agent>` |
| Mobile responsive polish on admin dashboard | Agent | ⬜ Pending | 1 hr | Admin page works but not optimized for mobile |
| Error toast notifications on website forms | Agent | ⬜ Pending | 30 min | Better UX for form validation errors |
| **[Post-pilot] Currency-awareness (stop hardcoding symbols)** | Agent | ⬜ Pending | 2–3 hrs | Currency is assumed, not detected. `shopify.py:158` / `threadless.py:97` / `universal.py:232` hardcode `$` in `price_range` (feeds the agent prompt); the widget hardcodes `₹` (`AvatarWidget.jsx:96,392`). Wrong for any non-matching store (INR store shows `$` in prompt; USD store shows `₹` in widget). Fix: detect store currency (Shopify exposes it), add `currency` to `store_context` + a `{currency}` placeholder in all prompt templates, make the widget symbol dynamic. Xfused pilot mitigated by manually pasting `Rs`/`₹` into the agent prompt. |
| **[Post-pilot] Bring the other 4 prompt templates up to date with PROMPT_CLAUDE** | Agent | ⬜ Pending | 1 hr | `PROMPT_CLAUDE` has accumulated several Xfused-pilot-only changes not yet ported: domain-neutral wording (colors/fabric/size/fashion-pairing → options/variants/specs), the search-first/clarify guardrails, the `go_to_cart` tool + quantity-aware `add_to_cart` section, and the Hindi/Tamil language directive. GPT/Gemini/Qwen/GLM templates in `elevenlabs_agent.py` still have none of this — port it so any store on any model gets the same behavior. |
| **[Metrics] Zero-result search logging in search-service** | Agent | ⬜ Pending | 1 hr | The widget can't see empty searches (agent only calls `update_products` when results exist). Log `store_id + query + result_count` in search-service `/search`, aggregate the `result_count=0` queries → tells the merchant exactly what shoppers ask for that the catalog doesn't carry (catalog-gap report). Follows the 2026-07-16 session-metrics work (`session_feedback` funnel columns). |
| **[Metrics] Aggregate metrics dashboard over `session_feedback`** | Agent | ⬜ Pending | 3–4 hrs | Client-facing numbers proving agent value: funnel % (sessions → search → product focused → cart add → checkout initiated), assisted cart value over time (`cart_value_paise`), rating breakdown, avg duration, resumed-session share. Simplest: an admin-dashboard page (`www.teampop/website`) querying Supabase aggregates; SQL views first, UI second. |
| **[Metrics] Shopify order webhooks for paid-order reconciliation** | Agent + Human | ⬜ Pending | 3–4 hrs | Today agent-assisted PAID orders are found by filtering Shopify admin on the `TeamPop Assisted` / `TeamPop Conversation` order attributes (set via `/cart/update.js` on every successful add, 2026-07-16). Automate: `orders/create` webhook (needs a small Shopify app/custom-app token from the merchant — human step) → endpoint in onboarding-service matches the attributes → store `order_id`, `total_price`, `conversation_id` in an `assisted_orders` table → true conversion + revenue per session with no manual admin work. |

---

## Low Priority / Future

| Task | Owner | Status | Effort | Notes |
|------|-------|--------|--------|-------|
| Admin auth upgrade (password → JWT tokens) | Agent | ⬜ Pending | 2 hrs | Current X-Admin-Password header is basic |
| RLS policies on `agent_requests` table | Agent | ⬜ Pending | 1 hr | Currently using service-role key (acceptable for backend) |
| Automated testing (API + frontend) | Agent | ⬜ Pending | 3 hrs | No test suite for the new endpoints |
| SEO meta tags + Open Graph for website | Agent | ⬜ Pending | 1 hr | Improve social sharing and search visibility |
| Dark mode toggle on website | Agent | ⬜ Pending | 1 hr | Currently dark-only, some users may prefer light |
| Multi-language support | Agent | ⬜ Pending | 4 hrs | i18n for the marketing website |
| Webhook retry logic for failed notifications | Agent | ⬜ Pending | 1 hr | Currently fire-and-forget, no retry on failure |
| Admin dashboard: search/filter requests | Agent | ⬜ Pending | 1 hr | Currently shows all requests in a flat list |
| Explicit agent-passed "browse all" flag | Agent | ⬜ Pending | 1 hr | Durable fix for the rerank browse-bypass edge (2026-07-03 decision): the agent reformulates "show me everything" freely, so phrase/low-score detection can miss. Add a `browse`/`limit` param to `search_products` the agent sets for full-catalog intent, and skip the relevance cutoff when set — more reliable than inferring from query text. |

---

## Known Bugs / Technical Debt

| Issue | Severity | Notes |
|-------|----------|-------|
| ngrok URL changes on restart | Medium | Single-tunnel setup mitigates (only 1 URL). After restart, update `IMAGE_SERVER_URL`/`SEARCH_API_URL`/`WIDGET_SCRIPT_URL` in both services' `.env` and restart — no re-onboard needed for images (search composes the host at read time as of 2026-06-12). A reserved ngrok domain removes this entirely. |
| Onboarding stores absolute `image_url` in DB | Low | `products.py:109` bakes `{IMAGE_SERVER_URL}/images/...` at ingest, which goes stale on host change. Search now ignores it (composes from `local_image_path`), so the column is redundant — store only the relative path and drop the absolute write. |
| Admin dashboard 422 on process-request | Medium | Needs investigation — may be Supabase schema or CORS issue |
| ngrok free interstitial blocks widget | Low | External users must click "Visit Site" before widget JS loads |
| Supermicro internal API undocumented | Low | `/en/structuredbapi/ps2/system/gpu/all` may change without notice |
| Universal adapter not integration-tested | Medium | JSON-LD, platform selectors, sitemap discovery need live-site testing |
| Gemini 2.5 Flash 2nd-turn dead air | Resolved (2026-04-17) | Fixed by STEP 3 model swap to `claude-haiku-4-5`. Default updated in code + .env.example. Existing agents still need per-agent upgrade via `testing/latency/upgrade_agent_model.py`. |
| `sys.path.insert` for shared/ imports | Low | Upgrade to `pip install -e .` when team grows |
| Search-service rate limiting assumes client IP visibility | Medium | If deployed behind a proxy/load balancer, configure forwarded IP handling or tune `SEARCH_RATE_LIMIT` to avoid mis-grouping traffic |

---

## Recently Completed

Move items here when done (keep last 5 for reference, then delete oldest).

| Date | Task | Who |
|------|------|-----|
| 2026-07-03 | Xfused skincare pilot: domain-neutral `PROMPT_CLAUDE` (apparel→neutral wording), `final_limit 5→12` in search-service (surface small catalogs fully), and strict search-first + clarify guardrails for unfamiliar product names. On `release/xfused-pilot`. | Claude |
| 2026-06-19 | Enforced `get_product_details` → `update_carousel_main_view` tool chain at three levels (tool description, `## Tools`, `# Guardrails`) across all 5 model prompts; disabled carousel click-to-agent context (visual-only now). | Antigravity |
| 2026-06-18 | Fixed carousel update delay (1-3s) by setting `expects_response: True` on client tools; fixed duplicate agent speech by consolidating thumbnail click into a single `sendUserMessage`. | Antigravity |
| 2026-06-18 | Resolved search service hangs (PyTorch CPU thread limits + semaphore gate); implemented smart inactivity timer (pauses during agent speech, grace windows); fixed VAD startup silence. | Antigravity |
| 2026-04-17 | Voice-agent latency STEP 3: A/B test picked Claude Haiku 4.5; code defaults flipped, harness moved to `testing/latency/` with new `upgrade_agent_model.py`. | Claude |
