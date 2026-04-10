# Roadmap And Open Gaps

## What This Is

This is a human-readable summary of what still needs work, combining the live roadmap, known risks, and gaps visible from the current repo shape.

## Why It Exists

`docs/agents/roadmap.md` is the live backlog. This file turns that backlog into a plain-English planning view.

## Near-Term Priorities

### Production Guardrails

- Restrict wildcard CORS in backend services.
- Add rate limiting to `POST /api/submit-request`.
- Add request deduplication for repeated submissions.
- Strengthen admin authentication beyond `X-Admin-Password`.

### Reliability

- Investigate and stabilize known request/admin flow rough edges.
- Add broader automated tests for onboarding, search, and website/admin paths.
- Improve observability around search empty results, WebSocket disconnects, and background onboarding failures.

### Demo And Delivery Stability

- Reduce ngrok fragility and webhook churn.
- Document a more stable deployment path for external demos.
- Keep widget build and serving instructions aligned with the real integration contract.

## Medium-Term Work

- polish website and admin UX
- add merchant-facing widget integration docs
- improve branded email templates and analytics
- add notification retry logic

## Longer-Term / Structural Work

- revisit auth and data access boundaries
- improve RLS and request-table hardening
- reduce reliance on fragile or undocumented scraper paths
- decide how much of the demo-oriented single-tunnel setup should survive into production

## Open Technical Gaps By Area

## Onboarding

- universal adapter is still not broadly integration-tested
- some adapters depend on brittle third-party page structure or internal APIs
- failure modes are clearer in logs than in admin UX

## Search

- ranking logic lives behind a critical RPC contract
- search tuning knowledge is not yet captured in a standalone operational guide
- silent quality regressions are possible if embedding assumptions drift

## Widget / Voice

- full conversation-cycle behavior still depends heavily on vendor and prompt behavior
- demo success still depends on the correct built widget asset path and live ngrok routing
- interruption and disconnect handling have improved, but need more confidence from repeatable tests

## Website / Admin

- auth is intentionally minimal
- mobile/admin polish is incomplete
- request submission hardening and analytics are still pending

## Documentation Gaps

- some older docs and examples still mention outdated layouts or paths
- some rationale is still preserved mainly in agent completions/decisions, not in dedicated engineering docs
- per-service operational runbooks remain light

## What Can Break If Deferred Too Long

- public request endpoint abuse
- confusing demo failures for external prospects
- onboarding regressions that are only found by manual testing
- knowledge loss when recent code changes are only understood through implementation memory

## Improve Next

1. Treat security hardening and test coverage as the next cross-cutting work.
2. Add at least one reliable end-to-end validation path for onboarding and search.
3. Keep this handbook in sync with `../agents/roadmap.md` as work lands.

## Related Sources

- `../agents/roadmap.md`
- `../agents/completions.md`
- `../agents/decisions.md`
