"""
Chat Router for Video Critique.

Handles web chat endpoints for the unified-ui integration.
Mirrors the sales-module AI chat pattern.
"""

import asyncio
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import config
from core.llm import main_llm_loop, get_conversation_state, clear_conversation_state
from handlers.tool_router import ToolRouter
from integrations.channels import get_channel
from core.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class ChatRequest(BaseModel):
    """Chat message request."""
    message: str = Field(..., description="User message")
    session_id: str | None = Field(None, description="Session ID for conversation continuity")
    user_id: str | None = Field(None, description="User ID")


class ChatResponse(BaseModel):
    """Chat message response."""
    response: str = Field(..., description="Assistant response")
    session_id: str = Field(..., description="Session ID")
    timestamp: str = Field(..., description="Response timestamp")


class ChatSession(BaseModel):
    """Chat session info."""
    session_id: str
    created_at: str
    message_count: int


class ClearSessionResponse(BaseModel):
    """Clear session response."""
    success: bool
    message: str


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post("/message", response_model=ChatResponse)
async def send_message(request: ChatRequest):
    """
    Send a chat message and get a response.

    This is the main chat endpoint for the web interface.
    """
    # Generate or use existing session ID
    session_id = request.session_id or str(uuid.uuid4())
    user_id = request.user_id or session_id

    logger.info(f"[Chat] Message from {user_id}: {request.message[:50]}...")

    try:
        # Get web channel adapter
        channel = get_channel("web")

        # Create tool router
        tool_router = ToolRouter()

        # Process through LLM
        response = await main_llm_loop(
            channel_id=session_id,
            user_id=user_id,
            user_input=request.message,
            files=None,
            channel=None,  # Don't send messages through channel for web
            tool_router=tool_router,
        )

        return ChatResponse(
            response=response,
            session_id=session_id,
            timestamp=datetime.now(config.UAE_TZ).isoformat(),
        )

    except Exception as e:
        logger.error(f"[Chat] Error processing message: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/message/stream")
async def send_message_stream(request: ChatRequest):
    """
    Send a chat message and stream the response.

    Uses Server-Sent Events for streaming.
    """
    session_id = request.session_id or str(uuid.uuid4())
    user_id = request.user_id or session_id

    async def generate():
        try:
            # Get LLM client
            from integrations.llm import LLMClient, LLMMessage
            from core.llm import create_design_request_system_prompt, get_conversation_state
            from core.tools import get_tool_definitions

            state = get_conversation_state(user_id)

            # Build messages
            system_prompt = create_design_request_system_prompt("User")
            messages = [
                LLMMessage.system(system_prompt),
                *[LLMMessage(role=m["role"], content=m["content"]) for m in state.history],
                LLMMessage.user(request.message),
            ]

            # Get tool definitions
            tools = get_tool_definitions()

            # Stream completion
            client = LLMClient.from_config()

            async for event in client.stream_complete(
                messages=messages,
                tools=tools,
                tool_choice="auto",
                workflow="chat_stream",
                user_id=user_id,
            ):
                event_type = event.get("type", "")

                if event_type == "response.output_text.delta":
                    # Text delta
                    text = event.get("delta", "")
                    if text:
                        yield f"data: {{'type': 'delta', 'content': {repr(text)}}}\n\n"

                elif event_type == "response.output_text.done":
                    # Text complete
                    text = event.get("text", "")
                    yield f"data: {{'type': 'text_done', 'content': {repr(text)}}}\n\n"

                elif event_type == "response.function_call_arguments.done":
                    # Tool call
                    yield f"data: {{'type': 'tool_call', 'name': '{event.get('name')}'}}\n\n"

                elif event_type == "response.completed":
                    # Done
                    yield f"data: {{'type': 'done', 'session_id': '{session_id}'}}\n\n"

        except Exception as e:
            logger.error(f"[Chat] Stream error: {e}")
            yield f"data: {{'type': 'error', 'message': {repr(str(e))}}}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Session-ID": session_id,
        },
    )


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    session_id: str | None = None,
    user_id: str | None = None,
):
    """
    Upload a file for processing.

    Handles both images (design requests) and videos (for approval).
    """
    session_id = session_id or str(uuid.uuid4())
    user_id = user_id or session_id

    logger.info(f"[Chat] File upload from {user_id}: {file.filename}")

    try:
        # Read file content
        content = await file.read()
        content_type = file.content_type or ""

        # Determine file type
        if content_type.startswith("image/"):
            # Image - process as design request image
            # For now, return acknowledgment
            return {
                "success": True,
                "file_id": str(uuid.uuid4()),
                "filename": file.filename,
                "type": "image",
                "message": "Image received. Please provide any additional context.",
            }

        elif content_type.startswith("video/") or file.filename.lower().endswith(
            (".mp4", ".mov", ".avi", ".mkv", ".webm")
        ):
            # Video - process for approval workflow
            return {
                "success": True,
                "file_id": str(uuid.uuid4()),
                "filename": file.filename,
                "type": "video",
                "message": "Video received. Which task number is this for?",
            }

        else:
            return {
                "success": False,
                "error": f"Unsupported file type: {content_type}",
            }

    except Exception as e:
        logger.error(f"[Chat] Upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/session/{session_id}", response_model=ChatSession)
async def get_session(session_id: str):
    """
    Get chat session information.
    """
    state = get_conversation_state(session_id)

    return ChatSession(
        session_id=session_id,
        created_at=datetime.now(config.UAE_TZ).isoformat(),
        message_count=len(state.history),
    )


@router.delete("/session/{session_id}", response_model=ClearSessionResponse)
async def clear_session(session_id: str):
    """
    Clear a chat session and its history.
    """
    clear_conversation_state(session_id)

    return ClearSessionResponse(
        success=True,
        message=f"Session {session_id} cleared",
    )


@router.get("/sessions")
async def list_sessions():
    """
    List active chat sessions.

    For admin/debugging purposes.
    """
    from core.llm import _conversation_states

    sessions = []
    for session_id, state in _conversation_states.items():
        sessions.append({
            "session_id": session_id,
            "message_count": len(state.history),
            "has_pending_confirmation": state.pending_confirmation is not None,
            "has_pending_edit": state.pending_edit is not None,
            "has_pending_delete": state.pending_delete is not None,
        })

    return {
        "count": len(sessions),
        "sessions": sessions,
    }
