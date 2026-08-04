from __future__ import annotations

import base64

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.config import settings
from app.models.user import User, UserRole
from app.services.auth import require_role

router = APIRouter(prefix="/api/v1/upload", tags=["Upload"])

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
IMAGEKIT_UPLOAD_URL = "https://upload.imagekit.io/api/v1/files/upload"


async def _upload_to_imagekit(file_bytes: bytes, filename: str, content_type: str, folder: str) -> dict:
    """Upload bytes to ImageKit via their REST API and return the result."""
    if not settings.imagekit_url_endpoint or not settings.imagekit_private_key:
        raise HTTPException(
            status_code=503,
            detail="ImageKit is not configured. Set IMAGEKIT_URL_ENDPOINT and IMAGEKIT_PRIVATE_KEY.",
        )

    auth_header = base64.b64encode(
        f"{settings.imagekit_private_key}:".encode()
    ).decode()

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            IMAGEKIT_UPLOAD_URL,
            headers={
                "Authorization": f"Basic {auth_header}",
            },
            files={
                "file": (filename, file_bytes, content_type),
            },
            data={
                "fileName": filename,
                "folder": folder,
                "useUniqueFileName": "true",
            },
        )

    if response.status_code not in (200, 201):
        detail = response.text
        try:
            detail = response.json().get("message", detail)
        except Exception:
            pass
        raise HTTPException(status_code=502, detail=f"ImageKit upload failed: {detail}")

    result = response.json()
    return {
        "url": result.get("url", ""),
        "file_id": result.get("fileId", ""),
        "name": result.get("name", ""),
    }


@router.post("/image")
async def upload_image(
    file: UploadFile = File(...),
    folder: str = "players",
    user: User = Depends(require_role(UserRole.ADMIN)),
):
    """Upload an image file to ImageKit.

    ImageKit handles format conversion on-the-fly via URL transforms
    (e.g. append ?tr=f-webp to any image URL to get WebP).

    Returns the public URL.
    """
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{file.content_type}' not allowed. Use JPEG, PNG, WebP, or GIF.",
        )

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 5 MB.")
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file.")

    # Sanitize folder path
    safe_folder = "/".join(part for part in folder.split("/") if part)
    if not safe_folder:
        safe_folder = "uploads"

    # Use original filename; ImageKit will deduplicate via useUniqueFileName
    filename = file.filename or "upload.jpg"

    result = await _upload_to_imagekit(
        file_bytes, filename, file.content_type or "image/jpeg", f"/babile-sport/{safe_folder}"
    )

    return {
        "url": result["url"],
        "file_id": result["file_id"],
        "name": result["name"],
    }
