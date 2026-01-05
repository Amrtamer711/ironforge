"""
Messaging Platform Abstraction Layer
=====================================
This module provides a platform-agnostic interface for messaging operations.
Currently implements Slack, but can be swapped for Teams/other platforms.

All functions hide platform-specific details (blocks, message IDs, etc.)
and provide a clean interface that can work with any messaging platform.
"""

from typing import Dict, List, Any, Optional, Union
import clients
from clients import logger
from utils import markdown_to_slack


def _get_client():
    """Get the current platform client (lazy access)"""
    return clients.slack_client


# ============================================================================
# MESSAGE OPERATIONS
# ============================================================================

async def send_message(
    channel: str,
    text: str,
    blocks: Optional[List[Dict]] = None,
    thread_ts: Optional[str] = None
) -> Dict[str, Any]:
    """
    Send a message to a channel or user.

    Args:
        channel: Channel ID or user ID
        text: Message text (will be converted from markdown)
        blocks: Optional rich formatting blocks (platform-specific)
        thread_ts: Optional thread ID to reply in thread

    Returns:
        Dict with 'ok', 'message_id', 'timestamp'
    """
    try:
        # Convert markdown to platform format
        formatted_text = markdown_to_slack(text) if not blocks else text

        result = await _get_client().chat_postMessage(
            channel=channel,
            text=formatted_text,
            blocks=blocks,
            thread_ts=thread_ts
        )

        return {
            'ok': result.get('ok', False),
            'message_id': result.get('ts'),
            'timestamp': result.get('ts'),
            'channel': result.get('channel')
        }
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return {'ok': False, 'error': str(e)}


async def update_message(
    channel: str,
    message_id: str,
    text: str,
    blocks: Optional[List[Dict]] = None
) -> Dict[str, Any]:
    """
    Update an existing message.

    Args:
        channel: Channel ID where message was sent
        message_id: Message ID to update
        text: New message text
        blocks: Optional new blocks

    Returns:
        Dict with 'ok', 'message_id'
    """
    try:
        formatted_text = markdown_to_slack(text) if not blocks else text

        result = await _get_client().chat_update(
            channel=channel,
            ts=message_id,
            text=formatted_text,
            blocks=blocks
        )

        return {
            'ok': result.get('ok', False),
            'message_id': result.get('ts')
        }
    except Exception as e:
        logger.error(f"Error updating message: {e}")
        return {'ok': False, 'error': str(e)}


async def delete_message(channel: str, message_id: str) -> Dict[str, Any]:
    """
    Delete a message.

    Args:
        channel: Channel ID where message was sent
        message_id: Message ID to delete

    Returns:
        Dict with 'ok'
    """
    try:
        result = await _get_client().chat_delete(
            channel=channel,
            ts=message_id
        )

        return {'ok': result.get('ok', False)}
    except Exception as e:
        logger.error(f"Error deleting message: {e}")
        return {'ok': False, 'error': str(e)}


# ============================================================================
# FILE OPERATIONS
# ============================================================================

async def upload_file(
    channel: str,
    file_path: str,
    filename: str,
    title: Optional[str] = None,
    initial_comment: Optional[str] = None
) -> Dict[str, Any]:
    """
    Upload a file to a channel.

    Args:
        channel: Channel ID to upload to
        file_path: Path to file or file object
        filename: Name for the file
        title: Optional file title
        initial_comment: Optional message with file

    Returns:
        Dict with 'ok', 'file_id', 'file_url'
    """
    try:
        with open(file_path, 'rb') as f:
            result = await _get_client().files_upload_v2(
                channel=channel,
                file=f,
                filename=filename,
                title=title or filename,
                initial_comment=initial_comment
            )

        return {
            'ok': result.get('ok', False),
            'file_id': result.get('file', {}).get('id'),
            'file_url': result.get('file', {}).get('url_private')
        }
    except Exception as e:
        logger.error(f"Error uploading file: {e}")
        return {'ok': False, 'error': str(e)}


async def get_file_info(file_id: str) -> Dict[str, Any]:
    """
    Get information about a file.

    Args:
        file_id: File ID

    Returns:
        Dict with file info
    """
    try:
        result = await _get_client().files_info(file=file_id)

        file_data = result.get('file', {})
        return {
            'ok': result.get('ok', False),
            'id': file_data.get('id'),
            'name': file_data.get('name'),
            'url': file_data.get('url_private'),
            'size': file_data.get('size'),
            'mimetype': file_data.get('mimetype')
        }
    except Exception as e:
        logger.error(f"Error getting file info: {e}")
        return {'ok': False, 'error': str(e)}


# ============================================================================
# INTERACTIVE ELEMENTS (Modals, Views)
# ============================================================================

async def open_modal(
    trigger_id: str,
    view: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Open a modal dialog.

    Args:
        trigger_id: Trigger ID from interaction
        view: Modal view definition (platform-specific)

    Returns:
        Dict with 'ok', 'view_id'
    """
    try:
        result = await _get_client().views_open(
            trigger_id=trigger_id,
            view=view
        )

        return {
            'ok': result.get('ok', False),
            'view_id': result.get('view', {}).get('id')
        }
    except Exception as e:
        logger.error(f"Error opening modal: {e}")
        return {'ok': False, 'error': str(e)}


# ============================================================================
# USER OPERATIONS
# ============================================================================

async def get_user_info(user_id: str) -> Dict[str, Any]:
    """
    Get information about a user.

    Args:
        user_id: User ID

    Returns:
        Dict with user info (name, email, etc.)
    """
    try:
        result = await _get_client().users_info(user=user_id)

        user_data = result.get('user', {})
        profile = user_data.get('profile', {})

        return {
            'ok': result.get('ok', False),
            'id': user_data.get('id'),
            'name': user_data.get('name'),
            'real_name': user_data.get('real_name'),
            'email': profile.get('email'),
            'display_name': profile.get('display_name'),
            'is_bot': user_data.get('is_bot', False)
        }
    except Exception as e:
        logger.error(f"Error getting user info: {e}")
        return {'ok': False, 'error': str(e)}


async def list_users() -> Dict[str, Any]:
    """
    List all users in the workspace.

    Returns:
        Dict with 'ok', 'users' (list of user dicts)
    """
    try:
        result = await _get_client().users_list()

        users = []
        for member in result.get('members', []):
            if not member.get('deleted') and not member.get('is_bot'):
                profile = member.get('profile', {})
                users.append({
                    'id': member.get('id'),
                    'name': member.get('name'),
                    'real_name': member.get('real_name'),
                    'email': profile.get('email'),
                    'display_name': profile.get('display_name')
                })

        return {
            'ok': result.get('ok', False),
            'users': users
        }
    except Exception as e:
        logger.error(f"Error listing users: {e}")
        return {'ok': False, 'error': str(e)}


# ============================================================================
# CHANNEL OPERATIONS
# ============================================================================

async def get_channel_info(channel_id: str) -> Dict[str, Any]:
    """
    Get information about a channel.

    Args:
        channel_id: Channel ID

    Returns:
        Dict with channel info
    """
    try:
        result = await _get_client().conversations_info(channel=channel_id)

        channel_data = result.get('channel', {})
        return {
            'ok': result.get('ok', False),
            'id': channel_data.get('id'),
            'name': channel_data.get('name'),
            'is_private': channel_data.get('is_private'),
            'is_channel': channel_data.get('is_channel'),
            'is_im': channel_data.get('is_im')
        }
    except Exception as e:
        logger.error(f"Error getting channel info: {e}")
        return {'ok': False, 'error': str(e)}


# ============================================================================
# AUTHENTICATION
# ============================================================================

async def verify_auth() -> Dict[str, Any]:
    """
    Verify authentication/connection to messaging platform.

    Returns:
        Dict with 'ok', 'user_id', 'team_id', 'bot_id'
    """
    try:
        result = await _get_client().auth_test()

        return {
            'ok': result.get('ok', False),
            'user_id': result.get('user_id'),
            'team_id': result.get('team_id'),
            'bot_id': result.get('bot_id'),
            'url': result.get('url')
        }
    except Exception as e:
        logger.error(f"Error verifying auth: {e}")
        return {'ok': False, 'error': str(e)}
