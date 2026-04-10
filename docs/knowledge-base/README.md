# Team Pop Knowledge Base

This folder is the human-facing knowledge transfer hub for the current Team Pop system.

Use it when you need to answer questions like:

- What does this product do today?
- What runs where?
- How do onboarding, search, and voice conversations actually work?
- Which architecture choices are deliberate versus temporary?
- What is risky, brittle, or unfinished?

The goal is to make the repo understandable without relying on chat history or one specific engineer.

## Reading Order

1. `system-overview.md`
2. `repo-map.md`
3. `core-flows.md`
4. `architecture-decisions-explained.md`
5. `technology-rationale.md`
6. `risks-security-gaps.md`
7. `roadmap-and-open-gaps.md`
8. `glossary.md`

## How This Doc Set Works

- `docs/knowledge-base/` is the readable handbook for humans.
- `docs/agents/constraints.md` owns hard rules and invariants.
- `docs/agents/decisions.md` owns durable architecture decisions and history.
- `docs/agents/completions.md` owns meaningful completed-work history and verification notes.
- `docs/agents/roadmap.md` owns the live backlog.

This means the knowledge base summarizes and links back to source docs instead of duplicating every fact verbatim.

## Documentation Contract

Each knowledge-base file should answer these questions where relevant:

1. What is this?
2. Why does it exist?
3. How does it work?
4. Where is the code?
5. What are the tradeoffs?
6. What can break?
7. What should improve next?

## Stable Interfaces To Notice Early

- `hybrid_search_products` is the core search RPC contract.
- `products.embedding` is locked to the `all-MiniLM-L6-v2` embedding model and `vector(384)`.
- `<team-pop-agent>` is the widget's public integration API.
- Onboarding API responses expose `store_id`, `agent_id`, `test_url`, `widget_snippet`, and `products_count`.
- ElevenLabs tool names must stay aligned across the agent config, system prompt, and widget client-tool handlers.

See also:

- `../agents/constraints.md`
- `../agents/decisions.md`
- `../agents/completions.md`
- `../agents/roadmap.md`

## Maintenance Rule

When architecture or shared behavior changes:

1. Update the source-of-truth agent doc first if it changed a hard rule, durable decision, completion history, or roadmap item.
2. Update the relevant `docs/knowledge-base/` summary so humans can still understand the current system quickly.

## Personal Notes Boundary

`.personal/learning/` is for optional study notes, reflections, and simplified learning material.

Those notes should point back to this folder. They should not become a second canonical architecture system.
