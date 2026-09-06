# Agent Memory — Active Work State

> **Keep this file under 2KB.** It is read by every agent at session start.
> **Last updated:** 2026-09-06

---

## Currently In Progress

| Task | Files | Owner | Status | Notes |
|------|-------|-------|--------|-------|
| Lightsail pull + widget copy of SEARCH_FAIL (`release/xfused-pilot` @ `3f411ce`) | live box `ubuntu@13.232.36.194` | Cloud agent | Blocked on SSH | Wrina PATCH already live. Do not re-PATCH. Do not change `language=hi`. Need `LIGHTSAIL_SSH_PRIVATE_KEY`. |

---

## Files Currently Being Modified

- none (ops deploy; widget `dist/` is gitignored)

---

## Recently Completed (Last 7 Days)

| Date | What Was Done | Files Changed | Agent/Author |
|------|--------------|---------------|--------------|
| 2026-09-06 | GET Wrina: `language=hi`, `show_search_error` present, store_id constant. Rebuilt widget locally (`SEARCH_FAIL` in `dist/widget.js`). Live widget script still Aug 12 bundle. SSH denied. | docs/agents/{memory,handoff,completions}.md | Cloud agent (this env) |
| 2026-09-04 | `update_agent` prompt+tools PATCH for Wrina; `language` left `hi`. Widget built on prior pod; not copied. | ElevenLabs live agent | Prior env-setup agent |
| 2026-09-04 | Tasks 1–6 coded + merged to `release/xfused-pilot` | widget, elevenlabs_agent, search-service | Claude Opus 5 |

---

## Open Questions / Blockers

- `LIGHTSAIL_SSH_PRIVATE_KEY` (and optionally `ADMIN_PASSWORD` for `/api/latency-summary`) still not in cloud env
- Do not pass `voice_id` / `tts_overrides` on Wrina PATCH — env voice/TTS do not match live `o6qTxWUeRyzRYZyUNDVJ` + multilingual TTS
- Do not run `create_agent` for xfused
