"""
Static file serving for Unified UI.

File endpoints require authentication to serve user-uploaded files.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from api.auth import require_auth
from integrations.auth import AuthUser

router = APIRouter(prefix="/api/files", tags=["files"])


@router.get("/{file_id}/{filename}")
async def serve_uploaded_file(
    file_id: str,
    filename: str,
    user: AuthUser = Depends(require_auth),
):
    """
    Serve files uploaded through the chat interface.

    Requires authentication. Only serves files owned by the authenticated user.
    """
    from core.chat_api import get_web_adapter

    web_adapter = get_web_adapter()
    file_path = web_adapter.get_file_path(file_id)

    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    # TODO: Add ownership check once files are associated with users
    return FileResponse(file_path, filename=filename)
