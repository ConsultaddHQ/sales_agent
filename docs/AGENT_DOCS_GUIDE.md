# Agent Docs Guide

This guide explains how to maintain the agent-doc system in this repo and how to reuse the same standard in future projects. It is the maintainer document for the system itself.

## Canonical Layout

```text
sales_agent/
├── AGENTS.md
├── CLAUDE.md
└── docs/
    ├── AGENT_DOCS_GUIDE.md
    ├── COLLABORATIVE.md
    └── agents/
        ├── completions.md
        ├── constraints.md
        ├── decisions.md
        ├── handoff.md
        └── memory.md
```

## What Each File Owns

| File | Owner role |
|------|------------|
| `AGENTS.md` | Canonical instructions for all agents |
| `CLAUDE.md` | Thin Claude-specific wrapper only |
| `docs/COLLABORATIVE.md` | Human-readable explainer of the system |
| `docs/agents/completions.md` | Durable completed-work summaries with tradeoffs and verification |
| `docs/agents/constraints.md` | Hard rules and non-negotiable invariants |
| `docs/agents/decisions.md` | Append-only architecture and process decisions |
| `docs/agents/handoff.md` | Unfinished task transfer notes |
| `docs/agents/memory.md` | Short current WIP state only |

## Rules For Maintaining This System

1. Keep `AGENTS.md` short. It is the entry point, not a changelog or scratchpad.
2. Do not create a second full handbook like `codex.md`, `cursor.md`, or another `CLAUDE.md` in subfolders unless a tool explicitly requires it.
3. Put stable instructions in `AGENTS.md` or `constraints.md`, not in `memory.md`.
4. Put long-term choices in `decisions.md`, not in `AGENTS.md`.
5. Put meaningful finished-task summaries in `completions.md`, not in `memory.md`.
6. Put active work only in `memory.md`, and keep it under the stated size limit.
7. Put partial-session context in `handoff.md` only when another agent must continue unfinished work.
8. If two files say the same thing, delete the duplicate and keep one owner.
9. Personal notes, private learning docs, and individual templates must stay in a gitignored local-only folder such as `.personal/`, not in tracked repo docs.

## When To Update Which File

- Update `AGENTS.md` when the read order, workflow, repo map, or standard operating rules change.
- Update `CLAUDE.md` only if Claude needs a tool-specific note beyond `AGENTS.md`.
- Update `constraints.md` when a new hard rule becomes non-negotiable.
- Update `decisions.md` when a non-obvious decision is made and future agents should not re-decide it.
- Update `completions.md` when completed work will be useful for future review, onboarding, or learning.
- Update `memory.md` at the start and end of meaningful work.
- Update `handoff.md` when work stops mid-task and someone else needs to continue.
- Update `COLLABORATIVE.md` only when the quick explainer needs to change.

## What To Tell Agents

Use wording close to this:

```text
Read AGENTS.md first.
Then read docs/agents/constraints.md and docs/agents/memory.md.
If your task changes architecture or shared behavior, read and update docs/agents/decisions.md.
If you complete meaningful work, add a durable summary to docs/agents/completions.md.
If you stop mid-task, append a structured note to docs/agents/handoff.md.
Do not create duplicate agent guides or store the same rule in multiple files.
```

## Future-Project Template

Use this structure by default in future collaborative repos:

```text
repo/
├── AGENTS.md
├── CLAUDE.md                # optional
└── docs/
    ├── COLLABORATIVE.md     # optional but useful for humans
    └── agents/
        ├── completions.md
        ├── constraints.md
        ├── decisions.md
        ├── handoff.md
        └── memory.md
```

Skip extra wrappers unless the tool truly benefits from a known root filename.
