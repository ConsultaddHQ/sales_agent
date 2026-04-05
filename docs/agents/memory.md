# Agent Memory — Active Work State

> **Keep this file under 2KB.** It is read by every agent at session start.
> **Last updated:** 2026-04-05

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
| 2026-04-05 | Supermicro GPU onboarding pipeline + ElevenLabs API update + search service debugging | `supermicro_scraper.py` (new), `supermicro_adapter.py` (new), `main.py`, `elevenlabs_agent.py`, `error_codes.py`, `search-service/main.py`, deleted `image-service/` | Claude Code |
| 2026-04-03 | Threadless store integration — full pipeline + ElevenLabs SDK v1.0 migration | `threadless_adapter.py` (new), `main.py`, `elevenlabs_agent.py`, `App.jsx`, `AvatarWidget.jsx`, `search-service/main.py` | Claude Code |
| 2026-04-02 | Added completed-work log and clarified agent-doc ownership | `AGENTS.md`, `CLAUDE.md`, `docs/agents/*` | Codex |
| 2026-04-05 | Auto: dff7d632 | 0 | Hook |
| 2026-04-05 | Auto: dff7d632 | 0 | Hook |
| 2026-04-05 | Auto: dff7d632 | 0 | Hook |
| 2026-04-05 | Auto: dff7d632 | 0 | Hook |
| 2026-04-05 | Auto: dff7d632 | 0 | Hook |
| 2026-04-05 | Auto: dff7d632 | 0 | Hook |

---

## Open Questions / Blockers

- ngrok URL changes on restart — agent webhook URL is baked in at creation time, agent must be re-created
- Supermicro internal API (`/en/structuredbapi/ps2/system/gpu/all`) is undocumented — may change without notice
- Image server path mismatch: images saved to `onboarding-service/images/` but served from repo-root `./images/`
