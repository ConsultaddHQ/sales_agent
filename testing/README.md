# testing/

Durable test harnesses that aren't part of a service's own code but that we
want to keep around for reruns. Each subfolder is one test kind.

| Subfolder | What it's for |
|-----------|---------------|
| `latency/` | Voice-agent latency A/B harness. Creates parallel ElevenLabs agents pinned to different LLMs, runs a fixed prompt protocol, compares results. Used on 2026-04-17 to pick Claude Haiku 4.5. Keep for future model comparisons. |

## Adding a new harness

Create a new subfolder with its own `README.md` describing what the harness
does, how to run it, and how to interpret results. Keep harnesses
self-contained: they should import from `shared/` and service modules via
relative path setup, not assume they live inside any particular service.
