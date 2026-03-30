# COLLABORATIVE.md — Human Guide To The Agent-Docs System

**Canonical entry point:** `../AGENTS.md`  
**Updated:** 2026-03-30

This file explains how the collaboration system is organized. It is **not** the primary instruction file for agents. Shared agent instructions now live in `AGENTS.md` at the repo root.

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
        ├── constraints.md  # Hard rules and invariants
        ├── decisions.md    # Append-only architectural decisions
        ├── handoff.md      # Structured handoffs
        └── memory.md       # Active WIP only; keep short
```

---

## How Agents Should Work

### Start Of Task

1. Read `AGENTS.md`
2. Read `docs/agents/constraints.md`
3. Check `docs/agents/memory.md`
4. Read `docs/agents/decisions.md` if the task affects architecture
5. Add active work to `docs/agents/memory.md`

### End Of Task

1. Remove stale in-progress notes from `docs/agents/memory.md`
2. Add a recent-completion note if the change was meaningful
3. Append to `docs/agents/decisions.md` for non-obvious architectural choices
4. Append to `docs/agents/handoff.md` if another agent needs to continue

---

## Which File Owns What

| File | Owns |
|------|------|
| `AGENTS.md` | Shared instructions, read order, repo snapshot, workflow |
| `CLAUDE.md` | Thin Claude-specific wrapper |
| `docs/AGENT_DOCS_GUIDE.md` | Human maintenance rules for this system |
| `docs/agents/constraints.md` | Hard rules that must not be broken |
| `docs/agents/decisions.md` | Durable design decisions |
| `docs/agents/memory.md` | Current edits and immediate work state |
| `docs/agents/handoff.md` | Incomplete work being transferred |

Do not store the same information in multiple places.

---

## Why This Hybrid Setup Exists

- A single giant file becomes noisy and expensive to keep loaded.
- A folder-only system is harder for tools to discover automatically.
- The hybrid model gives one predictable entry point plus specialized docs that can change at different rates.

---

## Future-Project Default

Use this same pattern in new collaborative repos unless the project is tiny:

- Required: `AGENTS.md`
- Optional root wrapper: `CLAUDE.md` when Claude is used
- Recommended: `docs/agents/constraints.md`, `decisions.md`, `memory.md`, `handoff.md`
- Optional: `docs/COLLABORATIVE.md` and `docs/AGENT_DOCS_GUIDE.md` for humans
