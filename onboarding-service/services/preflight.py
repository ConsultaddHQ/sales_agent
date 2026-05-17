"""Pure preflight logic for the live bring-up (no network/DB).

`preflight_sales.py` wires these to real Supabase/ElevenLabs/file I/O;
the decision logic (what's required, is the brain URL actually reachable
by ElevenLabs, do we proceed) is pure and unit-tested.
"""

from dataclasses import dataclass

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"


@dataclass
class Check:
    name: str
    status: str  # PASS | WARN | FAIL
    detail: str


# Hard requirements to even attempt a live run.
REQUIRED_ENV = {
    "SUPABASE_URL": "Supabase project URL",
    "SUPABASE_KEY": "Supabase service-role key",
    "ELEVENLABS_API_KEY": "ElevenLabs API key (agent provisioning + voice)",
}


def resolve_brain_url(env: dict) -> Check:
    """The URL ElevenLabs webhooks must reach for /sales/*.

    SALES_BRAIN_URL overrides SEARCH_API_URL (both front onboarding-service
    via the single ngrok tunnel). Local/non-https can't be reached by
    ElevenLabs, so those are surfaced loudly.
    """
    url = (env.get("SALES_BRAIN_URL") or env.get("SEARCH_API_URL") or "").strip().rstrip("/")
    if not url:
        return Check(
            "brain_url",
            FAIL,
            "SALES_BRAIN_URL / SEARCH_API_URL not set — ElevenLabs needs a public https URL to reach /sales/*",
        )
    if "localhost" in url or "127.0.0.1" in url or "0.0.0.0" in url:
        return Check(
            "brain_url",
            WARN,
            f"{url} is local — ElevenLabs webhooks cannot reach it; use the ngrok https URL",
        )
    if not url.startswith("https://"):
        return Check("brain_url", WARN, f"{url} is not https — ElevenLabs requires https webhooks")
    return Check("brain_url", PASS, url)


def env_checks(env: dict) -> list:
    """Required env + an LLM key from either supported provider."""
    checks = []
    for key, purpose in REQUIRED_ENV.items():
        present = bool((env.get(key) or "").strip())
        checks.append(
            Check(key, PASS if present else FAIL, purpose if present else f"missing — {purpose}")
        )
    has_llm = bool((env.get("OPENROUTER_API_KEY") or env.get("OPENAI_API_KEY") or "").strip())
    checks.append(
        Check(
            "LLM_API_KEY",
            PASS if has_llm else FAIL,
            "OPENROUTER_API_KEY or OPENAI_API_KEY present"
            if has_llm
            else "set OPENROUTER_API_KEY (or OPENAI_API_KEY) for the sales brain",
        )
    )
    return checks


def overall_ok(checks: list) -> bool:
    """Go/no-go: any FAIL blocks the live run; WARN is allowed (with eyes open)."""
    return all(c.status != FAIL for c in checks)
