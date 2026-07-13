# Agent Memory — Active Work State

> **Keep this file under 2KB.** It is read by every agent at session start.
> **Last updated:** 2026-07-10

---

## Active Tasks

- (none)

---

## Files Currently Being Modified

- (none)

---

## Recent Completions (for quick context)

- **2026-07-10** — Sensesindia demo carousel images fix: ngrok free-tier interstitial returned HTML (status 200) for widget image requests. Backfilled 151 `products.image_url` rows with original Shopify CDN URLs; `/search` now returns `image_url` (CDN) + `local_image_url` (served) separately so the widget's onError fallback works. Files: `search-service/main.py`, DB backfill. NOTE: re-onboarding overwrites image_url with served URL again (see roadmap).
- **2026-06-23** — Metrics enrichment + Cart integration + Product pairing: `conversation_id`/latency persisted to `session_feedback`, `add_to_cart` client tool + "Add to Cart" UI button (Shopify Ajax API), `get_similar_products` webhook tool + `/similar-products` endpoint (vector similarity). All 5 agent prompts updated. Build: 381KB gzip. Run `create_feedback_table.sql` migration in Supabase before using new metrics columns.
- **2026-06-23** — UI Overhaul (6 items): removed drag localStorage, split product layout (image above/details below), new LISTENING/THINKING/AGENT_SPEAKING orb states with volume-reactive detection (rAF loop), per-state status pill colors, first-visit nudge tooltip, "Talk to AI" label + mic icon in IDLE pill. Build: 380KB gzip. See completions.md.
- **2026-06-19** — Full codebase audit (`docs/audit-2026-06-19.md`) + performance audit (`docs/perf-audit-2026-06-19.md`) across 3 branches. Detailed refactor plan written (`docs/refactor-plan-2026-06-19.md`). Code not yet executed — see handoff.
