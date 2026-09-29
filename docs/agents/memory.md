# Agent Memory — Active Work State

> **Keep this file under 2KB.** It is read by every agent at session start.
> **Last updated:** 2026-09-30

---

## Active Tasks

- **2026-09-30 — Phase 0 observability** (`perf/phase0-observability`, rebased on `release/xfused-pilot` @ 3f411ce which is live on the box). Being deployed by Claude. Runbook: `docs/observability-runbook.md`.
- **Voice-latency Tasks 7–9** (`docs/superpowers/plans/2026-09-04-xfused-voice-latency.md`) stay STOP-gated until measured numbers exist — Phase 0 is what produces them.

---

## Files Currently Being Modified

- `perf/phase0-observability`: shared/observability.py, search-service/main.py, onboarding-service/{main.py,routes/webhooks.py,routes/client.py,elevenlabs_agent.py}, widget AvatarWidget.jsx/App.jsx/telemetry.js

---

## Recent Completions (for quick context)

- **2026-09-04** — Whole-branch review fixes: single latency row per leg, session-scoped SEARCH_FAIL, fallback re-armed after filler, timing headers on search errors.
- **2026-09-04** — Instant THINKING, SEARCH_FAIL UI, `show_search_error` tool, per-turn latency POST, error-path `search_latency` rows.
- **2026-08-13** — Latency-audit: 07-20 work never deployed; live agent `language="hi"` + `eleven_flash_v2_5`.
