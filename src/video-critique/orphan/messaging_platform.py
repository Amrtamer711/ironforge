"""
Platform Abstraction Layer
===========================
Abstracts platform-specific client initialization and webhook event handling.
Switch platforms by changing PLATFORM_TYPE in config or environment.

Supported platforms: 'slack', 'teams'
"""

from typing import Dict, Any, Optional, Protocol
from logger import logger
import os


# ============================================================================
# PLATFORM PROTOCOL (Interface)
# ============================================================================

class MessagingPlatform(Protocol):
    """Protocol defining the interface all platforms must implement"""

    async def initialize(self) -> None:
        """Initialize platform client"""
        ...

    async def verify_request(self, request_data: Dict[str, Any], headers: Dict[str, str]) -> bool:
        """Verify incoming webhook request is authentic"""
        ...

    def normalize_event(self, raw_payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Normalize platform-specific event to common format.

        Returns:
            {
                'type': 'message' | 'file_upload' | 'button_click' | 'command',
                'user_id': str,
                'channel_id': str,
                'text': Optional[str],
                'files': Optional[List[Dict]],
                'action_id': Optional[str],
                'action_value': Optional[str],
                'trigger_id': Optional[str],
                'response_url': Optional[str],
                'raw': Dict  # Original payload
            }
        """
        ...


# ============================================================================
# SLACK IMPLEMENTATION
# ============================================================================

class SlackPlatform:
    """Slack platform implementation"""

    def __init__(self):
        self.client = None
        self.signature_verifier = None

    async def initialize(self) -> None:
        """Initialize Slack client"""
        from slack_sdk.web.async_client import AsyncWebClient
        from slack_sdk.signature import SignatureVerifier
        from config import SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET

        self.client = AsyncWebClient(token=SLACK_BOT_TOKEN)
        self.signature_verifier = SignatureVerifier(SLACK_SIGNING_SECRET)

        # Validate
        if not SLACK_BOT_TOKEN:
            raise ValueError("SLACK_BOT_TOKEN is required")
        if not SLACK_SIGNING_SECRET:
            raise ValueError("SLACK_SIGNING_SECRET is required")

        logger.info("✅ Slack platform initialized")

    async def verify_request(self, request_data: Dict[str, Any], headers: Dict[str, str]) -> bool:
        """Verify Slack request signature"""
        try:
            return self.signature_verifier.is_valid(
                body=request_data.get('body', ''),
                timestamp=headers.get('x-slack-request-timestamp', ''),
                signature=headers.get('x-slack-signature', '')
            )
        except Exception as e:
            logger.error(f"Slack signature verification failed: {e}")
            return False

    def normalize_event(self, raw_payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalize Slack event to common format"""

        # Handle URL verification
        if raw_payload.get("type") == "url_verification":
            return None  # Special case, handled separately

        # Event callback (messages, file uploads, etc.)
        if raw_payload.get("type") == "event_callback":
            event = raw_payload.get("event", {})

            return {
                'type': self._map_event_type(event.get('type')),
                'user_id': event.get('user'),
                'channel_id': event.get('channel'),
                'text': event.get('text'),
                'files': event.get('files'),
                'thread_ts': event.get('thread_ts'),
                'ts': event.get('ts'),
                'raw': raw_payload
            }

        # Interactive components (buttons, modals)
        if raw_payload.get("type") == "block_actions":
            action = raw_payload.get('actions', [{}])[0]

            return {
                'type': 'button_click',
                'user_id': raw_payload.get('user', {}).get('id'),
                'channel_id': raw_payload.get('channel', {}).get('id'),
                'action_id': action.get('action_id'),
                'action_value': action.get('value'),
                'trigger_id': raw_payload.get('trigger_id'),
                'response_url': raw_payload.get('response_url'),
                'raw': raw_payload
            }

        # View submissions (modals)
        if raw_payload.get("type") == "view_submission":
            return {
                'type': 'modal_submission',
                'user_id': raw_payload.get('user', {}).get('id'),
                'view_id': raw_payload.get('view', {}).get('id'),
                'view_values': raw_payload.get('view', {}).get('state', {}).get('values', {}),
                'private_metadata': raw_payload.get('view', {}).get('private_metadata'),
                'response_url': raw_payload.get('response_url'),
                'raw': raw_payload
            }

        # Slash commands
        if 'command' in raw_payload:
            return {
                'type': 'command',
                'user_id': raw_payload.get('user_id'),
                'channel_id': raw_payload.get('channel_id'),
                'command': raw_payload.get('command'),
                'text': raw_payload.get('text'),
                'trigger_id': raw_payload.get('trigger_id'),
                'response_url': raw_payload.get('response_url'),
                'raw': raw_payload
            }

        logger.warning(f"Unknown Slack event type: {raw_payload.get('type')}")
        return None

    def _map_event_type(self, slack_type: str) -> str:
        """Map Slack event types to common types"""
        mapping = {
            'message': 'message',
            'file_shared': 'file_upload',
            'app_mention': 'mention',
        }
        return mapping.get(slack_type, slack_type)


# ============================================================================
# TEAMS IMPLEMENTATION (Placeholder for future)
# ============================================================================

class TeamsPlatform:
    """Microsoft Teams platform implementation (placeholder)"""

    async def initialize(self) -> None:
        """Initialize Teams client"""
        # TODO: Implement Teams initialization
        # from botbuilder.core import BotFrameworkAdapter
        # self.adapter = BotFrameworkAdapter(...)
        raise NotImplementedError("Teams platform not yet implemented")

    async def verify_request(self, request_data: Dict[str, Any], headers: Dict[str, str]) -> bool:
        """Verify Teams request"""
        # TODO: Implement Teams JWT validation
        raise NotImplementedError("Teams verification not yet implemented")

    def normalize_event(self, raw_payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalize Teams event to common format"""
        # TODO: Implement Teams event normalization
        # activity = raw_payload
        # return {
        #     'type': activity.get('type'),  # 'message', 'invoke', etc.
        #     'user_id': activity.get('from', {}).get('id'),
        #     'channel_id': activity.get('conversation', {}).get('id'),
        #     ...
        # }
        raise NotImplementedError("Teams event normalization not yet implemented")


# ============================================================================
# PLATFORM FACTORY
# ============================================================================

def get_platform(platform_type: Optional[str] = None) -> MessagingPlatform:
    """
    Get platform instance based on config.

    Args:
        platform_type: 'slack' or 'teams' (defaults to env PLATFORM_TYPE or 'slack')

    Returns:
        Platform instance
    """
    platform_type = platform_type or os.getenv('PLATFORM_TYPE', 'slack').lower()

    platforms = {
        'slack': SlackPlatform,
        'teams': TeamsPlatform,
    }

    platform_class = platforms.get(platform_type)
    if not platform_class:
        raise ValueError(f"Unsupported platform: {platform_type}. Supported: {list(platforms.keys())}")

    return platform_class()


# ============================================================================
# GLOBAL PLATFORM INSTANCE
# ============================================================================

# Initialize the platform based on config
platform = get_platform()
