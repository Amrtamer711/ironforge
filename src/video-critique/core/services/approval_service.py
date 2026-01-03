"""
Approval Service for Video Critique.

Handles the multi-stage approval workflow:
1. Videographer uploads video
2. Reviewer approves/rejects
3. Head of Sales approves/returns
4. Task completed or returned for revision
"""

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.utils.logging import get_logger
from core.utils.time import now_uae
from db.database import db
from db.models import ApprovalWorkflow

if TYPE_CHECKING:
    from core.services.notification_service import NotificationService
    from core.services.video_service import VideoService

logger = get_logger(__name__)


# Rejection categories with descriptions
REJECTION_CATEGORIES = {
    "Previous Artwork is Visible": "When mocked up, the previous artwork is still visible from the sides, or the lights from it.",
    "Competitor Billboard Visible": "A competing advertiser's billboard is in the frame.",
    "Artwork Color is Incorrect": "The colour of the artwork appears different from the actual artwork itself & proof of play.",
    "Artwork Order is Incorrect": "The mocked up sequence of creatives plays in the wrong order, needs to be the same as proof of play.",
    "Environment Too Dark": "The scene lacks adequate lighting, causing the billboard and surroundings to appear dark. (Night)",
    "Environment Too Bright": "Excessive brightness or glare washes out the creative, reducing legibility. (Day)",
    "Blurry Artwork": "The billboard content appears out of focus in the video, impairing readability.",
    "Ghost Effect": "The cladding, when mocked up looks like cars going through it/lampposts when removed, can makes car disappear when passing through them.",
    "Cladding Lighting": "The external lighting on the billboard frame or cladding is dull/not accurate or off.",
    "Shaking Artwork or Cladding": "Structural vibration or instability results in a visibly shaky frame or creative playback.",
    "Shooting Angle": "The chosen camera angle distorts the artwork or makes it smaller (Billboard).",
    "Visible Strange Elements": "Unintended objects, example when mocked up cladding appearing in a different frame, artwork not going away on time etc.",
    "Transition Overlayer": "Video captures unintended transition animations or overlays, obscuring the main creative.",
    "Other": "Other reasons not covered by the above categories.",
}


@dataclass
class ApprovalDecision:
    """Result of an approval decision."""
    approved: bool
    rejection_reason: str | None = None
    rejection_class: str | None = None
    decided_by: str = ""
    decided_by_name: str = ""


@dataclass
class WorkflowState:
    """Current state of an approval workflow."""
    workflow_id: str
    task_number: int
    stage: str  # "reviewer", "hos", "completed", "rejected", "returned"
    reviewer_approved: bool = False
    hos_approved: bool = False
    version: int = 1
    created_at: datetime | None = None


class ApprovalService:
    """
    Service for managing approval workflows.

    Coordinates the approval process between videographers,
    reviewers, and head of sales.
    """

    def __init__(
        self,
        video_service: "VideoService | None" = None,
        notification_service: "NotificationService | None" = None,
    ):
        """
        Initialize approval service.

        Args:
            video_service: VideoService for file operations
            notification_service: NotificationService for sending notifications
        """
        self._video_service = video_service
        self._notification_service = notification_service
        self._db = db
        # In-memory cache for active workflows
        self._active_workflows: dict[str, ApprovalWorkflow] = {}

    # ========================================================================
    # WORKFLOW LIFECYCLE
    # ========================================================================

    async def start_workflow(
        self,
        task_number: int,
        folder_name: str,
        dropbox_path: str,
        videographer_id: str,
        videographer_name: str,
        version: int,
        uploaded_files: list[dict[str, Any]],
        task_data: dict[str, Any] | None = None,
    ) -> str:
        """
        Start a new approval workflow.

        Args:
            task_number: Task number
            folder_name: Dropbox folder name
            dropbox_path: Full Dropbox path
            videographer_id: Videographer's user ID
            videographer_name: Videographer's display name
            version: Version number
            uploaded_files: List of uploaded file info
            task_data: Additional task data

        Returns:
            Workflow ID
        """
        workflow_id = f"folder_{task_number}_{int(datetime.now().timestamp())}"

        workflow = ApprovalWorkflow(
            workflow_id=workflow_id,
            task_number=task_number,
            folder_name=folder_name,
            dropbox_path=dropbox_path,
            videographer_id=videographer_id,
            task_data=task_data or {},
            version_info={"version": version, "files": uploaded_files},
            status="pending_reviewer",
            created_at=now_uae(),
            updated_at=now_uae(),
        )

        # Save to database
        await self._db.create_workflow(workflow)

        # Cache active workflow
        self._active_workflows[workflow_id] = workflow

        logger.info(f"[ApprovalService] Started workflow {workflow_id} for task #{task_number}")
        return workflow_id

    async def get_workflow(self, workflow_id: str) -> ApprovalWorkflow | None:
        """
        Get a workflow by ID.

        Args:
            workflow_id: Workflow ID

        Returns:
            ApprovalWorkflow or None
        """
        # Check cache first
        if workflow_id in self._active_workflows:
            return self._active_workflows[workflow_id]

        # Load from database
        workflow = await self._db.get_workflow(workflow_id)
        if workflow:
            self._active_workflows[workflow_id] = workflow

        return workflow

    async def get_pending_workflows(self) -> list[ApprovalWorkflow]:
        """
        Get all pending workflows.

        Returns:
            List of pending ApprovalWorkflow objects
        """
        return await self._db.get_pending_workflows()

    async def complete_workflow(
        self,
        workflow_id: str,
        final_status: str = "completed",
    ) -> bool:
        """
        Mark a workflow as complete.

        Args:
            workflow_id: Workflow ID
            final_status: Final status (completed, rejected, returned)

        Returns:
            True if successful
        """
        workflow = await self.get_workflow(workflow_id)
        if not workflow:
            return False

        workflow.status = final_status
        workflow.updated_at = now_uae()

        success = await self._db.update_workflow(workflow_id, {
            "status": final_status,
            "updated_at": now_uae(),
        })

        if success:
            # Remove from cache
            self._active_workflows.pop(workflow_id, None)
            logger.info(f"[ApprovalService] Completed workflow {workflow_id} with status {final_status}")

        return success

    async def cancel_workflow(self, workflow_id: str) -> bool:
        """
        Cancel and delete a workflow.

        Args:
            workflow_id: Workflow ID

        Returns:
            True if successful
        """
        success = await self._db.delete_workflow(workflow_id)
        if success:
            self._active_workflows.pop(workflow_id, None)
            logger.info(f"[ApprovalService] Cancelled workflow {workflow_id}")
        return success

    # ========================================================================
    # REVIEWER STAGE
    # ========================================================================

    async def submit_for_review(
        self,
        workflow_id: str,
        reviewer_id: str,
        reviewer_msg_ts: str | None = None,
    ) -> bool:
        """
        Submit workflow for reviewer approval.

        Args:
            workflow_id: Workflow ID
            reviewer_id: Reviewer's user ID
            reviewer_msg_ts: Message timestamp for the review request

        Returns:
            True if successful
        """
        workflow = await self.get_workflow(workflow_id)
        if not workflow:
            return False

        updates = {
            "reviewer_id": reviewer_id,
            "reviewer_msg_ts": reviewer_msg_ts,
            "status": "pending_reviewer",
            "updated_at": now_uae(),
        }

        success = await self._db.update_workflow(workflow_id, updates)

        if success:
            # Update cache
            for key, value in updates.items():
                if hasattr(workflow, key):
                    setattr(workflow, key, value)

            logger.info(f"[ApprovalService] Workflow {workflow_id} submitted for review")

        return success

    async def handle_reviewer_decision(
        self,
        workflow_id: str,
        decision: ApprovalDecision,
    ) -> dict[str, Any]:
        """
        Handle reviewer's approval/rejection decision.

        Args:
            workflow_id: Workflow ID
            decision: ApprovalDecision with decision details

        Returns:
            Dict with next action and status
        """
        workflow = await self.get_workflow(workflow_id)
        if not workflow:
            return {"success": False, "error": "Workflow not found"}

        if decision.approved:
            # Reviewer approved - move to HoS stage
            updates = {
                "reviewer_approved": True,
                "status": "pending_hos",
                "updated_at": now_uae(),
            }
            await self._db.update_workflow(workflow_id, updates)

            # Move video to submitted folder
            if self._video_service:
                await self._video_service.move_pending_to_submitted(workflow.task_number)

            # Update task status
            version = workflow.version_info.get("version", 1)
            await self._update_task_status(
                workflow.task_number,
                "Submitted to Sales",
                version=version,
            )

            logger.info(f"[ApprovalService] Reviewer approved workflow {workflow_id}")

            return {
                "success": True,
                "action": "forward_to_hos",
                "task_number": workflow.task_number,
                "folder_name": workflow.folder_name,
            }

        else:
            # Reviewer rejected - send back to videographer
            await self._db.update_workflow(workflow_id, {
                "reviewer_approved": False,
                "status": "rejected",
                "updated_at": now_uae(),
            })

            # Move video to rejected folder
            if self._video_service:
                await self._video_service.move_pending_to_rejected(workflow.task_number)

            # Update task status with rejection info
            version = workflow.version_info.get("version", 1)

            # Classify rejection reason if needed
            rejection_class = decision.rejection_class
            if not rejection_class and decision.rejection_reason:
                rejection_class = await self._classify_rejection(decision.rejection_reason)

            await self._update_task_status(
                workflow.task_number,
                "Editing",
                version=version,
                rejection_reason=decision.rejection_reason,
                rejection_class=rejection_class,
                rejected_by="Reviewer",
            )

            # Complete workflow
            await self.complete_workflow(workflow_id, "rejected")

            logger.info(f"[ApprovalService] Reviewer rejected workflow {workflow_id}")

            return {
                "success": True,
                "action": "notify_rejection",
                "task_number": workflow.task_number,
                "rejection_reason": decision.rejection_reason,
                "rejection_class": rejection_class,
            }

    # ========================================================================
    # HEAD OF SALES STAGE
    # ========================================================================

    async def submit_to_hos(
        self,
        workflow_id: str,
        hos_id: str,
        hos_msg_ts: str | None = None,
    ) -> bool:
        """
        Submit workflow to Head of Sales for final approval.

        Args:
            workflow_id: Workflow ID
            hos_id: HoS user ID
            hos_msg_ts: Message timestamp

        Returns:
            True if successful
        """
        workflow = await self.get_workflow(workflow_id)
        if not workflow:
            return False

        updates = {
            "hos_id": hos_id,
            "hos_msg_ts": hos_msg_ts,
            "status": "pending_hos",
            "updated_at": now_uae(),
        }

        success = await self._db.update_workflow(workflow_id, updates)

        if success:
            logger.info(f"[ApprovalService] Workflow {workflow_id} submitted to HoS")

        return success

    async def handle_hos_decision(
        self,
        workflow_id: str,
        decision: ApprovalDecision,
    ) -> dict[str, Any]:
        """
        Handle HoS approval/return decision.

        Args:
            workflow_id: Workflow ID
            decision: ApprovalDecision with decision details

        Returns:
            Dict with next action and status
        """
        workflow = await self.get_workflow(workflow_id)
        if not workflow:
            return {"success": False, "error": "Workflow not found"}

        if decision.approved:
            # HoS approved - task complete
            updates = {
                "hos_approved": True,
                "status": "completed",
                "updated_at": now_uae(),
            }
            await self._db.update_workflow(workflow_id, updates)

            # Move video to accepted folder
            if self._video_service:
                await self._video_service.move_submitted_to_accepted(workflow.task_number)

            # Update task status
            version = workflow.version_info.get("version", 1)
            await self._update_task_status(
                workflow.task_number,
                "Done",
                version=version,
            )

            # Archive the task
            await self._db.archive_task(workflow.task_number)

            # Complete workflow
            await self.complete_workflow(workflow_id, "completed")

            logger.info(f"[ApprovalService] HoS approved workflow {workflow_id} - task complete")

            return {
                "success": True,
                "action": "complete_task",
                "task_number": workflow.task_number,
            }

        else:
            # HoS returned - send back to videographer
            await self._db.update_workflow(workflow_id, {
                "hos_approved": False,
                "status": "returned",
                "updated_at": now_uae(),
            })

            # Move video to returned folder
            if self._video_service:
                await self._video_service.move_submitted_to_returned(workflow.task_number)

            # Update task status
            version = workflow.version_info.get("version", 1)

            rejection_class = decision.rejection_class
            if not rejection_class and decision.rejection_reason:
                rejection_class = await self._classify_rejection(decision.rejection_reason)

            await self._update_task_status(
                workflow.task_number,
                "Returned",
                version=version,
                rejection_reason=decision.rejection_reason,
                rejection_class=rejection_class,
                rejected_by="Head of Sales",
            )

            # Complete workflow
            await self.complete_workflow(workflow_id, "returned")

            logger.info(f"[ApprovalService] HoS returned workflow {workflow_id}")

            return {
                "success": True,
                "action": "notify_return",
                "task_number": workflow.task_number,
                "rejection_reason": decision.rejection_reason,
            }

    # ========================================================================
    # WORKFLOW QUERIES
    # ========================================================================

    async def get_workflow_by_task(self, task_number: int) -> ApprovalWorkflow | None:
        """
        Get active workflow for a task.

        Args:
            task_number: Task number

        Returns:
            ApprovalWorkflow or None
        """
        # Check cache first
        for workflow in self._active_workflows.values():
            if workflow.task_number == task_number and workflow.status.startswith("pending"):
                return workflow

        # Query database
        workflows = await self._db.get_pending_workflows()
        for workflow in workflows:
            if workflow.task_number == task_number:
                self._active_workflows[workflow.workflow_id] = workflow
                return workflow

        return None

    async def get_workflow_state(self, workflow_id: str) -> WorkflowState | None:
        """
        Get the current state of a workflow.

        Args:
            workflow_id: Workflow ID

        Returns:
            WorkflowState or None
        """
        workflow = await self.get_workflow(workflow_id)
        if not workflow:
            return None

        # Determine stage from status
        if workflow.status == "completed":
            stage = "completed"
        elif workflow.status == "rejected":
            stage = "rejected"
        elif workflow.status == "returned":
            stage = "returned"
        elif workflow.hos_approved:
            stage = "completed"
        elif workflow.reviewer_approved:
            stage = "hos"
        else:
            stage = "reviewer"

        return WorkflowState(
            workflow_id=workflow_id,
            task_number=workflow.task_number,
            stage=stage,
            reviewer_approved=workflow.reviewer_approved,
            hos_approved=workflow.hos_approved,
            version=workflow.version_info.get("version", 1),
            created_at=workflow.created_at,
        )

    # ========================================================================
    # RECOVERY
    # ========================================================================

    async def recover_pending_workflows(self) -> int:
        """
        Recover pending workflows on startup.

        Returns:
            Number of workflows recovered
        """
        workflows = await self._db.get_pending_workflows()

        for workflow in workflows:
            self._active_workflows[workflow.workflow_id] = workflow

        count = len(workflows)
        if count > 0:
            logger.info(f"[ApprovalService] Recovered {count} pending workflows")

        return count

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    async def _update_task_status(
        self,
        task_number: int,
        status: str,
        version: int | None = None,
        rejection_reason: str | None = None,
        rejection_class: str | None = None,
        rejected_by: str | None = None,
    ) -> bool:
        """Update task status with version history."""
        from core.services.task_service import TaskService

        task_service = TaskService()
        return await task_service.update_status(
            task_number,
            status,
            version=version,
            rejection_reason=rejection_reason,
            rejection_class=rejection_class,
            rejected_by=rejected_by,
        )

    async def _classify_rejection(self, reason: str) -> str:
        """
        Classify a rejection reason into a predefined category.

        Uses LLM if available, otherwise returns 'Other'.

        Args:
            reason: Rejection reason text

        Returns:
            Category name
        """
        if not reason:
            return "Other"

        try:
            from integrations.llm import LLMClient, LLMMessage

            client = LLMClient.from_config()

            categories_list = "\n".join([
                f"- {cat}: {desc}"
                for cat, desc in REJECTION_CATEGORIES.items()
            ])

            prompt = f"""Classify the following video rejection comment into EXACTLY one of these categories:

Categories:
{categories_list}

Comment: "{reason}"

Return ONLY the category name, nothing else."""

            response = await client.complete(
                messages=[
                    LLMMessage.system("You are a video quality classifier. Respond only with the category name."),
                    LLMMessage.user(prompt),
                ],
            )

            category = response.content.strip()
            if category in REJECTION_CATEGORIES:
                return category

        except Exception as e:
            logger.warning(f"[ApprovalService] Error classifying rejection: {e}")

        return "Other"
