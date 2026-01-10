"""
Unified UI chat endpoints.

All chat endpoints require authentication. User info is extracted from the
authenticated user token rather than being passed in the request body.
"""

import asyncio
import time
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from crm_security import require_permission_user as require_permission, AuthUser
from integrations.rbac import get_rbac_client
from core.utils.logging import get_logger

logger = get_logger("api.chat")

router = APIRouter(prefix="/api/chat", tags=["chat"])

# Security limits
MAX_MESSAGE_LENGTH = 10_000  # 10k characters max per message

# Profile cache for RBAC lookups (avoids 100-500ms per request)
_profile_cache: dict[str, tuple[list[str], float]] = {}
PROFILE_CACHE_TTL = 600  # 10 minutes


class ChatMessageRequest(BaseModel):
    """Request model for chat messages."""
    message: str
    conversation_id: str | None = None
    file_ids: list[str] | None = None  # IDs from /api/files/upload

    @field_validator("message")
    @classmethod
    def validate_message_length(cls, v: str) -> str:
        """Validate message is not too long (DoS protection, cost control)."""
        if len(v) > MAX_MESSAGE_LENGTH:
            raise ValueError(f"Message too long. Maximum {MAX_MESSAGE_LENGTH} characters allowed.")
        if not v.strip():
            raise ValueError("Message cannot be empty")
        return v

    @field_validator("file_ids")
    @classmethod
    def validate_file_ids(cls, v: list[str] | None) -> list[str] | None:
        """Validate file_ids list."""
        if v is not None and len(v) > 10:
            raise ValueError("Maximum 10 files per message")
        return v


class ChatMessageResponse(BaseModel):
    """Response model for chat messages."""
    content: str | None = None
    tool_call: dict | None = None
    files: list[dict] | None = None
    error: str | None = None
    conversation_id: str | None = None


class AttachmentRefreshRequest(BaseModel):
    """Request model for batch attachment URL refresh."""
    file_ids: list[str]  # Visible attachments to refresh
    prefetch_ids: list[str] = []  # Next page (pre-fetch for scroll-ahead)

    @field_validator("file_ids")
    @classmethod
    def validate_file_ids(cls, v: list[str]) -> list[str]:
        """Validate file_ids list."""
        if len(v) > 100:
            raise ValueError("Maximum 100 file_ids per request")
        return v

    @field_validator("prefetch_ids")
    @classmethod
    def validate_prefetch_ids(cls, v: list[str]) -> list[str]:
        """Validate prefetch_ids list."""
        if len(v) > 50:
            raise ValueError("Maximum 50 prefetch_ids per request")
        return v


def _build_file_info(stored_info: Any, file_id: str) -> dict | None:
    """Build file info dict from stored info. Extracted helper to avoid duplication."""
    if not stored_info:
        return None
    url = f"/api/files/{file_id}/{stored_info.filename}" if stored_info.filename else f"/api/files/{file_id}/file"
    return {
        "file_id": file_id,
        "filename": stored_info.filename,
        "mimetype": stored_info.content_type,
        "size": stored_info.size,
        "url": url,
    }


async def _get_user_profile(user: AuthUser) -> list[str]:
    """Get profile name for a user from RBAC (cached)."""
    cache_key = user.id
    now = time.time()

    # Check cache first
    if cache_key in _profile_cache:
        roles, cached_at = _profile_cache[cache_key]
        if now - cached_at < PROFILE_CACHE_TTL:
            return roles

    # Fetch from RBAC
    try:
        rbac = get_rbac_client()
        profile = await rbac.get_user_profile(user.id)
        profile_name = profile.name if profile else user.metadata.get("role", "sales_user")
        roles = [profile_name]
        _profile_cache[cache_key] = (roles, now)
        return roles
    except Exception as e:
        logger.warning(f"[CHAT] Failed to get profile for {user.email}: {e}")
        return [user.metadata.get("role", "sales_user")]


@router.post("/message", response_model=ChatMessageResponse)
async def chat_message(
    request: ChatMessageRequest,
    user: AuthUser = Depends(require_permission("sales:chat:use")),
):
    """
    Send a chat message and receive a response.

    This endpoint connects the Unified UI to the same LLM infrastructure
    used by the Slack bot. Requires sales:chat:use permission.

    Optionally include file_ids from /api/files/upload to attach files.
    """
    logger.info(f"[CHAT] Message from {user.email}: {request.message[:50]}... (files: {len(request.file_ids or [])})")

    from core.chat_api import get_web_adapter, process_chat_message

    try:
        roles = await _get_user_profile(user)

        # Convert file_ids to file info dicts for processing
        files = None
        if request.file_ids:
            web_adapter = get_web_adapter()
            # Build file infos (using helper to avoid duplication)
            file_infos = [
                _build_file_info(web_adapter.get_stored_file_info(fid), fid)
                for fid in request.file_ids
            ]
            files = [f for f in file_infos if f]
            if len(files) < len(request.file_ids):
                logger.warning(f"[CHAT] Some files not found for {user.email}")

        result = await process_chat_message(
            user_id=user.id,
            user_name=user.name or user.email,
            message=request.message,
            roles=roles,
            files=files,
            companies=user.companies,
            permissions=user.permissions,
        )

        logger.info(f"[CHAT] Response generated for {user.email}")
        return ChatMessageResponse(
            content=result.get("content"),
            tool_call=result.get("tool_call"),
            files=result.get("files"),
            error=result.get("error"),
            conversation_id=request.conversation_id
        )

    except Exception as e:
        logger.error(f"[CHAT] Error processing message for {user.email}: {e}", exc_info=True)
        return ChatMessageResponse(
            error=str(e),
            conversation_id=request.conversation_id
        )


@router.post("/stream")
async def chat_stream(
    request: ChatMessageRequest,
    user: AuthUser = Depends(require_permission("sales:chat:use")),
):
    """
    Stream a chat response using Server-Sent Events.

    Returns real-time chunks as the LLM generates the response.
    Requires sales:chat:use permission.

    Optionally include file_ids from /api/files/upload to attach files.
    """
    logger.info(f"[CHAT] Stream from {user.email}: {request.message[:50]}... (files: {len(request.file_ids or [])})")

    from core.chat_api import get_web_adapter, stream_chat_message

    roles = await _get_user_profile(user)

    # Convert file_ids to file info dicts (using helper to avoid duplication)
    files = None
    if request.file_ids:
        web_adapter = get_web_adapter()
        file_infos = [
            _build_file_info(web_adapter.get_stored_file_info(fid), fid)
            for fid in request.file_ids
        ]
        files = [f for f in file_infos if f]

    async def event_generator():
        try:
            async for chunk in stream_chat_message(
                user_id=user.id,
                user_name=user.name or user.email,
                message=request.message,
                roles=roles,
                files=files,
                companies=user.companies,
                permissions=user.permissions,
            ):
                yield chunk
            logger.info(f"[CHAT] Stream completed for {user.email}")
        except Exception as e:
            logger.error(f"[CHAT] Stream error for {user.email}: {e}", exc_info=True)
            yield f"data: {{\"error\": \"{str(e)}\"}}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/conversations")
async def get_conversations(user: AuthUser = Depends(require_permission("sales:chat:use"))):
    """Get conversation history for the authenticated user. Requires sales:chat:use permission."""
    from core.chat_api import get_conversation_history

    history = get_conversation_history(user.id)
    return {"conversations": [{"id": user.id, "messages": history}]}


@router.post("/conversation")
async def create_conversation(user: AuthUser = Depends(require_permission("sales:chat:use"))):
    """Create a new conversation (clears existing history). Requires sales:chat:use permission."""
    from core.chat_api import clear_conversation, get_web_adapter

    clear_conversation(user.id)

    web_adapter = get_web_adapter()
    session = web_adapter.create_session(user.id, user.name or user.email)

    return {
        "conversation_id": session.conversation_id,
        "user_id": user.id
    }


@router.delete("/conversation/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    user: AuthUser = Depends(require_permission("sales:chat:use")),
):
    """Delete a conversation for the authenticated user. Requires sales:chat:use permission."""
    from core.chat_api import clear_conversation

    clear_conversation(user.id)
    return {"success": True, "conversation_id": conversation_id}


@router.get("/history")
async def get_chat_history(user: AuthUser = Depends(require_permission("sales:chat:use"))):
    """
    Load persisted chat history for the authenticated user.

    This endpoint loads chat messages from the database, which persist
    across server restarts. Use this on login to restore previous conversations.

    PERFORMANCE: This endpoint returns messages immediately WITHOUT refreshing
    attachment URLs. Use POST /attachments/refresh to lazy-load attachment URLs
    when they become visible in the viewport.

    Requires sales:chat:use permission.

    Returns:
        messages: List of message objects with role, content, timestamp
        session_id: The conversation session ID
        message_count: Total number of messages
        attachment_file_ids: List of file_ids for lazy-loading attachments
    """
    from db.database import db

    try:
        # Single database call - get full session (cached)
        session = db.get_chat_session(user.id)

        if not session:
            return {
                "messages": [],
                "session_id": None,
                "message_count": 0,
                "last_updated": None,
                "attachment_file_ids": [],
            }

        messages = session.get("messages", [])

        # Collect attachment file_ids for frontend lazy loading
        # NO URL REFRESH HERE - done via /attachments/refresh endpoint
        attachment_ids = []
        for msg in messages:
            for att in (msg.get("attachments") or msg.get("files") or []):
                if att.get("file_id"):
                    attachment_ids.append(att["file_id"])

        logger.info(f"[CHAT] Loaded {len(messages)} messages ({len(attachment_ids)} attachments) for {user.email}")

        return {
            "messages": messages,
            "session_id": session.get("session_id"),
            "message_count": len(messages),
            "last_updated": session.get("updated_at"),
            "attachment_file_ids": attachment_ids,
        }
    except Exception as e:
        logger.error(f"[CHAT] Error loading history for {user.email}: {e}", exc_info=True)
        return {
            "messages": [],
            "session_id": None,
            "message_count": 0,
            "error": str(e),
            "attachment_file_ids": [],
        }


@router.post("/attachments/refresh")
async def refresh_attachment_urls(
    request: AttachmentRefreshRequest,
    user: AuthUser = Depends(require_permission("sales:chat:use")),
):
    """
    Batch refresh signed URLs for chat attachments.

    This endpoint is called by the frontend when attachments become visible
    in the viewport. It supports pre-fetching: pass prefetch_ids to load
    the next batch of attachments ahead of time.

    Pre-fetch Strategy:
    - file_ids: Currently visible attachments (refresh NOW)
    - prefetch_ids: Next page of attachments (load ahead for smooth scrolling)

    Returns:
        urls: Dict mapping file_id -> signed_url (24h expiry)
    """
    from db.database import db
    from integrations.storage import get_storage_client

    # Combine visible + prefetch, deduplicate
    all_ids = list(set(request.file_ids + request.prefetch_ids))

    if not all_ids:
        return {"urls": {}}

    storage_client = get_storage_client()
    if not storage_client or storage_client.provider_name == "local":
        # Local storage doesn't need signed URLs
        return {"urls": {}}

    # 1. Single batch DB lookup (instead of N sequential calls)
    docs = db.get_documents_batch(all_ids)

    # 2. Parallel signed URL generation (instead of sequential)
    async def refresh_one(file_id: str) -> tuple[str, str | None]:
        doc = docs.get(file_id)
        if not doc or doc.get("storage_provider") != "supabase":
            return (file_id, None)
        try:
            url = await storage_client.get_signed_url(
                bucket=doc["storage_bucket"],
                key=doc["storage_key"],
                expires_in=86400,  # 24 hours
            )
            return (file_id, url)
        except Exception as e:
            logger.warning(f"[CHAT] Failed to refresh URL for {file_id}: {e}")
            return (file_id, None)

    tasks = [refresh_one(fid) for fid in all_ids]
    results = await asyncio.gather(*tasks)

    # Build response (only include successful refreshes)
    urls = {fid: url for fid, url in results if url}

    logger.info(f"[CHAT] Refreshed {len(urls)}/{len(all_ids)} attachment URLs for {user.email}")

    return {"urls": urls}
