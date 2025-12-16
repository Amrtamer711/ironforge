"""
Channel Identity Management.

This module provides a unified interface for recording channel user interactions
(Slack, Teams, etc.) and checking authorization status.

All channel adapters can use this to:
1. Record user interactions (track who's using the bot)
2. Check if a user is authorized (when strict mode is enabled)
3. Get linked platform user info if available

Usage:
    from integrations.channel_identity import ChannelIdentity

    # Record interaction (fire-and-forget, doesn't block bot)
    await ChannelIdentity.record(
        provider='slack',
        provider_user_id='U12345',
        provider_team_id='T67890',
        email='user@company.com',
        display_name='John Doe'
    )

    # Check authorization (when strict mode is enabled)
    auth = await ChannelIdentity.check('slack', 'U12345')
    if not auth['is_authorized']:
        # Handle unauthorized user
"""

import asyncio
import logging
import os
from typing import Any, Optional

import aiohttp

logger = logging.getLogger("proposal-bot")

# UI service URL - where channel identity APIs live
_ui_service_url: Optional[str] = None


def _get_ui_url() -> str:
    """Get the UI service URL."""
    global _ui_service_url
    if _ui_service_url is None:
        # In production, services communicate via internal URLs
        # In dev, default to localhost
        _ui_service_url = os.getenv("UI_SERVICE_URL", "http://localhost:3005")
    return _ui_service_url


class ChannelIdentity:
    """
    Unified channel identity management.

    Provides static methods for recording and checking channel user identities.
    All methods are designed to be non-blocking and fail gracefully.
    """

    @staticmethod
    async def record(
        provider: str,
        provider_user_id: str,
        provider_team_id: Optional[str] = None,
        email: Optional[str] = None,
        display_name: Optional[str] = None,
        real_name: Optional[str] = None,
        avatar_url: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Record a channel user interaction.

        This should be called whenever a user interacts with the bot.
        It updates last_seen_at and caches user profile info.

        Args:
            provider: Channel provider ('slack', 'teams', etc.)
            provider_user_id: User ID from the provider
            provider_team_id: Workspace/tenant ID from the provider
            email: User's email (for auto-linking)
            display_name: User's display name
            real_name: User's real name
            avatar_url: User's avatar URL

        Returns:
            Dict with:
            - recorded: bool - whether the record was saved
            - is_authorized: bool - whether user can use the bot
            - is_linked: bool - whether linked to platform user
            - platform_user_id: str or None - linked platform user ID
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{_get_ui_url()}/api/channel-identity/record",
                    json={
                        "provider": provider,
                        "provider_user_id": provider_user_id,
                        "provider_team_id": provider_team_id,
                        "email": email,
                        "display_name": display_name,
                        "real_name": real_name,
                        "avatar_url": avatar_url,
                    },
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.debug(f"[ChannelIdentity] Record failed: {response.status}")
                        return {"recorded": False, "is_authorized": True}

        except asyncio.TimeoutError:
            logger.debug("[ChannelIdentity] Record timeout - continuing")
            return {"recorded": False, "is_authorized": True}
        except Exception as e:
            logger.debug(f"[ChannelIdentity] Record error: {e}")
            return {"recorded": False, "is_authorized": True}

    @staticmethod
    async def check(provider: str, provider_user_id: str) -> dict[str, Any]:
        """
        Check if a channel user is authorized.

        Use this when strict mode is enabled to verify users before
        allowing them to use the bot.

        Args:
            provider: Channel provider ('slack', 'teams', etc.)
            provider_user_id: User ID from the provider

        Returns:
            Dict with:
            - is_authorized: bool
            - reason: str ('open_access', 'linked_active', 'blocked', etc.)
            - platform_user_id: str or None
            - platform_user_name: str or None
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{_get_ui_url()}/api/channel-identity/check/{provider}/{provider_user_id}",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        return {"is_authorized": True, "reason": "check_failed"}

        except Exception as e:
            logger.debug(f"[ChannelIdentity] Check error: {e}")
            return {"is_authorized": True, "reason": "check_failed"}

    @staticmethod
    def record_fire_and_forget(
        provider: str,
        provider_user_id: str,
        provider_team_id: Optional[str] = None,
        email: Optional[str] = None,
        display_name: Optional[str] = None,
        real_name: Optional[str] = None,
        avatar_url: Optional[str] = None,
    ) -> None:
        """
        Record interaction without waiting for result.

        Use this when you don't need the response and want to
        avoid any potential delay in the bot's response.
        """
        asyncio.create_task(
            ChannelIdentity.record(
                provider=provider,
                provider_user_id=provider_user_id,
                provider_team_id=provider_team_id,
                email=email,
                display_name=display_name,
                real_name=real_name,
                avatar_url=avatar_url,
            )
        )
