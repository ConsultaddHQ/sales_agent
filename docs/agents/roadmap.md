# Roadmap — Tasks, Improvements & Pending Work

> **Purpose:** Single source of truth for what needs to be done, by whom, and priority.
> **Updated:** 2026-04-17
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
| Product-description strategy for larger catalogs | Agent | ✅ Done (2026-06-17) | — | Solved via option (b): `get_product_details` on-demand tool + `metadata` JSONB column. Search payload stays lean (200-char blurb); full variants/options/fabric fetched only when asked. See decisions 2026-06-17. |
| Evaluate moving Supabase region closer to India (e.g. Mumbai) OR add search-service result cache | Human | ⬜ Pending | 2–4 hrs | ~1 s network floor on every search call today; region move or LRU cache are the two remaining levers to break that floor. |
| Rate limiting on `/api/submit-request` | Agent | ⬜ Pending | 1 hr | Prevent spam submissions before public launch |
| CORS restriction from `*` to actual domains | Agent | ✅ Done (2026-06-17) | — | Now env-driven `ALLOWED_ORIGINS` (default `*`) in search/onboarding/image_server. Set real domains in prod `.env`. |
| Activate webhook auth (set `WEBHOOK_SECRET`) | Human + Agent | ⬜ Pending | 30 min | Code shipped 2026-06-17, OFF by default. Set the same `WEBHOOK_SECRET` in both services' `.env`, re-push live agents (header baked at creation time), restart. |
| Per-store rate limiting (shared state) | Agent | ⬜ Pending | 2–3 hrs | IP-based limiting mis-groups ElevenLabs' shared egress IPs. Needs Redis/shared store keyed by `store_id`. Fold into the AWS phase. |
| Production deployment + custom domain + SSL | Human + Agent | ⬜ Pending | 1 day | Target (2026-06-17 plan): containerize both services + Caddy for domain+TLS to retire ngrok; keep a warm host so the embedding model stays loaded (EC2+Compose recommended for SMB; ECS Fargate when concurrency grows). |
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
| Automated testing (API + frontend) | Agent | 🟡 Partial (2026-06-17) | 2 hrs | search-service has a 13-test hermetic pytest suite (`search-service/tests/`). Still needed: onboarding-service + frontend tests. |
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
| Custom-domain Shopify auto-detects as universal | Medium | `ShopifyAdapter.matches_url` only matches `myshopify.com`, so custom domains (e.g. `sensesindia.in`) route to the universal adapter and lose variants/options/`body_html` (empty `metadata`). Workaround: onboard with `store_type="shopify"`. Fix: probe `/products.json` in `matches_url`. |
| Gemini 2.5 Flash 2nd-turn dead air | Resolved (2026-04-17) | Fixed by STEP 3 model swap to `claude-haiku-4-5`. Default updated in code + .env.example. Existing agents still need per-agent upgrade via `testing/latency/upgrade_agent_model.py`. |
| `sys.path.insert` for shared/ imports | Low | Upgrade to `pip install -e .` when team grows |
| Search-service rate limiting is IP-based | Medium | All ElevenLabs webhook calls share egress IPs, so per-IP limits mis-group them. Webhook shared-secret (2026-06-17) blocks external abuse; true per-store limiting needs shared state (Redis) — tracked in High Priority. Behind a proxy, also configure forwarded-IP handling. |

---

## Recently Completed

Move items here when done (keep last 5 for reference, then delete oldest).

| Date | Task | Who |
|------|------|-----|
| 2026-06-17 | Prod-hardening #2: cross-service request-id correlation + 13-test hermetic search-service pytest suite | Claude |
| 2026-06-17 | Prod-hardening #1: webhook shared-secret auth, session cap 600→300, scope guardrail (5 prompts), env-driven CORS | Claude |
| 2026-06-17 | Wired `get_product_details` end-to-end (fixed search crash, proxy 404, anti-fabrication prompts, idempotent migration); sensesindia re-onboarded as Shopify | Claude |
| 2026-06-12 | Fixed product-image 404s in voice agent (4-layer root cause) | Claude |
| 2026-04-17 | Voice-agent latency STEP 3: 6-model A/B → Claude Haiku 4.5 default; harness in `testing/latency/` | Claude |
