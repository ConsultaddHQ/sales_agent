# Agent Memory — Active Work State

> **Keep this file under 2KB.** It is read by every agent at session start.
> **Last updated:** 2026-09-30

---

## Active Tasks

- **2026-10-02 — Fast flow ready:** voice-test bugs fixed + deployed. Branches at 0%: `fast-v1` (Haiku, recommended, 28/28) and `fast-gemini35lite` (runner-up). Waiting on the human to ear-test both and pick one → deploy %. Still needed: Grafana stack URL (not the Loki URL), Slack webhook, alert email. Shopify token deferred.
- **Voice-latency Tasks 7–9** (`docs/superpowers/plans/2026-09-04-xfused-voice-latency.md`) stay STOP-gated until measured numbers exist — Phase 0 is what produces them.

---

## Files Currently Being Modified

- none

---

## Recent Completions (for quick context)

- **2026-09-04** — Whole-branch review fixes: single latency row per leg, session-scoped SEARCH_FAIL, fallback re-armed after filler, timing headers on search errors.
- **2026-09-04** — Instant THINKING, SEARCH_FAIL UI, `show_search_error` tool, per-turn latency POST, error-path `search_latency` rows.
- **2026-08-13** — Latency-audit: 07-20 work never deployed; live agent `language="hi"` + `eleven_flash_v2_5`.
