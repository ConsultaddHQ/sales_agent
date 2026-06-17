# Agent Memory — Active Work State

> **Keep this file under 2KB.** It is read by every agent at session start.
> **Last updated:** 2026-06-17

---

## Currently In Progress

| Task | Files | Owner | Status | Notes |
|------|-------|-------|--------|-------|
| (paused) Production hardening — workstream 1 | — | — | Paused | Lean core done (abuse/cost + logging + tests). Remaining: per-store rate limiting (needs Redis). Next workstreams: AWS deploy, generalize enrichment to other store types. Branch: `production-hardening`. |

---

## Files Currently Being Modified

- (none)

---

## Recently Completed (Last 7 Days)

| Date | What Was Done | Files Changed | Agent/Author |
|------|--------------|---------------|--------------|
| 2026-06-17 | Prod-hardening #2 (observability+tests): request-id correlation across onboarding↔search; 13-test hermetic pytest harness | `search-service/main.py`, `onboarding-service/main.py`, `search-service/tests/*` | Claude |
| 2026-06-17 | Prod-hardening #1 (abuse/cost): webhook shared-secret on `/search`+`/product-details`, session cap 600→300, scope guardrail in all 5 prompts, env-driven CORS allowlist | `search-service/main.py`, `onboarding-service/main.py`+`elevenlabs_agent.py`, `image_server.py` | Claude |
| 2026-06-17 | Wired `get_product_details` end-to-end: fixed search-service `Any`-import crash, `/product-details` proxy 404, prompt anti-fabrication contract, idempotent migration; re-onboarded sensesindia as Shopify with rich metadata | `search-service/main.py`, `onboarding-service/main.py`+`elevenlabs_agent.py`, `add_metadata_column.sql` | Claude |
| 2026-06-16 | `get_product_details` tool + `metadata` JSONB capture (initial impl) | `onboarding-service/services/products.py`, `search-service/main.py` | Gemini |
| 2026-06-12 | Fixed product-image 404s in voice agent (4 layers) | `search-service/main.py`, `search-service/.env`, `onboarding-service/elevenlabs_agent.py`, widget | Claude |
| 2026-04-17 | STEP 3: 6-model A/B → Claude Haiku 4.5 default; harness in `testing/latency/` | `onboarding-service/elevenlabs_agent.py`, `testing/latency/*` | Claude |
| 2026-04-17 | STEP 1+2+4: warmup, timing header, HNSW+GIN `hybrid_search_products` | `search-service/main.py`, `onboarding-service/main.py`, Supabase | Claude |

---

## Open Questions / Blockers

- **Webhook secret not yet activated:** `WEBHOOK_SECRET` is unset in prod (enforcement off, demo works). To activate: set the same value in both services' `.env`, set `ALLOWED_ORIGINS`, re-push agents, restart.
- **Per-store rate limiting** still IP-based (mis-groups ElevenLabs' shared IPs). Needs shared state (Redis) — fold into AWS phase.
- Supabase region (US/EU) vs. app region (India) = ~1s network floor per search. Mitigation: move region or short-TTL cache.
- ngrok URL changes on restart — mitigated by single-tunnel setup (one URL to update). Retire ngrok in the AWS phase (Caddy + domain).
