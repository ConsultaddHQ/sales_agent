# Risks, Security, And Production Gaps

## What This Is

This file is a candid summary of the current operational, security, and production-readiness gaps in the repo.

## Why It Exists

The project is an early-alpha prototype. Honest documentation of the gaps is part of making the system maintainable and safe to improve.

## Current Security Gaps

### Wildcard CORS

- Current state: both services allow `allow_origins=["*"]`.
- Why it exists: local/demo convenience during alpha.
- Where the code is: `onboarding-service/main.py`, `search-service/main.py`.
- Risk: too permissive for production; broadens browser-access surface.
- Improve next: restrict allowed origins to known domains before public deployment.

### Basic Admin Authentication

- Current state: admin endpoints use `X-Admin-Password`.
- Where the code is: `onboarding-service/routes/admin.py`, `onboarding-service/routes/client.py`, `www.teampop/website/src/lib/api.js`.
- Risk: weak operational security, poor auditability, easy credential sharing.
- Improve next: migrate to stronger auth such as JWT/session-based admin auth.

### Missing Rate Limiting

- Current state: public request submission has no rate limiting.
- Where the code is: `onboarding-service/routes/client.py`.
- Risk: spam, abuse, unnecessary notification load, and noisy database growth.
- Improve next: add per-IP or per-identity throttling before wider exposure.

### Service-Role Key Boundaries

- Current state: backend services depend on Supabase service-role credentials.
- Where the rule lives: `../agents/constraints.md`.
- Risk: accidental client-side exposure would bypass row-level protections.
- Improve next: maintain strict backend-only usage and review any future frontend DB access carefully.

## Operational Risks

### ngrok / Demo Fragility

- Current state: demos rely on a single-tunnel pattern and can require reconfiguration after restart.
- Source: `../agents/decisions.md`, `../agents/roadmap.md`.
- Risk: broken demo links, stale webhook URLs, confusing external testing experience.
- Improve next: move to a more stable deployment path for shared demos.

### ElevenLabs Conversation Reliability

- Current state: recent work improved latency and tool ordering, but the flow is still sensitive.
- Where the code is: `onboarding-service/elevenlabs_agent.py`, `www.teampop/frontend/src/components/AvatarWidget.jsx`.
- Risk: missed tool calls, WebSocket disconnects, filler responses, or inconsistent interruption behavior.
- Improve next: automate end-to-end validation and add stronger observability.

### Adapter / Scraper Brittleness

- Current state: some platforms depend on brittle HTML, Playwright rendering, or undocumented APIs.
- Where the code is: `onboarding-service/adapters/`, `onboarding-service/scraping/`, `universal-scraper/`.
- Risk: source sites change and silently reduce onboarding quality or coverage.
- Improve next: test known target sites regularly and capture scraper health regressions.

## Product And Quality Gaps

### Limited Test Coverage

- Current state: there is not yet broad automated coverage for the key cross-service flows.
- Source: `../agents/roadmap.md`.
- Risk: regressions in onboarding, search, and admin flows are caught late.
- Improve next: add integration tests for onboarding, search, widget, and request workflows.

### Backlog Features Still Lightly Hardened

- request deduplication is missing
- admin workflow has known rough edges
- notification retry behavior is minimal
- some docs and service READMEs lag behind the current architecture

## Stable Contracts With High Blast Radius

These are not “bugs,” but they are risk concentration points:

- `hybrid_search_products`
- embedding model + `vector(384)` lockstep
- `<team-pop-agent>` custom element
- onboarding response shape
- ElevenLabs tool-name alignment

These are called out because accidental changes here create broad regressions.

## Risk Ranking Snapshot

| Area | Current risk | Why |
|------|---------------|-----|
| Public API abuse | Medium | no rate limiting on request submission |
| Admin auth | Medium | shared password header pattern |
| Demo reliability | Medium | ngrok dependence and URL churn |
| Search correctness | High blast radius | RPC + embedding contract drift can silently degrade results |
| Widget conversation loop | Medium | real-time voice flow has many moving parts |
| Production deployment posture | Medium to High | alpha defaults still present |

## What Should Improve Next

1. Restrict CORS.
2. Add rate limiting and request deduplication.
3. Replace password-header admin auth.
4. Add integration tests for onboarding and search.
5. Stabilize the external demo/deployment path.
6. Increase monitoring around ElevenLabs and scraper failures.

## Related Sources

- `../agents/constraints.md`
- `../agents/decisions.md`
- `../agents/roadmap.md`
