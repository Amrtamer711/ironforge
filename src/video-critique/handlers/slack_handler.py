"""
Slack Event Handler for Video Critique.

Processes Slack events (messages, file uploads, buttons, commands)
and routes them to the appropriate handlers.
"""

import json
from typing import Any

from integrations.channels import SlackAdapter
from core.llm import main_llm_loop
from core.utils.logging import get_logger
from handlers.tool_router import ToolRouter

logger = get_logger(__name__)


class SlackEventHandler:
    """
    Handles Slack events and routes them to appropriate handlers.

    Processes:
    - Message events (DMs and mentions)
    - File uploads (images for design requests, videos for approval)
    - Interactive components (buttons, modals)
    - Slash commands
    """

    def __init__(
        self,
        channel: SlackAdapter | None = None,
        tool_router: ToolRouter | None = None,
    ):
        """
        Initialize the Slack event handler.

        Args:
            channel: SlackAdapter for sending messages
            tool_router: ToolRouter for handling tool calls
        """
        self._channel = channel or SlackAdapter()
        self._tool_router = tool_router or ToolRouter()

    # =========================================================================
    # EVENT DISPATCH
    # =========================================================================

    async def handle_event(self, event: dict[str, Any]) -> dict[str, Any]:
        """
        Main event dispatcher.

        Args:
            event: Slack event payload

        Returns:
            Response dict with status and any data
        """
        event_type = event.get("type")

        logger.info(f"[SlackHandler] Received event type: {event_type}")

        try:
            if event_type == "message":
                return await self._handle_message_event(event)
            elif event_type == "app_mention":
                return await self._handle_mention_event(event)
            elif event_type == "file_shared":
                return await self._handle_file_shared(event)
            else:
                logger.debug(f"[SlackHandler] Unhandled event type: {event_type}")
                return {"status": "ignored", "reason": f"unhandled_event_type:{event_type}"}

        except Exception as e:
            logger.error(f"[SlackHandler] Error handling event: {e}")
            return {"status": "error", "error": str(e)}

    async def handle_interactive(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Handle interactive component actions.

        Args:
            payload: Slack interactive payload

        Returns:
            Response dict
        """
        payload_type = payload.get("type")

        logger.info(f"[SlackHandler] Received interactive type: {payload_type}")

        try:
            if payload_type == "block_actions":
                return await self._handle_block_actions(payload)
            elif payload_type == "view_submission":
                return await self._handle_view_submission(payload)
            elif payload_type == "shortcut":
                return await self._handle_shortcut(payload)
            else:
                logger.debug(f"[SlackHandler] Unhandled interactive type: {payload_type}")
                return {"status": "ignored"}

        except Exception as e:
            logger.error(f"[SlackHandler] Error handling interactive: {e}")
            return {"status": "error", "error": str(e)}

    async def handle_command(
        self,
        command: str,
        text: str,
        user_id: str,
        channel_id: str,
        response_url: str | None = None,
    ) -> dict[str, Any]:
        """
        Handle slash commands.

        Args:
            command: The command name (e.g., /log, /recent)
            text: Text following the command
            user_id: User who invoked the command
            channel_id: Channel where command was invoked
            response_url: URL for delayed responses

        Returns:
            Response dict
        """
        logger.info(f"[SlackHandler] Received command: {command} from {user_id}")

        try:
            # Map commands to actions
            if command in ["/log", "/design"]:
                # Start design request flow
                user_input = text or "I want to log a design request"
                return await self._process_message(
                    channel_id=channel_id,
                    user_id=user_id,
                    text=user_input,
                    response_url=response_url,
                )

            elif command == "/recent":
                # Export recent tasks
                return await self._process_message(
                    channel_id=channel_id,
                    user_id=user_id,
                    text="export current data",
                    response_url=response_url,
                )

            elif command == "/edit":
                # Edit a task
                if text and text.strip().isdigit():
                    user_input = f"edit task {text.strip()}"
                else:
                    user_input = text or "I want to edit a task"

                return await self._process_message(
                    channel_id=channel_id,
                    user_id=user_id,
                    text=user_input,
                    response_url=response_url,
                )

            elif command == "/delete":
                # Delete a task
                if text and text.strip().isdigit():
                    user_input = f"delete task {text.strip()}"
                else:
                    return {
                        "response_type": "ephemeral",
                        "text": "Please provide a task number: /delete <task_number>",
                    }

                return await self._process_message(
                    channel_id=channel_id,
                    user_id=user_id,
                    text=user_input,
                    response_url=response_url,
                )

            elif command == "/help":
                return {
                    "response_type": "ephemeral",
                    "text": self._get_help_text(),
                }

            else:
                return {
                    "response_type": "ephemeral",
                    "text": f"Unknown command: {command}",
                }

        except Exception as e:
            logger.error(f"[SlackHandler] Error handling command: {e}")
            return {
                "response_type": "ephemeral",
                "text": f"Error processing command: {str(e)}",
            }

    # =========================================================================
    # MESSAGE HANDLERS
    # =========================================================================

    async def _handle_message_event(self, event: dict[str, Any]) -> dict[str, Any]:
        """Handle message events."""
        # Skip bot messages
        if event.get("bot_id") or event.get("subtype") == "bot_message":
            return {"status": "ignored", "reason": "bot_message"}

        # Skip message edits/deletes
        if event.get("subtype") in ["message_changed", "message_deleted"]:
            return {"status": "ignored", "reason": event.get("subtype")}

        channel_id = event.get("channel", "")
        user_id = event.get("user", "")
        text = event.get("text", "")
        files = event.get("files", [])

        # Only respond to DMs or direct mentions
        channel_type = event.get("channel_type", "")
        if channel_type != "im":
            # Check if bot was mentioned
            if not self._is_bot_mentioned(text):
                return {"status": "ignored", "reason": "not_dm_or_mention"}

        return await self._process_message(
            channel_id=channel_id,
            user_id=user_id,
            text=text,
            files=files,
        )

    async def _handle_mention_event(self, event: dict[str, Any]) -> dict[str, Any]:
        """Handle app mention events."""
        channel_id = event.get("channel", "")
        user_id = event.get("user", "")
        text = event.get("text", "")
        files = event.get("files", [])

        # Remove bot mention from text
        text = self._remove_bot_mention(text)

        return await self._process_message(
            channel_id=channel_id,
            user_id=user_id,
            text=text,
            files=files,
        )

    async def _handle_file_shared(self, event: dict[str, Any]) -> dict[str, Any]:
        """Handle file shared events."""
        # File shared events are usually followed by a message event
        # that includes the file, so we typically ignore these
        return {"status": "ignored", "reason": "handled_with_message"}

    async def _process_message(
        self,
        channel_id: str,
        user_id: str,
        text: str,
        files: list[dict] | None = None,
        response_url: str | None = None,
    ) -> dict[str, Any]:
        """Process a message through the LLM loop."""
        # Get full user identity (email is primary identifier per platform pattern)
        slack_user_id, user_email, user_name = await self._get_user_identity(user_id)

        # Log identity resolution for debugging
        if user_email:
            logger.debug(f"[SlackHandler] Resolved {slack_user_id} to email: {user_email}")
        else:
            logger.warning(f"[SlackHandler] Could not resolve email for {slack_user_id}")

        # Check for image vs video files
        image_files = []
        video_files = []

        if files:
            for file in files:
                mimetype = file.get("mimetype", "")
                if mimetype.startswith("image/"):
                    image_files.append(file)
                elif mimetype.startswith("video/") or file.get("name", "").lower().endswith(
                    (".mp4", ".mov", ".avi", ".mkv", ".webm")
                ):
                    video_files.append(file)

        # If video files, this might be a video upload for approval
        if video_files and not text.strip():
            # Route to video upload flow
            return await self._handle_video_upload(
                channel_id=channel_id,
                user_id=user_id,
                user_name=user_name,
                files=video_files,
            )

        # Download image files if present (channel-specific operation)
        image_data: list[tuple[bytes, str]] = []
        if image_files:
            for file_info in image_files:
                result = await self._channel.download_file_bytes(file_info)
                if result:
                    image_data.append(result)
                else:
                    logger.warning(f"[SlackHandler] Failed to download image: {file_info.get('name')}")

        # Process through LLM - pass image bytes (channel-agnostic)
        response = await main_llm_loop(
            channel_id=channel_id,
            user_id=user_id,
            user_input=text,
            image_data=image_data or None,
            channel=self._channel,
            user_name=user_name,
            tool_router=self._tool_router,
        )

        return {
            "status": "success",
            "response": response,
        }

    # =========================================================================
    # INTERACTIVE HANDLERS
    # =========================================================================

    async def _handle_block_actions(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Handle button clicks and other block actions."""
        actions = payload.get("actions", [])
        user = payload.get("user", {})
        user_id = user.get("id", "")
        channel = payload.get("channel", {})
        channel_id = channel.get("id", "")

        for action in actions:
            action_id = action.get("action_id", "")
            value = action.get("value", "")

            logger.info(f"[SlackHandler] Button action: {action_id} = {value}")

            # Handle approval actions
            if action_id.startswith("approve_"):
                return await self._handle_approval_action(
                    action_id=action_id,
                    value=value,
                    user_id=user_id,
                    channel_id=channel_id,
                    payload=payload,
                )

            # Handle reject actions
            elif action_id.startswith("reject_"):
                return await self._handle_rejection_action(
                    action_id=action_id,
                    value=value,
                    user_id=user_id,
                    channel_id=channel_id,
                    payload=payload,
                )

            # Handle return actions
            elif action_id.startswith("return_"):
                return await self._handle_return_action(
                    action_id=action_id,
                    value=value,
                    user_id=user_id,
                    channel_id=channel_id,
                    payload=payload,
                )

        return {"status": "handled"}

    async def _handle_view_submission(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Handle modal form submissions."""
        view = payload.get("view", {})
        callback_id = view.get("callback_id", "")
        values = view.get("state", {}).get("values", {})

        logger.info(f"[SlackHandler] View submission: {callback_id}")

        if callback_id.startswith("rejection_modal_"):
            return await self._handle_rejection_modal(payload, values)

        return {"response_action": "clear"}

    async def _handle_shortcut(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Handle global and message shortcuts."""
        callback_id = payload.get("callback_id", "")
        logger.info(f"[SlackHandler] Shortcut: {callback_id}")
        return {"status": "handled"}

    # =========================================================================
    # APPROVAL FLOW HANDLERS
    # =========================================================================

    async def _handle_approval_action(
        self,
        action_id: str,
        value: str,
        user_id: str,
        channel_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle approval button clicks."""
        # Parse workflow ID from value
        workflow_id = value

        # Import here to avoid circular imports
        from core.workflows.approval_flow import ApprovalWorkflow

        workflow = ApprovalWorkflow()

        # Get user name
        user_name = ""
        try:
            user_info = await self._channel.get_user_info(user_id)
            user_name = user_info.get("display_name") or user_info.get("name", "")
        except Exception:
            pass

        if action_id == "approve_reviewer":
            result = await workflow.handle_reviewer_approve(
                workflow_id=workflow_id,
                reviewer_id=user_id,
                reviewer_name=user_name,
            )
        elif action_id == "approve_hos":
            result = await workflow.handle_hos_approve(
                workflow_id=workflow_id,
                hos_id=user_id,
                hos_name=user_name,
            )
        else:
            return {"status": "error", "error": f"Unknown action: {action_id}"}

        # Update the original message
        if result.success:
            await self._update_approval_message(
                payload=payload,
                new_text=result.message,
            )

        return {"status": "success" if result.success else "error"}

    async def _handle_rejection_action(
        self,
        action_id: str,
        value: str,
        user_id: str,
        channel_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle rejection button clicks - opens modal for reason."""
        workflow_id = value

        # Open rejection modal
        modal = self._build_rejection_modal(
            workflow_id=workflow_id,
            action_type="reject" if "reviewer" in action_id else "return",
            stage="reviewer" if "reviewer" in action_id else "hos",
        )

        trigger_id = payload.get("trigger_id")
        if trigger_id:
            await self._channel.open_modal(trigger_id, modal)

        return {"status": "modal_opened"}

    async def _handle_return_action(
        self,
        action_id: str,
        value: str,
        user_id: str,
        channel_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle HoS return button clicks."""
        return await self._handle_rejection_action(
            action_id=action_id,
            value=value,
            user_id=user_id,
            channel_id=channel_id,
            payload=payload,
        )

    async def _handle_rejection_modal(
        self,
        payload: dict[str, Any],
        values: dict[str, Any],
    ) -> dict[str, Any]:
        """Process rejection modal submission."""
        view = payload.get("view", {})
        callback_id = view.get("callback_id", "")
        private_metadata = json.loads(view.get("private_metadata", "{}"))

        workflow_id = private_metadata.get("workflow_id")
        stage = private_metadata.get("stage", "reviewer")

        user = payload.get("user", {})
        user_id = user.get("id", "")

        # Extract reason from modal
        reason = ""
        reason_class = ""
        for block_id, block_values in values.items():
            for action_id, action_value in block_values.items():
                if action_id == "rejection_reason":
                    reason = action_value.get("value", "")
                elif action_id == "rejection_class":
                    option = action_value.get("selected_option", {})
                    reason_class = option.get("value", "")

        # Get user name
        user_name = ""
        try:
            user_info = await self._channel.get_user_info(user_id)
            user_name = user_info.get("display_name") or user_info.get("name", "")
        except Exception:
            pass

        # Process rejection
        from core.workflows.approval_flow import ApprovalWorkflow

        workflow = ApprovalWorkflow()

        if stage == "reviewer":
            result = await workflow.handle_reviewer_reject(
                workflow_id=workflow_id,
                reviewer_id=user_id,
                reviewer_name=user_name,
                rejection_reason=reason,
                rejection_class=reason_class,
            )
        else:
            result = await workflow.handle_hos_return(
                workflow_id=workflow_id,
                hos_id=user_id,
                hos_name=user_name,
                return_reason=reason,
                return_class=reason_class,
            )

        return {"response_action": "clear"}

    # =========================================================================
    # VIDEO UPLOAD HANDLER
    # =========================================================================

    async def _handle_video_upload(
        self,
        channel_id: str,
        user_id: str,
        user_name: str | None,
        files: list[dict],
    ) -> dict[str, Any]:
        """Handle video file uploads for approval workflow."""
        from core.workflows.video_upload import VideoUploadWorkflow

        workflow = VideoUploadWorkflow()

        # The workflow needs task context - prompt user if not in context
        # For now, acknowledge and request task number
        await self._channel.send_message(
            channel_id=channel_id,
            content="I see you've uploaded a video file. "
            "Which task number is this for? Please reply with the task number.",
        )

        return {"status": "awaiting_task_number"}

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    async def _resolve_user_email(self, slack_user_id: str) -> str | None:
        """
        Resolve Slack user ID to email address.

        Uses platform pattern where email is the primary identifier.
        First checks ConfigService for database mappings, then falls back to Slack API.

        Args:
            slack_user_id: Slack user ID (e.g., U12345678)

        Returns:
            Email address or None if not found
        """
        # Check ConfigService for database mappings (cached with TTL)
        from core.services import get_config_service
        config_service = get_config_service()

        email = config_service.resolve_email_from_slack_id(slack_user_id)
        if email:
            return email

        # Fallback: Slack API users.info
        try:
            user_info = await self._channel.get_user_info(slack_user_id)
            if user_info:
                # Slack API returns email in profile
                email = user_info.get("profile", {}).get("email")
                if email:
                    return email
                # Some workspace configs return email at top level
                return user_info.get("email")
        except Exception as e:
            logger.warning(f"[SlackHandler] Failed to resolve email for {slack_user_id}: {e}")

        return None

    async def _get_user_identity(self, slack_user_id: str) -> tuple[str, str | None, str | None]:
        """
        Get full user identity from Slack user ID.

        Returns:
            Tuple of (user_id, email, display_name)
            - user_id is always set (to slack_user_id)
            - email may be None if resolution fails
            - display_name may be None if not available
        """
        email = await self._resolve_user_email(slack_user_id)
        display_name = None

        try:
            user_info = await self._channel.get_user_info(slack_user_id)
            if user_info:
                display_name = user_info.get("display_name") or user_info.get("name")
        except Exception:
            pass

        return (slack_user_id, email, display_name)

    def _is_bot_mentioned(self, text: str) -> bool:
        """Check if the bot was mentioned in the text."""
        import config

        bot_id = getattr(config, "SLACK_BOT_ID", "")
        if bot_id and f"<@{bot_id}>" in text:
            return True
        return False

    def _remove_bot_mention(self, text: str) -> str:
        """Remove bot mention from text."""
        import re
        import config

        bot_id = getattr(config, "SLACK_BOT_ID", "")
        if bot_id:
            text = re.sub(rf"<@{bot_id}>", "", text)
        return text.strip()

    def _get_help_text(self) -> str:
        """Get help text for slash commands."""
        return """*Video Critique Bot Commands*

*Design Requests:*
- `/log` or `/design` - Start a new design request
- `/recent` - Export recent task data
- `/edit <task_number>` - Edit an existing task
- `/delete <task_number>` - Delete a task

*Direct Message:*
You can also DM me directly to:
- Paste an email with design request details
- Upload an image/screenshot of a request
- Ask questions about tasks

*Admin Commands:*
Ask me to:
- "list videographers" - See all videographers
- "list locations" - See location mappings
- "add videographer [name] [email]" - Add a new videographer
- "add location [name] to [videographer]" - Map a location"""

    def _build_rejection_modal(
        self,
        workflow_id: str,
        action_type: str,
        stage: str,
    ) -> dict[str, Any]:
        """Build the rejection/return modal view."""
        title = "Reject Video" if action_type == "reject" else "Return for Revision"

        return {
            "type": "modal",
            "callback_id": f"rejection_modal_{workflow_id}",
            "private_metadata": json.dumps({
                "workflow_id": workflow_id,
                "stage": stage,
                "action_type": action_type,
            }),
            "title": {"type": "plain_text", "text": title},
            "submit": {"type": "plain_text", "text": "Submit"},
            "close": {"type": "plain_text", "text": "Cancel"},
            "blocks": [
                {
                    "type": "input",
                    "block_id": "rejection_class_block",
                    "label": {"type": "plain_text", "text": "Category"},
                    "element": {
                        "type": "static_select",
                        "action_id": "rejection_class",
                        "placeholder": {"type": "plain_text", "text": "Select category"},
                        "options": [
                            {"text": {"type": "plain_text", "text": "Technical Issue"}, "value": "technical"},
                            {"text": {"type": "plain_text", "text": "Content Issue"}, "value": "content"},
                            {"text": {"type": "plain_text", "text": "Quality Issue"}, "value": "quality"},
                            {"text": {"type": "plain_text", "text": "Missing Elements"}, "value": "missing"},
                            {"text": {"type": "plain_text", "text": "Other"}, "value": "other"},
                        ],
                    },
                },
                {
                    "type": "input",
                    "block_id": "rejection_reason_block",
                    "label": {"type": "plain_text", "text": "Details"},
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "rejection_reason",
                        "multiline": True,
                        "placeholder": {"type": "plain_text", "text": "Please describe what needs to be fixed..."},
                    },
                },
            ],
        }

    async def _update_approval_message(
        self,
        payload: dict[str, Any],
        new_text: str,
    ) -> None:
        """Update the approval message after action is taken."""
        channel = payload.get("channel", {})
        channel_id = channel.get("id", "")
        message = payload.get("message", {})
        message_ts = message.get("ts", "")

        if channel_id and message_ts:
            try:
                await self._channel.update_message(
                    channel_id=channel_id,
                    message_id=message_ts,
                    content=new_text,
                )
            except Exception as e:
                logger.error(f"[SlackHandler] Error updating message: {e}")
