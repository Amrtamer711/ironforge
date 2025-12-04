"""
Slack channel adapter implementation.

This adapter implements the ChannelAdapter interface for Slack,
wrapping the slack_sdk client with the unified interface.
"""

import logging
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import aiohttp
from slack_sdk.web.async_client import AsyncWebClient

from ..base import (
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
from ..formatting import ChannelFormatter

logger = logging.getLogger(__name__)


class SlackAdapter(ChannelAdapter):
    """
    Slack implementation of the channel adapter.

    Wraps slack_sdk's AsyncWebClient with the unified channel interface.
    """

    def __init__(self, client: AsyncWebClient, bot_token: str):
        """
        Initialize Slack adapter.

        Args:
            client: Slack AsyncWebClient instance
            bot_token: Slack bot token for file downloads
        """
        self._client = client
        self._bot_token = bot_token
        self._user_cache: Dict[str, User] = {}

    @property
    def channel_type(self) -> ChannelType:
        return ChannelType.SLACK

    @property
    def name(self) -> str:
        return "Slack"

    # ========================================================================
    # MESSAGING
    # ========================================================================

    async def send_message(
        self,
        channel_id: str,
        content: str,
        *,
        thread_id: Optional[str] = None,
        buttons: Optional[List[Button]] = None,
        attachments: Optional[List[Attachment]] = None,
        format: MessageFormat = MessageFormat.MARKDOWN,
        ephemeral: bool = False,
        user_id: Optional[str] = None,
    ) -> Message:
        """Send a message to a Slack channel."""
        # Format text for Slack
        formatted_text = self.format_text(content, format)

        # Build blocks if we have buttons
        blocks = None
        if buttons:
            blocks = self._build_blocks(formatted_text, buttons)

        try:
            if ephemeral and user_id:
                response = await self._client.chat_postEphemeral(
                    channel=channel_id,
                    user=user_id,
                    text=formatted_text,
                    blocks=blocks,
                    thread_ts=thread_id,
                )
                # Ephemeral messages don't have a ts
                return Message(
                    id=str(uuid.uuid4()),
                    channel_id=channel_id,
                    content=content,
                    user_id="bot",
                    thread_id=thread_id,
                    metadata={"ephemeral": True},
                )
            else:
                response = await self._client.chat_postMessage(
                    channel=channel_id,
                    text=formatted_text,
                    blocks=blocks,
                    thread_ts=thread_id,
                )
                return Message(
                    id=response["ts"],
                    channel_id=channel_id,
                    content=content,
                    user_id="bot",
                    thread_id=thread_id or response.get("thread_ts"),
                    timestamp=response["ts"],
                    platform_message_id=response["ts"],
                    metadata={"response": dict(response)},
                )

        except Exception as e:
            logger.error(f"[SlackAdapter] Failed to send message: {e}")
            raise

    async def update_message(
        self,
        channel_id: str,
        message_id: str,
        content: str,
        *,
        buttons: Optional[List[Button]] = None,
        format: MessageFormat = MessageFormat.MARKDOWN,
    ) -> Message:
        """Update an existing Slack message."""
        formatted_text = self.format_text(content, format)

        blocks = None
        if buttons:
            blocks = self._build_blocks(formatted_text, buttons)

        try:
            response = await self._client.chat_update(
                channel=channel_id,
                ts=message_id,
                text=formatted_text,
                blocks=blocks,
            )
            return Message(
                id=response["ts"],
                channel_id=channel_id,
                content=content,
                timestamp=response["ts"],
                platform_message_id=response["ts"],
            )

        except Exception as e:
            logger.error(f"[SlackAdapter] Failed to update message: {e}")
            raise

    async def delete_message(
        self,
        channel_id: str,
        message_id: str,
    ) -> bool:
        """Delete a Slack message."""
        try:
            await self._client.chat_delete(
                channel=channel_id,
                ts=message_id,
            )
            return True
        except Exception as e:
            logger.error(f"[SlackAdapter] Failed to delete message: {e}")
            return False

    # ========================================================================
    # REACTIONS
    # ========================================================================

    async def add_reaction(
        self,
        channel_id: str,
        message_id: str,
        reaction: str,
    ) -> bool:
        """Add a reaction to a Slack message."""
        try:
            await self._client.reactions_add(
                channel=channel_id,
                timestamp=message_id,
                name=reaction,
            )
            return True
        except Exception as e:
            # Ignore "already_reacted" errors
            if "already_reacted" in str(e):
                return True
            logger.error(f"[SlackAdapter] Failed to add reaction: {e}")
            return False

    async def remove_reaction(
        self,
        channel_id: str,
        message_id: str,
        reaction: str,
    ) -> bool:
        """Remove a reaction from a Slack message."""
        try:
            await self._client.reactions_remove(
                channel=channel_id,
                timestamp=message_id,
                name=reaction,
            )
            return True
        except Exception as e:
            logger.error(f"[SlackAdapter] Failed to remove reaction: {e}")
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
    ) -> FileUpload:
        """Upload a file to Slack."""
        path = Path(file_path)
        if not path.exists():
            return FileUpload(
                success=False,
                error=f"File not found: {file_path}",
            )

        actual_filename = filename or path.name
        formatted_comment = self.format_text(comment) if comment else None

        try:
            response = await self._client.files_upload_v2(
                channel=channel_id,
                file=str(path),
                filename=actual_filename,
                title=title or actual_filename,
                initial_comment=formatted_comment,
                thread_ts=thread_id,
            )

            # Extract file info from response
            file_info = response.get("file", {})
            return FileUpload(
                success=True,
                url=file_info.get("permalink"),
                file_id=file_info.get("id"),
                filename=actual_filename,
            )

        except Exception as e:
            logger.error(f"[SlackAdapter] Failed to upload file: {e}")
            return FileUpload(
                success=False,
                error=str(e),
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
    ) -> FileUpload:
        """Upload file from bytes to Slack."""
        formatted_comment = self.format_text(comment) if comment else None

        try:
            response = await self._client.files_upload_v2(
                channel=channel_id,
                content=file_bytes,
                filename=filename,
                title=title or filename,
                initial_comment=formatted_comment,
                thread_ts=thread_id,
            )

            file_info = response.get("file", {})
            return FileUpload(
                success=True,
                url=file_info.get("permalink"),
                file_id=file_info.get("id"),
                filename=filename,
            )

        except Exception as e:
            logger.error(f"[SlackAdapter] Failed to upload file bytes: {e}")
            return FileUpload(
                success=False,
                error=str(e),
            )

    async def download_file(
        self,
        file_info: Dict[str, Any],
    ) -> Optional[Path]:
        """Download a file from Slack."""
        url = file_info.get("url_private_download") or file_info.get("url_private")
        if not url:
            logger.error("[SlackAdapter] No download URL in file_info")
            return None

        filename = file_info.get("name", "downloaded_file")

        try:
            async with aiohttp.ClientSession() as session:
                headers = {"Authorization": f"Bearer {self._bot_token}"}
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        logger.error(f"[SlackAdapter] Download failed: {response.status}")
                        return None

                    # Create temp file
                    suffix = Path(filename).suffix
                    with tempfile.NamedTemporaryFile(
                        delete=False,
                        suffix=suffix,
                        prefix="slack_download_"
                    ) as tmp:
                        content = await response.read()
                        tmp.write(content)
                        return Path(tmp.name)

        except Exception as e:
            logger.error(f"[SlackAdapter] Failed to download file: {e}")
            return None

    # ========================================================================
    # USER MANAGEMENT
    # ========================================================================

    async def get_user(self, user_id: str) -> Optional[User]:
        """Get user information from Slack."""
        # Check cache first
        if user_id in self._user_cache:
            return self._user_cache[user_id]

        try:
            response = await self._client.users_info(user=user_id)
            user_data = response.get("user", {})
            profile = user_data.get("profile", {})

            user = User(
                id=user_id,
                name=user_data.get("name", user_id),
                display_name=profile.get("display_name") or profile.get("real_name"),
                email=profile.get("email"),
                avatar_url=profile.get("image_192"),
                is_bot=user_data.get("is_bot", False),
                slack_id=user_id,
                metadata={"raw": dict(user_data)},
            )

            # Cache the result
            self._user_cache[user_id] = user
            return user

        except Exception as e:
            logger.error(f"[SlackAdapter] Failed to get user {user_id}: {e}")
            return None

    async def get_user_display_name(self, user_id: str) -> str:
        """Get user's display name, falling back to ID."""
        user = await self.get_user(user_id)
        if user:
            return user.display_name or user.name or user_id
        return user_id

    async def open_dm(self, user_id: str) -> Optional[str]:
        """Open a DM channel with a user."""
        try:
            response = await self._client.conversations_open(users=[user_id])
            channel = response.get("channel", {})
            return channel.get("id")
        except Exception as e:
            logger.error(f"[SlackAdapter] Failed to open DM with {user_id}: {e}")
            return None

    # ========================================================================
    # INTERACTIVE COMPONENTS
    # ========================================================================

    async def open_modal(
        self,
        trigger_id: str,
        modal: Modal,
    ) -> bool:
        """Open a modal dialog in Slack."""
        try:
            view = self._build_modal_view(modal)
            await self._client.views_open(
                trigger_id=trigger_id,
                view=view,
            )
            return True
        except Exception as e:
            logger.error(f"[SlackAdapter] Failed to open modal: {e}")
            return False

    async def respond_to_action(
        self,
        response_url: str,
        content: str,
        *,
        replace_original: bool = True,
        buttons: Optional[List[Button]] = None,
    ) -> bool:
        """Respond to an interactive action via response URL."""
        formatted_text = self.format_text(content)

        blocks = None
        if buttons:
            blocks = self._build_blocks(formatted_text, buttons)

        payload = {
            "text": formatted_text,
            "replace_original": replace_original,
        }
        if blocks:
            payload["blocks"] = blocks

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(response_url, json=payload) as response:
                    return response.status == 200
        except Exception as e:
            logger.error(f"[SlackAdapter] Failed to respond to action: {e}")
            return False

    # ========================================================================
    # FORMATTING
    # ========================================================================

    def format_text(
        self,
        text: str,
        source_format: MessageFormat = MessageFormat.MARKDOWN,
    ) -> str:
        """Convert text to Slack's mrkdwn format."""
        if not text:
            return text
        if source_format == MessageFormat.PLAIN:
            return text
        return ChannelFormatter.markdown_to_slack(text)

    def format_user_mention(self, user_id: str) -> str:
        """Format a user mention for Slack."""
        return f"<@{user_id}>"

    def format_channel_mention(self, channel_id: str) -> str:
        """Format a channel mention for Slack."""
        return f"<#{channel_id}>"

    # ========================================================================
    # SLACK-SPECIFIC HELPERS
    # ========================================================================

    def _build_blocks(
        self,
        text: str,
        buttons: Optional[List[Button]] = None,
    ) -> List[Dict[str, Any]]:
        """Build Slack blocks from text and buttons."""
        blocks = []

        # Add text section
        if text:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": text,
                },
            })

        # Add buttons if provided
        if buttons:
            elements = []
            for btn in buttons:
                element = {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": btn.text,
                    },
                    "action_id": btn.action_id,
                }

                if btn.value:
                    element["value"] = btn.value

                # Map button style
                if btn.style == ButtonStyle.PRIMARY:
                    element["style"] = "primary"
                elif btn.style == ButtonStyle.DANGER:
                    element["style"] = "danger"

                # Add confirmation dialog if specified
                if btn.confirm_title and btn.confirm_text:
                    element["confirm"] = {
                        "title": {"type": "plain_text", "text": btn.confirm_title},
                        "text": {"type": "mrkdwn", "text": btn.confirm_text},
                        "confirm": {"type": "plain_text", "text": "Confirm"},
                        "deny": {"type": "plain_text", "text": "Cancel"},
                    }

                elements.append(element)

            blocks.append({
                "type": "actions",
                "elements": elements,
            })

        return blocks

    def _build_modal_view(self, modal: Modal) -> Dict[str, Any]:
        """Build a Slack modal view from Modal config."""
        blocks = []

        for field in modal.fields:
            block = self._build_field_block(field)
            if block:
                blocks.append(block)

        view = {
            "type": "modal",
            "callback_id": modal.modal_id,
            "title": {
                "type": "plain_text",
                "text": modal.title[:24],  # Slack limit
            },
            "submit": {
                "type": "plain_text",
                "text": modal.submit_text,
            },
            "close": {
                "type": "plain_text",
                "text": modal.cancel_text,
            },
            "blocks": blocks,
        }

        if modal.private_metadata:
            view["private_metadata"] = modal.private_metadata

        return view

    def _build_field_block(self, field: ModalField) -> Optional[Dict[str, Any]]:
        """Build a Slack input block from ModalField."""
        element: Dict[str, Any] = {}

        if field.field_type == FieldType.TEXT:
            element = {
                "type": "plain_text_input",
                "action_id": field.field_id,
            }
            if field.placeholder:
                element["placeholder"] = {
                    "type": "plain_text",
                    "text": field.placeholder,
                }
            if field.default_value:
                element["initial_value"] = field.default_value
            if field.max_length:
                element["max_length"] = field.max_length

        elif field.field_type == FieldType.TEXTAREA:
            element = {
                "type": "plain_text_input",
                "action_id": field.field_id,
                "multiline": True,
            }
            if field.placeholder:
                element["placeholder"] = {
                    "type": "plain_text",
                    "text": field.placeholder,
                }
            if field.default_value:
                element["initial_value"] = field.default_value

        elif field.field_type == FieldType.SELECT and field.options:
            element = {
                "type": "static_select",
                "action_id": field.field_id,
                "options": [
                    {
                        "text": {"type": "plain_text", "text": opt["text"]},
                        "value": opt["value"],
                    }
                    for opt in field.options
                ],
            }
            if field.placeholder:
                element["placeholder"] = {
                    "type": "plain_text",
                    "text": field.placeholder,
                }

        else:
            return None

        # Use custom block_id if provided, otherwise generate from field_id
        block_id = field.block_id if field.block_id else f"block_{field.field_id}"

        return {
            "type": "input",
            "block_id": block_id,
            "label": {
                "type": "plain_text",
                "text": field.label,
            },
            "element": element,
            "optional": not field.required,
        }

    # ========================================================================
    # SLACK-SPECIFIC METHODS (Not in base interface)
    # ========================================================================

    async def get_file_info(self, file_id: str) -> Optional[Dict[str, Any]]:
        """
        Get file information from Slack.

        This is a Slack-specific method not in the base interface.
        """
        try:
            response = await self._client.files_info(file=file_id)
            return response.get("file")
        except Exception as e:
            logger.error(f"[SlackAdapter] Failed to get file info: {e}")
            return None

    @property
    def client(self) -> AsyncWebClient:
        """
        Get the underlying Slack client.

        Use this for Slack-specific operations not covered by the interface.
        """
        return self._client
