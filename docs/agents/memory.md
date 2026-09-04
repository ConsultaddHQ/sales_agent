# Agent Memory — Active Work State

> **Keep this file under 2KB.** It is read by every agent at session start.
> **Last updated:** 2026-09-04

---

## Active Tasks

- **Voice latency work implemented on `cursor/voice-latency-design-bcc1`** — Tasks 1–6 of `docs/superpowers/plans/2026-09-04-xfused-voice-latency.md` are coded and unit-tested on that branch. Nothing is live yet.
- **Blocked on human Lightsail deploy** — pull the branch on the box, rebuild the widget locally and scp `dist/`, then PATCH the Wrina agent via `update_agent` (prompt + tools only). Do **not** re-run `create_agent`; `language="hi"` must stay. Runbook: `docs/agents/handoff.md` (2026-09-04).
- **Tasks 7–9 are STOP-gated** — do not start them until the deployed numbers from checklist A1–A10 come back. They exist to be chosen by data, not guessed.

---

## Files Currently Being Modified

- none (branch is clean; awaiting deploy + measurement)

---

## Recent Completions (for quick context)

- **2026-09-04** — Whole-branch review fixes: single latency row per leg, session-scoped SEARCH_FAIL, fallback re-armed after filler, timing headers on search errors.
- **2026-09-04** — Instant THINKING, SEARCH_FAIL UI, `show_search_error` tool, per-turn latency POST, error-path `search_latency` rows.
- **2026-08-13** — Latency-audit: 07-20 work never deployed; live agent `language="hi"` + `eleven_flash_v2_5`.
