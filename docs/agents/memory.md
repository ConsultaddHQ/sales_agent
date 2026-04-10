# Agent Memory — Active Work State

> **Keep this file under 2KB.** It is read by every agent at session start.
> **Last updated:** 2026-04-10

---

## Currently In Progress

| Task | Files | Owner | Status | Notes |
|------|-------|-------|--------|-------|
| Conservative cleanup pass 2: remaining lint-safe cleanup and stale current-guidance references | `docs/agents/memory.md`, `www.teampop/frontend/`, `www.teampop/website/` | Codex | In progress | Fix only low-risk lint items and preserve historical docs |

---

## Files Currently Being Modified

- `docs/agents/memory.md` — Codex

---

## Recently Completed (Last 7 Days)

| Date | What Was Done | Files Changed | Agent/Author |
|------|--------------|---------------|--------------|
| 2026-04-10 | Conservative cleanup: removed legacy adapters, stale widget z-index helper, unused website starter assets, and low-risk dead comments/imports after verification | `onboarding-service/`, `www.teampop/frontend/`, `www.teampop/website/`, `docs/Engineering Standards.md` | Codex |
| 2026-04-09 | Tools-first Gemini prompt + WebSocket disconnect diagnostic logging + complete agent conversation cycle docs | `elevenlabs_agent.py`, `AvatarWidget.jsx`, `completions.md`, `decisions.md` | Claude Code |
| 2026-04-08 | ElevenLabs API migration + latency optimization + single-tunnel sharing + widget latency tracking | `elevenlabs_agent.py`, `main.py`, `AvatarWidget.jsx`, `image_server.py`, `admin.py`, `client.py` | Claude Code |
| 2026-04-07 | Monorepo refactoring: adapter registry, shared/ library, unified pipeline, universal scraping chain | `shared/`, `onboarding-service/` | Claude Code |
| 2026-04-07 | Website redesign: monochrome theme, CSS+GSAP orb, request form + admin dashboard | `www.teampop/website/src/` | Claude Code |
| 2026-04-07 | Client acquisition backend: submit-request, admin auth, process/send pipelines, notifications | `onboarding-service/main.py`, `notifications.py` | Claude Code |
| 2026-04-06 | Repo cleanup: removed dashboard, dead scripts, updated docs | Deleted `dashboard/`, `scripts/` | Claude Code |
| 2026-04-05 | Supermicro GPU onboarding + search service debugging | `supermicro_scraper.py`, `supermicro_adapter.py` | Claude Code |
| 2026-04-08 | Auto: fb58ef88 | 0 | Hook |
| 2026-04-08 | Auto: 7d827691 | 0 | Hook |
| 2026-04-08 | Auto: 7d827691 | 0 | Hook |
| 2026-04-08 | Auto: fb58ef88 | 0 | Hook |
| 2026-04-08 | Auto: fb58ef88 | 0 | Hook |
| 2026-04-08 | Auto: fb58ef88 | 0 | Hook |
| 2026-04-08 | Auto: fb58ef88 | 0 | Hook |
| 2026-04-09 | Auto: 1f65f923 | 0 | Hook |
| 2026-04-09 | Auto: 1f65f923 | 0 | Hook |
| 2026-04-09 | Auto: 1f65f923 | 0 | Hook |
| 2026-04-09 | Auto: 1f65f923 | 0 | Hook |
| 2026-04-09 | Auto: 1f65f923 | 0 | Hook |
| 2026-04-09 | Auto: 1f65f923 | 0 | Hook |
| 2026-04-09 | Auto: 1f65f923 | 0 | Hook |
| 2026-04-09 | Auto: 1f65f923 | 0 | Hook |
| 2026-04-09 | Auto: 1f65f923 | 0 | Hook |
| 2026-04-09 | Auto: 1f65f923 | 0 | Hook |
| 2026-04-10 | Auto: fb58ef88 | 0 | Hook |
| 2026-04-10 | Auto: 7d827691 | 0 | Hook |
| 2026-04-10 | Auto: 899ded9c | 0 | Hook |
| 2026-04-10 | Auto: bd854b47 | 0 | Hook |

---

## Open Questions / Blockers

- ngrok URL changes on restart — agent webhook URL is baked in at creation time; single-tunnel setup mitigates (only 1 URL to update)
- ngrok free tier interstitial may block widget script load on first visit for external users
- `glm-45-air-fp8` LLM needs validation on complex tool-calling prompts — fallback to `gpt-4o-mini` via env var
