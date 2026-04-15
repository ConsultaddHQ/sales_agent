# ElevenLabs Limits and Constraints

Updated: 2026-04-14

This note captures the current externally documented ElevenLabs limits that matter
for this repo's voice agent architecture. These values can change, so treat this
as an operational snapshot rather than a permanent contract.

## What matters for this repo

- The main external scaling constraint for the widget is ElevenLabs workspace
  concurrency, not browser-session handling in our frontend.
- ElevenLabs does not publish a cap on how many agents you can create; the
  documented constraint is concurrent conversations plus your available credits.
- Burst pricing can raise concurrency during spikes, but it trades higher cost
  and lower priority processing for that extra headroom.

## Published concurrency limits

The current ElevenAgents help article says concurrency is measured per workspace
across all agents and all conversations running in parallel.

| Plan | Concurrent conversations |
|------|--------------------------|
| Free | 4 |
| Starter | 6 |
| Creator | 10 |
| Pro | 20 |
| Scale | 30 |
| Business | 30 |

If you need more than the published tier limits, ElevenLabs says to contact
their enterprise team.

## Burst pricing

Burst pricing is configured per agent through `call_limits`.

- It allows traffic above the normal workspace concurrency limit.
- Published burst capacity is up to 3x the normal limit, capped at 300
  concurrent calls for non-enterprise customers.
- Burst calls are charged at 2x the standard rate.
- Burst calls are deprioritized and may see worse speech-processing latency.
- Calls above the burst ceiling are rejected.

For this repo, burst pricing is relevant if demos or launches create short-lived
spikes that exceed the normal plan limit.

## Cost snapshot

Current help-center pricing for voice-only ElevenAgents calls:

| Plan | Included minutes | Extra-minute pricing |
|------|------------------|----------------------|
| Free | 15 | Unavailable |
| Starter | 50 | Unavailable |
| Creator | 250 | 400 credits/min |
| Pro | 1,100 | 454 credits/min |
| Scale | 3,600 | 555 credits/min |
| Business | 13,750 | 800 credits/min |

Additional notes from ElevenLabs:

- Voice-only calls are billed by connection duration.
- Silence longer than 10 seconds is discounted by 95%.
- LLM costs are passed through separately.
- Setup and prompt-testing calls are billed at half cost.

The March 14, 2026 pricing update also states calls now start at $0.10/minute
on lower self-serve plans, $0.08/minute on annual Business, and lower on
Enterprise. That aligns directionally with the help-center minute tables above.

## Agent creation and per-agent controls

- ElevenLabs' public agents page says there is no published limit on the number
  of agents you can create on any plan.
- The API and changelog show per-agent `call_limits` support with:
  `agent_concurrency_limit`, `daily_limit`, and `bursting_enabled`.

For this repo, that means "agent count" is not the limiter; concurrency and
credits are.

## Error behavior that affects production handling

ElevenLabs documents two separate 429 scenarios:

- `rate_limit_exceeded`: too many requests in a short time.
- `concurrent_limit_exceeded`: too many simultaneous requests/conversations for
  the current plan.

Their docs recommend exponential backoff for rate limits and waiting for active
requests to finish when concurrency is exceeded.

## What is not clearly documented

- I did not find an official published hard cap for maximum conversation
  duration. The agent API exposes `conversation.max_duration_seconds`, but the
  docs I found do not state a platform-wide maximum.
- I did not find a separate published WebSocket-session limit for browser widget
  conversations. My inference is that browser WebSocket sessions count against
  the same workspace conversation concurrency limit, because ElevenLabs' help
  wording uses "calls/conversations running in parallel."
- I did not find a published "agent creation limit per plan" because the public
  FAQ explicitly says there is no such limit.

## Practical guidance for this repo

- For simultaneous shopper usage, assume the hard external ceiling is the
  ElevenLabs workspace concurrency limit first.
- Keep the search service multi-worker and non-blocking so our own backend is
  not the first bottleneck.
- If the product needs to tolerate short demand spikes, evaluate per-agent burst
  pricing and measure the latency impact before enabling it broadly.
- If the team needs exact current plan entitlements before a launch, re-check
  the linked help articles because ElevenLabs notes these values may change.

## Sources

- Agents FAQ: https://elevenlabs.io/agents/
- Concurrency limits help article: https://help.elevenlabs.io/hc/en-us/articles/31601651829393-How-many-Conversational-AI-requests-can-I-make-and-can-I-increase-it
- Burst pricing guide: https://elevenlabs.io/docs/eleven-agents/guides/burst-pricing
- Agents pricing help article: https://help.elevenlabs.io/hc/en-us/articles/29298065878929-How-much-does-Conversational-AI-cost
- Pricing update blog: https://elevenlabs.io/blog/we-cut-our-pricing-for-conversational-ai
- Error handling docs: https://elevenlabs.io/docs/eleven-api/resources/errors
- Agent API reference: https://elevenlabs.io/docs/eleven-agents/api-reference/agents/get
- Changelog entry for `call_limits`: https://elevenlabs.io/docs/changelog/2025/1/27
