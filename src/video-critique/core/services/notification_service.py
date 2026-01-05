"""
Notification Service for Video Critique.

Handles all notifications to users through various channels:
- Assignment notifications to videographers
- Review requests to reviewers
- Approval requests to Head of Sales
- Rejection/return notifications
- Status update notifications
"""

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any

from core.utils.logging import get_logger
from core.utils.time import format_uae_date

if TYPE_CHECKING:
    from integrations.channels import ChannelAdapter

logger = get_logger(__name__)


@dataclass
class NotificationResult:
    """Result of a notification operation."""
    success: bool
    message_id: str = ""
    channel_id: str = ""
    error: str = ""


class NotificationService:
    """
    Service for sending notifications to users.

    Abstracts channel-specific details and provides unified
    notification methods for the video production workflow.
    """

    def __init__(self, channel: "ChannelAdapter | None" = None):
        """
        Initialize notification service.

        Args:
            channel: Optional ChannelAdapter for sending messages
        """
        self._channel = channel

    async def _get_channel(self) -> "ChannelAdapter":
        """Get or create channel adapter."""
        if self._channel is None:
            from integrations.channels import get_channel
            self._channel = get_channel()
        return self._channel

    # ========================================================================
    # ASSIGNMENT NOTIFICATIONS
    # ========================================================================

    async def notify_assignment(
        self,
        videographer_id: str,
        task_number: int,
        brand: str,
        location: str,
        filming_date: date | None = None,
        campaign_start: date | None = None,
        campaign_end: date | None = None,
        reference_number: str | None = None,
    ) -> NotificationResult:
        """
        Notify a videographer of a new task assignment.

        Args:
            videographer_id: Videographer's user/channel ID
            task_number: Task number
            brand: Brand name
            location: Location
            filming_date: Assigned filming date
            campaign_start: Campaign start date
            campaign_end: Campaign end date
            reference_number: Reference number

        Returns:
            NotificationResult
        """
        try:
            channel = await self._get_channel()

            # Build message
            lines = [
                f"**New Task Assignment: Task #{task_number}**",
                "",
                f"**Brand:** {brand}",
                f"**Location:** {location}",
            ]

            if reference_number:
                lines.append(f"**Reference:** {reference_number}")

            if campaign_start:
                lines.append(f"**Campaign Start:** {format_uae_date(campaign_start)}")

            if campaign_end:
                lines.append(f"**Campaign End:** {format_uae_date(campaign_end)}")

            if filming_date:
                lines.append(f"**Filming Date:** {format_uae_date(filming_date)}")

            lines.extend([
                "",
                "Please review the task details and plan your filming schedule.",
            ])

            message = "\n".join(lines)

            result = await channel.send_message(
                channel_id=videographer_id,
                content=message,
            )

            return NotificationResult(
                success=True,
                message_id=result.message_id,
                channel_id=videographer_id,
            )

        except Exception as e:
            logger.error(f"[NotificationService] Error notifying assignment: {e}")
            return NotificationResult(success=False, error=str(e))

    # ========================================================================
    # REVIEWER NOTIFICATIONS
    # ========================================================================

    async def notify_reviewer(
        self,
        reviewer_id: str,
        task_number: int,
        folder_name: str,
        folder_url: str,
        videographer_name: str,
        task_data: dict[str, Any],
        uploaded_files: list[str],
        workflow_id: str,
    ) -> NotificationResult:
        """
        Send a video submission to reviewer for approval.

        Args:
            reviewer_id: Reviewer's user/channel ID
            task_number: Task number
            folder_name: Dropbox folder name
            folder_url: Shareable folder URL
            videographer_name: Uploader's name
            task_data: Task details
            uploaded_files: List of uploaded file names
            workflow_id: Workflow ID for button actions

        Returns:
            NotificationResult with message ID for updates
        """
        try:
            from integrations.channels import Button, ButtonStyle

            channel = await self._get_channel()

            # Build message
            lines = [
                f"**Video Review Request: Task #{task_number}**",
                "",
                f"**Brand:** {task_data.get('Brand', 'N/A')}",
                f"**Location:** {task_data.get('Location', 'N/A')}",
                f"**Reference:** {task_data.get('Reference Number', 'N/A')}",
                f"**Submitted by:** {videographer_name}",
                "",
                f"**Folder:** [{folder_name}]({folder_url})",
                "",
                "**Files uploaded:**",
            ]

            for filename in uploaded_files:
                lines.append(f"  - {filename}")

            message = "\n".join(lines)

            # Create approval buttons
            buttons = [
                Button(
                    action_id=f"reviewer_approve_{workflow_id}",
                    text="Approve",
                    style=ButtonStyle.PRIMARY,
                ),
                Button(
                    action_id=f"reviewer_reject_{workflow_id}",
                    text="Reject",
                    style=ButtonStyle.DANGER,
                ),
            ]

            result = await channel.send_message(
                channel_id=reviewer_id,
                content=message,
                buttons=buttons,
            )

            return NotificationResult(
                success=True,
                message_id=result.message_id,
                channel_id=reviewer_id,
            )

        except Exception as e:
            logger.error(f"[NotificationService] Error notifying reviewer: {e}")
            return NotificationResult(success=False, error=str(e))

    # ========================================================================
    # HEAD OF SALES NOTIFICATIONS
    # ========================================================================

    async def notify_hos(
        self,
        hos_id: str,
        task_number: int,
        folder_name: str,
        folder_url: str,
        videographer_name: str,
        task_data: dict[str, Any],
        workflow_id: str,
    ) -> NotificationResult:
        """
        Send approved video to Head of Sales for final approval.

        Args:
            hos_id: HoS user/channel ID
            task_number: Task number
            folder_name: Dropbox folder name
            folder_url: Shareable folder URL
            videographer_name: Videographer's name
            task_data: Task details
            workflow_id: Workflow ID for button actions

        Returns:
            NotificationResult with message ID
        """
        try:
            from integrations.channels import Button, ButtonStyle

            channel = await self._get_channel()

            # Build message
            lines = [
                f"**Final Approval Request: Task #{task_number}**",
                "",
                "This video has been reviewed and approved by the reviewer.",
                "",
                f"**Brand:** {task_data.get('Brand', 'N/A')}",
                f"**Location:** {task_data.get('Location', 'N/A')}",
                f"**Reference:** {task_data.get('Reference Number', 'N/A')}",
                f"**Sales Person:** {task_data.get('Sales Person', 'N/A')}",
                f"**Videographer:** {videographer_name}",
                "",
                f"**Folder:** [{folder_name}]({folder_url})",
            ]

            message = "\n".join(lines)

            # Create approval buttons
            buttons = [
                Button(
                    action_id=f"hos_approve_{workflow_id}",
                    text="Accept",
                    style=ButtonStyle.PRIMARY,
                ),
                Button(
                    action_id=f"hos_return_{workflow_id}",
                    text="Return for Revision",
                    style=ButtonStyle.DANGER,
                ),
            ]

            result = await channel.send_message(
                channel_id=hos_id,
                content=message,
                buttons=buttons,
            )

            return NotificationResult(
                success=True,
                message_id=result.message_id,
                channel_id=hos_id,
            )

        except Exception as e:
            logger.error(f"[NotificationService] Error notifying HoS: {e}")
            return NotificationResult(success=False, error=str(e))

    # ========================================================================
    # REJECTION/RETURN NOTIFICATIONS
    # ========================================================================

    async def notify_rejection(
        self,
        videographer_id: str,
        task_number: int,
        rejection_reason: str | None,
        rejection_class: str | None,
        rejected_by: str,
        task_data: dict[str, Any],
    ) -> NotificationResult:
        """
        Notify videographer of a video rejection.

        Args:
            videographer_id: Videographer's user/channel ID
            task_number: Task number
            rejection_reason: Detailed rejection reason
            rejection_class: Rejection category
            rejected_by: Who rejected (Reviewer/HoS)
            task_data: Task details

        Returns:
            NotificationResult
        """
        try:
            channel = await self._get_channel()

            # Build message
            lines = [
                f"**Video Rejected: Task #{task_number}**",
                "",
                f"Your video submission has been rejected by {rejected_by}.",
                "",
                f"**Brand:** {task_data.get('Brand', 'N/A')}",
                f"**Location:** {task_data.get('Location', 'N/A')}",
                "",
            ]

            if rejection_class:
                lines.append(f"**Category:** {rejection_class}")

            if rejection_reason:
                lines.extend([
                    "**Reason:**",
                    f"> {rejection_reason}",
                ])

            lines.extend([
                "",
                "Please address the issues and resubmit your video.",
            ])

            message = "\n".join(lines)

            result = await channel.send_message(
                channel_id=videographer_id,
                content=message,
            )

            return NotificationResult(
                success=True,
                message_id=result.message_id,
                channel_id=videographer_id,
            )

        except Exception as e:
            logger.error(f"[NotificationService] Error notifying rejection: {e}")
            return NotificationResult(success=False, error=str(e))

    async def notify_return(
        self,
        videographer_id: str,
        task_number: int,
        return_reason: str | None,
        return_class: str | None,
        task_data: dict[str, Any],
    ) -> NotificationResult:
        """
        Notify videographer of a video return from HoS.

        Args:
            videographer_id: Videographer's user/channel ID
            task_number: Task number
            return_reason: Reason for return
            return_class: Return category
            task_data: Task details

        Returns:
            NotificationResult
        """
        try:
            channel = await self._get_channel()

            # Build message
            lines = [
                f"**Video Returned: Task #{task_number}**",
                "",
                "Your video has been returned by Head of Sales for revision.",
                "",
                f"**Brand:** {task_data.get('Brand', 'N/A')}",
                f"**Location:** {task_data.get('Location', 'N/A')}",
                "",
            ]

            if return_class:
                lines.append(f"**Category:** {return_class}")

            if return_reason:
                lines.extend([
                    "**Reason:**",
                    f"> {return_reason}",
                ])

            lines.extend([
                "",
                "Please make the requested changes and resubmit.",
            ])

            message = "\n".join(lines)

            result = await channel.send_message(
                channel_id=videographer_id,
                content=message,
            )

            return NotificationResult(
                success=True,
                message_id=result.message_id,
                channel_id=videographer_id,
            )

        except Exception as e:
            logger.error(f"[NotificationService] Error notifying return: {e}")
            return NotificationResult(success=False, error=str(e))

    # ========================================================================
    # COMPLETION NOTIFICATIONS
    # ========================================================================

    async def notify_completion(
        self,
        videographer_id: str,
        task_number: int,
        task_data: dict[str, Any],
    ) -> NotificationResult:
        """
        Notify videographer that a task is complete.

        Args:
            videographer_id: Videographer's user/channel ID
            task_number: Task number
            task_data: Task details

        Returns:
            NotificationResult
        """
        try:
            channel = await self._get_channel()

            message = "\n".join([
                f"**Task Completed: Task #{task_number}**",
                "",
                "Congratulations! Your video has been approved and finalized.",
                "",
                f"**Brand:** {task_data.get('Brand', 'N/A')}",
                f"**Location:** {task_data.get('Location', 'N/A')}",
                f"**Reference:** {task_data.get('Reference Number', 'N/A')}",
            ])

            result = await channel.send_message(
                channel_id=videographer_id,
                content=message,
            )

            return NotificationResult(
                success=True,
                message_id=result.message_id,
                channel_id=videographer_id,
            )

        except Exception as e:
            logger.error(f"[NotificationService] Error notifying completion: {e}")
            return NotificationResult(success=False, error=str(e))

    # ========================================================================
    # MESSAGE UPDATES
    # ========================================================================

    async def update_approval_message(
        self,
        channel_id: str,
        message_id: str,
        status_text: str,
        actioned_by: str,
    ) -> bool:
        """
        Update an approval message after action taken.

        Args:
            channel_id: Channel ID
            message_id: Message timestamp/ID
            status_text: New status text
            actioned_by: User who took action

        Returns:
            True if successful
        """
        try:
            channel = await self._get_channel()

            message = f"{status_text}\n\nActioned by: {actioned_by}"

            # Update the message
            await channel.update_message(
                channel_id=channel_id,
                message_id=message_id,
                content=message,
            )

            return True

        except Exception as e:
            logger.error(f"[NotificationService] Error updating message: {e}")
            return False

    # ========================================================================
    # BULK NOTIFICATIONS
    # ========================================================================

    async def notify_daily_summary(
        self,
        channel_id: str,
        pending_tasks: int,
        assigned_today: int,
        completed_today: int,
    ) -> NotificationResult:
        """
        Send daily summary notification.

        Args:
            channel_id: Channel to send to
            pending_tasks: Number of pending tasks
            assigned_today: Tasks assigned today
            completed_today: Tasks completed today

        Returns:
            NotificationResult
        """
        try:
            channel = await self._get_channel()

            message = "\n".join([
                "**Daily Video Production Summary**",
                "",
                f"**Pending Tasks:** {pending_tasks}",
                f"**Assigned Today:** {assigned_today}",
                f"**Completed Today:** {completed_today}",
            ])

            result = await channel.send_message(
                channel_id=channel_id,
                content=message,
            )

            return NotificationResult(
                success=True,
                message_id=result.message_id,
                channel_id=channel_id,
            )

        except Exception as e:
            logger.error(f"[NotificationService] Error sending summary: {e}")
            return NotificationResult(success=False, error=str(e))
