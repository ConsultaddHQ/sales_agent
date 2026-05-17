#!/usr/bin/env python3
"""Provision the Team Pop sales agent on ElevenLabs (one command).

Resolves the public brain URL (the ngrok tunnel fronting onboarding-service
/sales/*), validates it can actually be reached by ElevenLabs, creates the
agent, and prints the exact env line to paste.

Run AFTER ngrok is up and SEARCH_API_URL (or SALES_BRAIN_URL) points at it
— the URL is baked into the agent at creation time (same gotcha as store
onboarding; re-run if the tunnel changes).

    cd onboarding-service && source .venv/bin/activate
    python provision_sales_agent.py                 # uses env
    python provision_sales_agent.py --brain-url https://abc.ngrok-free.app
    python provision_sales_agent.py --site teampop --name "Team Pop" --force
"""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

_SERVICE_DIR = str(Path(__file__).resolve().parent)
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
for _p in (_SERVICE_DIR, _REPO_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

load_dotenv(Path(__file__).resolve().parent / ".env")

from services.preflight import resolve_brain_url, PASS, WARN, FAIL  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Provision the Team Pop sales agent")
    ap.add_argument("--site", default="teampop", help="site id (default: teampop)")
    ap.add_argument("--name", default="Team Pop", help="site display name")
    ap.add_argument("--brain-url", default=None, help="override the public /sales brain URL")
    ap.add_argument("--force", action="store_true", help="proceed even if the URL looks local/non-https")
    args = ap.parse_args()

    if args.brain_url:
        brain_url = args.brain_url.rstrip("/")
        print(f"Using --brain-url: {brain_url}")
    else:
        check = resolve_brain_url(os.environ)
        if check.status == FAIL:
            print(f"❌ {check.detail}")
            print("   Set SEARCH_API_URL (or SALES_BRAIN_URL) to the ngrok https URL, or pass --brain-url.")
            return 1
        if check.status == WARN and not args.force:
            print(f"⚠️  {check.detail}")
            print("   ElevenLabs likely can't reach this. Fix the URL, or re-run with --force if you know better.")
            return 2
        brain_url = check.detail if check.status == PASS else (
            os.environ.get("SALES_BRAIN_URL") or os.environ.get("SEARCH_API_URL", "")
        ).strip().rstrip("/")

    try:
        from elevenlabs_agent import create_sales_agent
    except Exception as e:  # pragma: no cover - import guard
        print(f"❌ Could not import create_sales_agent: {e}")
        return 1

    if not os.getenv("ELEVENLABS_API_KEY"):
        print("❌ ELEVENLABS_API_KEY not set — cannot provision.")
        return 1

    print(f"Creating sales agent: site={args.site!r} name={args.name!r} brain={brain_url}")
    try:
        result = create_sales_agent(
            site=args.site,
            brain_api_url=brain_url,
            site_name=args.name,
        )
    except Exception as e:
        print(f"❌ Provisioning failed: {e}")
        return 1

    agent_id = result.get("agent_id")
    print("\n✅ Sales agent created")
    print(f"   agent_id : {agent_id}")
    print(f"   dashboard: {result.get('agent_url')}")
    print("\nPaste this into www.teampop/website/.env (then rebuild the site):\n")
    print(f"   VITE_SALES_AGENT_ID={agent_id}\n")
    print("Re-run this script if the ngrok URL changes (the URL is baked in).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
