import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "onboarding-service"))
os.environ.setdefault("ELEVENLABS_API_KEY", "test-key")

from elevenlabs_agent import PROMPT_CLAUDE, ElevenLabsAgentCreator  # noqa: E402


class ShowSearchErrorToolTests(unittest.TestCase):
    def setUp(self):
        self.creator = ElevenLabsAgentCreator(api_key="test-key")
        self.tools = self.creator._get_tool_config(
            "https://api.example.com", "9cec7cd0-9252-4aa2-985b-71c2a42018cb"
        )
        self.by_name = {t["name"]: t for t in self.tools}

    def test_show_search_error_is_client_tool_without_response(self):
        tool = self.by_name["show_search_error"]
        self.assertEqual(tool["type"], "client")
        self.assertFalse(tool["expects_response"])
        self.assertEqual(tool["execution_mode"], "immediate")

    def test_prompt_claude_calls_show_search_error_only_on_tool_failure(self):
        self.assertIn("show_search_error", PROMPT_CLAUDE)
        self.assertIn("NOT when the catalog is empty", PROMPT_CLAUDE)
        self.assertNotIn(
            'The ONLY allowed process phrase is one short filler before the very first search ("Let me check that.")',
            PROMPT_CLAUDE,
        )


if __name__ == "__main__":
    unittest.main()
