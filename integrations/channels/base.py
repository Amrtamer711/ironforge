"""
Base abstractions for channel adapters.

This module defines the core interfaces that all channel implementations
must follow, similar to how integrations/llm/base.py defines LLM interfaces.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union


class ChannelType(str, Enum):
    """Supported channel types."""
    SLACK = "slack"
    WEB = "web"
    TEAMS = "teams"
    API = "api"  # Direct API calls (no UI)


class ButtonStyle(str, Enum):
    """Button styling options."""
    PRIMARY = "primary"      # Blue/highlighted
    SECONDARY = "secondary"  # Grey/neutral
    DANGER = "danger"        # Red/destructive
    SUCCESS = "success"      # Green/positive


class FieldType(str, Enum):
    """Form field types for modals."""
    TEXT = "text"
    TEXTAREA = "textarea"
    SELECT = "select"
    MULTISELECT = "multiselect"
    DATE = "date"
    CHECKBOX = "checkbox"


class MessageFormat(str, Enum):
    """Message formatting types."""
    PLAIN = "plain"      # Plain text
    MARKDOWN = "markdown"  # Standard markdown
    RICH = "rich"        # Platform-specific rich formatting


@dataclass
class User:
    """Platform-agnostic user representation."""
    id: str
    name: str
    display_name: Optional[str] = None
    email: Optional[str] = None
    avatar_url: Optional[str] = None
    is_bot: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    # Platform-specific IDs (for cross-referencing)
    slack_id: Optional[str] = None
    teams_id: Optional[str] = None
    web_user_id: Optional[str] = None


@dataclass
class Attachment:
    """File or media attachment."""
    url: str
    filename: str
    mimetype: Optional[str] = None
    size: Optional[int] = None
    title: Optional[str] = None
    thumbnail_url: Optional[str] = None


@dataclass
class Message:
    """Platform-agnostic message representation."""
    id: str
    channel_id: str
    content: str
    user_id: Optional[str] = None
    thread_id: Optional[str] = None
    timestamp: Optional[str] = None
    attachments: list[Attachment] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    # For tracking platform-specific IDs
    platform_message_id: Optional[str] = None  # e.g., Slack's ts


@dataclass
class Button:
    """Interactive button element."""
    action_id: str
    text: str
    value: Optional[str] = None
    style: ButtonStyle = ButtonStyle.SECONDARY
    confirm_title: Optional[str] = None  # Optional confirmation dialog
    confirm_text: Optional[str] = None


@dataclass
class ModalField:
    """Form field for modals."""
    field_id: str
    label: str
    field_type: FieldType = FieldType.TEXT
    placeholder: Optional[str] = None
    default_value: Optional[str] = None
    required: bool = False
    options: Optional[list[dict[str, str]]] = None  # For select fields
    max_length: Optional[int] = None
    multiline: bool = False
    block_id: Optional[str] = None  # Custom block ID (for Slack submission handling)


@dataclass
class Modal:
    """Modal/dialog configuration."""
    modal_id: str
    title: str
    fields: list[ModalField] = field(default_factory=list)
    submit_text: str = "Submit"
    cancel_text: str = "Cancel"
    private_metadata: Optional[str] = None  # For passing data through


@dataclass
class ActionResult:
    """Result from handling an interactive action."""
    success: bool
    action_id: str
    user_id: str
    channel_id: str
    value: Optional[str] = None
    form_values: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    # For tracking the source
    message_id: Optional[str] = None
    thread_id: Optional[str] = None
    response_url: Optional[str] = None  # For deferred responses


@dataclass
class FileUpload:
    """File upload result."""
    success: bool
    url: Optional[str] = None
    file_id: Optional[str] = None
    filename: Optional[str] = None
    error: Optional[str] = None


class ChannelAdapter(ABC):
    """
    Abstract base class for channel adapters.

    All channel implementations (Slack, Web, Teams) must implement this interface.
    This provides a consistent API regardless of the underlying platform.
    """

    @property
    @abstractmethod
    def channel_type(self) -> ChannelType:
        """Return the channel type identifier."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for this channel."""
        pass

    @property
    def supports_threads(self) -> bool:
        """Whether this channel supports threaded conversations."""
        return True

    @property
    def supports_reactions(self) -> bool:
        """Whether this channel supports message reactions."""
        return True

    @property
    def supports_buttons(self) -> bool:
        """Whether this channel supports interactive buttons."""
        return True

    @property
    def supports_modals(self) -> bool:
        """Whether this channel supports modal dialogs."""
        return True

    @property
    def supports_file_upload(self) -> bool:
        """Whether this channel supports file uploads."""
        return True

    # ========================================================================
    # MESSAGING
    # ========================================================================

    @abstractmethod
    async def send_message(
        self,
        channel_id: str,
        content: str,
        *,
        thread_id: Optional[str] = None,
        buttons: Optional[list[Button]] = None,
        attachments: Optional[list[Attachment]] = None,
        format: MessageFormat = MessageFormat.MARKDOWN,
        ephemeral: bool = False,
        user_id: Optional[str] = None,  # For ephemeral messages
    ) -> Message:
        """
        Send a message to a channel.

        Args:
            channel_id: Target channel/conversation ID
            content: Message content (markdown supported)
            thread_id: Optional thread ID for threaded replies
            buttons: Optional interactive buttons
            attachments: Optional file/media attachments
            format: Message format type
            ephemeral: If True, only visible to specified user
            user_id: Required for ephemeral messages

        Returns:
            Message object with platform-specific ID
        """
        pass

    @abstractmethod
    async def update_message(
        self,
        channel_id: str,
        message_id: str,
        content: str,
        *,
        buttons: Optional[list[Button]] = None,
        format: MessageFormat = MessageFormat.MARKDOWN,
    ) -> Message:
        """
        Update an existing message.

        Args:
            channel_id: Channel containing the message
            message_id: Platform-specific message ID (e.g., Slack ts)
            content: New message content
            buttons: Updated buttons (None to remove)
            format: Message format type

        Returns:
            Updated Message object
        """
        pass

    @abstractmethod
    async def delete_message(
        self,
        channel_id: str,
        message_id: str,
    ) -> bool:
        """
        Delete a message.

        Args:
            channel_id: Channel containing the message
            message_id: Platform-specific message ID

        Returns:
            True if successfully deleted
        """
        pass

    # ========================================================================
    # REACTIONS
    # ========================================================================

    @abstractmethod
    async def add_reaction(
        self,
        channel_id: str,
        message_id: str,
        reaction: str,
    ) -> bool:
        """
        Add a reaction to a message.

        Args:
            channel_id: Channel containing the message
            message_id: Platform-specific message ID
            reaction: Reaction emoji name (without colons)

        Returns:
            True if successfully added
        """
        pass

    @abstractmethod
    async def remove_reaction(
        self,
        channel_id: str,
        message_id: str,
        reaction: str,
    ) -> bool:
        """
        Remove a reaction from a message.

        Args:
            channel_id: Channel containing the message
            message_id: Platform-specific message ID
            reaction: Reaction emoji name (without colons)

        Returns:
            True if successfully removed
        """
        pass

    # ========================================================================
    # FILE HANDLING
    # ========================================================================

    @abstractmethod
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
        Upload a file to a channel.

        Args:
            channel_id: Target channel
            file_path: Path to file on disk
            filename: Display filename (defaults to actual filename)
            title: File title/description
            comment: Initial comment with the file
            thread_id: Optional thread for the upload

        Returns:
            FileUpload result with URL and file ID
        """
        pass

    @abstractmethod
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
        """
        Upload file from bytes.

        Args:
            channel_id: Target channel
            file_bytes: File content as bytes
            filename: Display filename
            title: File title/description
            comment: Initial comment with the file
            thread_id: Optional thread for the upload
            mimetype: File MIME type

        Returns:
            FileUpload result with URL and file ID
        """
        pass

    @abstractmethod
    async def download_file(
        self,
        file_info: dict[str, Any],
    ) -> Optional[Path]:
        """
        Download a file from the channel.

        Args:
            file_info: Platform-specific file metadata dict

        Returns:
            Path to downloaded temporary file, or None if failed
        """
        pass

    # ========================================================================
    # USER MANAGEMENT
    # ========================================================================

    @abstractmethod
    async def get_user(self, user_id: str) -> Optional[User]:
        """
        Get user information.

        Args:
            user_id: Platform-specific user ID

        Returns:
            User object or None if not found
        """
        pass

    @abstractmethod
    async def get_user_display_name(self, user_id: str) -> str:
        """
        Get user's display name (fallback to ID if not found).

        Args:
            user_id: Platform-specific user ID

        Returns:
            Display name string
        """
        pass

    @abstractmethod
    async def open_dm(self, user_id: str) -> Optional[str]:
        """
        Open a direct message channel with a user.

        Args:
            user_id: Platform-specific user ID

        Returns:
            DM channel ID or None if failed
        """
        pass

    # ========================================================================
    # INTERACTIVE COMPONENTS
    # ========================================================================

    @abstractmethod
    async def open_modal(
        self,
        trigger_id: str,
        modal: Modal,
    ) -> bool:
        """
        Open a modal dialog.

        Args:
            trigger_id: Platform-specific trigger ID from interaction
            modal: Modal configuration

        Returns:
            True if successfully opened
        """
        pass

    @abstractmethod
    async def respond_to_action(
        self,
        response_url: str,
        content: str,
        *,
        replace_original: bool = True,
        buttons: Optional[list[Button]] = None,
    ) -> bool:
        """
        Respond to an interactive action via response URL.

        Args:
            response_url: Platform-specific response URL
            content: Response content
            replace_original: Whether to replace the original message
            buttons: Optional updated buttons

        Returns:
            True if successfully responded
        """
        pass

    # ========================================================================
    # FORMATTING
    # ========================================================================

    @abstractmethod
    def format_text(
        self,
        text: str,
        source_format: MessageFormat = MessageFormat.MARKDOWN,
    ) -> str:
        """
        Convert text to platform-specific format.

        Args:
            text: Input text (typically markdown)
            source_format: Format of input text

        Returns:
            Platform-formatted text
        """
        pass

    @abstractmethod
    def format_user_mention(self, user_id: str) -> str:
        """
        Format a user mention for this platform.

        Args:
            user_id: User ID to mention

        Returns:
            Platform-specific mention string
        """
        pass

    @abstractmethod
    def format_channel_mention(self, channel_id: str) -> str:
        """
        Format a channel mention for this platform.

        Args:
            channel_id: Channel ID to mention

        Returns:
            Platform-specific mention string
        """
        pass

    # ========================================================================
    # CAPABILITY CHECKS
    # ========================================================================

    def get_capabilities(self) -> dict[str, bool]:
        """Get all capabilities of this channel."""
        return {
            "threads": self.supports_threads,
            "reactions": self.supports_reactions,
            "buttons": self.supports_buttons,
            "modals": self.supports_modals,
            "file_upload": self.supports_file_upload,
        }
