"""
Chat Persistence Module.

Handles saving and loading chat messages to/from the database.
Provides a simple interface for chat_api and WebAdapter to persist chat history.

Supports parallel request handling by maintaining logical message ordering:
user messages are paired with their assistant responses via parent_id.
"""

import logging
from typing import Any

logger = logging.getLogger("proposal-bot")


def _sort_messages_by_pairs(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Sort messages so each user message is followed by its assistant response(s).

    This ensures logical conversation flow even when parallel requests complete
    out of order. Messages are ordered by user message timestamp, with each
    user message immediately followed by its linked assistant responses.

    Args:
        messages: List of message dicts with id, role, parent_id, timestamp

    Returns:
        Sorted list with user-assistant pairs grouped together
    """
    if not messages:
        return messages

    # Separate user and assistant messages
    user_messages = []
    assistant_messages = []

    for msg in messages:
        if msg.get("role") == "user":
            user_messages.append(msg)
        elif msg.get("role") == "assistant":
            assistant_messages.append(msg)

    # Sort user messages by timestamp
    user_messages.sort(key=lambda m: m.get("timestamp", ""))

    # Build parent_id -> assistant messages mapping
    responses_by_parent: dict[str, list[dict[str, Any]]] = {}
    orphan_responses: list[dict[str, Any]] = []

    for msg in assistant_messages:
        parent_id = msg.get("parent_id")
        if parent_id:
            if parent_id not in responses_by_parent:
                responses_by_parent[parent_id] = []
            responses_by_parent[parent_id].append(msg)
        else:
            # No parent_id - orphan response (legacy or error)
            orphan_responses.append(msg)

    # Sort responses within each parent group by timestamp
    for parent_id in responses_by_parent:
        responses_by_parent[parent_id].sort(key=lambda m: m.get("timestamp", ""))

    # Build sorted result: user message followed by its responses
    sorted_messages = []
    for user_msg in user_messages:
        sorted_messages.append(user_msg)
        user_id = user_msg.get("id")
        if user_id and user_id in responses_by_parent:
            sorted_messages.extend(responses_by_parent[user_id])

    # Append orphan responses at the end (sorted by timestamp)
    orphan_responses.sort(key=lambda m: m.get("timestamp", ""))
    sorted_messages.extend(orphan_responses)

    return sorted_messages


def _get_db():
    """Get the database instance."""
    from db.database import db
    return db


def save_chat_messages(
    user_id: str,
    messages: list[dict[str, Any]],
    session_id: str | None = None,
) -> bool:
    """
    Save chat messages for a user to the database (FULL REPLACEMENT).

    WARNING: This replaces ALL messages. Use append_chat_messages() for adding
    new messages to avoid race conditions in concurrent request scenarios.

    Messages are sorted to maintain logical conversation flow: each user message
    is followed by its assistant response(s), linked via parent_id. This ensures
    correct ordering even when parallel requests complete out of order.

    Args:
        user_id: User's unique ID
        messages: List of message dictionaries with role, content, timestamp, parent_id
        session_id: Optional session ID

    Returns:
        True if saved successfully
    """
    try:
        db = _get_db()
        # Sort messages to ensure logical pair ordering before saving
        sorted_messages = _sort_messages_by_pairs(messages)
        return db.save_chat_session(user_id, sorted_messages, session_id)
    except Exception as e:
        logger.error(f"[CHAT PERSIST] Failed to save messages for {user_id}: {e}")
        return False


def append_chat_messages(
    user_id: str,
    new_messages: list[dict[str, Any]],
    session_id: str | None = None,
) -> bool:
    """
    Atomically append new messages to a user's chat history.

    This is the PREFERRED method for saving new messages as it:
    - Prevents race conditions when concurrent requests save messages
    - Uses PostgreSQL JSONB concatenation for atomic appends
    - Falls back to optimistic locking if RPC is unavailable

    Args:
        user_id: User's unique ID
        new_messages: New message(s) to append (not the full history)
        session_id: Optional session ID

    Returns:
        True if appended successfully
    """
    if not new_messages:
        return True

    try:
        db = _get_db()
        return db.append_chat_messages(user_id, new_messages, session_id)
    except Exception as e:
        logger.error(f"[CHAT PERSIST] Failed to append messages for {user_id}: {e}")
        return False


def load_chat_messages(user_id: str) -> list[dict[str, Any]]:
    """
    Load chat messages for a user from the database.

    Args:
        user_id: User's unique ID

    Returns:
        List of message dictionaries, or empty list if none found
    """
    try:
        db = _get_db()
        session = db.get_chat_session(user_id)
        if session and session.get("messages"):
            logger.debug(f"[CHAT PERSIST] Loaded {len(session['messages'])} messages for {user_id}")
            return session["messages"]
        return []
    except Exception as e:
        logger.error(f"[CHAT PERSIST] Failed to load messages for {user_id}: {e}")
        return []


def clear_chat_messages(user_id: str) -> bool:
    """
    Clear chat messages for a user from the database.

    Args:
        user_id: User's unique ID

    Returns:
        True if cleared successfully
    """
    try:
        db = _get_db()
        return db.delete_chat_session(user_id)
    except Exception as e:
        logger.error(f"[CHAT PERSIST] Failed to clear messages for {user_id}: {e}")
        return False


def get_chat_session_info(user_id: str) -> dict[str, Any] | None:
    """
    Get chat session metadata without full messages.

    Args:
        user_id: User's unique ID

    Returns:
        Dict with session_id, message_count, created_at, updated_at or None
    """
    try:
        db = _get_db()
        session = db.get_chat_session(user_id)
        if session:
            return {
                "session_id": session.get("session_id"),
                "message_count": len(session.get("messages", [])),
                "created_at": session.get("created_at"),
                "updated_at": session.get("updated_at"),
            }
        return None
    except Exception as e:
        logger.error(f"[CHAT PERSIST] Failed to get session info for {user_id}: {e}")
        return None
