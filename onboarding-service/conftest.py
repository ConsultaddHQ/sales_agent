"""Pytest path setup — mirrors the sys.path bootstrap in main.py.

Makes `elevenlabs_agent`, `services.*`, and repo-root `shared.*`
importable when running `pytest` from onboarding-service/.
"""

import sys
from pathlib import Path

_SERVICE_DIR = str(Path(__file__).resolve().parent)
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
for _p in (_SERVICE_DIR, _REPO_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)
