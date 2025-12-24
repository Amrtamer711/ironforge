"""
Web Channel Adapter for Unified UI.

This adapter handles communication with the web-based unified UI,
storing messages in memory/sessions and returning them via API responses.
Unlike Slack which pushes messages, the web adapter stores responses
that are polled/streamed by the frontend.

File Storage:
- When STORAGE_PROVIDER=supabase, files are stored in Supabase Storage
- Files persist across deployments/restarts
- Signed URLs are used for secure access
"""

import contextvars
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# Context variable to track current request ID for parallel request support
# This allows adapter methods to tag events with the correct request_id
current_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    'web_request_id', default=None
)

# Context variable to track the parent message ID (user message that triggered this response)
# This allows assistant responses to be linked to their originating user message
current_parent_message_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    'web_parent_message_id', default=None
)

from ..base import (
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

logger = logging.getLogger(__name__)


# Storage metadata for files (maps file_id to storage info)
@dataclass
class StoredFileInfo:
    """Metadata for a stored file."""
    file_id: str
    bucket: str
    key: str
    filename: str
    content_type: str
    size: int
    user_id: str | None = None
    local_path: Path | None = None  # For local storage fallback
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class WebSession:
    """Represents a web user session.

    Supports parallel requests: multiple requests can be processed simultaneously,
    each with its own event stream identified by request_id.
    """
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
    response_chunks: list[str] = field(default_factory=list)

    # Real-time event queue for SSE streaming (supports parallel requests)
    # Events: {"type": "status"|"message"|"file"|"delete"|"done", "request_id": str, ...}
    events: list[dict[str, Any]] = field(default_factory=list)

    # Track active requests by request_id (supports parallel processing)
    active_requests: dict[str, bool] = field(default_factory=dict)

    # Legacy field for backwards compatibility (deprecated, use active_requests)
    processing_complete: bool = False


class WebAdapter(ChannelAdapter):
    """
    Channel adapter for the web-based Unified UI.

    Key differences from Slack:
    - Messages are stored in session and returned via HTTP
    - Supports SSE streaming for real-time responses
    - File uploads return URLs accessible by the web frontend
    - No modals (uses frontend UI instead)

    File Storage:
    - Uses Supabase Storage when STORAGE_PROVIDER=supabase
    - Falls back to local temp files when local
    - Files organized by bucket: 'uploads' for user files, 'proposals' for generated docs
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
        self._uploaded_files: dict[str, Path] = {}  # Legacy: file_id -> path (for local storage)
        self._stored_files: dict[str, StoredFileInfo] = {}  # file_id -> StoredFileInfo

        # Callbacks for streaming (set by the API layer)
        self._stream_callbacks: dict[str, Callable[[str], Awaitable[None]]] = {}

        # Storage client (lazy loaded)
        self._storage_client = None

    def _get_storage_client(self):
        """Get or create the storage client."""
        if self._storage_client is None:
            try:
                from integrations.storage import get_storage_client
                self._storage_client = get_storage_client()
                logger.info(f"[WebAdapter] Using storage provider: {self._storage_client.provider_name}")
            except Exception as e:
                logger.warning(f"[WebAdapter] Failed to initialize storage client: {e}")
                self._storage_client = None
        return self._storage_client

    def _is_using_remote_storage(self) -> bool:
        """Check if we're using remote storage (Supabase/S3)."""
        client = self._get_storage_client()
        return client is not None and client.provider_name != "local"

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

        # Also store user
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
        """Get existing session or create new one.

        When creating a new session, loads persisted messages from database
        and rebuilds LLM context so the bot remembers previous conversation.
        """
        session = self.get_session(user_id)
        if not session:
            session = self.create_session(user_id, user_name, email, roles)
            # Load persisted messages and rebuild LLM context for new sessions
            self._restore_session_state(user_id, session)
        return session

    def _sanitize_content(self, text: str) -> str:
        """
        Remove any leaked frontend placeholders from message content.

        The frontend's formatContent() uses __INLINE_CODE_X__ and __CODE_BLOCK_X__
        placeholders internally. These should never be persisted or sent to the LLM.
        """
        if not text:
            return text
        import re
        text = re.sub(r'__INLINE_CODE_\d+__', '', text)
        text = re.sub(r'__CODE_BLOCK_\d+__', '', text)
        return text

    def _restore_session_state(self, user_id: str, session: WebSession) -> None:
        """
        Restore session state from database for a newly created session.

        This loads persisted chat messages and rebuilds the LLM context,
        ensuring continuity after server restarts.
        """
        try:
            from core.chat_persistence import load_chat_messages
            from db.cache import user_history

            persisted_messages = load_chat_messages(user_id)
            if persisted_messages:
                # Restore UI messages (sanitize any leaked placeholders)
                for msg in persisted_messages:
                    if msg.get("content"):
                        msg["content"] = self._sanitize_content(msg["content"])
                session.messages = persisted_messages

                # Rebuild LLM context from persisted messages (last 10)
                llm_history = []
                for msg in persisted_messages:
                    role = msg.get("role")
                    content = msg.get("content")
                    if role in ("user", "assistant") and content:
                        llm_history.append({
                            "role": role,
                            "content": content,
                            "timestamp": msg.get("timestamp", "")
                        })

                if llm_history:
                    user_history[user_id] = llm_history[-10:]
                    logger.info(
                        f"[WebAdapter] Restored session for {user_id}: "
                        f"{len(persisted_messages)} messages, "
                        f"{len(user_history[user_id])} in LLM context"
                    )
        except Exception as e:
            logger.warning(f"[WebAdapter] Failed to restore session state for {user_id}: {e}")

    def clear_session(self, user_id: str) -> None:
        """Clear a user's session."""
        if user_id in self._sessions:
            del self._sessions[user_id]
            logger.info(f"[WebAdapter] Cleared session for user {user_id}")

    # ========================================================================
    # PARALLEL REQUEST SUPPORT
    # ========================================================================

    def start_request(self, user_id: str, request_id: str) -> None:
        """Mark a request as active for a user session."""
        session = self.get_session(user_id)
        if session:
            session.active_requests[request_id] = True
            logger.debug(f"[WebAdapter] Started request {request_id[:8]}... for {user_id}")

    def complete_request(self, user_id: str, request_id: str) -> None:
        """Mark a request as complete and clean up its events."""
        session = self.get_session(user_id)
        if session:
            session.active_requests[request_id] = False
            logger.debug(f"[WebAdapter] Completed request {request_id[:8]}... for {user_id}")

    def is_request_active(self, user_id: str, request_id: str) -> bool:
        """Check if a specific request is still active."""
        session = self.get_session(user_id)
        if session:
            return session.active_requests.get(request_id, False)
        return False

    def cleanup_old_events(self, user_id: str, max_age_seconds: int = 300) -> int:
        """
        Clean up old events from completed requests to prevent memory growth.

        Args:
            user_id: User session to clean
            max_age_seconds: Remove events older than this (default 5 minutes)

        Returns:
            Number of events removed
        """
        session = self.get_session(user_id)
        if not session:
            return 0

        now = datetime.now()
        initial_count = len(session.events)

        # Keep events that are either:
        # 1. From active requests, OR
        # 2. Less than max_age_seconds old
        cleaned_events = []
        for event in session.events:
            req_id = event.get("request_id")
            timestamp_str = event.get("timestamp", "")

            # Keep if request is still active
            if req_id and session.active_requests.get(req_id, False):
                cleaned_events.append(event)
                continue

            # Keep if event is recent enough
            try:
                event_time = datetime.fromisoformat(timestamp_str)
                age = (now - event_time).total_seconds()
                if age < max_age_seconds:
                    cleaned_events.append(event)
            except (ValueError, TypeError):
                # Can't parse timestamp, keep event to be safe
                cleaned_events.append(event)

        session.events = cleaned_events
        removed = initial_count - len(cleaned_events)

        if removed > 0:
            logger.debug(f"[WebAdapter] Cleaned up {removed} old events for {user_id}")

        # Also clean up completed request entries older than max_age
        completed_requests = [
            req_id for req_id, active in session.active_requests.items()
            if not active
        ]
        for req_id in completed_requests[:max(0, len(completed_requests) - 10)]:
            # Keep last 10 completed requests for debugging
            del session.active_requests[req_id]

        return removed

    def get_conversation_history(self, user_id: str) -> list[dict[str, Any]]:
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
        thread_id: str | None = None,
        buttons: list[Button] | None = None,
        attachments: list[Attachment] | None = None,
        format: MessageFormat = MessageFormat.MARKDOWN,
        ephemeral: bool = False,
        user_id: str | None = None,
    ) -> Message:
        """
        Send a message to the web session.

        For web adapter, channel_id is the user_id (each user has their own "channel").
        """
        target_user = user_id or channel_id
        session = self.get_session(target_user)

        message_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()

        # Get parent message ID from context (links response to originating user message)
        parent_id = current_parent_message_id.get()

        message_data = {
            "id": message_id,
            "role": "assistant",
            "content": content,
            "timestamp": timestamp,
            "parent_id": parent_id,  # Link to the user message that triggered this response
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

            # Push event for real-time streaming (tagged with request_id and parent_id)
            req_id = current_request_id.get()
            session.events.append({
                "type": "message",
                "request_id": req_id,
                "parent_id": parent_id,  # Frontend uses this to place response under correct user message
                "message_id": message_id,
                "content": content,
                "attachments": message_data.get("attachments", []),
                "timestamp": timestamp,
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
        """
        Push a streaming text delta event for real-time token-by-token display.

        Args:
            user_id: User session to push to
            message_id: ID of the message being streamed
            delta: Text chunk to append
        """
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
        """
        Signal that streaming for a message is complete and provide full content.

        Args:
            user_id: User session to push to
            message_id: ID of the streamed message
            full_content: Complete message content
        """
        session = self.get_session(user_id)
        if not session:
            return

        req_id = current_request_id.get()
        parent_id = current_parent_message_id.get()

        # Add the complete message to session.messages for persistence
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

        # Push stream complete event
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

            # Push status update event for real-time streaming (tagged with request_id)
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

            # Push delete event for real-time streaming (tagged with request_id)
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
        file_path: str | Path,
        *,
        filename: str | None = None,
        title: str | None = None,
        comment: str | None = None,
        thread_id: str | None = None,
        bucket: str = "uploads",
        user_id: str | None = None,
        document_type: str | None = None,
        bo_id: int | None = None,
        proposal_id: int | None = None,
    ) -> FileUpload:
        """
        Store a file and return URL for web download.

        When STORAGE_PROVIDER=supabase, uploads to Supabase Storage.
        Otherwise, stores locally in temp files.

        Also records file in documents table with hash for integrity/deduplication.

        Args:
            channel_id: User/channel identifier
            file_path: Local path to the file
            filename: Optional override for filename
            title: Optional title for the file
            comment: Optional message to add with the file
            thread_id: Not used in web adapter
            bucket: Storage bucket ('uploads', 'proposals', etc.)
            user_id: User who owns this file (for organization)
            document_type: Classification ('bo_pdf', 'creative', etc.)
            bo_id: Link to booking order
            proposal_id: Link to proposal
        """
        path = Path(file_path)
        if not path.exists():
            return FileUpload(success=False, error="File not found")

        file_id = str(uuid.uuid4())
        actual_filename = filename or path.name
        owner_id = user_id or channel_id

        # Determine content type
        import mimetypes
        content_type, _ = mimetypes.guess_type(actual_filename)
        content_type = content_type or "application/octet-stream"

        # Calculate file hash for integrity/deduplication
        file_hash = None
        file_size = path.stat().st_size
        try:
            from core.utils.files import calculate_sha256, get_file_extension
            file_hash = calculate_sha256(path)
            file_extension = get_file_extension(actual_filename)
        except Exception as e:
            logger.warning(f"[WebAdapter] Failed to calculate file hash: {e}")
            file_extension = path.suffix.lower()

        # Try to use remote storage (Supabase)
        storage_client = self._get_storage_client()
        if storage_client and storage_client.provider_name != "local":
            try:
                # Generate storage key: {bucket}/{user_id}/{date}/{file_id}_{filename}
                date_prefix = datetime.now().strftime("%Y/%m/%d")
                storage_key = f"{owner_id}/{date_prefix}/{file_id}_{actual_filename}"

                # Upload to Supabase Storage
                result = await storage_client.upload_from_path(
                    bucket=bucket,
                    key=storage_key,
                    local_path=path,
                    content_type=content_type,
                )

                if result.success:
                    # Store metadata in memory cache
                    self._stored_files[file_id] = StoredFileInfo(
                        file_id=file_id,
                        bucket=bucket,
                        key=storage_key,
                        filename=actual_filename,
                        content_type=content_type,
                        size=file_size,
                        user_id=owner_id,
                    )

                    # Store document record in database
                    try:
                        from db.database import db
                        db.create_document(
                            file_id=file_id,
                            user_id=owner_id,
                            original_filename=actual_filename,
                            file_type=content_type,
                            storage_provider=storage_client.provider_name,
                            storage_bucket=bucket,
                            storage_key=storage_key,
                            file_size=file_size,
                            file_extension=file_extension,
                            file_hash=file_hash,
                            document_type=document_type,
                            bo_id=bo_id,
                            proposal_id=proposal_id,
                        )
                    except Exception as db_err:
                        logger.warning(f"[WebAdapter] Failed to store document in DB (file still uploaded): {db_err}")

                    # Get signed URL directly for Supabase storage (no auth required to view)
                    # This allows files to be opened in new tabs and images to be displayed inline
                    try:
                        signed_url = await storage_client.get_signed_url(
                            bucket=bucket,
                            key=storage_key,
                            expires_in=86400,  # 24 hours - long enough for chat sessions
                        )
                        url = signed_url if signed_url else f"{self._file_base_url}/{file_id}/{actual_filename}"
                    except Exception as sign_err:
                        logger.warning(f"[WebAdapter] Failed to get signed URL, using API URL: {sign_err}")
                        url = f"{self._file_base_url}/{file_id}/{actual_filename}"

                    logger.info(f"[WebAdapter] File uploaded to {storage_client.provider_name}: {actual_filename} -> {bucket}/{storage_key} (hash={file_hash[:16] if file_hash else 'N/A'}...)")

                    # Add message with attachment if comment provided
                    session = self.get_session(channel_id)
                    if session:
                        if comment:
                            # Get parent_id to link this response to the originating user message
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

                        # Push file event for real-time streaming (tagged with request_id)
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
                else:
                    logger.error(f"[WebAdapter] Storage upload failed: {result.error}")
                    # Fall through to local storage
            except Exception as e:
                logger.error(f"[WebAdapter] Storage upload error: {e}")
                # Fall through to local storage

        # Fallback: Local storage (temp files)
        self._uploaded_files[file_id] = path
        self._stored_files[file_id] = StoredFileInfo(
            file_id=file_id,
            bucket=bucket,
            key=actual_filename,
            filename=actual_filename,
            content_type=content_type,
            size=file_size,
            user_id=owner_id,
            local_path=path,
        )

        # Store document record in database (even for local storage)
        try:
            from db.database import db
            db.create_document(
                file_id=file_id,
                user_id=owner_id,
                original_filename=actual_filename,
                file_type=content_type,
                storage_provider="local",
                storage_bucket=bucket,
                storage_key=str(path),
                file_size=file_size,
                file_extension=file_extension,
                file_hash=file_hash,
                document_type=document_type,
                bo_id=bo_id,
                proposal_id=proposal_id,
            )
        except Exception as db_err:
            logger.warning(f"[WebAdapter] Failed to store document in DB (file still stored): {db_err}")

        # Create download URL
        url = f"{self._file_base_url}/{file_id}/{actual_filename}"

        logger.info(f"[WebAdapter] File stored locally: {actual_filename} -> {url} (hash={file_hash[:16] if file_hash else 'N/A'}...)")

        # If there's a comment, add as message with attachment
        session = self.get_session(channel_id)
        if session:
            if comment:
                # Get parent_id to link this response to the originating user message
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

            # Push file event for real-time streaming (tagged with request_id)
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
        bucket: str = "uploads",
        user_id: str | None = None,
        document_type: str | None = None,
        bo_id: int | None = None,
        proposal_id: int | None = None,
    ) -> FileUpload:
        """
        Upload file from bytes.

        When STORAGE_PROVIDER=supabase, uploads directly to Supabase Storage.
        Otherwise, writes to temp file first.

        Also records file in documents table with hash for integrity/deduplication.
        """
        import tempfile

        file_id = str(uuid.uuid4())
        owner_id = user_id or channel_id
        content_type = mimetype

        # Determine content type if not provided
        if not content_type:
            import mimetypes
            content_type, _ = mimetypes.guess_type(filename)
            content_type = content_type or "application/octet-stream"

        # Calculate file hash for integrity/deduplication
        file_hash = None
        try:
            from core.utils.files import calculate_sha256, get_file_extension
            file_hash = calculate_sha256(file_bytes)
            file_extension = get_file_extension(filename)
        except Exception as e:
            logger.warning(f"[WebAdapter] Failed to calculate file hash: {e}")
            file_extension = Path(filename).suffix.lower()

        # Try to use remote storage (Supabase)
        storage_client = self._get_storage_client()
        if storage_client and storage_client.provider_name != "local":
            try:
                # Generate storage key
                date_prefix = datetime.now().strftime("%Y/%m/%d")
                storage_key = f"{owner_id}/{date_prefix}/{file_id}_{filename}"

                # Upload directly from bytes
                result = await storage_client.upload(
                    bucket=bucket,
                    key=storage_key,
                    data=file_bytes,
                    content_type=content_type,
                )

                if result.success:
                    # Store metadata in memory cache
                    self._stored_files[file_id] = StoredFileInfo(
                        file_id=file_id,
                        bucket=bucket,
                        key=storage_key,
                        filename=filename,
                        content_type=content_type,
                        size=len(file_bytes),
                        user_id=owner_id,
                    )

                    # Store document record in database
                    try:
                        from db.database import db
                        db.create_document(
                            file_id=file_id,
                            user_id=owner_id,
                            original_filename=filename,
                            file_type=content_type,
                            storage_provider=storage_client.provider_name,
                            storage_bucket=bucket,
                            storage_key=storage_key,
                            file_size=len(file_bytes),
                            file_extension=file_extension,
                            file_hash=file_hash,
                            document_type=document_type,
                            bo_id=bo_id,
                            proposal_id=proposal_id,
                        )
                    except Exception as db_err:
                        logger.warning(f"[WebAdapter] Failed to store document in DB (file still uploaded): {db_err}")

                    # Get signed URL directly for Supabase storage (no auth required to view)
                    try:
                        signed_url = await storage_client.get_signed_url(
                            bucket=bucket,
                            key=storage_key,
                            expires_in=86400,  # 24 hours
                        )
                        url = signed_url if signed_url else f"{self._file_base_url}/{file_id}/{filename}"
                    except Exception as sign_err:
                        logger.warning(f"[WebAdapter] Failed to get signed URL, using API URL: {sign_err}")
                        url = f"{self._file_base_url}/{file_id}/{filename}"

                    logger.info(f"[WebAdapter] File bytes uploaded to {storage_client.provider_name}: {filename} -> {bucket}/{storage_key} (hash={file_hash[:16] if file_hash else 'N/A'}...)")

                    if comment:
                        session = self.get_session(channel_id)
                        if session:
                            # Get parent_id to link this response to the originating user message
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

                    return FileUpload(
                        success=True,
                        url=url,
                        file_id=file_id,
                        filename=filename
                    )
                else:
                    logger.error(f"[WebAdapter] Storage upload failed: {result.error}")
            except Exception as e:
                logger.error(f"[WebAdapter] Storage upload error: {e}")

        # Fallback: Write to temp file
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
            thread_id=thread_id,
            bucket=bucket,
            user_id=user_id,
        )

    def get_file_path(self, file_id: str) -> Path | None:
        """Get the local path for an uploaded file (for local storage only)."""
        # Check new stored files first
        stored = self._stored_files.get(file_id)
        if stored and stored.local_path:
            return stored.local_path
        # Legacy fallback
        return self._uploaded_files.get(file_id)

    def get_stored_file_info(self, file_id: str) -> StoredFileInfo | None:
        """Get storage metadata for a file."""
        return self._stored_files.get(file_id)

    async def get_file_download_url(self, file_id: str, expires_in: int = 3600) -> str | None:
        """
        Get a download URL for a file.

        For Supabase Storage, returns a signed URL.
        For local storage, returns the API file path.
        """
        stored = self._stored_files.get(file_id)
        if not stored:
            return None

        # If using remote storage, get signed URL
        storage_client = self._get_storage_client()
        if storage_client and storage_client.provider_name != "local" and not stored.local_path:
            try:
                signed_url = await storage_client.get_signed_url(
                    bucket=stored.bucket,
                    key=stored.key,
                    expires_in=expires_in,
                )
                if signed_url:
                    return signed_url
            except Exception as e:
                logger.error(f"[WebAdapter] Failed to get signed URL: {e}")

        # Fallback to API URL
        return f"{self._file_base_url}/{file_id}/{stored.filename}"

    async def download_file_bytes(self, file_id: str) -> bytes | None:
        """
        Download file contents as bytes.

        For Supabase Storage, downloads from remote.
        For local storage, reads from disk.
        """
        stored = self._stored_files.get(file_id)
        if not stored:
            return None

        # If local path exists, read from disk
        if stored.local_path and stored.local_path.exists():
            return stored.local_path.read_bytes()

        # Try remote storage
        storage_client = self._get_storage_client()
        if storage_client and storage_client.provider_name != "local":
            try:
                result = await storage_client.download(
                    bucket=stored.bucket,
                    key=stored.key,
                )
                if result.success and result.data:
                    return result.data
            except Exception as e:
                logger.error(f"[WebAdapter] Failed to download from storage: {e}")

        return None

    async def download_file(
        self,
        file_info: dict[str, Any],
    ) -> Path | None:
        """
        Download a file from file_info.

        For web uploads, file_info may contain:
        - temp_path: Local temp file path (immediate uploads)
        - file_id: ID of file uploaded via /api/files/upload (may be in Supabase)
        """
        import tempfile

        # Check for local temp path first
        if file_info.get("temp_path"):
            return Path(file_info["temp_path"])

        # Check for file_id - may be local or in remote storage
        file_id = file_info.get("file_id")
        if file_id:
            # First check local uploaded files cache
            local_path = self._uploaded_files.get(file_id)
            if local_path and local_path.exists():
                return local_path

            # Check stored files (Supabase storage)
            stored = self._stored_files.get(file_id)
            if stored:
                # If local path exists and is valid, use it
                if stored.local_path and stored.local_path.exists():
                    return stored.local_path

                # Download from remote storage
                file_bytes = await self.download_file_bytes(file_id)
                if file_bytes:
                    # Save to temp file
                    suffix = Path(stored.filename).suffix if stored.filename else ""
                    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                        tmp.write(file_bytes)
                        tmp_path = Path(tmp.name)
                    logger.debug(f"[WebAdapter] Downloaded file {file_id} to temp: {tmp_path}")
                    return tmp_path

        return None

    # ========================================================================
    # USER MANAGEMENT
    # ========================================================================

    async def get_user(self, user_id: str) -> User | None:
        """Get user information."""
        return self._users.get(user_id)

    async def get_user_display_name(self, user_id: str) -> str:
        """Get user's display name."""
        user = self._users.get(user_id)
        if user:
            return user.display_name or user.name
        return user_id

    async def open_dm(self, user_id: str) -> str | None:
        """Open a DM channel (for web, this is just the user_id)."""
        return user_id

    async def get_file_info(self, file_id: str) -> dict[str, Any] | None:
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
        buttons: list[Button] | None = None,
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
