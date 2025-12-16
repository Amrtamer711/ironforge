"""
Channel router for managing multiple channel adapters.

Similar to how LLMClient routes to different providers, ChannelRouter
manages multiple channel adapters and provides a unified interface.
"""

import logging
from typing import TYPE_CHECKING, Optional

from .base import ChannelAdapter

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Global router instance
_router: Optional["ChannelRouter"] = None


class ChannelRouter:
    """
    Routes channel operations to the appropriate adapter.

    Usage:
        router = ChannelRouter()
        router.register(SlackAdapter(...))
        router.register(WebAdapter(...))

        # Set active channel for current context
        router.set_active("slack")

        # Or get specific adapter
        slack = router.get("slack")
    """

    def __init__(self):
        self._adapters: dict[str, ChannelAdapter] = {}
        self._active_channel: str | None = None

    def register(self, adapter: ChannelAdapter) -> None:
        """
        Register a channel adapter.

        Args:
            adapter: Channel adapter instance
        """
        key = adapter.channel_type.value
        self._adapters[key] = adapter
        logger.info(f"[ChannelRouter] Registered adapter: {adapter.name} ({key})")

        # Auto-set as active if it's the first one
        if self._active_channel is None:
            self._active_channel = key
            logger.info(f"[ChannelRouter] Set default active channel: {key}")

    def get(self, channel_type: str) -> ChannelAdapter | None:
        """
        Get a specific channel adapter.

        Args:
            channel_type: Channel type string (e.g., "slack", "web")

        Returns:
            Channel adapter or None if not registered
        """
        return self._adapters.get(channel_type)

    def get_active(self) -> ChannelAdapter | None:
        """
        Get the currently active channel adapter.

        Returns:
            Active channel adapter or None
        """
        if self._active_channel is None:
            return None
        return self._adapters.get(self._active_channel)

    def set_active(self, channel_type: str) -> bool:
        """
        Set the active channel.

        Args:
            channel_type: Channel type to activate

        Returns:
            True if successfully set
        """
        if channel_type not in self._adapters:
            logger.warning(f"[ChannelRouter] Cannot set active: {channel_type} not registered")
            return False

        self._active_channel = channel_type
        logger.info(f"[ChannelRouter] Active channel set to: {channel_type}")
        return True

    @property
    def active_channel_type(self) -> str | None:
        """Get the active channel type."""
        return self._active_channel

    def list_adapters(self) -> dict[str, str]:
        """
        List all registered adapters.

        Returns:
            Dict mapping channel_type to adapter name
        """
        return {k: v.name for k, v in self._adapters.items()}

    def has(self, channel_type: str) -> bool:
        """Check if a channel type is registered."""
        return channel_type in self._adapters


def get_router() -> ChannelRouter:
    """
    Get the global channel router instance.

    Creates one if it doesn't exist.
    """
    global _router
    if _router is None:
        _router = ChannelRouter()
    return _router


def get_channel(channel_type: str | None = None) -> ChannelAdapter | None:
    """
    Get a channel adapter.

    Args:
        channel_type: Specific channel type, or None for active channel

    Returns:
        Channel adapter or None
    """
    router = get_router()
    if channel_type:
        return router.get(channel_type)
    return router.get_active()


def set_channel(channel_type: str) -> bool:
    """
    Set the active channel.

    Args:
        channel_type: Channel type to activate

    Returns:
        True if successfully set
    """
    return get_router().set_active(channel_type)


def register_channel(adapter: ChannelAdapter) -> None:
    """
    Register a channel adapter globally.

    Args:
        adapter: Channel adapter to register
    """
    get_router().register(adapter)


def reset_router() -> None:
    """Reset the global router (mainly for testing)."""
    global _router
    _router = None
