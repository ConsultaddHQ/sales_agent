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
| 2026-04-07 | Website redesign: Resend-inspired monochrome theme, CSS+GSAP orb (replaced Three.js), enhanced cards with Winterfell-style scroll animation + tilt + tag pills, 2-column FAQ section, request form + admin dashboard | `www.teampop/website/src/` (all components, pages, index.css, api.js), `package.json` | Claude Code |
| 2026-04-07 | Client acquisition backend: submit-request, admin auth, process/send pipelines, Resend+Slack notifications | `onboarding-service/main.py`, `notifications.py` (new), `.env.example`, `requirements.txt` | Claude Code |
| 2026-04-06 | Repo cleanup: removed dashboard, dead frontend pages, stale scripts, updated all docs | Deleted `dashboard/`, `scripts/`, dead pages/CSS; updated `AGENTS.md`, `README.md` | Claude Code |
| 2026-04-05 | Supermicro GPU onboarding pipeline + ElevenLabs API update + search service debugging | `supermicro_scraper.py`, `supermicro_adapter.py`, `main.py`, `elevenlabs_agent.py` | Claude Code |
| 2026-04-07 | Auto: 899ded9c | 0 | Hook |

---

## Open Questions / Blockers

- ngrok URL changes on restart — agent webhook URL is baked in at creation time
- Supermicro internal API (`/en/structuredbapi/ps2/system/gpu/all`) is undocumented
- Image server path mismatch: images saved to `onboarding-service/images/` but served from `./images/`
- `agent_requests` table not yet created in Supabase (manual step required)
- External services not yet configured: Resend API key, Slack webhook, Calendly link
