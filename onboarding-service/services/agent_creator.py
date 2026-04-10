"""Re-export from elevenlabs_agent for clean import paths.

The actual implementation stays in elevenlabs_agent.py — this module
just provides a cleaner import path from the services/ package.
"""

import sys
from pathlib import Path

# Ensure the onboarding-service root is importable
_SERVICE_DIR = str(Path(__file__).resolve().parent.parent)
if _SERVICE_DIR not in sys.path:
    sys.path.insert(0, _SERVICE_DIR)

from elevenlabs_agent import create_agent_for_store  # noqa: F401
