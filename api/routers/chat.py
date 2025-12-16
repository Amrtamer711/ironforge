"""
Unified UI chat endpoints.

All chat endpoints require authentication. User info is extracted from the
authenticated user token rather than being passed in the request body.
"""

from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from api.auth import require_permission
from integrations.auth import AuthUser
from integrations.rbac import get_rbac_client
from utils.logging import get_logger

logger = get_logger("api.chat")

router = APIRouter(prefix="/api/chat", tags=["chat"])

# Security limits
MAX_MESSAGE_LENGTH = 10_000  # 10k characters max per message


class ChatMessageRequest(BaseModel):
    """Request model for chat messages."""
    message: str
    conversation_id: Optional[str] = None
    file_ids: Optional[list[str]] = None  # IDs from /api/files/upload

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
    def validate_file_ids(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        """Validate file_ids list."""
        if v is not None and len(v) > 10:
            raise ValueError("Maximum 10 files per message")
        return v


class ChatMessageResponse(BaseModel):
    """Response model for chat messages."""
    content: Optional[str] = None
    tool_call: Optional[dict] = None
    files: Optional[list[dict]] = None
    error: Optional[str] = None
    conversation_id: Optional[str] = None


async def _get_user_profile(user: AuthUser) -> list[str]:
    """Get profile name for a user from RBAC."""
    try:
        rbac = get_rbac_client()
        profile = await rbac.get_user_profile(user.id)
        profile_name = profile.name if profile else user.metadata.get("role", "sales_user")
        return [profile_name]
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
            files = []
            for file_id in request.file_ids:
                stored_info = web_adapter.get_stored_file_info(file_id)
                if stored_info:
                    # Include URL for persistence
                    url = f"/api/files/{file_id}/{stored_info.filename}" if stored_info.filename else f"/api/files/{file_id}/file"
                    files.append({
                        "file_id": file_id,
                        "filename": stored_info.filename,
                        "mimetype": stored_info.content_type,
                        "size": stored_info.size,
                        "url": url,
                    })
                else:
                    logger.warning(f"[CHAT] File not found: {file_id}")

        result = await process_chat_message(
            user_id=user.id,
            user_name=user.name or user.email,
            message=request.message,
            roles=roles,
            files=files,
            companies=user.companies,
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

    # Convert file_ids to file info dicts
    files = None
    if request.file_ids:
        web_adapter = get_web_adapter()
        files = []
        for file_id in request.file_ids:
            stored_info = web_adapter.get_stored_file_info(file_id)
            if stored_info:
                # Include URL for persistence
                url = f"/api/files/{file_id}/{stored_info.filename}" if stored_info.filename else f"/api/files/{file_id}/file"
                files.append({
                    "file_id": file_id,
                    "filename": stored_info.filename,
                    "mimetype": stored_info.content_type,
                    "size": stored_info.size,
                    "url": url,
                })

    async def event_generator():
        try:
            async for chunk in stream_chat_message(
                user_id=user.id,
                user_name=user.name or user.email,
                message=request.message,
                roles=roles,
                files=files,
                companies=user.companies,
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

    Requires sales:chat:use permission.

    Returns:
        messages: List of message objects with role, content, timestamp
        session_id: The conversation session ID
        message_count: Total number of messages
    """
    from core.chat_persistence import get_chat_session_info, load_chat_messages

    try:
        messages = load_chat_messages(user.id)
        session_info = get_chat_session_info(user.id)

        # Refresh signed URLs for attachments (they expire after 24h)
        messages = await _refresh_attachment_urls(messages)

        logger.info(f"[CHAT] Loaded {len(messages)} persisted messages for {user.email}")

        return {
            "messages": messages,
            "session_id": session_info.get("session_id") if session_info else None,
            "message_count": len(messages),
            "last_updated": session_info.get("updated_at") if session_info else None,
        }
    except Exception as e:
        logger.error(f"[CHAT] Error loading history for {user.email}: {e}", exc_info=True)
        return {
            "messages": [],
            "session_id": None,
            "message_count": 0,
            "error": str(e)
        }


async def _refresh_attachment_urls(messages: list) -> list:
    """
    Refresh signed URLs for attachments that may have expired.

    Looks up file storage info from the database and generates fresh signed URLs.
    """
    from db.database import db
    from integrations.storage import get_storage_client

    storage_client = get_storage_client()
    if not storage_client or storage_client.provider_name == "local":
        return messages  # No refresh needed for local storage

    for msg in messages:
        attachments = msg.get("attachments") or msg.get("files") or []
        for attachment in attachments:
            file_id = attachment.get("file_id")
            if not file_id:
                continue

            # Look up file storage info from database
            try:
                doc = db.get_document(file_id)
                if doc and doc.get("storage_provider") == "supabase":
                    # Generate fresh signed URL
                    signed_url = await storage_client.get_signed_url(
                        bucket=doc["storage_bucket"],
                        key=doc["storage_key"],
                        expires_in=86400,  # 24 hours
                    )
                    if signed_url:
                        attachment["url"] = signed_url
            except Exception as e:
                logger.warning(f"[CHAT] Failed to refresh URL for file {file_id}: {e}")
                continue

    return messages
