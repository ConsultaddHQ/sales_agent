#!/usr/bin/env python3
"""Apply migrations/*.sql in order via SUPABASE_DB_URL (psql).

Removes the "paste SQL in the Supabase editor" manual step when a direct
Postgres connection string is available. Migrations are idempotent, so
re-running is safe. Falls back to clear instructions if it can't run them
itself (no SUPABASE_DB_URL or no psql) — exit 3 = "do it manually", which
bringup.sh treats as a non-fatal warning (preflight will catch a real miss).

    python apply_migrations.py            # apply
    python apply_migrations.py --dry-run  # just list, in order
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

_SERVICE_DIR = str(Path(__file__).resolve().parent)
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
for _p in (_SERVICE_DIR, _REPO_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

load_dotenv(Path(__file__).resolve().parent / ".env")

from services.bringup import ordered_migrations  # noqa: E402

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply Supabase migrations in order")
    ap.add_argument("--dry-run", action="store_true", help="list ordered migrations and exit")
    args = ap.parse_args()

    if not MIGRATIONS_DIR.is_dir():
        print(f"❌ migrations dir not found: {MIGRATIONS_DIR}")
        return 1
    files = ordered_migrations([p.name for p in MIGRATIONS_DIR.iterdir()])
    if not files:
        print("No migrations found.")
        return 0

    print("Migrations (in order):")
    for f in files:
        print(f"  - {f}")
    if args.dry_run:
        return 0

    db_url = os.getenv("SUPABASE_DB_URL", "").strip()
    psql = shutil.which("psql")
    if not db_url or not psql:
        why = "SUPABASE_DB_URL not set" if not db_url else "psql not installed"
        print(
            f"\n⚠️  Cannot auto-apply ({why}). Apply these in the Supabase SQL "
            f"editor instead (idempotent), in order:\n  "
            + "\n  ".join(str(MIGRATIONS_DIR / f) for f in files)
        )
        return 3

    for f in files:
        path = MIGRATIONS_DIR / f
        print(f"\n▶ applying {f} …")
        proc = subprocess.run(
            [psql, db_url, "-v", "ON_ERROR_STOP=1", "-f", str(path)],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            print(f"❌ {f} failed:\n{proc.stderr.strip()}")
            return 1
        print(f"✅ {f} applied")
    print("\nAll migrations applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
