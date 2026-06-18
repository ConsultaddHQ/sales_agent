# Roadmap — Tasks, Improvements & Pending Work

> **Purpose:** Single source of truth for what needs to be done, by whom, and priority.
> **Updated:** 2026-06-19
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
| Upgrade existing production agents to Claude Haiku 4.5 | Human | ⬜ Pending | 15 min per agent | Run `./onboarding-service/.venv/bin/python testing/latency/upgrade_agent_model.py --agent-id <id> --store-id <uuid>` for each live agent that should inherit the 2026-04-17 winner. `--from-json` for batch. |
| Product-description strategy for larger catalogs | Agent | ⬜ Pending | 3–4 hrs | Today we truncate to 200 chars in `_truncate_for_voice`. As descriptions grow, consider: (a) pre-generate a 150-char `voice_description` column at ingestion and send that instead of truncation; or (b) add a `get_product_details(product_id)` tool the agent calls only when the user asks for more. Keep the full description in DB for the carousel card. |
| Evaluate moving Supabase region closer to India (e.g. Mumbai) OR add search-service result cache | Human | ⬜ Pending | 2–4 hrs | ~1 s network floor on every search call today; region move or LRU cache are the two remaining levers to break that floor. |
| Rate limiting on `/api/submit-request` | Agent | ⬜ Pending | 1 hr | Prevent spam submissions before public launch |
| CORS restriction from `*` to actual domains | Agent | ⬜ Pending | 30 min | All services currently use wildcard — must restrict before production |
| Production deployment + custom domain + SSL | Human + Agent | ⬜ Pending | 1 day | Needed before sharing with real clients |
| Request deduplication (same email/URL) | Agent | ⬜ Pending | 30 min | Prevent duplicate submissions |

---

## Medium Priority Improvements

| Task | Owner | Status | Effort | Notes |
|------|-------|--------|--------|-------|
| Email template polish (branded HTML) | Agent | ⬜ Pending | 2 hrs | Current templates are functional but plain |
| Conversion analytics (form submissions, completion rate) | Agent | ⬜ Pending | 2 hrs | No tracking on the funnel yet |
| Widget integration/docs page for merchants | Agent | ⬜ Pending | 3 hrs | Show how to embed `<team-pop-agent>` |
| Mobile responsive polish on admin dashboard | Agent | ⬜ Pending | 1 hr | Admin page works but not optimized for mobile |
| Error toast notifications on website forms | Agent | ⬜ Pending | 30 min | Better UX for form validation errors |

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
| 2026-06-19 | Enforced `get_product_details` → `update_carousel_main_view` tool chain at three levels (tool description, `## Tools`, `# Guardrails`) across all 5 model prompts; disabled carousel click-to-agent context (visual-only now). | Antigravity |
| 2026-06-18 | Fixed carousel update delay (1-3s) by setting `expects_response: True` on client tools; fixed duplicate agent speech by consolidating thumbnail click into a single `sendUserMessage`. | Antigravity |
| 2026-06-18 | Resolved search service hangs (PyTorch CPU thread limits + semaphore gate); implemented smart inactivity timer (pauses during agent speech, grace windows); fixed VAD startup silence. | Antigravity |
| 2026-04-17 | Voice-agent latency STEP 3: A/B test picked Claude Haiku 4.5; code defaults flipped, harness moved to `testing/latency/` with new `upgrade_agent_model.py`. | Claude |
| 2026-04-17 | Voice-agent latency STEP 1+2+4: search warmup, timing headers, proxy client reuse, HNSW/GIN database search indices, tool-first prompt rule. | Claude |
