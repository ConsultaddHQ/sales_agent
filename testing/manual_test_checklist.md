# Manual Test Checklist — Voice Agent (Xfused Pilot)

> **Purpose:** Structured scenarios to run against the live `goxfused.com` widget, tied
> directly to the client's reported issues + the architecture's known failure points.
> Re-run the relevant sections after **any** change to `elevenlabs_agent.py`,
> `search-service/main.py`, or the widget — not just when chasing new bugs.
>
> **Live agent under test:** `agent_4901kwna71tve5nbyy85c8v20yre` ("Wrina - Xfused v2")
> **Before testing:** confirm which code is actually deployed — see "Pre-flight" below.
> A test run against stale code produces misleading conclusions.

---

## Pre-flight (do this first, every time)

1. Check what's actually live vs. what's in the branch:
   ```
   curl -s -o /dev/null -w "%{http_code}\n" https://api.teampop.com/api/turn-latency
   ```
   `405` = new code is deployed (route exists, GET not allowed). `404` = still running old code — **stop, deploy first**, the results below won't mean anything.
2. Note the current `LATENCY_CONFIG_VERSION` / `SEARCH_CONFIG_VERSION` you deployed with (see handoff.md). You'll need this to pull the right slice out of `/api/latency-summary` afterward.
3. Have two test devices ready: one on decent WiFi, one on actual mobile data (4G) — client's users are on mobile, and voice/network behavior differs meaningfully.

---

## Section A — Latency (client feedback #1, #7: "takes too long, people bail after first question")

Run each scenario **3 times** on WiFi and **3 times** on 4G. For each turn, note: time from when you stop speaking to (a) first sound from the agent, (b) products appearing in the carousel.

| # | Scenario | What to watch for |
|---|---|---|
| A1 | First message of a fresh session, ask for a common product ("show me t-shirts") | Cold-start delay — should be masked by the warmup on the search-service side. If slow, warmup may not have run (service just restarted). |
| A2 | Same query twice in the same session, 10s apart | Second call should be near-instant if the search cache is live and hit. If not faster, the cache isn't deployed or isn't hitting (check `cache_hit` in `search_latency`). |
| A3 | A specific, narrow query ("red cotton kurta size M") | Exercises full embed→RPC→rerank path — this is the slow path the cache doesn't help on the first hit. |
| A4 | Ask a question requiring **two tool calls in one turn** (e.g. "show me shirts under 1000" then immediately "tell me more about the second one") | Watch whether the soft-timeout filler fires twice — it's capped at `max_soft_timeouts_per_generation: 2` live; if you hear 3+ fillers or dead air after 2, something regressed. |
| A5 | Ask something that returns **zero results** ("show me a red spaceship") | No search-result cache benefit here (nothing to cache well) — confirm the agent still responds quickly with a "couldn't find that" instead of hanging on an empty carousel. |
| A6 | 5+ turn conversation, check if turn 5 is noticeably slower than turn 1 | Tests whether latency degrades over a long session (bloated conversation context) — this is explicitly why turn-latency is sent at end-of-session per-turn instead of only once. |

**Pass bar:** p50 (typical) time-to-first-audio under ~1.5s, p90 under ~2.5s. Pull actual numbers from `GET /api/latency-summary/agent_4901kwna71tve5nbyy85c8v20yre?store_id=9cec7cd0-9252-4aa2-985b-71c2a42018cb` after the session — don't rely on stopwatch feel alone.

---

## Section B — Background noise / distraction (client feedback #3, #5)

There is currently **no server-side noise suppression lever** — `asr.quality` only accepts `high`, and the widget sets no explicit mic constraints. These tests establish whether that's actually the problem before spending effort on it.

| # | Scenario | What to watch for |
|---|---|---|
| B1 | Speak a query in a silent room | Baseline — should transcribe correctly, no false interruptions. |
| B2 | Speak the same query with a TV/music playing at moderate volume in the background | Does the agent transcribe wrong words, or interrupt itself, or the ASR pick up the background audio as a second "speaker"? |
| B3 | Speak with a second person talking nearby (not to the agent) | Real-world "shop floor" / "family in the room" scenario the client described. |
| B4 | Let the agent start speaking (TTS playing), then make background noise (not user speech) mid-response | Check if the agent falsely thinks it was interrupted and cuts off mid-sentence. |
| B5 | Test on the phone's built-in mic vs. wired/bluetooth headset if available | Isolates whether it's a browser mic-capture issue vs. an ElevenLabs ASR issue. |

**If B2/B3 reproduce real mis-transcriptions or false interruptions:** the fix path is client-side mic constraints (`getUserMedia` with `noiseSuppression: true, echoCancellation: true, autoGainControl: true`), which the widget doesn't currently set at all. Log exact repro steps — this needs a code change, not a config toggle.

---

## Section C — Product detail depth (client feedback #2, #6)

| # | Scenario | What to watch for |
|---|---|---|
| C1 | Ask a detail question the description likely doesn't cover (fabric care, exact fit, sizing chart) | Confirms today's gap — description is capped at 300 chars for the rerank doc and further truncated for voice. Agent should say it doesn't know rather than guessing/hallucinating. |
| C2 | Ask about something covered in the product title/description | Confirms the baseline still works before any enrichment change. |
| C3 | After any future catalog/description enrichment ships, repeat C1 with the same product | Should now get a real answer — this is the regression check for that future work. |

---

## Section D — Known, accepted issue (client feedback #4 — do not re-test as a bug)

"Shows detox when talking about dwell" — client has explicitly accepted this for the pilot's current scope. No action needed; just confirm it hasn't gotten *worse* (e.g. wrong category entirely, not just an adjacent one) if you're near that code path for another reason.

---

## Section E — Regression checklist (run after ANY future change to agent config, search-service, or widget)

These aren't client-reported issues — they're existing behaviors that have broken before (see `docs/agents/decisions.md`) and have no automated test guarding them.

- [ ] **Language switching**: mid-conversation, switch to Hindi and to Tamil (`language_presets` for `en`/`ta` exist on the live agent; base language is `hi`). Confirm the agent responds in the right language and prices stay in English (a past bug).
- [ ] **Hinglish**: speak a mixed Hindi-English sentence — confirm natural Hinglish blending, not pure Hindi or an accent mismatch.
- [ ] **Cart sync**: add to cart via voice, confirm the cart badge updates instantly (not on a delay) and `add_to_cart` never routes to checkout by itself.
- [ ] **Carousel sync**: confirm products appear in the carousel in speech-order, not all-at-once ahead of narration.
- [ ] **Interruption handling**: interrupt the agent mid-sentence — confirm it stops cleanly, doesn't restart from the top, and doesn't get "stuck".
- [ ] **Soft-timeout fillers**: trigger a slow tool call — confirm at most 2 fillers per generation, and they rotate (not the same line twice in a row).
- [ ] **Session end reasons**: end a session by (a) explicit goodbye, (b) closing the tab, (c) idle timeout — confirm `session_feedback` rows land for all three with the correct `end_reason`.
- [ ] **config_variant tagging**: after deploying a latency-affecting change, confirm new `turn_latency`/`search_latency`/`session_feedback` rows carry the *new* `config_variant` string, not the old one (i.e. you actually bumped `LATENCY_CONFIG_VERSION`/`SEARCH_CONFIG_VERSION` before restarting the services).
- [ ] **Mobile network**: run the core "search for a product → add to cart" flow once on throttled/flaky mobile data — this is the client's actual user environment, not WiFi.

---

## Reading the results

- `GET /api/latency-summary/{agent_id}?store_id={store_id}` (admin password header) — per-`config_variant` p50/p95/avg for both turn latency (widget-reported) and search latency (server-reported, breaks down embedding/RPC/queue-wait).
- `session_feedback` table — end-of-session ratings + funnel columns (`products_shown`, `cart_adds`, `checkout_initiated`) tagged with the same `config_variant`.
- If a scenario fails, capture: timestamp, `conversation_id` (visible in ElevenLabs dashboard → Conversations), and which `config_variant` was live — that's enough for whoever picks up the fix to pull the exact conversation transcript and the exact latency numbers for that turn.
