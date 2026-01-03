"""
Unified Channel Abstraction Layer.

This module provides a platform-agnostic interface for messaging channels,
using crm-channels for base types and providing sales-module specific adapters.

Supported Channels:
- Slack (SlackAdapter)
- Web UI (WebAdapter)
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

# Import adapters from local implementations (they have sales-specific dependencies)
from integrations.channels.adapters import SlackAdapter, WebAdapter

# Re-export base types from crm-channels
from crm_channels import (
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
    # Router
    ChannelRouter,
    get_channel,
    get_router,
    register_channel,
    set_channel,
    # Formatting
    ChannelFormatter,
    to_html,
    to_plain,
    to_slack,
)

__all__ = [
    # Base types (from crm-channels)
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
    # Router (from crm-channels)
    "ChannelRouter",
    "get_channel",
    "set_channel",
    "register_channel",
    "get_router",
    # Formatting (from crm-channels)
    "ChannelFormatter",
    "to_slack",
    "to_html",
    "to_plain",
    # Adapters (sales-module specific)
    "SlackAdapter",
    "WebAdapter",
]
