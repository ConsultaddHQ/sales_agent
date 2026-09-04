# Agent Memory — Active Work State

> **Keep this file under 2KB.** It is read by every agent at session start.
> **Last updated:** 2026-09-04

---

## Active Tasks

- **Wrina PATCH done** — `agent_4901kwna71tve5nbyy85c8v20yre` has `show_search_error`; `language` still `"hi"`. Do not run `create_agent`.
- **Blocked on Lightsail SSH** — this env has all 24 API secrets, but SSH to the Mumbai box as `ubuntu` is `Permission denied (publickey)`. Need `LIGHTSAIL_SSH_PRIVATE_KEY` (or a human) to pull `release/xfused-pilot`, bump config versions, restart `tp-onboard`/`tp-search`, and scp `www.teampop/frontend/dist/`.
- **Live widget is stale** — production `/widget/widget.js` has `turn-latency` but not `SEARCH_FAIL`. Local dist is built and ready to copy.
- **Tasks 7–9 are STOP-gated** — wait for A1–A10 numbers. `ADMIN_PASSWORD` is not in this env.

---

## Files Currently Being Modified

- none (ops session; widget `dist/` is gitignored)

---

## Recent Completions (for quick context)

- **2026-09-04** — Confirmed new env has all 24 injected secrets. PATCHed Wrina prompt+tools only; `language=hi` unchanged.
- **2026-09-04** — Whole-branch review fixes: single latency row per leg, session-scoped SEARCH_FAIL, fallback re-armed after filler, timing headers on search errors.
- **2026-09-04** — Instant THINKING, SEARCH_FAIL UI, `show_search_error` tool, per-turn latency POST, error-path `search_latency` rows.
- **2026-08-13** — Latency-audit: 07-20 work never deployed; live agent `language="hi"` + dashboard TTS.

