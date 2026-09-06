# Agent Memory — Active Work State

> **Keep this file under 2KB.** It is read by every agent at session start.
> **Last updated:** 2026-09-06

---

## Active Tasks

- **A1–A10 measurement (STOP-gated Tasks 7–9)** — Lightsail pull, widget copy, and Wrina `language=hi` are done. Next is `testing/manual_test_checklist.md` A1–A10 (3× WiFi, 3× 4G). Needs `ADMIN_PASSWORD` for `/api/latency-summary`. Do **not** re-PATCH Wrina or run `create_agent`.
- **Do not start Tasks 7–9** until those numbers exist.

---

## Files Currently Being Modified

- none (ops deploy landed; this branch only records it)

---

## Recent Completions (for quick context)

- **2026-09-06** — Lightsail `ubuntu@13.232.36.194`: `90e9b00` → `3f411ce`, widget `dist/` copied (`SEARCH_FAIL` live), env tags `v3-heardyou-searchfail` / `v3-error-persist`. Wrina GET-only; `language=hi` unchanged.
- **2026-09-04** — Wrina `update_agent` prompt+tools PATCH (`show_search_error`); `language` left `hi`.
- **2026-09-04** — Tasks 1–6 coded + merged to `release/xfused-pilot`.
