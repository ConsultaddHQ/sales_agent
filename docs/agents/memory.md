# Agent Memory — Active Work State

> **Keep this file under 2KB.** It is read by every agent at session start.
> **Last updated:** 2026-04-03

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
| 2026-04-03 | Threadless store integration — full pipeline + ElevenLabs SDK v1.0 migration | `onboarding-service/threadless_adapter.py` (new), `main.py`, `elevenlabs_agent.py`, `requirements.txt`, `www.teampop/frontend/src/App.jsx`, `AvatarWidget.jsx`, `search-service/main.py` | Claude Code |
| 2026-04-02 | Added completed-work log and clarified agent-doc ownership | `AGENTS.md`, `CLAUDE.md`, `docs/agents/*` | Codex |
| 2026-03-30 | Created initial agent docs and support folder | `docs/agents/*`, `AGENTS.md` | Claude Code |
| 2026-04-03 | Auto: 87f42ae0 | 0 | Hook |
| 2026-04-03 | Auto: 87f42ae0 | 0 | Hook |

---

## Open Questions / Blockers

- ElevenLabs API PATCH for tools has validation issue — tools must be added via dashboard UI for now
- Image server path mismatch: images saved to `onboarding-service/images/` but served from repo-root `./images/` — needs copy after onboarding
- ngrok URL changes on restart — agent webhook URL must be manually updated each time
