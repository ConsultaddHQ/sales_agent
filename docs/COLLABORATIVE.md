# COLLABORATIVE.md — Quick Overview Of The Agent-Docs System

**Canonical entry point:** `../AGENTS.md`  
**Updated:** 2026-04-02

This file gives humans a quick overview of how the collaboration system is organized. It is **not** the primary instruction file for agents. Shared agent instructions live in `AGENTS.md` at the repo root, and the detailed maintenance rules live in `docs/AGENT_DOCS_GUIDE.md`.

---

## Standard Layout

```text
sales_agent/
├── AGENTS.md               # Canonical shared agent instructions
├── CLAUDE.md               # Thin Claude wrapper
└── docs/
    ├── AGENT_DOCS_GUIDE.md # Human maintenance guide
    ├── COLLABORATIVE.md    # Human-readable explainer (this file)
    └── agents/
        ├── completions.md  # Meaningful completed work + verification
        ├── constraints.md  # Hard rules and invariants
        ├── decisions.md    # Append-only architectural decisions
        ├── handoff.md      # Structured handoffs
        └── memory.md       # Active WIP only; keep short
```

---

## Fast Mental Model

- `AGENTS.md` tells agents where to start and what each collaboration file owns.
- `docs/agents/memory.md` is the short-lived "what is active right now?" file.
- `docs/agents/decisions.md` records durable design and process decisions.
- `docs/agents/completions.md` records meaningful finished work, tradeoffs, and verification.
- `docs/agents/handoff.md` is only for unfinished work that another agent must resume.
- `docs/AGENT_DOCS_GUIDE.md` is the maintainer handbook for evolving this system.

---

## What To Read For Different Questions

- Want the rules agents must follow? Read `AGENTS.md`.
- Want the non-negotiable technical constraints? Read `docs/agents/constraints.md`.
- Want to understand why a design choice was made? Read `docs/agents/decisions.md`.
- Want to review meaningful work that was completed and how it was validated? Read `docs/agents/completions.md`.
- Want to know what is actively being worked on right now? Read `docs/agents/memory.md`.
- Want to resume unfinished work? Read `docs/agents/handoff.md`.
- Want to maintain or evolve the system itself? Read `docs/AGENT_DOCS_GUIDE.md`.
This separation is intentional so each type of knowledge has one owner.
