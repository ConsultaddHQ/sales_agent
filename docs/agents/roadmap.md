# Roadmap — Tasks, Improvements & Pending Work

> **Purpose:** Single source of truth for what needs to be done, by whom, and priority.
> **Updated:** 2026-04-10
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
| ngrok URL changes on restart | Medium | Single-tunnel setup mitigates (only 1 URL). Must re-onboard after restart. |
| Admin dashboard 422 on process-request | Medium | Needs investigation — may be Supabase schema or CORS issue |
| ngrok free interstitial blocks widget | Low | External users must click "Visit Site" before widget JS loads |
| Supermicro internal API undocumented | Low | `/en/structuredbapi/ps2/system/gpu/all` may change without notice |
| Universal adapter not integration-tested | Medium | JSON-LD, platform selectors, sitemap discovery need live-site testing |
| `glm-45-air-fp8` tool-calling unverified | Medium | New ElevenLabs-hosted LLM — may struggle with complex prompts, fallback to `gpt-4o-mini` via env var |
| `sys.path.insert` for shared/ imports | Low | Upgrade to `pip install -e .` when team grows |

---

## Recently Completed

Move items here when done (keep last 5 for reference, then delete oldest).

| Date | Task | Who |
|------|------|-----|
| 2026-04-10 | Human-facing `docs/knowledge-base/` handbook, root pointers, and personal-note canonical links | Codex |
| 2026-04-08 | ElevenLabs API migration + latency optimization + single-tunnel sharing + widget latency tracking | Agent |
| 2026-04-07 | Monorepo refactoring: shared/, adapter registry, unified pipeline, universal scraping chain | Agent |
| 2026-04-07 | Marketing website redesign (monochrome + GSAP orb) | Agent |
| 2026-04-07 | Client acquisition backend (6 endpoints + notifications) | Agent |
| 2026-04-06 | Repo cleanup (removed dashboard, dead code, stale scripts) | Agent |
