"""
Unified Channel Abstraction Layer for Video Critique.

This module provides a platform-agnostic interface for messaging channels,
using crm-channels for base types and providing video-critique specific adapters.

Supported Channels:
- Slack (SlackAdapter) - Direct Slack integration
- Web UI (WebAdapter) - Web chat through unified-ui

Usage:
    from integrations.channels import get_channel, ChannelType

    # Get the active channel adapter
    channel = get_channel()

    # Send a message
    await channel.send_message(
        channel_id="C123456",
        content="Task #123 created successfully",
        buttons=[
            Button(action_id="edit_task", text="Edit Task"),
            Button(action_id="delete_task", text="Delete", style=ButtonStyle.DANGER),
        ]
    )
"""

# Import adapters from local implementations
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
    # Adapters (video-critique specific)
    "SlackAdapter",
    "WebAdapter",
]
