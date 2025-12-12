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
    user_id: Optional[str] = None
    local_path: Optional[Path] = None  # For local storage fallback
    created_at: datetime = field(default_factory=datetime.now)


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
        self._sessions: Dict[str, WebSession] = {}
        self._file_base_url = file_base_url
        self._users: Dict[str, User] = {}
        self._uploaded_files: Dict[str, Path] = {}  # Legacy: file_id -> path (for local storage)
        self._stored_files: Dict[str, StoredFileInfo] = {}  # file_id -> StoredFileInfo

        # Callbacks for streaming (set by the API layer)
        self._stream_callbacks: Dict[str, Callable[[str], Awaitable[None]]] = {}

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
        bucket: str = "uploads",
        user_id: Optional[str] = None,
        document_type: Optional[str] = None,
        bo_id: Optional[int] = None,
        proposal_id: Optional[int] = None,
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
            from utils.files import calculate_sha256, get_file_extension
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

                    # Create download URL (goes through our API for auth)
                    url = f"{self._file_base_url}/{file_id}/{actual_filename}"

                    logger.info(f"[WebAdapter] File uploaded to {storage_client.provider_name}: {actual_filename} -> {bucket}/{storage_key} (hash={file_hash[:16] if file_hash else 'N/A'}...)")

                    # Add message with attachment if comment provided
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
        bucket: str = "uploads",
        user_id: Optional[str] = None,
        document_type: Optional[str] = None,
        bo_id: Optional[int] = None,
        proposal_id: Optional[int] = None,
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
            from utils.files import calculate_sha256, get_file_extension
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

                    url = f"{self._file_base_url}/{file_id}/{filename}"
                    logger.info(f"[WebAdapter] File bytes uploaded to {storage_client.provider_name}: {filename} -> {bucket}/{storage_key} (hash={file_hash[:16] if file_hash else 'N/A'}...)")

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

    def get_file_path(self, file_id: str) -> Optional[Path]:
        """Get the local path for an uploaded file (for local storage only)."""
        # Check new stored files first
        stored = self._stored_files.get(file_id)
        if stored and stored.local_path:
            return stored.local_path
        # Legacy fallback
        return self._uploaded_files.get(file_id)

    def get_stored_file_info(self, file_id: str) -> Optional[StoredFileInfo]:
        """Get storage metadata for a file."""
        return self._stored_files.get(file_id)

    async def get_file_download_url(self, file_id: str, expires_in: int = 3600) -> Optional[str]:
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

    async def download_file_bytes(self, file_id: str) -> Optional[bytes]:
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
