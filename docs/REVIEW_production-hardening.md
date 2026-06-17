# Branch review: `production-hardening`

A guided walkthrough of every **code** change on this branch so you can review, verify, and learn
the techniques used. (Doc/agent-file updates are intentionally excluded here.)

**Branch:** `production-hardening` (off `version/v2`)
**Commits:**
- `7b264a8` — fix: wire `get_product_details` end-to-end *(also lives on `version/v2`)*
- `bf36d6f` — feat: abuse/cost protection (webhook secret, session caps, CORS)
- `ce996cc` — feat: request-id log correlation + search-service test harness

Quick verify (all hermetic, no live services needed):
```bash
# 1. search-service imports + 13 tests pass
cd search-service && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/python -m pytest -q
# 2. all changed modules compile
cd .. && onboarding-service/.venv/bin/python -m py_compile \
  onboarding-service/main.py onboarding-service/elevenlabs_agent.py image_server.py
```

---

## 1. `get_product_details` wired end-to-end (`7b264a8`)

The on-demand detail tool + `metadata` JSONB column existed but was non-functional. Five fixes:

| # | File | Change | Why |
|---|------|--------|-----|
| B1 | `search-service/main.py` | `from typing import Any, Dict, List, Optional` | The `/product-details` return annotation `Dict[str, Any]` was evaluated at import time but `Any` wasn't imported → `NameError` crashed the **whole** service (incl. `/search`). |
| B2 | `onboarding-service/main.py` | Added `POST /product-details` proxy; generalized `_do_proxy(path, …)` | The single ngrok tunnel only routes through onboarding, which previously proxied `/search` only → the tool 404'd in the demo. |
| Q1/Q2/Q3 | `onboarding-service/elevenlabs_agent.py` | Documented `get_product_details` in all 5 prompt templates; removed the contradicting "route sizing to Shop Now"; added the **anti-fabrication** rule | The agent must answer specifics only from the tool result and say "not listed" when data is absent — never invent (e.g. wash-care). |
| B3 | `add_metadata_column.sql` | `ADD COLUMN IF NOT EXISTS` | Idempotent — safe to re-run. |

**Ops (not code):** apply the migration in Supabase; re-onboard sensesindia with `store_type="shopify"`
(custom domains auto-detect as *universal*, which drops variants).

**Concept to learn:** Python evaluates function annotations at `def` time unless
`from __future__ import annotations` is set — a missing name in an annotation is a real import-time crash,
not just a type-checker warning. `py_compile` won't catch it; an actual `import` will.

---

## 2. Abuse / cost protection (`bf36d6f`)

All backward-compatible — defaults preserve current behavior.

### 2a. Webhook shared-secret auth
- `search-service/main.py`: `WEBHOOK_SECRET` env + `_check_webhook_secret(request)` called at the top of
  `/search` and `/product-details`. Uses **`hmac.compare_digest`** (constant-time) to avoid timing attacks.
  When the env is unset it's a no-op (demo stays open).
- `onboarding-service/main.py`: the proxy reads `X-TeamPop-Secret` off the incoming request and **forwards**
  it downstream (the public edge relays; search-service validates — defense in depth).
- `onboarding-service/elevenlabs_agent.py`: `_get_tool_config` bakes the secret into both webhook tools'
  `request_headers` at agent-creation time, so the LLM never sees or handles it.

### 2b. Session cost caps
- `elevenlabs_agent.py`: `max_duration_seconds` 600 → 300 (caps voice minutes per conversation).
- All 5 prompts gained a **scope guardrail**: "only help with shopping here … not a general assistant"
  — stops users burning minutes/tokens off-topic.

### 2c. CORS allowlist
- `search-service/main.py`, `onboarding-service/main.py`, `image_server.py`: wildcard `["*"]` →
  `ALLOWED_ORIGINS` env (comma-split, default `*`).

**To activate the secret:** set the same `WEBHOOK_SECRET` in both `.env`s, set `ALLOWED_ORIGINS` to real
domains, re-push live agents (the header is baked at creation), restart. Until then nothing changes.

**Concepts to learn:** constant-time secret comparison (`hmac.compare_digest`); server-to-server webhook
auth via a baked header rather than user identity; "open by default, enforce when configured" rollout.

---

## 3. Request-id correlation + test harness (`ce996cc`)

### 3a. Cross-service log correlation
- `search-service/main.py`: a `contextvars.ContextVar` holds the request id; a `logging.Filter` injects it
  into **every** log record as `[request_id]` (format string updated). The filter is attached to the
  **handler** (not a logger) so even uvicorn's records get the field — no `KeyError` on the new format.
  `RequestLoggingMiddleware` reads an incoming `X-Request-ID` or generates one, sets the contextvar for the
  request, and echoes it back in the response header.
- `onboarding-service/main.py`: the proxy generates/propagates `X-Request-ID` and forwards it downstream, so
  one voice turn shares a single id across both services' logs.

### 3b. Hermetic test harness
- `search-service/tests/test_main.py` (13 tests) + `conftest.py`. **No DB, no model download** — `FakeSupabase`
  and `FakeEmbedder` are injected with `monkeypatch.setattr(main, "get_supabase", …)`, and FastAPI's
  `TestClient` drives the endpoints. `conftest.py` pins a high rate limit and disables the secret by default,
  setting env **before** `main` is imported (the limiter + secret are read at import time).
- Coverage: `/health`; `/search` (happy / empty / bad-store-id / no-results); `/product-details`
  (happy / 404 / bad-uuid); secret auth (401 + accept on both endpoints); `_truncate_for_voice`.
- `requirements-dev.txt`: `pytest`, `httpx` (dev-only).

**Concepts to learn:** `contextvars` for per-request state in async code; a logging `Filter` as the clean way
to add a field to every log line without touching call sites; `monkeypatch` + dependency-style globals to make
FastAPI tests fully hermetic; why test env must be set before module import when values are read at import time.

---

## What is NOT done yet (tracked in `docs/agents/roadmap.md`)
- **Per-store rate limiting** — current limiting is per-IP, which mis-groups ElevenLabs' shared egress IPs.
  Real per-store limits need shared state (Redis); deferred to the AWS phase.
- **Activate the webhook secret** in production (currently off by default).
- **`ShopifyAdapter.matches_url`** should probe `/products.json` so custom-domain Shopify auto-detects
  correctly (today you must pass `store_type="shopify"`).
