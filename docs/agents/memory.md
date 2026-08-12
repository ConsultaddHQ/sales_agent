# Agent Memory — Active Work State

> **Keep this file under 2KB.** It is read by every agent at session start.
> **Last updated:** 2026-08-13

---

## Active Tasks

- **Deploy blocked on human** — the 2026-07-20 latency work (cache, tracking tables, soft-timeout fix) was never deployed to `api.teampop.com`; still running pre-`03ef0af` code as of 2026-08-13. Two blocking bugs fixed in code this session; human still needs to run the actual deploy. Full runbook in `docs/agents/handoff.md` (2026-08-13 entry) — do that before any further latency work, or new numbers will be meaningless.

---

## Files Currently Being Modified

- (none)

---

## Recent Completions (for quick context)

- **2026-08-13** — Latency-audit reconciliation: found the 07-20 latency work was never deployed (0 rows in `turn_latency`/`search_latency` despite live traffic); found live ElevenLabs agent diverged from code (`language="hi"` + `eleven_flash_v2_5`, not code's hardcoded `"en"`+`eleven_flash_v2`); fixed `/api/latency-summary` 500 (`agent_requests` table doesn't exist on this Supabase project); made `create_agent()`'s `language` configurable instead of hardcoded. See handoff.md + decisions.md (2026-08-12 entry).
- **2026-07-20** — Per-turn latency tracking (`turn_latency`, `search_latency` tables, `config_variant` tagging) + soft_timeout 2.5s→1.2s + search result cache (5min TTL). Run `create_latency_tracking_table.sql` in Supabase. See completions.md.
- **2026-07-03** — Xfused skincare pilot launch (`release/xfused-pilot`): deployed on AWS Lightsail Mumbai (Caddy → onboarding :8005 proxies /search; 2 GB + swap). Domain-neutral Claude prompt + strict search-first/clarify guardrails; `final_limit` 5→12; rerank **relevance cutoff** (`RERANK_SCORE_MARGIN`) with **browse-intent bypass** (specific queries trim to relevant, "show me everything" returns all). Load-test + latency-report + per-agent cost scripts under `testing/`. See completions.md + decisions.md.
- **2026-06-29** — Context-aware dock button: "Chat" ↔ "← Products" toggle in OrbDock based on activeView + latestProducts. `www.teampop/frontend/src/components/AvatarWidget.jsx`
- **2026-06-23** — Metrics enrichment + Cart integration + Product pairing: `conversation_id`/latency persisted to `session_feedback`, `add_to_cart` client tool + "Add to Cart" UI button (Shopify Ajax API), `get_similar_products` webhook tool + `/similar-products` endpoint (vector similarity). All 5 agent prompts updated. Build: 381KB gzip. Run `create_feedback_table.sql` migration in Supabase before using new metrics columns.
- **2026-06-23** — UI Overhaul (6 items): removed drag localStorage, split product layout (image above/details below), new LISTENING/THINKING/AGENT_SPEAKING orb states with volume-reactive detection (rAF loop), per-state status pill colors, first-visit nudge tooltip, "Talk to AI" label + mic icon in IDLE pill. Build: 380KB gzip. See completions.md.
