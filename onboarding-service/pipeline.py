"""Unified onboarding pipeline.

Replaces the 3 duplicated if/elif branches in _run_onboarding_pipeline().
All store types flow through the same 7-step process; only the adapter differs.
"""

import logging
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from shared.config import SEARCH_API_URL, STORE_IMAGES_PATH, WIDGET_SCRIPT_URL, MAX_PRODUCTS
from shared.db import get_supabase
from error_codes import ErrorCodes, get_error_response, success_response
from services.products import build_product_rows, store_products_in_supabase
from services.agent_creator import create_agent_for_store
from services.test_page import generate_test_page
from adapters import get_adapter, detect_store_type

logger = logging.getLogger("onboarding-service")


class OnboardingPipeline:
    """Runs the 7-step onboarding flow for any store type."""

    def run(
        self,
        url: str,
        store_type: str = "auto",
        max_products: int = MAX_PRODUCTS,
    ) -> Dict[str, Any]:
        """Execute the full pipeline synchronously.

        Returns a success_response dict with store_id, agent_id, etc.
        """
        # Normalize URL
        clean_url = url.strip().rstrip("/")
        if not clean_url.startswith("http"):
            clean_url = f"https://{clean_url}"
        domain = urlparse(clean_url).netloc

        # Resolve adapter
        if store_type == "auto":
            store_type = detect_store_type(clean_url)
        adapter = get_adapter(store_type)

        store_id = str(uuid.uuid4())
        logger.info(f"Pipeline started: {domain} (type={store_type}, store_id={store_id})")

        # Step 1: Scrape products
        logger.info(f"Step 1/7: Scraping products (max {max_products})...")
        raw_products = adapter.scrape_products(clean_url, max_products=max_products)
        if not raw_products:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=400,
                detail=get_error_response(ErrorCodes.NO_PRODUCTS),
            )

        # Step 2: Process products (images + embeddings)
        logger.info("Step 2/7: Processing products and downloading images...")
        images_dir = STORE_IMAGES_PATH() / store_id
        product_rows = build_product_rows(domain, store_id, raw_products, images_dir)

        # Step 3: Store in Supabase
        logger.info("Step 3/7: Storing products in database...")
        store_products_in_supabase(product_rows)

        # Step 4: Create ElevenLabs agent
        logger.info("Step 4/7: Creating ElevenLabs agent...")
        store_context = adapter.extract_store_context(raw_products, domain)
        agent_result = create_agent_for_store(
            store_id=store_id,
            store_context=store_context,
            search_api_url=SEARCH_API_URL(),
            tags=adapter.get_agent_tags(store_id),
        )
        agent_id = agent_result["agent_id"]
        logger.info(f"Agent created: {agent_id}")

        # Step 5: Generate test page
        logger.info("Step 5/7: Generating test page...")
        try:
            filename = generate_test_page(
                clean_url,
                store_id,
                agent_id,
                use_playwright=adapter.needs_playwright,
                challenge_wait=adapter.challenge_wait,
            )
            test_url = f"/demo/{filename}"
        except Exception as e:
            logger.warning(f"Test page generation failed: {e}")
            test_url = f"/demo/test_{store_id[:8]}.html"

        # Step 6: Generate widget snippet
        logger.info("Step 6/7: Generating widget snippet...")
        widget_script_url = WIDGET_SCRIPT_URL()
        widget_snippet = (
            f'<!-- TeamPop Voice Widget -->\n'
            f'<script>\n'
            f'window.__TEAM_POP_AGENT_ID__ = "{agent_id}";\n'
            f'</script>\n'
            f'<script src="{widget_script_url}"></script>\n'
            f'<team-pop-agent></team-pop-agent>'
        )

        logger.info(f"Pipeline complete: {len(product_rows)} products, agent={agent_id}")

        return success_response({
            "store_id": store_id,
            "agent_id": agent_id,
            "test_url": test_url,
            "widget_snippet": widget_snippet,
            "products_count": len(product_rows),
            "store_url": clean_url,
        })

    def run_background(self, request_id: str, scrape_url: str, store_type: str) -> None:
        """Run pipeline in background thread, update agent_requests table on completion."""
        sb = get_supabase()
        try:
            result = self.run(scrape_url, store_type=store_type)
            sb.table("agent_requests").update({
                "status": "ready",
                "agent_id": result["agent_id"],
                "test_url": result["test_url"],
                "updated_at": datetime.now().isoformat(),
            }).eq("id", request_id).execute()
            logger.info(f"Onboarding pipeline complete for request {request_id}")
        except Exception as e:
            logger.error(f"Onboarding pipeline failed for {request_id}: {e}")
            sb.table("agent_requests").update({
                "status": "failed",
                "error_message": str(e)[:500],
                "updated_at": datetime.now().isoformat(),
            }).eq("id", request_id).execute()


# Module-level singleton
pipeline = OnboardingPipeline()
