"""
Chat Persistence Module.

Handles saving and loading chat messages to/from the database.
Provides a simple interface for chat_api and WebAdapter to persist chat history.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("proposal-bot")


def _get_db():
    """Get the database instance."""
    from db.database import db
    return db


def save_chat_messages(
    user_id: str,
    messages: List[Dict[str, Any]],
    session_id: Optional[str] = None,
) -> bool:
    """
    Save chat messages for a user to the database.

    Args:
        user_id: User's unique ID
        messages: List of message dictionaries with role, content, timestamp
        session_id: Optional session ID

    Returns:
        True if saved successfully
    """
    try:
        db = _get_db()
        return db.save_chat_session(user_id, messages, session_id)
    except Exception as e:
        logger.error(f"[CHAT PERSIST] Failed to save messages for {user_id}: {e}")
        return False


def load_chat_messages(user_id: str) -> List[Dict[str, Any]]:
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


def get_chat_session_info(user_id: str) -> Optional[Dict[str, Any]]:
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
