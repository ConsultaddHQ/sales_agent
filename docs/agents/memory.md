# Agent Memory — Active Work State

> **Keep this file under 2KB.** It is read by every agent at session start.
> **Last updated:** 2026-09-04

---

## Active Tasks

- **Voice latency design (brainstorming)** — spec at `docs/superpowers/specs/2026-09-04-xfused-voice-latency-design.md` on `cursor/voice-latency-design-bcc1`. Waiting on human spec review before writing-plans / implementation. Live `api.teampop.com` still needs human Lightsail deploy of cache + tracking or numbers are meaningless.

---

## Files Currently Being Modified

- `docs/superpowers/specs/2026-09-04-xfused-voice-latency-design.md`

---

## Recent Completions (for quick context)

- **2026-08-13** — Latency-audit reconciliation: 07-20 latency work never deployed; live agent `language="hi"` + `eleven_flash_v2_5`; `/api/latency-summary` no longer 500s without `agent_requests`. See handoff.md.
- **2026-07-20** — Per-turn latency tracking + search cache + soft_timeout 1.2s. Coded, not deployed.
- **2026-07-03** — Xfused pilot on Lightsail Mumbai (`release/xfused-pilot`).
