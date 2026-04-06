# AGENTS.md — Canonical Agent Instructions

**Project:** sales-voice-agent (Team Pop)  
**Status:** Early alpha / lab prototype  
**Purpose:** Voice-first AI shopping assistant for Shopify storefronts, Threadless artist shops, and Supermicro enterprise catalogs.

This is the **canonical shared instruction file** for all coding agents working in this repo.

- Read this file first.
- Use `docs/agents/` for specialized state.
- Do not create a second full agent handbook elsewhere.

---

## Read Order

1. Read this file.
2. Read `docs/agents/constraints.md` before touching code.
3. Read `docs/agents/memory.md` before starting active work.
4. Read `docs/agents/decisions.md` if your task touches architecture or shared behavior.
5. Read `docs/agents/completions.md` if you need historical implementation context, tradeoffs, or prior verification notes.
6. Read `docs/agents/handoff.md` if you are resuming interrupted work.

---

## Repo Snapshot

- `onboarding-service/`: FastAPI service for store validation, crawling, embeddings, agent creation + client acquisition API
- `onboarding-service/notifications.py`: Resend email + Slack webhook notifications for client acquisition
- `onboarding-service/threadless_adapter.py`: Adapter bridging Threadless scraper into the onboarding pipeline
- `onboarding-service/supermicro_adapter.py`: Adapter bridging Supermicro scraper into the onboarding pipeline
- `search-service/`: FastAPI hybrid search API (includes request logging middleware)
- `image_server.py`: primary image server used by `start_services.sh`
- `www.teampop/frontend/`: embeddable React widget in Shadow DOM
- `www.teampop/website/`: marketing website + client acquisition flow (React + GSAP + Tailwind)
- `universal-scraper/`: scraping workflow and fallback strategies
- `docs/`: human-facing project docs and agent support files

---

## Common Commands

```bash
# Start all services
./start_services.sh

# Stop all services
./stop_services.sh

# Onboarding service
cd onboarding-service && source .venv/bin/activate && python main.py

# Search service
cd search-service && source .venv/bin/activate && uvicorn main:app --port 8006

# Widget
cd www.teampop/frontend && npm run dev
cd www.teampop/frontend && npm run build

# Threadless onboarding (non-Shopify)
curl -X POST http://localhost:8005/onboard-threadless \
  -H "Content-Type: application/json" \
  -d '{"url": "https://nurdluv.threadless.com"}'

# Supermicro GPU onboarding (enterprise catalog)
curl -X POST http://localhost:8005/onboard-supermicro \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.supermicro.com/en/products/gpu"}'

# ngrok tunnel for search webhook (required for ElevenLabs agent)
ngrok http 8006
```

---

## Critical Invariants

- `all-MiniLM-L6-v2` must stay aligned across onboarding and search.
- `products.embedding` is `vector(384)`; embedding changes require migration + full re-embed.
- `hybrid_search_products` is a core API contract for search.
- Widget public API is the `<team-pop-agent>` custom element.
- Shadow DOM means `@import` does not work inside widget CSS.
- `image_server.py` is the active image server used by startup scripts.
- Widget must be served as built IIFE from `/widget/widget.js`, NOT via Vite dev server (Fast Refresh breaks it).
- `@elevenlabs/react` v1.0+ requires `<ConversationProvider>` wrapper and `useConversationClientTool` for tool registration.
- ElevenLabs agent tool names must match exactly across: ElevenLabs config, system prompt, and widget code.
- Never commit `.env` files or secrets.
- User-facing onboarding errors must go through `error_codes.py`.
- ElevenLabs webhook `store_id` must use `value_type: "constant"`, never `"llm_prompt"` (LLMs truncate UUIDs).

For the full non-negotiable rules, read `docs/agents/constraints.md`.

---

## Working Agreement

### Before Work

- Check `docs/agents/memory.md` for active ownership and files being modified.
- Add your task to `docs/agents/memory.md` before significant work.
- Prefer existing patterns over inventing new structure.

### During Work

- Keep changes scoped to the task.
- Record non-obvious architectural choices in `docs/agents/decisions.md`.
- Keep `docs/agents/memory.md` short and current.
- Do not add duplicate rules or duplicate agent guides.
- If the task becomes a meaningful completed change, prepare a short durable summary for `docs/agents/completions.md`.

### After Work

- Remove stale in-progress entries from `docs/agents/memory.md`.
- Add a recent-completion note if the work was meaningful.
- Append a durable summary to `docs/agents/completions.md` when the completed task will be useful for future review, onboarding, or learning.
- Add a handoff entry to `docs/agents/handoff.md` if another agent must continue.
- Keep `AGENTS.md` concise; do not turn it into a changelog.

### File Update Rules

- Update `AGENTS.md` only for shared workflow, read order, repo structure, or project-wide agent rules.
- Update `docs/agents/constraints.md` for hard rules only.
- Update `docs/agents/decisions.md` for durable decisions only.
- Update `docs/agents/memory.md` for active work only.
- Update `docs/agents/completions.md` for meaningful completed work, rationale, tradeoffs, and verification.
- Update `docs/agents/handoff.md` only when handing incomplete work to another agent.
- Keep one owner per piece of information; delete duplicates instead of maintaining two copies.

---

## File Roles

| File | Role |
|------|------|
| `AGENTS.md` | Canonical entry point for shared agent instructions |
| `docs/agents/constraints.md` | Stable hard rules and invariants |
| `docs/agents/decisions.md` | Append-only architectural decisions |
| `docs/agents/memory.md` | Current work in progress and active edits |
| `docs/agents/completions.md` | Durable summaries of completed work, tradeoffs, and verification |
| `docs/agents/handoff.md` | Structured task-transfer log |
| `docs/COLLABORATIVE.md` | Human-readable explainer for this collaboration system |
| `docs/AGENT_DOCS_GUIDE.md` | Human maintenance guide for this agent-doc system |
| `CLAUDE.md` | Thin Claude wrapper that imports/references canonical docs |

---

## Architecture Quick Map

| Area | Path | Notes |
|------|------|-------|
| Onboarding | `onboarding-service/` | Crawl, validate, embed, create voice agent + client acquisition API |
| Search | `search-service/` | Semantic + full-text product search |
| Widget | `www.teampop/frontend/` | Shadow DOM custom element |
| Website | `www.teampop/website/` | Marketing site + client request form + admin dashboard |
| Scraper | `universal-scraper/` | HTTP -> Playwright -> LLM fallback chain |
| Images | `image_server.py` | Primary image server (image-service/ removed) |
| Database | Supabase | `products` + `agent_requests` tables + `hybrid_search_products` RPC |

---

## Related Docs

- `docs/Engineering Standards.md`: commits, tickets, PRs, workflow
- `docs/AI Collaboration Guide - Project Tickets.md`: AI request patterns
- `docs/AGENT_DOCS_GUIDE.md`: how to maintain this doc system
- `docs/ticket_creation_standards.md`: ticket structure
- `SHOPIFY_FLOW_COMPLETE.md`: env vars, SQL, troubleshooting
- `README.md`: high-level project overview

---

## Future-Project Standard

Use this default structure for future collaborative repos unless the repo is tiny:

- Required: `AGENTS.md`
- Recommended: `docs/agents/constraints.md`, `decisions.md`, `memory.md`, `completions.md`, `handoff.md`
- Optional: tool-specific wrappers like `CLAUDE.md` only when the tool benefits from a known filename
- Optional later: path-specific instruction files when the codebase grows enough to justify them
