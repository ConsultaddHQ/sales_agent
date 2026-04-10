"""
Image Server for Product Images
Serves product images downloaded during onboarding with proper CORS headers
"""

import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="TeamPop Image Server", version="1.0.0")

# CORS configuration - allow all origins for now
# TODO: Update with specific domains in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Base directory for images
# Images are organized as: {base}/images/{store_id}/{filename}.jpg
# Default: onboarding-service/images/ (where the pipeline saves them)
_DEFAULT_IMAGES_PATH = str(Path(__file__).resolve().parent / "onboarding-service" / "images")
IMAGES_BASE_DIR = Path(os.getenv("STORE_IMAGES_PATH", _DEFAULT_IMAGES_PATH)).resolve()

logger.info(f"📁 Serving images from: {IMAGES_BASE_DIR}")


@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {
        "status": "ok",
        "service": "image-server",
        "images_dir": str(IMAGES_BASE_DIR),
        "images_dir_exists": IMAGES_BASE_DIR.exists()
    }


@app.get("/images/{store_id}/{filename}")
async def serve_image(store_id: str, filename: str):
    """
    Serve a product image
    
    Args:
        store_id: UUID of the store
        filename: Image filename (e.g., product-handle.jpg)
    
    Returns:
        Image file with appropriate headers
    
    Raises:
        404 if image not found
        403 if path traversal attempted
    """
    # Security: Prevent path traversal attacks
    if ".." in store_id or ".." in filename:
        logger.warning(f"⚠️ Path traversal attempt: {store_id}/{filename}")
        raise HTTPException(status_code=403, detail="Invalid path")
    
    # Validate filename format
    if not filename.endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif')):
        raise HTTPException(status_code=400, detail="Invalid image format")
    
    # Construct file path
    image_path = IMAGES_BASE_DIR / store_id / filename
    
    # Check if file exists
    if not image_path.exists() or not image_path.is_file():
        logger.warning(f"❌ Image not found: {image_path}")
        raise HTTPException(status_code=404, detail="Image not found")
    
    # Check if path is within base directory (extra security)
    try:
        image_path.resolve().relative_to(IMAGES_BASE_DIR.resolve())
    except ValueError:
        logger.error(f"🚨 Security violation: Attempted access outside base dir")
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Determine media type
    media_type_map = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.webp': 'image/webp',
        '.gif': 'image/gif'
    }
    
    ext = image_path.suffix.lower()
    media_type = media_type_map.get(ext, 'application/octet-stream')
    
    # Serve the file
    logger.info(f"✅ Serving image: {store_id}/{filename}")
    return FileResponse(
        path=image_path,
        media_type=media_type,
        headers={
            "Cache-Control": "public, max-age=31536000",  # Cache for 1 year
            "Access-Control-Allow-Origin": "*"  # CORS header
        }
    )


@app.get("/images/{store_id}")
async def list_store_images(store_id: str):
    """
    List all images for a store (useful for debugging)
    
    Args:
        store_id: UUID of the store
    
    Returns:
        List of image filenames
    """
    store_dir = IMAGES_BASE_DIR / store_id
    
    if not store_dir.exists():
        raise HTTPException(status_code=404, detail="Store not found")
    
    images = []
    for img in store_dir.glob("*"):
        if img.is_file() and img.suffix.lower() in ['.jpg', '.jpeg', '.png', '.webp', '.gif']:
            images.append({
                "filename": img.name,
                "size": img.stat().st_size,
                "url": f"/images/{store_id}/{img.name}"
            })
    
    return {
        "store_id": store_id,
        "image_count": len(images),
        "images": images
    }


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("IMAGE_SERVER_PORT", 8000))
    
    logger.info(f"🚀 Starting Image Server on port {port}")
    logger.info(f"📁 Images directory: {IMAGES_BASE_DIR}")
    
    # Create images directory if it doesn't exist
    IMAGES_BASE_DIR.mkdir(parents=True, exist_ok=True)
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
