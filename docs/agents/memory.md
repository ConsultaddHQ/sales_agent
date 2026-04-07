# Agent Memory — Active Work State

> **Keep this file under 2KB.** It is read by every agent at session start.
> **Last updated:** 2026-04-07

---

## Currently In Progress

| Task | Files | Owner | Status | Notes |
|------|-------|-------|--------|-------|
| *(none active)* | — | — | — | Update this before significant work |

---

## Files Currently Being Modified

*(none)*

---

## Recently Completed (Last 7 Days)

| Date | What Was Done | Files Changed | Agent/Author |
|------|--------------|---------------|--------------|
| 2026-04-07 | Monorepo refactoring: plug-and-play adapter registry, shared/ library, unified pipeline, universal scraping chain (JSON-LD, microdata, OG, sitemap, platform selectors, LLM fallback) | `shared/`, `onboarding-service/{adapters,routes,services,scraping,pipeline}.py`, `main.py`, `search-service/main.py` | Claude Code |
| 2026-04-07 | Website redesign: monochrome theme, CSS+GSAP orb, Winterfell cards, FAQ, request form + admin dashboard | `www.teampop/website/src/` | Claude Code |
| 2026-04-07 | Client acquisition backend: submit-request, admin auth, process/send pipelines, notifications | `onboarding-service/main.py`, `notifications.py` | Claude Code |
| 2026-04-06 | Repo cleanup: removed dashboard, dead scripts, updated docs | Deleted `dashboard/`, `scripts/` | Claude Code |
| 2026-04-05 | Supermicro GPU onboarding + search service debugging | `supermicro_scraper.py`, `supermicro_adapter.py` | Claude Code |
| 2026-04-07 | Auto: 4e3d92ea | 0 | Hook |
| 2026-04-07 | Auto: 4e3d92ea | 0 | Hook |
| 2026-04-07 | Auto: 4e3d92ea | 0 | Hook |
| 2026-04-07 | Auto: 7d827691 | 0 | Hook |

---

## Open Questions / Blockers

- ngrok URL changes on restart — agent webhook URL is baked in at creation time
- `agent_requests` table not yet created in Supabase (manual step required)
- External services not yet configured: Resend API key, Slack webhook, Calendly link
