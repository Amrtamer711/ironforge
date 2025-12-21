"""
File handling for Unified UI.

File endpoints require authentication for both uploads and downloads.

Supports both local file storage and Supabase Storage:
- Local: Serves files from disk via FileResponse
- Supabase: Redirects to signed URL or streams from storage
"""

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
from pydantic import BaseModel

from crm_security import (
    AuthUser,
    require_auth_user as require_auth,
    has_permission,
)
from utils.logging import get_logger

router = APIRouter(prefix="/api/files", tags=["files"])
logger = get_logger("api.files")

# Allowed file types for upload
ALLOWED_EXTENSIONS = {
    # Images
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp",
    # Documents
    ".pdf", ".xlsx", ".xls", ".csv", ".docx", ".doc", ".pptx", ".ppt", ".txt",
}

# Max file size: 200MB (PowerPoints and PDFs can be very large)
MAX_FILE_SIZE = 200 * 1024 * 1024


class UploadResponse(BaseModel):
    """Response from file upload."""
    file_id: str
    filename: str
    url: str
    size: int
    content_type: str


class MultiUploadResponse(BaseModel):
    """Response from multiple file upload."""
    files: list[UploadResponse]
    errors: list[str] = []


@router.post("/upload", response_model=UploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    user: AuthUser = Depends(require_auth),
):
    """
    Upload a file for use in chat.

    Uploaded files are stored in Supabase Storage (or locally in dev).
    Returns a file_id that can be passed to the chat endpoint.

    Accepts: images, PDFs, Office documents (up to 200MB)
    """
    logger.info(f"[FILES] Upload request from {user.email}: {file.filename}")

    # Validate file extension
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        logger.warning(f"[FILES] Rejected file type: {ext} from {user.email}")
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not allowed. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    # Read file content
    content = await file.read()
    file_size = len(content)

    # Check file size
    if file_size > MAX_FILE_SIZE:
        logger.warning(f"[FILES] File too large: {file_size} bytes from {user.email}")
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB"
        )

    if file_size == 0:
        raise HTTPException(status_code=400, detail="Empty file not allowed")

    # Get content type
    content_type = file.content_type or "application/octet-stream"

    # Upload via WebAdapter
    from core.chat_api import get_web_adapter

    web_adapter = get_web_adapter()

    try:
        result = await web_adapter.upload_file_bytes(
            channel_id=user.id,
            file_bytes=content,
            filename=file.filename or "upload",
            mimetype=content_type,
            bucket="uploads",
            user_id=user.id,
        )

        if not result.success:
            logger.error(f"[FILES] Upload failed for {user.email}: {result.error}")
            raise HTTPException(status_code=500, detail=result.error or "Upload failed")

        logger.info(f"[FILES] Upload success: {result.file_id} ({file_size} bytes) for {user.email}")

        return UploadResponse(
            file_id=result.file_id,
            filename=file.filename or "upload",
            url=result.url,
            size=file_size,
            content_type=content_type,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[FILES] Upload error for {user.email}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to upload file")


@router.post("/upload/multi", response_model=MultiUploadResponse)
async def upload_multiple_files(
    files: list[UploadFile] = File(...),
    user: AuthUser = Depends(require_auth),
):
    """
    Upload multiple files at once.

    Returns list of uploaded files and any errors encountered.
    """
    logger.info(f"[FILES] Multi-upload request from {user.email}: {len(files)} files")

    if len(files) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 files per upload")

    results = []
    errors = []

    for file in files:
        try:
            # Validate extension
            ext = Path(file.filename or "").suffix.lower()
            if ext not in ALLOWED_EXTENSIONS:
                errors.append(f"{file.filename}: File type '{ext}' not allowed")
                continue

            # Read and check size
            content = await file.read()
            if len(content) > MAX_FILE_SIZE:
                errors.append(f"{file.filename}: File too large (max {MAX_FILE_SIZE // (1024*1024)}MB)")
                continue

            if len(content) == 0:
                errors.append(f"{file.filename}: Empty file")
                continue

            # Upload
            from core.chat_api import get_web_adapter
            web_adapter = get_web_adapter()

            result = await web_adapter.upload_file_bytes(
                channel_id=user.id,
                file_bytes=content,
                filename=file.filename or "upload",
                mimetype=file.content_type or "application/octet-stream",
                bucket="uploads",
                user_id=user.id,
            )

            if result.success:
                results.append(UploadResponse(
                    file_id=result.file_id,
                    filename=file.filename or "upload",
                    url=result.url,
                    size=len(content),
                    content_type=file.content_type or "application/octet-stream",
                ))
            else:
                errors.append(f"{file.filename}: {result.error or 'Upload failed'}")

        except Exception as e:
            logger.error(f"[FILES] Error uploading {file.filename}: {e}")
            errors.append(f"{file.filename}: Upload error")

    logger.info(f"[FILES] Multi-upload complete: {len(results)} success, {len(errors)} errors")

    return MultiUploadResponse(files=results, errors=errors)


def _validate_filename(filename: str) -> bool:
    """Validate filename doesn't contain path traversal attempts."""
    if not filename:
        return False
    # Block path traversal patterns
    if ".." in filename or "/" in filename or "\\" in filename:
        return False
    # Block null bytes
    if "\x00" in filename:
        return False
    return True


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

    # Validate filename for path traversal
    if not _validate_filename(filename):
        logger.warning(f"[FILES] Invalid filename rejected: {filename!r} from {user.email}")
        raise HTTPException(status_code=400, detail="Invalid filename")

    from core.chat_api import get_web_adapter

    web_adapter = get_web_adapter()

    # Get stored file info
    stored_info = web_adapter.get_stored_file_info(file_id)

    if stored_info:
        # RBAC: Check file ownership - user must own the file or have admin permission
        file_owner = getattr(stored_info, 'user_id', None) or getattr(stored_info, 'owner_id', None)
        if file_owner and file_owner != user.id:
            # User doesn't own this file - check if they have admin permission
            can_access_all = has_permission(user.permissions, "core:files:read")
            if not can_access_all:
                logger.warning(f"[FILES] Access denied: {user.email} tried to access file owned by {file_owner}")
                raise HTTPException(status_code=403, detail="Not authorized to access this file")

        # Validate filename matches stored metadata (security check)
        if stored_info.filename and stored_info.filename != filename:
            logger.warning(f"[FILES] Filename mismatch: requested '{filename}', stored '{stored_info.filename}'")
            raise HTTPException(status_code=404, detail="File not found")

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

    Access: Own files or core:files:read permission.
    """
    logger.info(f"[FILES] URL request for {file_id} by {user.email}")

    from core.chat_api import get_web_adapter

    web_adapter = get_web_adapter()

    # RBAC: Check file ownership
    stored_info = web_adapter.get_stored_file_info(file_id)
    if stored_info:
        file_owner = getattr(stored_info, 'user_id', None) or getattr(stored_info, 'owner_id', None)
        if file_owner and file_owner != user.id:
            can_access_all = has_permission(user.permissions, "core:files:read")
            if not can_access_all:
                logger.warning(f"[FILES] Access denied: {user.email} tried to get URL for file owned by {file_owner}")
                raise HTTPException(status_code=403, detail="Not authorized to access this file")

    url = await web_adapter.get_file_download_url(file_id, expires_in=expires_in)

    if not url:
        raise HTTPException(status_code=404, detail="File not found")

    return {"url": url, "expires_in": expires_in}
