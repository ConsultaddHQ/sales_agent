# Agent Memory — Active Work State

> **Keep this file under 2KB.** It is read by every agent at session start.
> **Last updated:** 2026-09-30

---

## Active Tasks

- **2026-10-02 — Phases 0–4 deployed** on branch `perf/phase0-observability` (box). Fast flow built on ElevenLabs branches `fast-v1` (Haiku) and `fast-v2-gpt54mini` at 0% live — **waiting on the human voice test**, then deploy %. Waiting on the human for: Grafana stack URL, Slack webhook URL, alert email, Shopify admin token + app secret. See handoff.md 2026-10-02.
- **Voice-latency Tasks 7–9** (`docs/superpowers/plans/2026-09-04-xfused-voice-latency.md`) stay STOP-gated until measured numbers exist — Phase 0 is what produces them.

---

## Files Currently Being Modified

- none

---

## Recent Completions (for quick context)

- **2026-09-04** — Whole-branch review fixes: single latency row per leg, session-scoped SEARCH_FAIL, fallback re-armed after filler, timing headers on search errors.
- **2026-09-04** — Instant THINKING, SEARCH_FAIL UI, `show_search_error` tool, per-turn latency POST, error-path `search_latency` rows.
- **2026-08-13** — Latency-audit: 07-20 work never deployed; live agent `language="hi"` + `eleven_flash_v2_5`.
