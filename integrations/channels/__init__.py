"""
Unified Channel Abstraction Layer.

This module provides a platform-agnostic interface for messaging channels,
following the same pattern as integrations/llm/ for LLM providers.

Supported Channels:
- Slack (SlackAdapter)
- Web UI (WebAdapter) - Future
- Microsoft Teams (TeamsAdapter) - Future

Usage:
    from integrations.channels import get_channel, ChannelType

    # Get the active channel adapter
    channel = get_channel()

    # Send a message
    await channel.send_message(
        channel_id="C123456",
        content="Hello world",
        thread_id="optional_thread"
    )

    # Upload a file
    url = await channel.upload_file(
        channel_id="C123456",
        file_path="/path/to/file.pdf",
        filename="report.pdf",
        title="Monthly Report"
    )
"""

from .adapters import SlackAdapter, WebAdapter
from .base import (
    ActionResult,
    Attachment,
    Button,
    ButtonStyle,
    ChannelAdapter,
    ChannelType,
    FieldType,
    FileUpload,
    Message,
    MessageFormat,
    Modal,
    ModalField,
    User,
)
from .formatting import ChannelFormatter, to_html, to_plain, to_slack
from .router import ChannelRouter, get_channel, get_router, register_channel, set_channel

__all__ = [
    # Base types
    "ChannelAdapter",
    "ChannelType",
    "Message",
    "User",
    "FileUpload",
    "Button",
    "ButtonStyle",
    "ActionResult",
    "Modal",
    "ModalField",
    "FieldType",
    "Attachment",
    "MessageFormat",
    # Router
    "ChannelRouter",
    "get_channel",
    "set_channel",
    "register_channel",
    "get_router",
    # Formatting
    "ChannelFormatter",
    "to_slack",
    "to_html",
    "to_plain",
    # Adapters
    "SlackAdapter",
    "WebAdapter",
]
