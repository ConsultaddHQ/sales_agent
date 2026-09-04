import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "search-service"))
sys.path.insert(0, str(ROOT))

import main as search_main  # noqa: E402


class SearchErrorLatencyTests(unittest.TestCase):
    def test_persist_called_when_hybrid_search_raises(self):
        persisted = []

        def fake_persist(**kwargs):
            persisted.append(kwargs)

        async def boom(**kwargs):
            raise HTTPException(status_code=503, detail="overloaded")

        with patch.object(search_main, "_hybrid_search_products", side_effect=boom), \
             patch.object(search_main, "_persist_search_latency", side_effect=fake_persist):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(
                    search_main._search_uncached(
                        sb=object(),
                        store_id="9cec7cd0-9252-4aa2-985b-71c2a42018cb",
                        query="moisturizer",
                        t0=search_main.time.perf_counter(),
                    )
                )

        self.assertEqual(len(persisted), 1)
        self.assertEqual(persisted[0]["result_count"], 0)
        self.assertFalse(persisted[0]["cache_hit"])
        self.assertEqual(persisted[0]["query"], "moisturizer")
        # Headers must ride on the exception — FastAPI discards the Response object
        # it handed the endpoint once an HTTPException propagates.
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertEqual(ctx.exception.headers.get("X-Search-Cache"), "error")
        self.assertIn("X-Search-Duration-Ms", ctx.exception.headers)


if __name__ == "__main__":
    unittest.main()
