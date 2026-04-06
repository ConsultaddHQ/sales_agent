"""Onboarding endpoints — unified /onboard + backward-compatible aliases."""

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from error_codes import ErrorCodes, get_error_response
from pipeline import pipeline
from shopify_validator import validate_shopify_store

logger = logging.getLogger("onboarding-service")

router = APIRouter()


class OnboardRequest(BaseModel):
    url: str = Field(..., examples=["sensesindia.in", "https://example.myshopify.com"])
    store_type: str = Field(default="auto", examples=["auto", "shopify", "threadless", "supermicro"])


@router.post("/onboard")
def onboard(req: OnboardRequest) -> Dict[str, Any]:
    """Unified onboarding endpoint for all store types.

    Set store_type="auto" (default) for automatic platform detection,
    or specify explicitly: "shopify", "threadless", "supermicro", "universal".
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"ONBOARDING STARTED: {req.url} (type={req.store_type})")
    logger.info(f"{'='*60}\n")

    try:
        # For Shopify, validate first
        if req.store_type in ("shopify", "auto"):
            from adapters import detect_store_type
            detected = detect_store_type(req.url) if req.store_type == "auto" else "shopify"
            if detected == "shopify":
                validation = validate_shopify_store(req.url)
                if not validation.get("valid"):
                    raise HTTPException(status_code=400, detail=validation)
                # Use the cleaned URL from validation
                return pipeline.run(validation["url"], store_type="shopify")

        return pipeline.run(req.url, store_type=req.store_type)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Onboarding failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=get_error_response(ErrorCodes.UNKNOWN_ERROR, str(e)),
        )


# ── Backward-compatible aliases ──

class ThreadlessOnboardRequest(BaseModel):
    url: str = Field(
        default="https://nurdluv.threadless.com",
        examples=["https://nurdluv.threadless.com"],
    )


@router.post("/onboard-threadless")
def onboard_threadless(req: ThreadlessOnboardRequest) -> Dict[str, Any]:
    """Legacy endpoint — delegates to unified /onboard with store_type=threadless."""
    return onboard(OnboardRequest(url=req.url, store_type="threadless"))


class SupermicroOnboardRequest(BaseModel):
    url: str = Field(
        default="https://www.supermicro.com/en/products/gpu",
        examples=["https://www.supermicro.com/en/products/gpu"],
    )


@router.post("/onboard-supermicro")
def onboard_supermicro(req: SupermicroOnboardRequest) -> Dict[str, Any]:
    """Legacy endpoint — delegates to unified /onboard with store_type=supermicro."""
    return onboard(OnboardRequest(url=req.url, store_type="supermicro"))
