"""
Generalized Chat API for the Unified UI.

This module provides a chat interface that uses the SAME LLM infrastructure
and tool execution as the Slack bot, ensuring feature parity across channels.

Key principle: ALL functionality is channel-agnostic. The web UI gets
exactly the same capabilities as Slack by using the same main_llm_loop.
"""

import json
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, List, AsyncGenerator

import config
from db.cache import user_history
from core.chat_persistence import save_chat_messages, load_chat_messages, clear_chat_messages
from integrations.channels import WebAdapter

logger = config.logger

# Global WebAdapter instance for the unified UI
_web_adapter: Optional[WebAdapter] = None


def get_web_adapter() -> WebAdapter:
    """Get or create the global WebAdapter instance."""
    global _web_adapter
    if _web_adapter is None:
        _web_adapter = WebAdapter(file_base_url="/api/files")
    return _web_adapter


def _ensure_web_adapter_registered():
    """Ensure the WebAdapter is registered as the channel adapter for web requests."""
    web_adapter = get_web_adapter()
    # Register the web adapter in config so main_llm_loop uses it
    config.set_channel_adapter(web_adapter)
    return web_adapter


async def process_chat_message(
    user_id: str,
    user_name: str,
    message: str,
    roles: Optional[List[str]] = None,
    files: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Process a chat message from the unified UI.

    Uses the SAME main_llm_loop as Slack to ensure feature parity.
    All tools (mockups, proposals, booking orders, etc.) work identically.

    Args:
        user_id: Unique user identifier
        user_name: Display name for the user
        message: User's message text
        roles: User's roles (for permission checks)
        files: Optional list of file info dicts (for uploads)

    Returns:
        Dict containing response data:
        {
            "content": str,
            "files": Optional[list],
            "error": Optional[str]
        }
    """
    from core.llm import main_llm_loop

    roles = roles or []
    web_adapter = _ensure_web_adapter_registered()

    # Get or create session
    session = web_adapter.get_or_create_session(user_id, user_name, roles=roles)

    # Load persisted history if session is new (no messages yet)
    if not session.messages:
        try:
            persisted_messages = load_chat_messages(user_id)
            if persisted_messages:
                session.messages = persisted_messages
                logger.info(f"[WebChat] Loaded {len(persisted_messages)} persisted messages for {user_id}")
        except Exception as e:
            logger.warning(f"[WebChat] Failed to load persisted messages: {e}")

    # Add user message to session history
    user_msg = {
        "id": f"user-{datetime.now().timestamp()}",
        "role": "user",
        "content": message,
        "timestamp": datetime.now().isoformat()
    }
    if files:
        user_msg["files"] = [
            {
                "file_id": f.get("file_id"),
                "filename": f.get("filename"),
                "url": f.get("url"),
                "mimetype": f.get("mimetype"),
            }
            for f in files
        ]
    session.messages.append(user_msg)

    # Check if user has admin permissions using RBAC
    from integrations.rbac import has_permission
    is_admin = await has_permission(user_id, "core:*:*")

    # Build channel_event in the same format as Slack events
    # This allows main_llm_loop to process files, etc.
    channel_event = {
        "type": "message",
        "user": user_id,
        "channel": user_id,  # For web, channel == user_id
    }

    # Add files in a format compatible with the channel adapter
    if files:
        channel_event["files"] = []
        for f in files:
            file_info = {
                "name": f.get("filename", ""),
                "filetype": _get_filetype_from_mimetype(f.get("mimetype", "")),
                "mimetype": f.get("mimetype", ""),
                "file_id": f.get("file_id"),
                "temp_path": f.get("temp_path"),  # Web uploads have temp_path
            }
            channel_event["files"].append(file_info)

    # Get message count before processing
    messages_before = len(session.messages)

    try:
        logger.info(f"[WebChat] Calling main_llm_loop for user={user_id}, admin={is_admin}")

        # Call the SAME main_llm_loop as Slack
        # The channel adapter abstraction handles all the differences
        await main_llm_loop(
            channel=user_id,  # For web, channel is user_id
            user_id=user_id,
            user_input=message,
            channel_event=channel_event if files else None,
            is_admin_override=is_admin,
        )

        logger.info(f"[WebChat] main_llm_loop completed for user={user_id}")

        # Get the new messages added by main_llm_loop
        new_messages = session.messages[messages_before:]

        # Build response from new messages
        result = {
            "content": None,
            "files": [],
            "error": None
        }

        for msg in new_messages:
            if msg.get("role") == "assistant":
                # Concatenate content from all assistant messages
                content = msg.get("content", "")
                if content:
                    if result["content"]:
                        result["content"] += "\n\n" + content
                    else:
                        result["content"] = content

                # Collect files/attachments
                attachments = msg.get("attachments", [])
                for att in attachments:
                    result["files"].append({
                        "url": att.get("url"),
                        "filename": att.get("filename"),
                        "title": att.get("title"),
                    })

        # Persist messages to database
        try:
            save_chat_messages(user_id, session.messages, session.conversation_id)
        except Exception as persist_err:
            logger.warning(f"[WebChat] Failed to persist messages: {persist_err}")

        return result

    except Exception as e:
        logger.error(f"[WebChat] Error processing message: {e}", exc_info=True)
        return {
            "content": None,
            "files": [],
            "error": str(e)
        }


async def stream_chat_message(
    user_id: str,
    user_name: str,
    message: str,
    roles: Optional[List[str]] = None,
    files: Optional[List[Dict[str, Any]]] = None
) -> AsyncGenerator[str, None]:
    """
    Stream a chat response using Server-Sent Events format.

    Streams events in REAL-TIME as main_llm_loop executes, including:
    - Status updates (tool execution progress)
    - File uploads
    - Message content
    - Delete events (ephemeral status cleanup)

    This gives the web UI the same real-time experience as Slack.
    """
    from core.llm import main_llm_loop

    logger.info(f"[WebChat] stream_chat_message called for user={user_id}")

    roles = roles or []
    web_adapter = _ensure_web_adapter_registered()

    # Get or create session
    session = web_adapter.get_or_create_session(user_id, user_name, roles=roles)

    # Load persisted history if session is new
    if not session.messages:
        try:
            persisted_messages = load_chat_messages(user_id)
            if persisted_messages:
                session.messages = persisted_messages
                logger.info(f"[WebChat] Loaded {len(persisted_messages)} persisted messages for {user_id}")
        except Exception as e:
            logger.warning(f"[WebChat] Failed to load persisted messages: {e}")

    # Add user message to session history
    user_msg = {
        "id": f"user-{datetime.now().timestamp()}",
        "role": "user",
        "content": message,
        "timestamp": datetime.now().isoformat()
    }
    if files:
        user_msg["files"] = [
            {
                "file_id": f.get("file_id"),
                "filename": f.get("filename"),
                "url": f.get("url"),
                "mimetype": f.get("mimetype"),
            }
            for f in files
        ]
    session.messages.append(user_msg)

    # Clear any stale events and reset processing flag
    session.events.clear()
    session.processing_complete = False

    # Check if user has admin permissions using RBAC
    from integrations.rbac import has_permission
    is_admin = await has_permission(user_id, "core:*:*")

    # Build channel_event
    channel_event = {
        "type": "message",
        "user": user_id,
        "channel": user_id,
    }

    if files:
        channel_event["files"] = []
        for f in files:
            file_info = {
                "name": f.get("filename", ""),
                "filetype": _get_filetype_from_mimetype(f.get("mimetype", "")),
                "mimetype": f.get("mimetype", ""),
                "file_id": f.get("file_id"),
                "temp_path": f.get("temp_path"),
            }
            channel_event["files"].append(file_info)

    # Track messages before processing
    messages_before = len(session.messages)

    async def run_llm():
        """Run main_llm_loop in background and mark complete when done."""
        try:
            await main_llm_loop(
                channel=user_id,
                user_id=user_id,
                user_input=message,
                channel_event=channel_event if files else None,
                is_admin_override=is_admin,
            )
        except Exception as e:
            logger.error(f"[WebChat] main_llm_loop error: {e}", exc_info=True)
            session.events.append({
                "type": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            })
        finally:
            session.processing_complete = True

    # Start LLM processing in background
    llm_task = asyncio.create_task(run_llm())

    try:
        # Send initial processing indicator
        yield f"data: {json.dumps({'type': 'status', 'content': 'Processing...'})}\n\n"

        event_index = 0
        poll_interval = 0.1  # 100ms polling

        # Stream events as they arrive
        while not session.processing_complete or event_index < len(session.events):
            # Process any new events
            while event_index < len(session.events):
                event = session.events[event_index]
                event_index += 1

                event_type = event.get("type")

                if event_type == "status":
                    # Status update (tool progress, etc.)
                    yield f"data: {json.dumps({'type': 'status', 'message_id': event.get('message_id'), 'content': event.get('content')})}\n\n"

                elif event_type == "message":
                    # New message from assistant
                    content = event.get("content", "")
                    if content:
                        # Stream word by word for typing effect
                        words = content.split(' ')
                        for i, word in enumerate(words):
                            chunk = word + (' ' if i < len(words) - 1 else '')
                            yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"
                            await asyncio.sleep(0.02)

                elif event_type == "file":
                    # File uploaded
                    yield f"data: {json.dumps({'type': 'file', 'file': {'file_id': event.get('file_id'), 'url': event.get('url'), 'filename': event.get('filename'), 'title': event.get('title'), 'comment': event.get('comment')}})}\n\n"

                elif event_type == "delete":
                    # Status message deleted (tool completed successfully)
                    yield f"data: {json.dumps({'type': 'delete', 'message_id': event.get('message_id')})}\n\n"

                elif event_type == "error":
                    # Error occurred
                    yield f"data: {json.dumps({'type': 'error', 'error': event.get('error')})}\n\n"

            # Wait before polling again (only if not complete)
            if not session.processing_complete:
                await asyncio.sleep(poll_interval)

        # Ensure task is done
        await llm_task

        # Persist messages
        try:
            save_chat_messages(user_id, session.messages, session.conversation_id)
        except Exception as persist_err:
            logger.warning(f"[WebChat] Failed to persist messages: {persist_err}")

        yield "data: [DONE]\n\n"

    except Exception as e:
        logger.error(f"[WebChat] Streaming error: {e}", exc_info=True)
        yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
        yield "data: [DONE]\n\n"
    finally:
        # Clean up events
        session.events.clear()
        session.processing_complete = False


def _get_filetype_from_mimetype(mimetype: str) -> str:
    """Extract file type from MIME type."""
    mime_to_type = {
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/png": "png",
        "image/gif": "gif",
        "image/bmp": "bmp",
        "application/pdf": "pdf",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
        "application/vnd.ms-excel": "xls",
        "text/csv": "csv",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
        "application/msword": "doc",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
        "application/vnd.ms-powerpoint": "ppt",
    }
    return mime_to_type.get(mimetype, "")


def get_conversation_history(user_id: str) -> List[Dict[str, Any]]:
    """Get conversation history for a user."""
    web_adapter = get_web_adapter()
    return web_adapter.get_conversation_history(user_id)


def clear_conversation(user_id: str) -> None:
    """Clear conversation history for a user."""
    web_adapter = get_web_adapter()
    web_adapter.clear_session(user_id)

    # Also clear from user_history cache
    if user_id in user_history:
        del user_history[user_id]

    # Clear from database
    try:
        clear_chat_messages(user_id)
    except Exception as e:
        logger.warning(f"[WebChat] Failed to clear persisted messages for {user_id}: {e}")
