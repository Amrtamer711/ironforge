"""
CRM Channels - Platform-agnostic messaging channel abstractions.

This library provides:
- Base types for channel adapters (ChannelAdapter, Message, Button, etc.)
- Text formatting utilities (markdown to Slack, HTML, plain text)
- Channel router for managing multiple adapters

Usage:
    from crm_channels import ChannelAdapter, Message, Button
    from crm_channels import ChannelFormatter, to_slack, to_html
    from crm_channels import ChannelRouter, get_channel

Example:
    # Implement a channel adapter
    class MyAdapter(ChannelAdapter):
        @property
        def channel_type(self) -> ChannelType:
            return ChannelType.WEB

        async def send_message(self, channel_id, content, **kwargs) -> Message:
            # Implementation...

    # Use the router
    router = ChannelRouter()
    router.register(MyAdapter())
    channel = router.get_active()
    await channel.send_message("user123", "Hello!")
"""

from crm_channels.base import (
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
from crm_channels.formatting import (
    ChannelFormatter,
    to_html,
    to_plain,
    to_slack,
    to_teams,
)
from crm_channels.router import (
    ChannelRouter,
    get_channel,
    get_router,
    register_channel,
    reset_router,
    set_channel,
)

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
    "reset_router",
    # Formatting
    "ChannelFormatter",
    "to_slack",
    "to_teams",
    "to_html",
    "to_plain",
]
