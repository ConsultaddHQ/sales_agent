#!/usr/bin/env python3
"""
Image Server for Product Images
Serves downloaded images with CORS support
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Product Image Server")

# Enable CORS for all origins (adjust in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Images directory
IMAGES_DIR = Path("./product_images").resolve()

@app.get("/health")
def health():
    return {"status": "ok", "images_dir": str(IMAGES_DIR)}

@app.get("/images/{store_id}/{filename}")
def serve_image(store_id: str, filename: str):
    """Serve product image"""
    file_path = IMAGES_DIR / store_id / filename
    
    if not file_path.exists():
        logger.warning(f"Image not found: {file_path}")
        raise HTTPException(status_code=404, detail="Image not found")
    
    # Security: ensure path is within IMAGES_DIR
    try:
        file_path.resolve().relative_to(IMAGES_DIR)
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return FileResponse(file_path)

@app.get("/")
def root():
    return {
        "service": "Product Image Server",
        "status": "running",
        "endpoint": "/images/{store_id}/{filename}"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
