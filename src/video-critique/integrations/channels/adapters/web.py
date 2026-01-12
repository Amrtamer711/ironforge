"""
Web Channel Adapter for Video Critique.

This adapter handles communication with the web-based unified UI,
storing messages in memory/sessions and returning them via API responses.
Unlike Slack which pushes messages, the web adapter stores responses
that are polled/streamed by the frontend via the unified-ui.

API-based Architecture:
- Video-critique exposes REST APIs for all operations
- Unified-ui proxies requests from the frontend to video-critique
- Messages and events are returned via API responses or SSE streaming
"""

import contextvars
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from crm_channels import (
    Attachment,
    Button,
    ChannelAdapter,
    ChannelType,
    FileUpload,
    Message,
    MessageFormat,
    Modal,
    User,
)

from core.utils.logging import get_logger

logger = get_logger(__name__)

# Context variable to track current request ID for parallel request support
current_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    'web_request_id', default=None
)

# Context variable to track the parent message ID
current_parent_message_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    'web_parent_message_id', default=None
)


@dataclass
class WebSession:
    """Represents a web user session for video critique chat."""
    user_id: str
    user_name: str
    email: str | None = None
    roles: list[str] = field(default_factory=list)
    conversation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)

    # For streaming responses
    pending_response: str | None = None
    response_complete: bool = False

    # Real-time event queue for SSE streaming
    events: list[dict[str, Any]] = field(default_factory=list)

    # Track active requests (supports parallel processing)
    active_requests: dict[str, bool] = field(default_factory=dict)


class WebAdapter(ChannelAdapter):
    """
    Channel adapter for the web-based Video Critique UI.

    Key differences from Slack:
    - Messages are stored in session and returned via HTTP APIs
    - Supports SSE streaming for real-time responses
    - File uploads stored in persistent directory and tracked in database
    - No modals (uses frontend UI instead)

    API Integration:
    - All operations are exposed via REST APIs
    - Unified-ui proxies requests to video-critique service
    - Events are streamed back to frontend via SSE
    """

    def __init__(self, file_base_url: str = "/api/files"):
        """
        Initialize the web adapter.

        Args:
            file_base_url: Base URL for file downloads
        """
        self._sessions: dict[str, WebSession] = {}
        self._file_base_url = file_base_url
        self._users: dict[str, User] = {}
        self._uploaded_files: dict[str, Path] = {}

        # Initialize persistent file storage directory
        self._init_file_storage()

    def _init_file_storage(self) -> None:
        """Initialize persistent file storage directory."""
        import config

        # Use DATA_DIR for persistent storage
        data_dir = getattr(config, "DATA_DIR", Path("./data"))
        self._file_storage_dir = Path(data_dir) / "web_uploads"
        self._file_storage_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"[WebAdapter] File storage: {self._file_storage_dir}")

        # Load existing file mappings from database
        self._load_file_mappings()

    def _load_file_mappings(self) -> None:
        """Load existing file mappings from database on startup."""
        try:
            # Check for existing files in storage directory
            for file_path in self._file_storage_dir.glob("*/*"):
                if file_path.is_file():
                    file_id = file_path.parent.name
                    self._uploaded_files[file_id] = file_path
            logger.info(f"[WebAdapter] Loaded {len(self._uploaded_files)} existing file mappings")
        except Exception as e:
            logger.warning(f"[WebAdapter] Failed to load file mappings: {e}")

    def _save_file_persistent(self, file_id: str, filename: str, content: bytes) -> Path:
        """Save file to persistent storage."""
        # Create subdirectory for this file
        file_dir = self._file_storage_dir / file_id
        file_dir.mkdir(parents=True, exist_ok=True)

        # Save file
        file_path = file_dir / filename
        file_path.write_bytes(content)

        # Track in memory
        self._uploaded_files[file_id] = file_path

        logger.info(f"[WebAdapter] Saved file to persistent storage: {file_path}")
        return file_path

    @property
    def channel_type(self) -> ChannelType:
        return ChannelType.WEB

    @property
    def name(self) -> str:
        return "Video Critique Web UI"

    @property
    def supports_threads(self) -> bool:
        return False

    @property
    def supports_reactions(self) -> bool:
        return False

    @property
    def supports_buttons(self) -> bool:
        return True

    @property
    def supports_modals(self) -> bool:
        return False

    # ========================================================================
    # SESSION MANAGEMENT
    # ========================================================================

    def create_session(
        self,
        user_id: str,
        user_name: str,
        email: str | None = None,
        roles: list[str] | None = None
    ) -> WebSession:
        """Create a new web session for a user."""
        session = WebSession(
            user_id=user_id,
            user_name=user_name,
            email=email,
            roles=roles or []
        )
        self._sessions[user_id] = session

        self._users[user_id] = User(
            id=user_id,
            name=user_name,
            email=email,
            web_user_id=user_id
        )

        logger.info(f"[WebAdapter] Created session for user {user_id}")
        return session

    def get_session(self, user_id: str) -> WebSession | None:
        """Get existing session for a user."""
        session = self._sessions.get(user_id)
        if session:
            session.last_activity = datetime.now()
        return session

    def get_or_create_session(
        self,
        user_id: str,
        user_name: str,
        email: str | None = None,
        roles: list[str] | None = None
    ) -> WebSession:
        """Get existing session or create new one."""
        session = self.get_session(user_id)
        if not session:
            session = self.create_session(user_id, user_name, email, roles)
            self._restore_session_state(user_id, session)
        return session

    def _restore_session_state(self, user_id: str, session: WebSession) -> None:
        """Restore session state from database."""
        try:
            from db.database import db
            chat_data = db.get_chat_session(user_id)
            if chat_data and chat_data.get("messages"):
                session.messages = chat_data["messages"]
                logger.info(f"[WebAdapter] Restored {len(session.messages)} messages for {user_id}")
        except Exception as e:
            logger.warning(f"[WebAdapter] Failed to restore session for {user_id}: {e}")

    def clear_session(self, user_id: str) -> None:
        """Clear a user's session."""
        if user_id in self._sessions:
            del self._sessions[user_id]
            logger.info(f"[WebAdapter] Cleared session for user {user_id}")

    # ========================================================================
    # PARALLEL REQUEST SUPPORT
    # ========================================================================

    def start_request(self, user_id: str, request_id: str) -> None:
        """Mark a request as active."""
        session = self.get_session(user_id)
        if session:
            session.active_requests[request_id] = True

    def complete_request(self, user_id: str, request_id: str) -> None:
        """Mark a request as complete."""
        session = self.get_session(user_id)
        if session:
            session.active_requests[request_id] = False

    def get_conversation_history(self, user_id: str) -> list[dict[str, Any]]:
        """Get conversation history for a user."""
        session = self.get_session(user_id)
        return session.messages if session else []

    # ========================================================================
    # MESSAGING
    # ========================================================================

    async def send_message(
        self,
        channel_id: str,
        content: str,
        *,
        thread_id: str | None = None,
        buttons: list[Button] | None = None,
        attachments: list[Attachment] | None = None,
        format: MessageFormat = MessageFormat.MARKDOWN,
        ephemeral: bool = False,
        user_id: str | None = None,
        is_tool_response: bool = False,
    ) -> Message:
        """Send a message to the web session."""
        target_user = user_id or channel_id
        session = self.get_session(target_user)

        message_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()
        parent_id = current_parent_message_id.get()

        message_data = {
            "id": message_id,
            "role": "assistant",
            "content": content,
            "timestamp": timestamp,
            "parent_id": parent_id,
            "is_tool_response": is_tool_response,
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

            # Push event for SSE streaming
            req_id = current_request_id.get()
            session.events.append({
                "type": "message",
                "request_id": req_id,
                "parent_id": parent_id,
                "message_id": message_id,
                "content": content,
                "attachments": message_data.get("attachments", []),
                "buttons": message_data.get("buttons", []),
                "timestamp": timestamp,
                "is_tool_response": is_tool_response,
            })

        logger.debug(f"[WebAdapter] Sent message to {target_user}: {content[:50]}...")

        return Message(
            id=message_id,
            channel_id=channel_id,
            content=content,
            user_id="assistant",
            timestamp=timestamp,
            platform_message_id=message_id
        )

    def push_stream_delta(
        self,
        user_id: str,
        message_id: str,
        delta: str,
    ) -> None:
        """Push a streaming text delta for real-time display."""
        session = self.get_session(user_id)
        if not session:
            return

        req_id = current_request_id.get()
        parent_id = current_parent_message_id.get()

        session.events.append({
            "type": "stream_delta",
            "request_id": req_id,
            "parent_id": parent_id,
            "message_id": message_id,
            "delta": delta,
            "timestamp": datetime.now().isoformat(),
        })

    def push_stream_complete(
        self,
        user_id: str,
        message_id: str,
        full_content: str,
    ) -> None:
        """Signal that streaming for a message is complete."""
        session = self.get_session(user_id)
        if not session:
            return

        req_id = current_request_id.get()
        parent_id = current_parent_message_id.get()
        timestamp = datetime.now().isoformat()

        message_data = {
            "id": message_id,
            "role": "assistant",
            "content": full_content,
            "timestamp": timestamp,
            "parent_id": parent_id,
            "buttons": [],
            "attachments": [],
        }
        session.messages.append(message_data)

        session.events.append({
            "type": "stream_complete",
            "request_id": req_id,
            "parent_id": parent_id,
            "message_id": message_id,
            "content": full_content,
            "timestamp": timestamp,
        })

    async def update_message(
        self,
        channel_id: str,
        message_id: str,
        content: str,
        *,
        buttons: list[Button] | None = None,
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

            req_id = current_request_id.get()
            session.events.append({
                "type": "status",
                "request_id": req_id,
                "message_id": message_id,
                "content": content,
                "timestamp": datetime.now().isoformat(),
            })

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

            req_id = current_request_id.get()
            session.events.append({
                "type": "delete",
                "request_id": req_id,
                "message_id": message_id,
                "timestamp": datetime.now().isoformat(),
            })

            return True
        return False

    # ========================================================================
    # REACTIONS (Not supported)
    # ========================================================================

    async def add_reaction(self, channel_id: str, message_id: str, reaction: str) -> bool:
        return False

    async def remove_reaction(self, channel_id: str, message_id: str, reaction: str) -> bool:
        return False

    # ========================================================================
    # FILE HANDLING
    # ========================================================================

    async def upload_file(
        self,
        channel_id: str,
        file_path: str | Path,
        *,
        filename: str | None = None,
        title: str | None = None,
        comment: str | None = None,
        thread_id: str | None = None,
    ) -> FileUpload:
        """Store a file in persistent storage and return URL for web download."""
        path = Path(file_path)
        if not path.exists():
            return FileUpload(success=False, error="File not found")

        file_id = str(uuid.uuid4())
        actual_filename = filename or path.name

        # Read file content and save to persistent storage
        content = path.read_bytes()
        persistent_path = self._save_file_persistent(file_id, actual_filename, content)

        # Create download URL
        url = f"{self._file_base_url}/{file_id}/{actual_filename}"

        logger.info(f"[WebAdapter] File stored persistently: {actual_filename} -> {url}")

        # Add message with attachment if comment provided
        session = self.get_session(channel_id)
        if session:
            if comment:
                parent_id = current_parent_message_id.get()
                session.messages.append({
                    "id": str(uuid.uuid4()),
                    "role": "assistant",
                    "content": comment,
                    "timestamp": datetime.now().isoformat(),
                    "parent_id": parent_id,
                    "attachments": [{
                        "file_id": file_id,
                        "url": url,
                        "filename": actual_filename,
                        "title": title
                    }]
                })

            req_id = current_request_id.get()
            session.events.append({
                "type": "file",
                "request_id": req_id,
                "file_id": file_id,
                "url": url,
                "filename": actual_filename,
                "title": title,
                "comment": comment,
                "timestamp": datetime.now().isoformat(),
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
        title: str | None = None,
        comment: str | None = None,
        thread_id: str | None = None,
        mimetype: str | None = None,
    ) -> FileUpload:
        """Upload file from bytes to persistent storage."""
        file_id = str(uuid.uuid4())

        # Save directly to persistent storage (no temp files)
        persistent_path = self._save_file_persistent(file_id, filename, file_bytes)

        # Create download URL
        url = f"{self._file_base_url}/{file_id}/{filename}"

        logger.info(f"[WebAdapter] File bytes stored persistently: {filename} -> {url}")

        # Add message with attachment if comment provided
        session = self.get_session(channel_id)
        if session:
            if comment:
                parent_id = current_parent_message_id.get()
                session.messages.append({
                    "id": str(uuid.uuid4()),
                    "role": "assistant",
                    "content": comment,
                    "timestamp": datetime.now().isoformat(),
                    "parent_id": parent_id,
                    "attachments": [{
                        "file_id": file_id,
                        "url": url,
                        "filename": filename,
                        "title": title
                    }]
                })

            req_id = current_request_id.get()
            session.events.append({
                "type": "file",
                "request_id": req_id,
                "file_id": file_id,
                "url": url,
                "filename": filename,
                "title": title,
                "comment": comment,
                "timestamp": datetime.now().isoformat(),
            })

        return FileUpload(
            success=True,
            url=url,
            file_id=file_id,
            filename=filename
        )

    def get_file_path(self, file_id: str) -> Path | None:
        """Get the local path for an uploaded file."""
        return self._uploaded_files.get(file_id)

    async def download_file(self, file_info: dict[str, Any]) -> Path | None:
        """Download a file from file_info."""
        if file_info.get("temp_path"):
            return Path(file_info["temp_path"])

        file_id = file_info.get("file_id")
        if file_id:
            return self._uploaded_files.get(file_id)

        return None

    # ========================================================================
    # USER MANAGEMENT
    # ========================================================================

    async def get_user(self, user_id: str) -> User | None:
        return self._users.get(user_id)

    async def get_user_display_name(self, user_id: str) -> str:
        user = self._users.get(user_id)
        if user:
            return user.display_name or user.name
        return user_id

    async def open_dm(self, user_id: str) -> str | None:
        return user_id

    async def get_file_info(self, file_id: str) -> dict[str, Any] | None:
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

    async def open_modal(self, trigger_id: str, modal: Modal) -> bool:
        logger.warning("[WebAdapter] open_modal - handled by frontend")
        return False

    async def respond_to_action(
        self,
        response_url: str,
        content: str,
        *,
        replace_original: bool = True,
        buttons: list[Button] | None = None,
    ) -> bool:
        logger.warning("[WebAdapter] respond_to_action - handled by frontend")
        return False

    # ========================================================================
    # FORMATTING
    # ========================================================================

    def format_text(
        self,
        text: str,
        source_format: MessageFormat = MessageFormat.MARKDOWN,
    ) -> str:
        return text

    def format_user_mention(self, user_id: str) -> str:
        user = self._users.get(user_id)
        if user:
            return f"@{user.name}"
        return f"@{user_id}"

    def format_channel_mention(self, channel_id: str) -> str:
        return f"#{channel_id}"
