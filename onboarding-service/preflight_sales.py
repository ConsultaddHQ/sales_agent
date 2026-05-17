#!/usr/bin/env python3
"""Preflight for the Pop Sales Agent live test.

Verifies env, the public brain URL, that Supabase migrations 0001/0002 are
applied, and that the widget IIFE is built — PASS/WARN/FAIL per check —
BEFORE you try a live conversation, so failures aren't a confusing
mid-call surprise.

    cd onboarding-service && source .venv/bin/activate
    python preflight_sales.py        # exit 0 = go, 1 = blocked

Note: WARN does not block (e.g. local URL while you're still setting up).
"""

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

from services.preflight import (  # noqa: E402
    Check, env_checks, resolve_brain_url, overall_ok, PASS, WARN, FAIL,
)

ICON = {PASS: "✅", WARN: "⚠️ ", FAIL: "❌"}


def _supabase_checks() -> list:
    checks: list = []
    try:
        from shared.db import get_supabase
        sb = get_supabase()
    except Exception as e:
        return [Check("supabase", FAIL, f"cannot connect: {e}")]

    # Migration 0001 — sales_sessions / sales_proof + agent_requests columns.
    for table in ("sales_sessions", "sales_proof"):
        try:
            sb.table(table).select("*").limit(1).execute()
            checks.append(Check(f"table {table}", PASS, "exists"))
        except Exception:
            checks.append(Check(f"table {table}", FAIL, "missing — apply migrations/0001_sales_agent.sql"))
    try:
        sb.table("agent_requests").select("source,transcript,discovery,pic").limit(1).execute()
        checks.append(Check("agent_requests cols", PASS, "source/transcript/discovery/pic present"))
    except Exception:
        checks.append(Check("agent_requests cols", FAIL, "missing — apply migrations/0001 (ALTER section)"))

    # Migration 0002 — seeded proof (WARN: agent works, just no proof to surface).
    try:
        rows = sb.table("sales_proof").select("id").limit(1).execute().data
        if rows:
            checks.append(Check("proof content", PASS, "sales_proof has rows"))
        else:
            checks.append(Check("proof content", WARN, "empty — apply migrations/0002 or add proof in /admin"))
    except Exception:
        pass  # table-missing already reported above
    return checks


def _widget_check() -> Check:
    dist = Path(__file__).resolve().parent.parent / "www.teampop" / "frontend" / "dist" / "widget.js"
    if dist.exists():
        return Check("widget build", PASS, "dist/widget.js present")
    return Check("widget build", WARN, "missing — cd www.teampop/frontend && npm run build")


def main() -> int:
    checks: list = []
    checks += env_checks(os.environ)
    checks.append(resolve_brain_url(os.environ))

    env_ok = all(
        c.status != FAIL for c in checks if c.name in ("SUPABASE_URL", "SUPABASE_KEY")
    )
    if env_ok:
        checks += _supabase_checks()
    else:
        checks.append(Check("supabase", FAIL, "skipped — fix SUPABASE_URL/SUPABASE_KEY first"))
    checks.append(_widget_check())

    width = max(len(c.name) for c in checks)
    print("\nPop Sales Agent — preflight\n" + "=" * 52)
    for c in checks:
        print(f"{ICON.get(c.status, '?')} {c.name.ljust(width)}  {c.detail}")
    print("=" * 52)

    if overall_ok(checks):
        warns = [c for c in checks if c.status == WARN]
        print(f"READY{' (note ' + str(len(warns)) + ' WARN)' if warns else ''} — provision the agent, then talk to it.\n")
        return 0
    print("NOT READY — resolve the ❌ above (see docs/pop-sales-agent/RUNBOOK.md).\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
