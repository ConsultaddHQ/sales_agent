"""Pure orchestration helpers for the one-command bring-up.

bringup.sh wires these to real ngrok / psql / services. The error-prone
bits live here so they're unit-tested, not discovered live:
  - pick the https tunnel out of ngrok's API
  - order migration files deterministically
  - idempotently rewrite a single .env line (no dup, no partial match)
  - decide which secrets the user still has to paste
"""

import json
import re
from typing import List, Optional

_REQUIRED_SECRETS = ("SUPABASE_URL", "SUPABASE_KEY", "ELEVENLABS_API_KEY")
_MIGRATION_RE = re.compile(r"^(\d+)_.*\.sql$")


def parse_ngrok_url(api) -> Optional[str]:
    """Return the https public_url from ngrok's /api/tunnels payload."""
    if isinstance(api, str):
        try:
            api = json.loads(api)
        except Exception:
            return None
    if not isinstance(api, dict):
        return None
    tunnels = api.get("tunnels") or []
    for t in tunnels:
        if isinstance(t, dict) and t.get("proto") == "https" and t.get("public_url"):
            return t["public_url"]
    for t in tunnels:
        url = isinstance(t, dict) and t.get("public_url")
        if url and str(url).startswith("https://"):
            return url
    return None


def ordered_migrations(filenames: List[str]) -> List[str]:
    """`NNNN_*.sql` files, ascending by numeric prefix; others ignored."""
    numbered = []
    for f in filenames:
        m = _MIGRATION_RE.match(f)
        if m:
            numbered.append((int(m.group(1)), f))
    return [f for _, f in sorted(numbered, key=lambda x: x[0])]


def env_upsert(text: str, key: str, value: str) -> str:
    """Set KEY=value in a .env body: replace the existing line (dedup) or
    append. Never partial-matches a similarly-named key. Trailing newline
    guaranteed."""
    new_line = f"{key}={value}"
    pat = re.compile(rf"^\s*{re.escape(key)}\s*=.*$")
    out: List[str] = []
    replaced = False
    for ln in text.split("\n"):
        if pat.match(ln):
            if not replaced:
                out.append(new_line)
                replaced = True
            # drop any duplicate definitions
        else:
            out.append(ln)
    if not replaced:
        while out and out[-1] == "":
            out.pop()
        out.append(new_line)
    res = "\n".join(out)
    if not res.endswith("\n"):
        res += "\n"
    return res


def missing_secrets(env: dict) -> List[str]:
    """Secrets the user must still paste into onboarding-service/.env.

    An LLM key from either supported provider counts; if neither is set we
    report OPENROUTER_API_KEY as the thing to add.
    """
    miss = [k for k in _REQUIRED_SECRETS if not (env.get(k) or "").strip()]
    if not (env.get("OPENROUTER_API_KEY") or env.get("OPENAI_API_KEY") or "").strip():
        miss.append("OPENROUTER_API_KEY")
    return miss
