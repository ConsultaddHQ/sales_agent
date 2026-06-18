# Agent Memory — Active Work State

> **Keep this file under 2KB.** It is read by every agent at session start.
> **Last updated:** 2026-06-19

---

## Active Tasks

- (none)

---

## Files Currently Being Modified

- (none)

---

## Recent Completions (for quick context)

- **2026-06-19** — Enforced `get_product_details → update_carousel_main_view` tool chain across all 5 model prompts (triple-lock pattern). Disabled carousel click-to-agent context in `AvatarWidget.jsx`. Build verified ✓. See `docs/agents/completions.md` for details.
- **2026-06-18** — Fixed carousel 1-3s delay (`expects_response: True`), duplicate agent speech (single `sendUserMessage`), search service hangs (PyTorch thread limits + semaphore), inactivity timer robustness, VAD startup silence.
