"""
Web Channel Adapter for Unified UI.

This adapter handles communication with the web-based unified UI,
storing messages in memory/sessions and returning them via API responses.
Unlike Slack which pushes messages, the web adapter stores responses
that are polled/streamed by the frontend.
"""

import asyncio
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Callable, Awaitable

from ..base import (
    ChannelAdapter,
    ChannelType,
    Message,
    User,
    FileUpload,
    Button,
    Attachment,
    MessageFormat,
    Modal,
)

logger = logging.getLogger(__name__)


@dataclass
class WebSession:
    """Represents a web user session."""
    user_id: str
    user_name: str
    email: Optional[str] = None
    roles: List[str] = field(default_factory=list)
    conversation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    messages: List[Dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)

    # For streaming responses
    pending_response: Optional[str] = None
    response_complete: bool = False
    response_chunks: List[str] = field(default_factory=list)


class WebAdapter(ChannelAdapter):
    """
    Channel adapter for the web-based Unified UI.

    Key differences from Slack:
    - Messages are stored in session and returned via HTTP
    - Supports SSE streaming for real-time responses
    - File uploads return URLs accessible by the web frontend
    - No modals (uses frontend UI instead)
    """

    def __init__(self, file_base_url: str = "/api/files"):
        """
        Initialize the web adapter.

        Args:
            file_base_url: Base URL for file downloads
        """
        self._sessions: Dict[str, WebSession] = {}
        self._file_base_url = file_base_url
        self._users: Dict[str, User] = {}
        self._uploaded_files: Dict[str, Path] = {}  # file_id -> path

        # Callbacks for streaming (set by the API layer)
        self._stream_callbacks: Dict[str, Callable[[str], Awaitable[None]]] = {}

    @property
    def channel_type(self) -> ChannelType:
        return ChannelType.WEB

    @property
    def name(self) -> str:
        return "Unified Web UI"

    @property
    def supports_threads(self) -> bool:
        return False  # Web UI uses flat conversation

    @property
    def supports_reactions(self) -> bool:
        return False  # Can add later

    @property
    def supports_buttons(self) -> bool:
        return True  # Frontend renders buttons

    @property
    def supports_modals(self) -> bool:
        return False  # Frontend handles modals

    # ========================================================================
    # SESSION MANAGEMENT
    # ========================================================================

    def create_session(
        self,
        user_id: str,
        user_name: str,
        email: Optional[str] = None,
        roles: Optional[List[str]] = None
    ) -> WebSession:
        """Create a new web session for a user."""
        session = WebSession(
            user_id=user_id,
            user_name=user_name,
            email=email,
            roles=roles or []
        )
        self._sessions[user_id] = session

        # Also store user
        self._users[user_id] = User(
            id=user_id,
            name=user_name,
            email=email,
            web_user_id=user_id
        )

        logger.info(f"[WebAdapter] Created session for user {user_id}")
        return session

    def get_session(self, user_id: str) -> Optional[WebSession]:
        """Get existing session for a user."""
        session = self._sessions.get(user_id)
        if session:
            session.last_activity = datetime.now()
        return session

    def get_or_create_session(
        self,
        user_id: str,
        user_name: str,
        email: Optional[str] = None,
        roles: Optional[List[str]] = None
    ) -> WebSession:
        """Get existing session or create new one."""
        session = self.get_session(user_id)
        if not session:
            session = self.create_session(user_id, user_name, email, roles)
        return session

    def clear_session(self, user_id: str) -> None:
        """Clear a user's session."""
        if user_id in self._sessions:
            del self._sessions[user_id]
            logger.info(f"[WebAdapter] Cleared session for user {user_id}")

    def get_conversation_history(self, user_id: str) -> List[Dict[str, Any]]:
        """Get conversation history for a user."""
        session = self.get_session(user_id)
        if session:
            return session.messages
        return []

    # ========================================================================
    # STREAMING SUPPORT
    # ========================================================================

    def set_stream_callback(
        self,
        user_id: str,
        callback: Callable[[str], Awaitable[None]]
    ) -> None:
        """Set a callback for streaming responses to a user."""
        self._stream_callbacks[user_id] = callback

    def clear_stream_callback(self, user_id: str) -> None:
        """Clear the stream callback for a user."""
        if user_id in self._stream_callbacks:
            del self._stream_callbacks[user_id]

    async def stream_chunk(self, user_id: str, chunk: str) -> None:
        """Stream a chunk of response to the user."""
        session = self.get_session(user_id)
        if session:
            session.response_chunks.append(chunk)

        # Call streaming callback if set
        callback = self._stream_callbacks.get(user_id)
        if callback:
            await callback(chunk)

    # ========================================================================
    # MESSAGING
    # ========================================================================

    async def send_message(
        self,
        channel_id: str,  # In web adapter, this is the user_id
        content: str,
        *,
        thread_id: Optional[str] = None,
        buttons: Optional[List[Button]] = None,
        attachments: Optional[List[Attachment]] = None,
        format: MessageFormat = MessageFormat.MARKDOWN,
        ephemeral: bool = False,
        user_id: Optional[str] = None,
    ) -> Message:
        """
        Send a message to the web session.

        For web adapter, channel_id is the user_id (each user has their own "channel").
        """
        target_user = user_id or channel_id
        session = self.get_session(target_user)

        message_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()

        message_data = {
            "id": message_id,
            "role": "assistant",
            "content": content,
            "timestamp": timestamp,
            "buttons": [
                {
                    "action_id": b.action_id,
                    "text": b.text,
                    "value": b.value,
                    "style": b.style.value if b.style else "secondary"
                }
                for b in (buttons or [])
            ],
            "attachments": [
                {
                    "url": a.url,
                    "filename": a.filename,
                    "mimetype": a.mimetype
                }
                for a in (attachments or [])
            ]
        }

        if session:
            session.messages.append(message_data)
            session.pending_response = content
            session.response_complete = True

        logger.debug(f"[WebAdapter] Sent message to {target_user}: {content[:50]}...")

        return Message(
            id=message_id,
            channel_id=channel_id,
            content=content,
            user_id="assistant",
            timestamp=timestamp,
            platform_message_id=message_id
        )

    async def update_message(
        self,
        channel_id: str,
        message_id: str,
        content: str,
        *,
        buttons: Optional[List[Button]] = None,
        format: MessageFormat = MessageFormat.MARKDOWN,
    ) -> Message:
        """Update an existing message in the session."""
        session = self.get_session(channel_id)

        if session:
            for msg in session.messages:
                if msg.get("id") == message_id:
                    msg["content"] = content
                    msg["updated_at"] = datetime.now().isoformat()
                    if buttons:
                        msg["buttons"] = [
                            {
                                "action_id": b.action_id,
                                "text": b.text,
                                "value": b.value,
                                "style": b.style.value if b.style else "secondary"
                            }
                            for b in buttons
                        ]
                    break

        return Message(
            id=message_id,
            channel_id=channel_id,
            content=content,
            platform_message_id=message_id
        )

    async def delete_message(
        self,
        channel_id: str,
        message_id: str,
    ) -> bool:
        """Delete a message from the session."""
        session = self.get_session(channel_id)

        if session:
            session.messages = [
                m for m in session.messages
                if m.get("id") != message_id
            ]
            return True
        return False

    # ========================================================================
    # REACTIONS (Not supported for web)
    # ========================================================================

    async def add_reaction(
        self,
        channel_id: str,
        message_id: str,
        reaction: str,
    ) -> bool:
        """Reactions not supported in web UI."""
        return False

    async def remove_reaction(
        self,
        channel_id: str,
        message_id: str,
        reaction: str,
    ) -> bool:
        """Reactions not supported in web UI."""
        return False

    # ========================================================================
    # FILE HANDLING
    # ========================================================================

    async def upload_file(
        self,
        channel_id: str,
        file_path: Union[str, Path],
        *,
        filename: Optional[str] = None,
        title: Optional[str] = None,
        comment: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> FileUpload:
        """
        Store a file and return URL for web download.
        """
        path = Path(file_path)
        if not path.exists():
            return FileUpload(success=False, error="File not found")

        file_id = str(uuid.uuid4())
        actual_filename = filename or path.name

        # Store file reference
        self._uploaded_files[file_id] = path

        # Create download URL
        url = f"{self._file_base_url}/{file_id}/{actual_filename}"

        logger.info(f"[WebAdapter] File uploaded: {actual_filename} -> {url}")

        # If there's a comment, add as message with attachment
        if comment:
            session = self.get_session(channel_id)
            if session:
                session.messages.append({
                    "id": str(uuid.uuid4()),
                    "role": "assistant",
                    "content": comment,
                    "timestamp": datetime.now().isoformat(),
                    "attachments": [{
                        "url": url,
                        "filename": actual_filename,
                        "title": title
                    }]
                })

        return FileUpload(
            success=True,
            url=url,
            file_id=file_id,
            filename=actual_filename
        )

    async def upload_file_bytes(
        self,
        channel_id: str,
        file_bytes: bytes,
        filename: str,
        *,
        title: Optional[str] = None,
        comment: Optional[str] = None,
        thread_id: Optional[str] = None,
        mimetype: Optional[str] = None,
    ) -> FileUpload:
        """Upload file from bytes."""
        import tempfile

        # Write to temp file
        suffix = Path(filename).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
            f.write(file_bytes)
            temp_path = Path(f.name)

        return await self.upload_file(
            channel_id,
            temp_path,
            filename=filename,
            title=title,
            comment=comment,
            thread_id=thread_id
        )

    def get_file_path(self, file_id: str) -> Optional[Path]:
        """Get the path for an uploaded file (for serving)."""
        return self._uploaded_files.get(file_id)

    async def download_file(
        self,
        file_info: Dict[str, Any],
    ) -> Optional[Path]:
        """
        Download a file from file_info.

        For web uploads, file_info contains the temp path directly.
        """
        if "temp_path" in file_info:
            return Path(file_info["temp_path"])
        if "file_id" in file_info:
            return self._uploaded_files.get(file_info["file_id"])
        return None

    # ========================================================================
    # USER MANAGEMENT
    # ========================================================================

    async def get_user(self, user_id: str) -> Optional[User]:
        """Get user information."""
        return self._users.get(user_id)

    async def get_user_display_name(self, user_id: str) -> str:
        """Get user's display name."""
        user = self._users.get(user_id)
        if user:
            return user.display_name or user.name
        return user_id

    async def open_dm(self, user_id: str) -> Optional[str]:
        """Open a DM channel (for web, this is just the user_id)."""
        return user_id

    async def get_file_info(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Get file info for a file ID."""
        path = self._uploaded_files.get(file_id)
        if path and path.exists():
            return {
                "id": file_id,
                "name": path.name,
                "path": str(path),
                "temp_path": str(path)
            }
        return None

    # ========================================================================
    # INTERACTIVE COMPONENTS
    # ========================================================================

    async def open_modal(
        self,
        trigger_id: str,
        modal: Modal,
    ) -> bool:
        """Modals handled by frontend."""
        logger.warning("[WebAdapter] open_modal called - handled by frontend")
        return False

    async def respond_to_action(
        self,
        response_url: str,
        content: str,
        *,
        replace_original: bool = True,
        buttons: Optional[List[Button]] = None,
    ) -> bool:
        """Actions handled by frontend."""
        logger.warning("[WebAdapter] respond_to_action called - handled by frontend")
        return False

    # ========================================================================
    # FORMATTING
    # ========================================================================

    def format_text(
        self,
        text: str,
        source_format: MessageFormat = MessageFormat.MARKDOWN,
    ) -> str:
        """Web UI uses markdown directly."""
        return text

    def format_user_mention(self, user_id: str) -> str:
        """Format user mention for web."""
        user = self._users.get(user_id)
        if user:
            return f"@{user.name}"
        return f"@{user_id}"

    def format_channel_mention(self, channel_id: str) -> str:
        """No channel mentions in web UI."""
        return f"#{channel_id}"
