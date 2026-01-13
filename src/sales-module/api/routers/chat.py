"""
Unified UI chat endpoints.

All chat endpoints require authentication. User info is extracted from the
authenticated user token rather than being passed in the request body.
"""

import asyncio
import io
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
        if len(v) > 500:
            raise ValueError("Maximum 500 file_ids per request")
        return v

    @field_validator("prefetch_ids")
    @classmethod
    def validate_prefetch_ids(cls, v: list[str]) -> list[str]:
        """Validate prefetch_ids list."""
        if len(v) > 200:
            raise ValueError("Maximum 200 prefetch_ids per request")
        return v


def _build_file_info(stored_info: Any, file_id: str) -> dict | None:
    """Build file info dict from stored info. Extracted helper to avoid duplication."""
    if not stored_info:
        return None
    # Use module-specific URL path for proper proxy routing
    url = f"/api/sales/files/{file_id}/{stored_info.filename}" if stored_info.filename else f"/api/sales/files/{file_id}/file"
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
async def get_chat_history(
    user: AuthUser = Depends(require_permission("sales:chat:use")),
    limit: int | None = None,
    offset: int = 0,
    newest_first: bool = False,
):
    """
    Load persisted chat history for the authenticated user.

    This endpoint loads chat messages from the database, which persist
    across server restarts. Use this on login to restore previous conversations.

    Messages include attachment metadata with dimensions for placeholder sizing.
    URLs are NOT included for fast response - use /attachments/refresh to get
    signed URLs for visible images (lazy loading).

    Requires sales:chat:use permission.

    Args:
        limit: Maximum number of messages to return (None = all messages)
        offset: Number of messages to skip (from start if newest_first=False, from end if newest_first=True)
        newest_first: If True, return newest messages first (for infinite scroll)
                      offset=0 returns last `limit` messages
                      offset=50 returns messages before the last 50

    Returns:
        messages: List of message objects with role, content, timestamp, enriched attachments
        session_id: The conversation session ID
        message_count: Total number of messages (before pagination)
        has_more: Whether there are more messages to load
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
                "has_more": False,
                "last_updated": None,
            }

        all_messages = session.get("messages", [])
        # Filter out any None/null messages (defensive against corrupted data)
        all_messages = [m for m in all_messages if m is not None]
        total_count = len(all_messages)

        # Apply pagination if limit is specified
        if limit is not None:
            if newest_first:
                # For infinite scroll: offset from end, return in chronological order
                # offset=0, limit=50 → last 50 messages (index [total-50:total])
                # offset=50, limit=50 → previous 50 messages (index [total-100:total-50])
                end_idx = total_count - offset
                start_idx = max(0, end_idx - limit)
                messages = all_messages[start_idx:end_idx]
                has_more = start_idx > 0
            else:
                # Original behavior: offset from start
                messages = all_messages[offset:offset + limit]
                has_more = (offset + limit) < total_count
        else:
            messages = all_messages[offset:] if offset > 0 else all_messages
            has_more = False

        # Collect all attachment file_ids for dimension enrichment (no URL generation)
        # URLs are loaded lazily via /attachments/refresh for faster initial load
        attachment_ids = [
            att["file_id"]
            for msg in messages
            if msg is not None
            for att in (msg.get("attachments") or msg.get("files") or [])
            if att and att.get("file_id")
        ]

        # Only fetch dimensions from DB - skip URL generation for fast response
        # Frontend will call /attachments/refresh to get URLs for visible images
        dimension_cache = {}
        if attachment_ids:
            docs = db.get_documents_batch(attachment_ids)
            for file_id, doc in docs.items():
                if doc:
                    dimension_cache[file_id] = {
                        "width": doc.get("image_width"),
                        "height": doc.get("image_height"),
                    }

        # Enrich messages with dimensions only (URLs loaded lazily by frontend)
        enriched_messages = []
        for msg in messages:
            if msg is None:
                continue
            msg_copy = dict(msg)
            attachments = msg_copy.get("attachments") or msg_copy.get("files") or []
            enriched_attachments = []
            for att in attachments:
                if not att:
                    continue
                att_copy = dict(att)
                file_id = att.get("file_id")
                if file_id and file_id in dimension_cache:
                    dim_data = dimension_cache[file_id]
                    att_copy["width"] = dim_data.get("width")
                    att_copy["height"] = dim_data.get("height")
                enriched_attachments.append(att_copy)
            # Use consistent key name
            msg_copy["files"] = enriched_attachments
            if "attachments" in msg_copy:
                del msg_copy["attachments"]
            enriched_messages.append(msg_copy)

        logger.info(f"[CHAT] Loaded {len(enriched_messages)}/{total_count} messages ({len(attachment_ids)} attachments) for {user.email}")

        return {
            "messages": enriched_messages,
            "session_id": session.get("session_id"),
            "message_count": total_count,
            "has_more": has_more,
            "last_updated": session.get("updated_at"),
        }
    except Exception as e:
        logger.error(f"[CHAT] Error loading history for {user.email}: {e}", exc_info=True)
        return {
            "messages": [],
            "session_id": None,
            "message_count": 0,
            "has_more": False,
            "error": str(e),
        }


@router.get("/resume/{request_id}")
async def resume_stream(
    request_id: str,
    event_index: int = 0,
    user: AuthUser = Depends(require_permission("sales:chat:use")),
):
    """
    Resume streaming from a previous request after page refresh.

    This endpoint allows the frontend to reconnect to an in-progress or
    recently completed request and receive any events that occurred since
    the last seen event.

    Args:
        request_id: The unique request ID from the original /stream call
        event_index: The index of the last event processed (resume from here)

    Returns:
        If request completed: {"status": "completed", "events": [...]}
        If request still running: SSE stream of remaining events
        If request not found: {"status": "not_found"}
        If request expired: {"status": "expired"}
    """
    from core.chat_api import get_web_adapter

    logger.info(f"[CHAT] Resume request {request_id[:8]}... from index {event_index} for {user.email}")

    web_adapter = get_web_adapter()
    session = web_adapter.get_session(user.id)

    if not session:
        logger.info(f"[CHAT] No session found for {user.email}")
        return {"status": "not_found", "message": "No active session"}

    # Check if this request_id exists in the session
    if request_id not in session.active_requests:
        logger.info(f"[CHAT] Request {request_id[:8]}... not found in session for {user.email}")
        return {"status": "not_found", "message": "Request not found or expired"}

    is_active = session.active_requests.get(request_id, False)

    # Collect events for this request starting from the given index
    all_events = list(session.events)  # Convert deque to list for indexing
    request_events = []
    event_count = 0

    for event in all_events:
        # Only include events for this specific request
        if event.get("request_id") == request_id:
            if event_count >= event_index:
                request_events.append(event)
            event_count += 1

    logger.info(f"[CHAT] Found {len(request_events)} events (from index {event_index}) for request {request_id[:8]}...")

    if not is_active:
        # Request completed - return all buffered events
        logger.info(f"[CHAT] Request {request_id[:8]}... completed, returning {len(request_events)} events")
        return {
            "status": "completed",
            "events": request_events,
            "total_events": event_count,
        }
    else:
        # Request still running - stream remaining events
        logger.info(f"[CHAT] Request {request_id[:8]}... still active, streaming events")

        async def resume_event_generator():
            """Stream events for the resumed request."""
            import json
            local_event_index = event_index

            # First, yield any events we already have
            for event in request_events:
                event_type = event.get("type")
                yield _format_event_for_sse(event)

            # Then continue polling for new events
            poll_interval = 0.02  # 20ms

            while True:
                # Check if request is still active
                if not session.active_requests.get(request_id, False):
                    # Request completed while we were streaming
                    break

                # Check for new events
                all_events_now = list(session.events)
                new_events = []
                current_count = 0

                for event in all_events_now:
                    if event.get("request_id") == request_id:
                        if current_count >= local_event_index + len(request_events):
                            new_events.append(event)
                        current_count += 1

                for event in new_events:
                    yield _format_event_for_sse(event)
                    local_event_index += 1

                await asyncio.sleep(poll_interval)

            yield "data: [DONE]\n\n"

        return StreamingResponse(
            resume_event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )


def _format_event_for_sse(event: dict) -> str:
    """Format an event dict for SSE transmission."""
    import json

    event_type = event.get("type")

    if event_type == "status":
        return f"data: {json.dumps({'type': 'status', 'message_id': event.get('message_id'), 'parent_id': event.get('parent_id'), 'content': event.get('content')})}\n\n"
    elif event_type == "message":
        return f"data: {json.dumps({'type': 'content', 'content': event.get('content', ''), 'message_id': event.get('message_id'), 'parent_id': event.get('parent_id')})}\n\n"
    elif event_type == "file":
        return f"data: {json.dumps({'type': 'file', 'parent_id': event.get('parent_id'), 'file': {'file_id': event.get('file_id'), 'url': event.get('url'), 'filename': event.get('filename'), 'title': event.get('title'), 'comment': event.get('comment')}})}\n\n"
    elif event_type == "delete":
        return f"data: {json.dumps({'type': 'delete', 'message_id': event.get('message_id')})}\n\n"
    elif event_type == "error":
        return f"data: {json.dumps({'type': 'error', 'error': event.get('error')})}\n\n"
    elif event_type == "stream_delta":
        return f"data: {json.dumps({'type': 'chunk', 'content': event.get('delta', ''), 'message_id': event.get('message_id'), 'parent_id': event.get('parent_id')})}\n\n"
    elif event_type == "stream_complete":
        return f"data: {json.dumps({'type': 'stream_complete', 'message_id': event.get('message_id'), 'parent_id': event.get('parent_id'), 'content': event.get('content', '')})}\n\n"
    else:
        return f"data: {json.dumps(event)}\n\n"


@router.post("/attachments/refresh")
async def refresh_attachment_urls(
    request: AttachmentRefreshRequest,
    user: AuthUser = Depends(require_permission("sales:chat:use")),
):
    """
    Batch refresh signed URLs for chat attachments.

    This endpoint is called by the frontend when attachments become visible.
    Returns full-quality signed URLs for all requested files.

    Pre-fetch Strategy:
    - file_ids: Currently visible attachments (refresh NOW)
    - prefetch_ids: Next page of attachments (load ahead for smooth scrolling)

    Returns:
        urls: Dict mapping file_id -> {full, width, height} (24h expiry)
    """
    from db.database import db
    from integrations.storage import get_storage_client

    # Combine visible + prefetch, deduplicate
    all_ids = list(set(request.file_ids + request.prefetch_ids))

    if not all_ids:
        return {"urls": {}}

    storage_client = get_storage_client()
    if not storage_client or storage_client.provider_name == "local":
        return {"urls": {}}

    # Single batch DB lookup
    docs = db.get_documents_batch(all_ids)

    # Collect storage keys for batch URL generation
    uploads_keys: dict[str, str] = {}  # storage_key -> file_id
    file_metadata: dict[str, dict] = {}  # file_id -> metadata

    for file_id in all_ids:
        doc = docs.get(file_id)
        if not doc or doc.get("storage_provider") != "supabase":
            continue

        bucket = doc.get("storage_bucket")
        key = doc.get("storage_key")
        if not bucket or not key:
            continue

        # Track for batch URL generation (most files are in "uploads" bucket)
        if bucket == "uploads":
            uploads_keys[key] = file_id

        file_metadata[file_id] = {
            "bucket": bucket,
            "key": key,
            "width": doc.get("image_width"),
            "height": doc.get("image_height"),
        }

    # Batch generate full URLs (ONE API call for all uploads)
    full_url_map: dict[str, str] = {}
    if uploads_keys:
        batch_urls = await storage_client.get_signed_urls_batch(
            bucket="uploads",
            keys=list(uploads_keys.keys()),
            expires_in=86400
        )
        for key, url in batch_urls.items():
            file_id = uploads_keys.get(key)
            if file_id and url:
                full_url_map[file_id] = url

    logger.info(f"[CHAT] Batch URLs: {len(full_url_map)} full URLs generated")

    # Build response
    urls = {}
    for file_id in all_ids:
        meta = file_metadata.get(file_id)
        if not meta:
            continue

        full_url = full_url_map.get(file_id)
        if not full_url:
            continue

        urls[file_id] = {
            "full": full_url,
            "width": meta.get("width"),
            "height": meta.get("height"),
        }

    logger.info(f"[CHAT] Refreshed {len(urls)}/{len(all_ids)} attachment URLs for {user.email}")

    return {"urls": urls}
