"""
Generalized Chat API for the Unified UI.

This module provides a simplified chat interface that uses the same LLM
infrastructure as the Slack bot but works with any channel adapter.
It's designed for synchronous HTTP request/response (with optional streaming).
"""

import json
import asyncio
import re
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, AsyncGenerator, Callable, Awaitable
from pathlib import Path

import config
from db.cache import user_history, mockup_history, get_mockup_history
from integrations.llm import LLMClient, LLMMessage
from integrations.llm.prompts.chat import get_main_system_prompt
from core.tools import get_base_tools, get_admin_tools
from integrations.channels import WebAdapter, ChannelType

logger = config.logger

# Global WebAdapter instance for the unified UI
_web_adapter: Optional[WebAdapter] = None


def get_web_adapter() -> WebAdapter:
    """Get or create the global WebAdapter instance."""
    global _web_adapter
    if _web_adapter is None:
        _web_adapter = WebAdapter(file_base_url="/api/files")
    return _web_adapter


async def process_chat_message(
    user_id: str,
    user_name: str,
    message: str,
    roles: Optional[List[str]] = None,
    files: Optional[List[Dict[str, Any]]] = None,
    stream_callback: Optional[Callable[[str], Awaitable[None]]] = None
) -> Dict[str, Any]:
    """
    Process a chat message from the unified UI.

    This is a simplified version of main_llm_loop that:
    - Uses the same LLM infrastructure
    - Uses the same tools
    - Returns the response directly instead of posting to Slack

    Args:
        user_id: Unique user identifier
        user_name: Display name for the user
        message: User's message text
        roles: User's roles (for permission checks)
        files: Optional list of file info dicts (for uploads)
        stream_callback: Optional callback for streaming chunks

    Returns:
        Dict containing response data:
        {
            "content": str,
            "tool_call": Optional[dict],
            "files": Optional[list],
            "error": Optional[str]
        }
    """
    web_adapter = get_web_adapter()
    roles = roles or []

    # Get or create session
    session = web_adapter.get_or_create_session(user_id, user_name, roles=roles)

    # Add user message to session history
    session.messages.append({
        "id": f"user-{datetime.now().timestamp()}",
        "role": "user",
        "content": message,
        "timestamp": datetime.now().isoformat()
    })

    # Check if user is admin (has 'admin' role)
    is_admin = 'admin' in roles

    # Get location lists for the prompt
    static_locations = []
    digital_locations = []
    for key, meta in config.LOCATION_METADATA.items():
        display_name = meta.get('display_name', key)
        if meta.get('display_type', '').lower() == 'static':
            static_locations.append(f"{display_name} ({key})")
        elif meta.get('display_type', '').lower() == 'digital':
            digital_locations.append(f"{display_name} ({key})")

    static_list = ", ".join(static_locations) if static_locations else "None"
    digital_list = ", ".join(digital_locations) if digital_locations else "None"

    # Build system prompt
    system_prompt = get_main_system_prompt(
        is_admin=is_admin,
        static_list=static_list,
        digital_list=digital_list,
    )

    # Build user message content with file info
    user_message_content = message
    image_files = []
    document_files = []

    if files:
        for f in files:
            filename = f.get("filename", "").lower()
            mimetype = f.get("mimetype", "")

            if mimetype.startswith("image/") or any(filename.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".bmp"]):
                image_files.append(f.get("filename", "image"))
            elif mimetype.startswith("application/") or any(filename.endswith(ext) for ext in [".pdf", ".xlsx", ".xls", ".csv", ".docx", ".doc"]):
                document_files.append(f.get("filename", "document"))

        if image_files:
            user_message_content = f"{message}\n\n[User uploaded {len(image_files)} image file(s): {', '.join(image_files)}]"
        elif document_files:
            user_message_content = f"{message}\n\n[User uploaded {len(document_files)} document file(s): {', '.join(document_files)}]"

    # Inject mockup history context if no files uploaded
    if not image_files and not document_files:
        mockup_hist = get_mockup_history(user_id)
        if mockup_hist:
            metadata = mockup_hist.get("metadata", {})
            stored_location = metadata.get("location_name", "unknown")
            stored_frames = metadata.get("num_frames", 1)
            mode = metadata.get("mode", "unknown")

            timestamp = mockup_hist.get("timestamp")
            if timestamp:
                time_remaining = 30 - int((datetime.now() - timestamp).total_seconds() / 60)
                time_remaining = max(0, time_remaining)

                user_message_content = (
                    f"{user_message_content}\n\n"
                    f"[SYSTEM: User has {stored_frames}-frame creative(s) in memory from '{stored_location}' ({mode}). "
                    f"Expires in {time_remaining} minutes. Can reuse for follow-up mockup requests on locations with {stored_frames} frame(s).]"
                )

    # Get conversation history
    history = user_history.get(user_id, [])
    history.append({"role": "user", "content": user_message_content, "timestamp": datetime.now().isoformat()})
    history = history[-10:]  # Keep last 10 messages

    # Build LLM messages
    llm_messages = [LLMMessage.system(system_prompt)]
    for msg in history:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "user":
            llm_messages.append(LLMMessage.user(content))
        elif role == "assistant":
            llm_messages.append(LLMMessage.assistant(content))

    # Get tools
    base_tools = get_base_tools()
    all_tools = list(base_tools)

    if is_admin:
        admin_tools = get_admin_tools()
        all_tools.extend(admin_tools)

    try:
        # Initialize LLM client
        logger.info(f"[WebChat] Initializing LLM client...")
        llm_client = LLMClient.from_config()
        logger.info(f"[WebChat] LLM client initialized: provider={llm_client.provider_name}")

        # Call LLM
        logger.info(f"[WebChat] Calling LLM with {len(llm_messages)} messages and {len(all_tools)} tools...")
        response = await llm_client.complete(
            messages=llm_messages,
            tools=all_tools,
            tool_choice="auto",
            cache_key="web-chat",
            cache_retention="24h",
            call_type="main_llm",
            workflow="general_chat",
            user_id=user_name,
            context=f"Channel: web_ui, User: {user_id}",
        )
        logger.info(f"[WebChat] LLM response received: has_content={bool(response.content)}, tool_calls={bool(response.tool_calls)}")

        result = {
            "content": None,
            "tool_call": None,
            "files": [],
            "error": None
        }

        # Handle tool calls
        if response.tool_calls:
            tool_call = response.tool_calls[0]
            logger.info(f"[WebChat] Tool call: {tool_call.name}")

            # For now, return the tool call info - let the API layer handle it
            result["tool_call"] = {
                "name": tool_call.name,
                "arguments": tool_call.arguments
            }

            # Handle specific tools inline that don't need complex workflows
            if tool_call.name == "list_locations":
                # Simple tool - return locations list
                locations_text = _format_locations_list()
                result["content"] = locations_text
                result["tool_call"] = None

            elif tool_call.name in ["get_separate_proposals", "get_combined_proposal"]:
                # Complex tool - will be handled by API layer
                result["content"] = "📄 _Generating proposal..._"

            elif tool_call.name == "generate_mockup":
                # Complex tool - will be handled by API layer
                args = tool_call.arguments
                location = args.get("location", "unknown")
                result["content"] = f"🎨 _Generating mockup for {location}..._"

            elif tool_call.name == "parse_booking_order":
                result["content"] = "📋 _Processing booking order..._"

            else:
                # Unknown tool
                result["content"] = f"⏳ Processing {tool_call.name}..."

            # Add assistant's tool call summary to history
            history.append({
                "role": "assistant",
                "content": result["content"],
                "timestamp": datetime.now().isoformat()
            })

        elif response.content:
            # Text response
            reply = response.content

            # Format markdown
            formatted_reply = reply
            formatted_reply = formatted_reply.replace('\n- ', '\n• ')
            formatted_reply = formatted_reply.replace('\n* ', '\n• ')
            formatted_reply = re.sub(r'^(For .+:)$', r'**\1**', formatted_reply, flags=re.MULTILINE)

            result["content"] = formatted_reply

            # Add to history
            history.append({
                "role": "assistant",
                "content": reply,
                "timestamp": datetime.now().isoformat()
            })

            # Stream if callback provided
            if stream_callback:
                words = formatted_reply.split(' ')
                for word in words:
                    await stream_callback(word + ' ')
                    await asyncio.sleep(0.02)

        else:
            result["content"] = "I can help with proposals, mockups, and business operations. What would you like to do?"

        # Update history cache
        user_history[user_id] = history[-10:]

        # Add to session
        if result["content"]:
            session.messages.append({
                "id": f"assistant-{datetime.now().timestamp()}",
                "role": "assistant",
                "content": result["content"],
                "timestamp": datetime.now().isoformat(),
                "tool_call": result["tool_call"]
            })

        return result

    except Exception as e:
        logger.error(f"[WebChat] Error processing message: {e}", exc_info=True)
        return {
            "content": None,
            "tool_call": None,
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

    Yields SSE-formatted strings that can be sent directly to the client.
    Sends heartbeats every 5 seconds to keep connection alive during LLM processing.
    """
    logger.info(f"[WebChat] stream_chat_message called for user={user_id}, message={message[:50]}...")
    collected_response = []

    async def collect_chunk(chunk: str):
        collected_response.append(chunk)

    try:
        logger.info(f"[WebChat] Calling process_chat_message...")

        # Create task for LLM processing
        process_task = asyncio.create_task(
            process_chat_message(
                user_id=user_id,
                user_name=user_name,
                message=message,
                roles=roles,
                files=files,
                stream_callback=collect_chunk
            )
        )

        # Send heartbeats while waiting for LLM response
        heartbeat_count = 0
        while not process_task.done():
            # Send SSE comment as heartbeat (keeps connection alive)
            yield ": heartbeat\n\n"
            heartbeat_count += 1
            if heartbeat_count <= 3:
                logger.info(f"[WebChat] Sent heartbeat {heartbeat_count}")
            try:
                # Wait up to 5 seconds for task to complete
                await asyncio.wait_for(asyncio.shield(process_task), timeout=5.0)
            except asyncio.TimeoutError:
                # Task not done yet, continue sending heartbeats
                pass

        # Get result
        result = await process_task
        logger.info(f"[WebChat] process_chat_message returned: error={result.get('error')}, has_content={bool(result.get('content'))}")

        if result.get("error"):
            yield f"data: {json.dumps({'error': result['error']})}\n\n"
        elif result.get("tool_call"):
            # Tool call - send special event
            yield f"data: {json.dumps({'type': 'tool_call', 'tool': result['tool_call']})}\n\n"
            if result.get("content"):
                yield f"data: {json.dumps({'type': 'content', 'content': result['content']})}\n\n"
        else:
            # Regular content - stream it
            content = result.get("content", "")
            words = content.split(' ')
            for i, word in enumerate(words):
                yield f"data: {json.dumps({'type': 'chunk', 'content': word + (' ' if i < len(words) - 1 else '')})}\n\n"
                await asyncio.sleep(0.02)

        yield "data: [DONE]\n\n"

    except Exception as e:
        logger.error(f"[WebChat] Streaming error: {e}", exc_info=True)
        yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield "data: [DONE]\n\n"


def _format_locations_list() -> str:
    """Format the locations list for display."""
    static_locations = []
    digital_locations = []

    for key, meta in config.LOCATION_METADATA.items():
        display_name = meta.get('display_name', key)
        display_type = meta.get('display_type', 'Unknown')

        if display_type.lower() == 'static':
            static_locations.append(f"• {display_name} (`{key}`)")
        elif display_type.lower() == 'digital':
            digital_locations.append(f"• {display_name} (`{key}`)")

    result = "**Available Locations**\n\n"

    if digital_locations:
        result += "**Digital Locations:**\n" + "\n".join(sorted(digital_locations)) + "\n\n"

    if static_locations:
        result += "**Static Locations:**\n" + "\n".join(sorted(static_locations))

    if not digital_locations and not static_locations:
        result = "No locations are currently configured."

    return result


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
