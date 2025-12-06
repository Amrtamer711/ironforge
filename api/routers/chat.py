"""
Unified UI chat endpoints.

All chat endpoints require authentication. User info is extracted from the
authenticated user token rather than being passed in the request body.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import config
from api.auth import get_current_user, require_auth
from integrations.auth import AuthUser
from integrations.rbac import get_rbac_client

logger = config.logger

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


async def _get_user_roles(user: AuthUser) -> List[str]:
    """Get role names for a user from RBAC."""
    try:
        rbac = get_rbac_client()
        roles = await rbac.get_user_roles(user.id)
        return [r.name for r in roles] or [user.metadata.get("role", "sales_person")]
    except Exception:
        return [user.metadata.get("role", "sales_person")]


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
    from core.chat_api import process_chat_message

    try:
        roles = await _get_user_roles(user)

        result = await process_chat_message(
            user_id=user.id,
            user_name=user.name or user.email,
            message=request.message,
            roles=roles
        )

        return ChatMessageResponse(
            content=result.get("content"),
            tool_call=result.get("tool_call"),
            files=result.get("files"),
            error=result.get("error"),
            conversation_id=request.conversation_id
        )

    except Exception as e:
        logger.error(f"[CHAT API] Error processing message: {e}", exc_info=True)
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
    from core.chat_api import stream_chat_message

    roles = await _get_user_roles(user)

    async def event_generator():
        async for chunk in stream_chat_message(
            user_id=user.id,
            user_name=user.name or user.email,
            message=request.message,
            roles=roles
        ):
            yield chunk

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
    from core.chat_api import get_conversation_history

    history = get_conversation_history(user.id)
    return {"conversations": [{"id": user.id, "messages": history}]}


@router.post("/conversation")
async def create_conversation(user: AuthUser = Depends(require_auth)):
    """Create a new conversation (clears existing history)."""
    from core.chat_api import clear_conversation, get_web_adapter

    # Clear existing conversation
    clear_conversation(user.id)

    # Create new session
    web_adapter = get_web_adapter()
    session = web_adapter.create_session(user.id, user.name or user.email)

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
    from core.chat_api import clear_conversation

    clear_conversation(user.id)
    return {"success": True, "conversation_id": conversation_id}
