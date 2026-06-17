# Agent Memory — Active Work State

> **Keep this file under 2KB.** It is read by every agent at session start.
> **Last updated:** 2026-06-12

---

## Currently In Progress

| Task | Files | Owner | Status | Notes |
|------|-------|-------|--------|-------|
| (none — latency plan complete) | — | — | — | Next pickups: existing-agent upgrades via `testing/latency/upgrade_agent_model.py`; product-description strategy for larger catalogs (tracked in roadmap) |

---

## Files Currently Being Modified

- (none)

---

## Recently Completed (Last 7 Days)

| Date | What Was Done | Files Changed | Agent/Author |
|------|--------------|---------------|--------------|
| 2026-06-12 | Fixed product-image 404s in voice agent (4 layers: search returned stale image_url; missing `IMAGE_SERVER_URL` in search `.env`; opaque `update_products` schema dropped image_url at the LLM hop; wrong DUMMY_IMAGE path). Pushed schema to live agent; rebuilt widget | `search-service/main.py`, `search-service/.env`, `onboarding-service/elevenlabs_agent.py`, `www.teampop/frontend/src/components/AvatarWidget.jsx` | Claude |
| 2026-04-17 | STEP 3: 6-model A/B picked Claude Haiku 4.5 (100% tool reliability, ~3.4s median). Default flipped; harness moved to `testing/latency/` with new upgrade helper | `onboarding-service/elevenlabs_agent.py`, `onboarding-service/.env.example`, `testing/latency/*` | Claude |
| 2026-04-17 | STEP 1+2+4: warmup + timing header + proxy client reuse; hybrid_search_products rewritten for HNSW + new products_fts_idx GIN; tool-first prompt rule in all 5 templates | `search-service/main.py`, `onboarding-service/main.py`, `onboarding-service/elevenlabs_agent.py`, Supabase | Claude |
| 2026-04-14 | Phase 1 voice UX: reduced ElevenLabs to two tools, rewrote prompts for one-turn context-before-search | `onboarding-service/elevenlabs_agent.py`, widget | Codex |
| 2026-04-14 | Phase 2 infrastructure: async search endpoint, thread-offloaded embedding/RPC, rate limiting | `search-service/`, `shared/` | Codex |
| 2026-04-10 | Conservative cleanup: removed legacy adapters, stale widget helper, low-risk dead code | `onboarding-service/`, `www.teampop/` | Codex |
| 2026-06-12 | Auto: a9fc0cd1 | 0 | Hook |
| 2026-06-16 | Auto: fb10cbb2 | 0 | Hook |
| 2026-06-17 | Auto: f204c865 | 0 | Hook |
| 2026-06-17 | Auto: f204c865 | 0 | Hook |

---

## Open Questions / Blockers

- Supabase region (US/EU) vs. app region (India) = ~1s network floor on every search call. Mitigation: move region or add short-TTL cache.
- Product description currently truncated to 200 chars in `_truncate_for_voice`. OK for now; revisit when catalogs grow or richer descriptions land.
- ngrok URL changes on restart — mitigated by single-tunnel setup (one URL to update).
