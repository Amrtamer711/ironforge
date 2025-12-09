"""
Unified UI chat endpoints.

All chat endpoints require authentication. User info is extracted from the
authenticated user token rather than being passed in the request body.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.auth import get_current_user, require_auth
from integrations.auth import AuthUser
from integrations.rbac import get_rbac_client
from utils.logging import get_logger

logger = get_logger("api.chat")

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatMessageRequest(BaseModel):
    """Request model for chat messages."""
    message: str
    conversation_id: Optional[str] = None


class ChatMessageResponse(BaseModel):
    """Response model for chat messages."""
    content: Optional[str] = None
    tool_call: Optional[dict] = None
    files: Optional[List[dict]] = None
    error: Optional[str] = None
    conversation_id: Optional[str] = None


async def _get_user_profile(user: AuthUser) -> List[str]:
    """Get profile name for a user from RBAC."""
    try:
        rbac = get_rbac_client()
        profile = await rbac.get_user_profile(user.id)
        profile_name = profile.name if profile else user.metadata.get("role", "sales_user")
        logger.debug(f"[CHAT] Got profile for {user.email}: {profile_name}")
        # Return as list for backwards compatibility with chat system
        return [profile_name]
    except Exception as e:
        logger.warning(f"[CHAT] Failed to get profile for {user.email}: {e}, using default")
        return [user.metadata.get("role", "sales_user")]


@router.post("/message", response_model=ChatMessageResponse)
async def chat_message(
    request: ChatMessageRequest,
    user: AuthUser = Depends(require_auth),
):
    """
    Send a chat message and receive a response.

    This endpoint connects the Unified UI to the same LLM infrastructure
    used by the Slack bot. Requires authentication.
    """
    logger.info(f"[CHAT] Message from {user.email}: {request.message[:50]}...")

    from core.chat_api import process_chat_message

    try:
        roles = await _get_user_profile(user)

        result = await process_chat_message(
            user_id=user.id,
            user_name=user.name or user.email,
            message=request.message,
            roles=roles
        )

        logger.info(f"[CHAT] Response generated for {user.email}, has_content={bool(result.get('content'))}")
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
    user: AuthUser = Depends(require_auth),
):
    """
    Stream a chat response using Server-Sent Events.

    Returns real-time chunks as the LLM generates the response.
    Requires authentication.
    """
    logger.info(f"[CHAT] === STREAM ENDPOINT HIT ===")
    logger.info(f"[CHAT] User: {user.email}, ID: {user.id}")
    logger.info(f"[CHAT] Message: {request.message[:100]}...")

    from core.chat_api import stream_chat_message

    logger.info(f"[CHAT] Getting user profile...")
    roles = await _get_user_profile(user)
    logger.info(f"[CHAT] Roles: {roles}")

    async def event_generator():
        try:
            logger.info(f"[CHAT] Starting stream_chat_message...")
            chunk_count = 0
            async for chunk in stream_chat_message(
                user_id=user.id,
                user_name=user.name or user.email,
                message=request.message,
                roles=roles
            ):
                chunk_count += 1
                if chunk_count <= 3:
                    logger.info(f"[CHAT] Chunk {chunk_count}: {chunk[:100]}...")
                yield chunk
            logger.info(f"[CHAT] Stream completed for {user.email}, {chunk_count} chunks sent")
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
async def get_conversations(user: AuthUser = Depends(require_auth)):
    """Get conversation history for the authenticated user."""
    logger.info(f"[CHAT] Get conversations for {user.email}")

    from core.chat_api import get_conversation_history

    history = get_conversation_history(user.id)
    logger.debug(f"[CHAT] Found {len(history)} messages for {user.email}")
    return {"conversations": [{"id": user.id, "messages": history}]}


@router.post("/conversation")
async def create_conversation(user: AuthUser = Depends(require_auth)):
    """Create a new conversation (clears existing history)."""
    logger.info(f"[CHAT] Creating new conversation for {user.email}")

    from core.chat_api import clear_conversation, get_web_adapter

    # Clear existing conversation
    clear_conversation(user.id)

    # Create new session
    web_adapter = get_web_adapter()
    session = web_adapter.create_session(user.id, user.name or user.email)

    logger.info(f"[CHAT] New conversation created for {user.email}: {session.conversation_id}")
    return {
        "conversation_id": session.conversation_id,
        "user_id": user.id
    }


@router.delete("/conversation/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    user: AuthUser = Depends(require_auth),
):
    """Delete a conversation for the authenticated user."""
    logger.info(f"[CHAT] Deleting conversation {conversation_id} for {user.email}")

    from core.chat_api import clear_conversation

    clear_conversation(user.id)
    logger.info(f"[CHAT] Conversation deleted for {user.email}")
    return {"success": True, "conversation_id": conversation_id}
