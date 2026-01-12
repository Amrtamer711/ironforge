"""
Generalized Chat API for the Unified UI.

This module provides a chat interface that uses the SAME LLM infrastructure
and tool execution as the Slack bot, ensuring feature parity across channels.

Key principle: ALL functionality is channel-agnostic. The web UI gets
exactly the same capabilities as Slack by using the same main_llm_loop.
"""

import asyncio
import json
import threading
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

import config
from core.chat_persistence import append_chat_messages, clear_chat_messages, save_chat_messages
from core.llm import main_llm_loop
from crm_security import has_permission
from db.cache import user_history
from integrations.channels import WebAdapter
from integrations.channels.adapters.web import current_parent_message_id, current_request_id

logger = config.logger

# Global WebAdapter instance for the unified UI (thread-safe initialization)
_web_adapter: WebAdapter | None = None
_web_adapter_lock = threading.Lock()


def get_web_adapter() -> WebAdapter:
    """
    Get or create the global WebAdapter instance.

    Uses double-checked locking for thread-safe initialization.
    """
    global _web_adapter
    if _web_adapter is None:
        with _web_adapter_lock:
            # Double-check after acquiring lock
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
    roles: list[str] | None = None,
    files: list[dict[str, Any]] | None = None,
    companies: list[str] | None = None,
    permissions: list[str] | None = None,
) -> dict[str, Any]:
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
        companies: List of company schemas user can access (for data filtering)
        permissions: User's RBAC permissions list

    Returns:
        Dict containing response data:
        {
            "content": str,
            "files": Optional[list],
            "error": Optional[str]
        }
    """
    roles = roles or []
    web_adapter = _ensure_web_adapter_registered()

    # Get or create session (adapter handles persistence loading + LLM context rebuild)
    session = web_adapter.get_or_create_session(user_id, user_name, roles=roles)

    # Track message count BEFORE adding new messages (for atomic append)
    messages_before = len(session.messages)

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
    is_admin = has_permission(permissions or [], "core:*:*")

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

    try:
        logger.info(f"[WebChat] Calling main_llm_loop for user={user_id}, admin={is_admin}, companies={companies}")

        # Call the SAME main_llm_loop as Slack
        # The channel adapter abstraction handles all the differences
        await main_llm_loop(
            channel=user_id,  # For web, channel is user_id
            user_id=user_id,
            user_input=message,
            channel_event=channel_event if files else None,
            is_admin_override=is_admin,
            user_companies=companies,
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

        # Persist only NEW messages using atomic append (race-condition safe)
        try:
            new_messages = session.messages[messages_before:]
            if new_messages:
                logger.info(f"[WebChat:sync] Persisting {len(new_messages)} new messages for user={user_id}")
                persist_result = append_chat_messages(user_id, new_messages, session.conversation_id)
                if persist_result:
                    logger.info(f"[WebChat:sync] Successfully persisted {len(new_messages)} messages for user={user_id}")
                else:
                    logger.error(f"[WebChat:sync] append_chat_messages returned False for user={user_id}")
        except Exception as persist_err:
            logger.error(f"[WebChat:sync] Failed to persist messages for user={user_id}: {persist_err}", exc_info=True)

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
    roles: list[str] | None = None,
    files: list[dict[str, Any]] | None = None,
    companies: list[str] | None = None,
    permissions: list[str] | None = None,
) -> AsyncGenerator[str, None]:
    """
    Stream a chat response using Server-Sent Events format.

    Streams events in REAL-TIME as main_llm_loop executes, including:
    - Status updates (tool execution progress)
    - File uploads
    - Message content
    - Delete events (ephemeral status cleanup)

    Supports parallel requests: multiple requests can be processed simultaneously,
    with each request receiving only its own events via request_id filtering.

    Args:
        user_id: Unique user identifier
        user_name: Display name for the user
        message: User's message text
        roles: User's roles (for permission checks)
        files: Optional list of file info dicts (for uploads)
        companies: List of company schemas user can access (for data filtering)
        permissions: User's RBAC permissions list
    """
    import uuid as uuid_module

    # Generate unique request ID for parallel request support
    request_id = str(uuid_module.uuid4())
    logger.info(f"[WebChat] stream_chat_message called for user={user_id}, request={request_id[:8]}...")

    roles = roles or []
    web_adapter = _ensure_web_adapter_registered()

    # Get or create session (adapter handles persistence loading + LLM context rebuild)
    session = web_adapter.get_or_create_session(user_id, user_name, roles=roles)

    # Register this request as active
    web_adapter.start_request(user_id, request_id)

    # Generate user message ID (used to link assistant responses to this message)
    user_msg_id = f"user-{datetime.now().timestamp()}-{request_id[:8]}"

    # Set context variables so adapter methods tag events correctly
    request_token = current_request_id.set(request_id)
    parent_token = current_parent_message_id.set(user_msg_id)  # Links responses to this user message

    # Track message count BEFORE adding new messages (for atomic append)
    messages_before = len(session.messages)

    # Add user message to session history (with timestamp for ordering)
    user_msg = {
        "id": user_msg_id,
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

    # Clean up old events from completed requests (memory management)
    web_adapter.cleanup_old_events(user_id)

    # Check if user has admin permissions using RBAC
    is_admin = has_permission(permissions or [], "core:*:*")

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

    # Track where we start in the event list (for this request only)
    event_start_index = len(session.events)
    request_complete = False

    async def run_llm():
        """Run main_llm_loop in background and mark complete when done."""
        nonlocal request_complete
        try:
            await main_llm_loop(
                channel=user_id,
                user_id=user_id,
                user_input=message,
                channel_event=channel_event if files else None,
                is_admin_override=is_admin,
                user_companies=companies,
            )
        except Exception as e:
            logger.error(f"[WebChat] main_llm_loop error: {e}", exc_info=True)
            # Push error event tagged with this request_id
            session.events.append({
                "type": "error",
                "request_id": request_id,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            })
        finally:
            request_complete = True
            web_adapter.complete_request(user_id, request_id)

    # Start LLM processing in background
    llm_task = asyncio.create_task(run_llm())

    try:
        # Send initial processing indicator with request_id (for resume capability)
        yield f"data: {json.dumps({'type': 'status', 'content': 'Processing...', 'request_id': request_id})}\n\n"

        event_index = event_start_index
        poll_interval = 0.02  # 20ms polling (reduced from 100ms for faster response)

        # Stream events as they arrive (filtered by request_id)
        while not request_complete or event_index < len(session.events):
            # Process any new events that belong to this request
            while event_index < len(session.events):
                event = session.events[event_index]
                event_index += 1

                # Only process events for THIS request (parallel request isolation)
                event_request_id = event.get("request_id")
                if event_request_id is not None and event_request_id != request_id:
                    continue  # Skip events from other parallel requests

                event_type = event.get("type")

                if event_type == "status":
                    # Status update (tool progress, etc.)
                    yield f"data: {json.dumps({'type': 'status', 'message_id': event.get('message_id'), 'parent_id': event.get('parent_id'), 'content': event.get('content')})}\n\n"

                elif event_type == "message":
                    # New message from assistant - send full content directly (no artificial delay)
                    content = event.get("content", "")
                    message_id = event.get("message_id")
                    if content:
                        # Send complete content as single event (real-time streaming uses stream_delta)
                        yield f"data: {json.dumps({'type': 'content', 'content': content, 'message_id': message_id, 'parent_id': event.get('parent_id')})}\n\n"

                elif event_type == "file":
                    # File uploaded
                    yield f"data: {json.dumps({'type': 'file', 'parent_id': event.get('parent_id'), 'file': {'file_id': event.get('file_id'), 'url': event.get('url'), 'filename': event.get('filename'), 'title': event.get('title'), 'comment': event.get('comment')}})}\n\n"

                elif event_type == "delete":
                    # Status message deleted (tool completed successfully)
                    yield f"data: {json.dumps({'type': 'delete', 'message_id': event.get('message_id')})}\n\n"

                elif event_type == "error":
                    # Error occurred
                    yield f"data: {json.dumps({'type': 'error', 'error': event.get('error')})}\n\n"

                elif event_type == "stream_delta":
                    # Real-time streaming delta from LLM (token-by-token)
                    yield f"data: {json.dumps({'type': 'chunk', 'content': event.get('delta', ''), 'message_id': event.get('message_id'), 'parent_id': event.get('parent_id')})}\n\n"

                elif event_type == "stream_complete":
                    # Streaming complete - final message content
                    yield f"data: {json.dumps({'type': 'stream_complete', 'message_id': event.get('message_id'), 'parent_id': event.get('parent_id'), 'content': event.get('content', '')})}\n\n"

            # Wait before polling again (only if not complete)
            if not request_complete:
                await asyncio.sleep(poll_interval)

        # Ensure task is done
        await llm_task

        # Persist only NEW messages using atomic append (race-condition safe)
        try:
            new_messages = session.messages[messages_before:]
            if new_messages:
                logger.info(f"[WebChat] Persisting {len(new_messages)} new messages for user={user_id}")
                result = append_chat_messages(user_id, new_messages, session.conversation_id)
                if result:
                    logger.info(f"[WebChat] Successfully persisted {len(new_messages)} messages for user={user_id}")
                else:
                    logger.error(f"[WebChat] append_chat_messages returned False for user={user_id}")
            else:
                logger.info(f"[WebChat] No new messages to persist for user={user_id}")
        except Exception as persist_err:
            logger.error(f"[WebChat] Failed to persist messages for user={user_id}: {persist_err}", exc_info=True)

        yield "data: [DONE]\n\n"

    except GeneratorExit:
        # Client disconnected (page refresh, navigation, abort)
        logger.info(f"[WebChat] Client disconnected for user={user_id}, cancelling LLM task")
        if not llm_task.done():
            llm_task.cancel()
            try:
                await llm_task
            except asyncio.CancelledError:
                logger.debug(f"[WebChat] LLM task cancelled for user={user_id}")
        raise  # Re-raise to properly close the generator
    except Exception as e:
        logger.error(f"[WebChat] Streaming error: {e}", exc_info=True)
        yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
        yield "data: [DONE]\n\n"
    finally:
        # Reset context variables (may fail if generator closed in different context)
        try:
            current_request_id.reset(request_token)
            current_parent_message_id.reset(parent_token)
        except ValueError:
            pass  # Token was created in a different async context

        # Cancel LLM task if still running (defensive cleanup)
        if not llm_task.done():
            logger.warning(f"[WebChat] LLM task still running in finally, cancelling for user={user_id}")
            llm_task.cancel()
            try:
                await llm_task
            except asyncio.CancelledError:
                pass

        # Mark request complete if not already
        if not request_complete:
            web_adapter.complete_request(user_id, request_id)


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


def get_conversation_history(user_id: str) -> list[dict[str, Any]]:
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
