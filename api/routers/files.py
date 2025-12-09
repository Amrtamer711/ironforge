"""
Static file serving for Unified UI.

File endpoints require authentication to serve user-uploaded files.

Supports both local file storage and Supabase Storage:
- Local: Serves files from disk via FileResponse
- Supabase: Redirects to signed URL or streams from storage
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, RedirectResponse, Response

from api.auth import require_auth
from integrations.auth import AuthUser
from utils.logging import get_logger

router = APIRouter(prefix="/api/files", tags=["files"])
logger = get_logger("api.files")


@router.get("/{file_id}/{filename}")
async def serve_uploaded_file(
    file_id: str,
    filename: str,
    user: AuthUser = Depends(require_auth),
    redirect: bool = True,  # If True, redirect to signed URL; if False, stream bytes
):
    """
    Serve files uploaded through the chat interface.

    Requires authentication. Supports both local and Supabase Storage.

    For Supabase Storage:
    - Default (redirect=True): Returns 302 redirect to signed URL
    - redirect=False: Streams file bytes directly (for compatibility)

    For local storage:
    - Returns file directly via FileResponse
    """
    logger.info(f"[FILES] File request: {file_id}/{filename} by {user.email}")

    from core.chat_api import get_web_adapter

    web_adapter = get_web_adapter()

    # Get stored file info
    stored_info = web_adapter.get_stored_file_info(file_id)

    if stored_info:
        # Check if file is in remote storage (no local_path)
        if not stored_info.local_path:
            # File is in Supabase Storage
            if redirect:
                # Get signed URL and redirect
                signed_url = await web_adapter.get_file_download_url(file_id, expires_in=3600)
                if signed_url:
                    logger.info(f"[FILES] Redirecting to signed URL for {file_id}")
                    return RedirectResponse(url=signed_url, status_code=302)
                else:
                    logger.error(f"[FILES] Failed to get signed URL for {file_id}")
                    raise HTTPException(status_code=500, detail="Failed to generate download URL")
            else:
                # Stream bytes directly
                file_bytes = await web_adapter.download_file_bytes(file_id)
                if file_bytes:
                    logger.info(f"[FILES] Streaming {len(file_bytes)} bytes for {file_id}")
                    return Response(
                        content=file_bytes,
                        media_type=stored_info.content_type,
                        headers={
                            "Content-Disposition": f'attachment; filename="{filename}"'
                        }
                    )
                else:
                    logger.error(f"[FILES] Failed to download file {file_id} from storage")
                    raise HTTPException(status_code=404, detail="File not found in storage")

        # File has local path - serve directly
        if stored_info.local_path and stored_info.local_path.exists():
            logger.info(f"[FILES] Serving local file: {stored_info.local_path}")
            return FileResponse(
                stored_info.local_path,
                filename=filename,
                media_type=stored_info.content_type
            )

    # Fallback: Try legacy file path lookup
    file_path = web_adapter.get_file_path(file_id)
    if file_path and file_path.exists():
        logger.info(f"[FILES] Serving legacy file: {file_path}")
        return FileResponse(file_path, filename=filename)

    logger.warning(f"[FILES] File not found: {file_id}/{filename} requested by {user.email}")
    raise HTTPException(status_code=404, detail="File not found")


@router.get("/{file_id}/{filename}/url")
async def get_file_download_url(
    file_id: str,
    filename: str,
    user: AuthUser = Depends(require_auth),
    expires_in: int = 3600,
):
    """
    Get a download URL for a file.

    For Supabase Storage, returns a signed URL that expires.
    For local storage, returns the API endpoint URL.
    """
    logger.info(f"[FILES] URL request for {file_id} by {user.email}")

    from core.chat_api import get_web_adapter

    web_adapter = get_web_adapter()
    url = await web_adapter.get_file_download_url(file_id, expires_in=expires_in)

    if not url:
        raise HTTPException(status_code=404, detail="File not found")

    return {"url": url, "expires_in": expires_in}
