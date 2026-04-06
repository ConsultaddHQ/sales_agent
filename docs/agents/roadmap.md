# Roadmap — Tasks, Improvements & Pending Work

> **Purpose:** Single source of truth for what needs to be done, by whom, and priority.
> **Updated:** 2026-04-07
> **Rule:** Agents update this after completing work or discovering new tasks. Remove done items, add new ones.

---

## Manual Steps (Human Required)

These cannot be done by an agent — they require account access, credentials, or external service setup.

| # | Task | Status | Notes |
|---|------|--------|-------|
| 1 | Create `agent_requests` table in Supabase | ⬜ Pending | SQL provided in project docs |
| 2 | Sign up for Resend → get API key | ⬜ Pending | [resend.com](https://resend.com), verify sending domain |
| 3 | Create Slack incoming webhook | ⬜ Pending | Slack workspace → Apps → Incoming Webhooks |
| 4 | Get Calendly booking link | ⬜ Pending | [calendly.com](https://calendly.com) free account |
| 5 | Fill `.env` in `onboarding-service/` | ⬜ Pending | RESEND_API_KEY, ADMIN_PASSWORD, SLACK_WEBHOOK_URL, CALENDLY_URL, FROM_EMAIL, ADMIN_EMAIL |
| 6 | Fill `.env` in `www.teampop/website/` | ⬜ Pending | VITE_API_URL, VITE_CALENDLY_URL |
| 7 | `pip install resend` in onboarding venv | ⬜ Pending | `cd onboarding-service && source .venv/bin/activate && pip install resend` |
| 8 | End-to-end test of full flow | ⬜ Pending | Submit form → check Slack/email → admin process → send agent |
| 9 | Merge PR #4 after testing | ⬜ Pending | `workflow/client` → `main` |

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
| ngrok URL changes on restart | Medium | Agent webhook URL baked in at creation time — must re-create agent |
| Image server path mismatch | Low | Images saved to `onboarding-service/images/` but served from `./images/` |
| Supermicro internal API undocumented | Low | `/en/structuredbapi/ps2/system/gpu/all` may change without notice |
| Universal adapter not integration-tested | Medium | JSON-LD, platform selectors, sitemap discovery need live-site testing |
| Old adapter files still in repo | Low | `threadless_adapter.py`, `supermicro_adapter.py` kept as legacy — can be removed after verifying new adapters work |
| `sys.path.insert` for shared/ imports | Low | Upgrade to `pip install -e .` when team grows |

---

## Recently Completed

Move items here when done (keep last 5 for reference, then delete oldest).

| Date | Task | Who |
|------|------|-----|
| 2026-04-07 | Monorepo refactoring: shared/, adapter registry, unified pipeline, universal scraping chain | Agent |
| 2026-04-07 | Marketing website redesign (monochrome + GSAP orb) | Agent |
| 2026-04-07 | Client acquisition backend (6 endpoints + notifications) | Agent |
| 2026-04-06 | Repo cleanup (removed dashboard, dead code, stale scripts) | Agent |
| 2026-04-05 | Supermicro GPU onboarding pipeline | Agent |
