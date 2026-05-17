# Pop Sales Agent — Vision, Architecture & Review

> **Status:** Foundation (Phase 0+1) complete, in review. Phases 2–4 planned.
> **Audience:** the two reviewing developers + team.
> **How to use this doc:** Skim §1–§3 for the vision, then go to **§5 (Decisions to agree/disagree)** and **§8 (Open questions)** — that's where we need your sign-off or pushback. §9 tells you how to run it locally.

---

## 1. Vision

Today `<team-pop-agent>` is a voice **shopping helper** ("Sam" finds products). We're evolving it into a true **AI account executive on Team Pop's own marketing site**. A visitor lands on teampop, and instead of reading static pages, they get a salesperson who:

- **watches what they do** on the page (scroll, dwell, pricing views, idle),
- **runs a real sales motion** — discovery → quantify the gap → demo → pricing → objection handling → close — driven by the uploaded sales playbook,
- **surfaces proof** (case studies, ROI math, testimonials) they'd normally never find,
- **acts on the page for them** (navigates, opens pricing, pre-fills the demo form),
- and converts them into a **qualified lead + booked meeting**.

It doubles as a live showcase: prospects literally experience what they'd be buying.

## 2. The core insight (why this beats the "inspiration" demos)

ElevenLabs has **no native "computer use."** The clunky demos we've seen drive a real browser with screenshots+clicks — slow, fragile, janky. Our differentiator:

1. **Server-side stateful "sales brain"** — the voice agent is just a mouth/ears. A backend service reasons over the playbook + live session state and decides the next best move like a trained AE. Not a 2000-token prompt; a stateful decision-maker.
2. **Instrumented in-page tools** — because it's *our own site*, the agent acts through purpose-built tools (`navigate_site`, `prefill_demo_form`, …), not screenshots. Fast, reliable, smooth.

This reuses patterns already proven in the repo (ElevenLabs client/webhook tools, the carousel-scroll → `sendContextualUpdate` bridge, the `/search` single-tunnel proxy, `submit_request`).

## 3. Architecture

```
Visitor on www.teampop site
  └─ <team-pop-agent> widget (ElevenLabs voice session)        [REUSE: AvatarWidget.jsx]
       ├─ Awareness bridge → sendContextualUpdate("[VISITOR ACTIVITY]…")   [Phase 2]
       ├─ webhook tool: sales_brain   → POST /sales/brain        [NEW]
       ├─ webhook tool: surface_proof → POST /sales/proof        [NEW]
       └─ client tools: navigate_site / show_proof /
            prefill_demo_form / open_booking   (via window.__TEAM_POP_HOST__)

onboarding-service (FastAPI :8005)              [REUSE: router pattern]
  ├─ routes/sales.py     → /sales/brain, /sales/proof
  ├─ services/sales_brain.py → pure, LLM-injected stateful AE
  └─ elevenlabs_agent.py → PROMPT_SALES + sales tool config + create_sales_agent

shared/llm.py  → minimal httpx OpenRouter client (no new dependency)

Supabase
  ├─ sales_sessions  → per-conversation stage, PIC, captured fields, transcript
  ├─ sales_proof     → curated case studies / ROI / testimonials / rebuttals
  └─ agent_requests  → lead + transcript on the assisted close   [REUSE]
```

**The brain loop, every visitor turn:** ElevenLabs calls `POST /sales/brain` → load `sales_sessions` by `conversation_id` → `SalesBrain.decide()` runs one LLM call over the playbook + state → returns `{stage, say, next_move, directives}` → persist → the voice agent speaks `say` and fires each `directive` as a client tool.

## 4. Data model

`migrations/0001_sales_agent.sql` (idempotent; **applied by a human in the Supabase SQL editor** — there is no programmatic DDL path, same as the original `products`/`agent_requests` tables):

- **`sales_sessions`** — `conversation_id` (unique), `stage`, `pic` jsonb, `captured` jsonb, `objections`, `proof_shown`, `transcript` jsonb, `next_move`, `booked`.
- **`sales_proof`** — `type` (case_study|roi|testimonial|objection_rebuttal), `title`, `body`, `metric`, `tags[]`, `active`.
- **`agent_requests`** — add `source`, `transcript` jsonb, `discovery` jsonb, `pic` jsonb (lead+transcript on close, reusing `submit_request`).

## 5. Key architectural decisions — **please ✅ agree / ❌ disagree on each**

| # | Decision | Rationale | Alternative rejected |
|---|----------|-----------|----------------------|
| D1 | **In-page instrumented tools**, not screenshot/Playwright computer-use | Our own site → fast, reliable, smooth; reuses client-tool pattern | True browser automation: works anywhere but slow/fragile (the demos we disliked) |
| D2 | **Server-side stateful sales brain** vs. an enhanced static prompt | Behaves like a trained AE with memory of stage + PIC; quality ceiling | Prompt-only: simple but no durable discovery state |
| D3 | **Assisted close** (agent pre-fills form + opens calendar; visitor confirms) | High conversion, visitor stays in control, low trust/error risk | Fully autonomous submit/book: higher "wow", higher risk |
| D4 | Brain is **pure + LLM-injected**; route owns DB/LLM | Fully unit-testable headless (13 tests, fake LLM); clean isolation | Brain calls DB/LLM directly: untestable without infra |
| D5 | **New `shared/llm.py`** (httpx → OpenRouter) — *deviation from the plan* | No LLM client existed (`get_openrouter_client()` was dead commented code; no SDK in requirements). httpx already a dep → **no new dependency** | Adding the `openai`/`anthropic` SDK: new dependency for one call |
| D6 | New **`migrations/`** convention (numbered, idempotent, human-applied) | No migration tooling existed; matches how `products` was created | Ad-hoc SQL in markdown (current state) — not reviewable |
| D7 | Tool names are a **hard invariant** across `elevenlabs_agent.py` + prompt + widget | Mismatch silently breaks the conversation (existing project invariant) | — |
| D8 | Host↔widget awareness via a `window` `teampop:activity` **CustomEvent seam** (host detects & emits; widget owns dedupe/throttle & whether to tell the agent) | Decouples the two Vite apps cleanly; pure logic is unit-testable; widget never force-narrates (only `sendContextualUpdate`) so it can't regress into the carousel duplicate-narration bug | Host calling widget internals directly: tight coupling, untestable |

## 6. Phase plan

| Phase | Scope | PR | Status |
|-------|-------|----|--------|
| 0 | Foundations: sales agent config/payload, playbook, migrations, site embed + host bridge | **Foundation PR** (this) | ✅ done, in review |
| 1 | Stateful sales brain + `shared/llm.py` + `/sales/*` routes | **Foundation PR** (this) | ✅ done, in review |
| 2 | Awareness bridge — host-page activity → contextual updates | own PR (stacked on Foundation) | ✅ done, in review |
| 3 | Proof surfacing — content + trust panel UI + admin CRUD + curated drafts | own PR (stacked on Phase 2) | ✅ done, in review |
| 4 | Assisted close — action tools wired + lead/transcript capture | own PR (stacked on Phase 3) | ✅ done, in review |

**All 5 phases implemented & in review (Draft PRs #8–#11). Remaining = team review + the live runtime gate in §9 / §8 Q2.**

(Phase 0+1 are combined because Phase 1's routes import Phase 0's config and depend on its migration/tables — they don't review independently.)

## 7. What's done & how it was verified (evidence, not claims)

- **19/19 pytest GREEN**, written RED→GREEN (TDD): `tests/test_sales_agent.py` (6 — tool/prompt/payload contract), `tests/test_sales_brain.py` (13 — stage machine refuses backward resets, PIC accumulates, directives whitelisted, junk-LLM fallback, session threading).
- Marketing website `npm run build` + `eslint`: clean.
- All Python modules byte-compile; `shared/llm.py` imports.

**NOT yet verified — gated on human/runtime steps (see §9):** the live ElevenLabs voice loop, real LLM responses, and DB persistence. The brain *logic* is fully tested with a fake LLM; the route is thin glue over it.

## 8. Open questions — **we need the team's call**

1. **D5/D6 deviations** — agree these are the right calls, or do you want the SDK / a real migration tool (Alembic-style) instead?
2. **⚠️ Load-bearing unverified assumption:** the `sales_brain` webhook sends `conversation_id` as the ElevenLabs system dynamic variable `{{system__conversation_id}}` (a *constant*, never LLM-generated — LLMs truncate ids, same class as the `store_id` invariant). **If ElevenLabs does not substitute this, cross-turn session memory breaks.** The code degrades safely (works statelessly + logs a warning), but someone with ElevenLabs API access must confirm substitution on first provision. Who owns this check?
3. **Voice persona** — keep "Sam", or a distinct sales identity?
4. **Booking** — stay on Calendly (prefill via URL params), or move to Cal.com for real availability API?
5. **Proof content (Phase 3)** — who supplies real case studies/metrics, or do we ship my curated drafts and replace later via admin?

## 9. Run & verify locally (for reviewers)

```bash
# Backend unit tests (no infra needed — this is the core verification)
cd onboarding-service && python3 -m pytest tests/ -v        # expect 19 passed

# Backend unit tests (Phases 1/3/4)
cd onboarding-service && python3 -m pytest tests/ -v          # expect 31 passed

# Widget awareness logic (Phase 2) — zero-dep node:test
cd www.teampop/frontend && npm test                          # expect 8 pass
cd www.teampop/frontend && npm run build                     # widget IIFE (Trust Panel)

# Proof content: apply migrations/0002_sales_proof_seed.sql after 0001.
# Admin can then edit/replace it at /admin → Proof Library.

# Marketing site builds with the embed + observer
cd www.teampop/website && npm install && npm run build && npx eslint src/

# Full live loop (needs credentials/runtime — NOT done by CI/me):
#   1. Apply migrations/0001_sales_agent.sql in Supabase SQL editor
#   2. Set OPENROUTER_API_KEY + ELEVENLABS_API_KEY in onboarding-service/.env
#   3. python -c "from elevenlabs_agent import create_sales_agent; print(create_sales_agent())"
#   4. Put the returned agent id in www.teampop/website/.env (VITE_SALES_AGENT_ID)
#   5. ./start_services.sh + ngrok; talk to the agent on the site
#   6. Confirm {{system__conversation_id}} substitution (open question #2)
```

## 10. PR & review workflow for this program

- **One Draft PR per phase** (Phase 0+1 combined as the Foundation PR). Opened as **GitHub Draft** so review starts immediately.
- **Merge gate:** every PR is **blocked from merge until it carries a `Closes HPF-XXX` Linear ref** (repo constraint #13). Drafts let review proceed without it.
- Reviewers: follow Engineering Standards §5.3. Pull the branch, run §9, and record agree/disagree on §5 + §8 directly in the PR.
- Phase 2+ branches off `main` after Foundation merges (or off the Foundation branch + rebase if work must continue before merge).
- Durable decisions are also logged append-only in `docs/agents/decisions.md` (2026-05-16 entry).

## 11. Non-goals / YAGNI (intentionally out of scope)

- No screenshot/browser-automation computer-use.
- No embeddings for proof retrieval in v1 (the curated set is tiny — keyword/tag filter is enough).
- No autonomous form-submit/booking without explicit visitor confirmation.
- Not changing the existing shopping agent path (`PROMPT_GEMINI` etc. untouched).
