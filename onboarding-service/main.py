"""
TeamPop Onboarding Service
Unified entry point — all business logic lives in routes/, services/, adapters/.
"""

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Ensure shared/ and this directory are importable
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
_SERVICE_DIR = str(Path(__file__).resolve().parent)
for p in (_REPO_ROOT, _SERVICE_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

# Load environment
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("onboarding-service")

# FastAPI app
app = FastAPI(title="TeamPop Onboarding Service", version="3.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve built widget.js from frontend dist
WIDGET_DIST_DIR = Path(__file__).parent.parent / "www.teampop" / "frontend" / "dist"
if WIDGET_DIST_DIR.exists():
    app.mount("/widget", StaticFiles(directory=str(WIDGET_DIST_DIR)), name="widget")
    logger.info(f"Widget served from: {WIDGET_DIST_DIR}")
else:
    logger.warning(f"Widget dist not found at {WIDGET_DIST_DIR} — run npm run build in frontend/")

# Serve generated demo pages
DEMO_PAGES_DIR = Path("./demo_pages")
DEMO_PAGES_DIR.mkdir(exist_ok=True)
app.mount("/demo", StaticFiles(directory=str(DEMO_PAGES_DIR), html=True), name="demo")

# Register routes
from routes.onboard import router as onboard_router
from routes.admin import router as admin_router
from routes.client import router as client_router

app.include_router(onboard_router)
app.include_router(admin_router)
app.include_router(client_router)

# Force adapter registration on startup
import adapters  # noqa: F401


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "onboarding-service",
        "version": "3.0.0",
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8005))
    logger.info(f"Starting Onboarding Service on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
