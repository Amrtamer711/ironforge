"""
Approval Flow Workflow for Video Critique.

Orchestrates the multi-stage approval process:
1. Reviewer receives video for review
2. Reviewer approves -> Forward to Head of Sales
3. Reviewer rejects -> Notify videographer, return for revision
4. HoS approves -> Complete task
5. HoS returns -> Notify videographer, return for revision
"""

from dataclasses import dataclass
from typing import Any

from core.services.approval_service import ApprovalDecision, ApprovalService
from core.services.notification_service import NotificationService
from core.services.task_service import TaskService
from core.services.video_service import VideoService
from core.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ApprovalFlowResult:
    """Result of an approval action."""
    success: bool
    action: str = ""  # "approved", "rejected", "returned", "completed"
    task_number: int | None = None
    next_stage: str | None = None  # "hos", "videographer", "completed"
    message: str = ""
    error: str = ""


class ApprovalWorkflow:
    """
    Orchestrates the approval workflow.

    Handles the complete approval process from initial submission
    through final approval or rejection, coordinating between
    services and notifications.
    """

    def __init__(
        self,
        task_service: TaskService | None = None,
        video_service: VideoService | None = None,
        approval_service: ApprovalService | None = None,
        notification_service: NotificationService | None = None,
    ):
        """
        Initialize workflow with required services.

        Args:
            task_service: TaskService instance
            video_service: VideoService instance
            approval_service: ApprovalService instance
            notification_service: NotificationService instance
        """
        self._task_service = task_service or TaskService()
        self._video_service = video_service or VideoService()
        self._approval_service = approval_service or ApprovalService(
            video_service=self._video_service,
        )
        self._notification_service = notification_service or NotificationService()

    # ========================================================================
    # REVIEWER ACTIONS
    # ========================================================================

    async def handle_reviewer_approve(
        self,
        workflow_id: str,
        reviewer_id: str,
        reviewer_name: str,
        hos_id: str | None = None,
    ) -> ApprovalFlowResult:
        """
        Handle reviewer approval action.

        Approves the video and forwards to Head of Sales.

        Args:
            workflow_id: Workflow ID
            reviewer_id: Reviewer's user ID
            reviewer_name: Reviewer's display name
            hos_id: Head of Sales user ID for notification

        Returns:
            ApprovalFlowResult
        """
        try:
            # Get workflow
            workflow = await self._approval_service.get_workflow(workflow_id)
            if not workflow:
                return ApprovalFlowResult(
                    success=False,
                    error=f"Workflow {workflow_id} not found",
                )

            # Process approval
            decision = ApprovalDecision(
                approved=True,
                decided_by=reviewer_id,
                decided_by_name=reviewer_name,
            )

            result = await self._approval_service.handle_reviewer_decision(
                workflow_id, decision
            )

            if not result.get("success"):
                return ApprovalFlowResult(
                    success=False,
                    error=result.get("error", "Approval failed"),
                )

            # Forward to HoS if ID provided
            if hos_id:
                folder_url = await self._video_service.get_folder_shared_link(
                    workflow.task_number, "submitted"
                )

                await self._notification_service.notify_hos(
                    hos_id=hos_id,
                    task_number=workflow.task_number,
                    folder_name=workflow.folder_name,
                    folder_url=folder_url,
                    videographer_name=workflow.videographer_id,
                    task_data=workflow.task_data,
                    workflow_id=workflow_id,
                )

                # Update workflow with HoS info
                await self._approval_service.submit_to_hos(workflow_id, hos_id)

            logger.info(
                f"[ApprovalWorkflow] Reviewer {reviewer_name} approved task #{workflow.task_number}"
            )

            return ApprovalFlowResult(
                success=True,
                action="approved",
                task_number=workflow.task_number,
                next_stage="hos",
                message=f"Video approved by {reviewer_name}. Forwarded to Head of Sales.",
            )

        except Exception as e:
            logger.error(f"[ApprovalWorkflow] Reviewer approval error: {e}")
            return ApprovalFlowResult(success=False, error=str(e))

    async def handle_reviewer_reject(
        self,
        workflow_id: str,
        reviewer_id: str,
        reviewer_name: str,
        rejection_reason: str | None = None,
        rejection_class: str | None = None,
    ) -> ApprovalFlowResult:
        """
        Handle reviewer rejection action.

        Rejects the video and notifies the videographer.

        Args:
            workflow_id: Workflow ID
            reviewer_id: Reviewer's user ID
            reviewer_name: Reviewer's display name
            rejection_reason: Reason for rejection
            rejection_class: Category of rejection

        Returns:
            ApprovalFlowResult
        """
        try:
            # Get workflow
            workflow = await self._approval_service.get_workflow(workflow_id)
            if not workflow:
                return ApprovalFlowResult(
                    success=False,
                    error=f"Workflow {workflow_id} not found",
                )

            # Process rejection
            decision = ApprovalDecision(
                approved=False,
                rejection_reason=rejection_reason,
                rejection_class=rejection_class,
                decided_by=reviewer_id,
                decided_by_name=reviewer_name,
            )

            result = await self._approval_service.handle_reviewer_decision(
                workflow_id, decision
            )

            if not result.get("success"):
                return ApprovalFlowResult(
                    success=False,
                    error=result.get("error", "Rejection failed"),
                )

            # Notify videographer
            videographer_id = workflow.videographer_id
            if videographer_id:
                await self._notification_service.notify_rejection(
                    videographer_id=videographer_id,
                    task_number=workflow.task_number,
                    rejection_reason=rejection_reason,
                    rejection_class=result.get("rejection_class", rejection_class),
                    rejected_by="Reviewer",
                    task_data=workflow.task_data,
                )

            logger.info(
                f"[ApprovalWorkflow] Reviewer {reviewer_name} rejected task #{workflow.task_number}"
            )

            return ApprovalFlowResult(
                success=True,
                action="rejected",
                task_number=workflow.task_number,
                next_stage="videographer",
                message=f"Video rejected by {reviewer_name}. Videographer notified.",
            )

        except Exception as e:
            logger.error(f"[ApprovalWorkflow] Reviewer rejection error: {e}")
            return ApprovalFlowResult(success=False, error=str(e))

    # ========================================================================
    # HEAD OF SALES ACTIONS
    # ========================================================================

    async def handle_hos_approve(
        self,
        workflow_id: str,
        hos_id: str,
        hos_name: str,
    ) -> ApprovalFlowResult:
        """
        Handle Head of Sales approval action.

        Approves the video and completes the task.

        Args:
            workflow_id: Workflow ID
            hos_id: HoS user ID
            hos_name: HoS display name

        Returns:
            ApprovalFlowResult
        """
        try:
            # Get workflow
            workflow = await self._approval_service.get_workflow(workflow_id)
            if not workflow:
                return ApprovalFlowResult(
                    success=False,
                    error=f"Workflow {workflow_id} not found",
                )

            # Process approval
            decision = ApprovalDecision(
                approved=True,
                decided_by=hos_id,
                decided_by_name=hos_name,
            )

            result = await self._approval_service.handle_hos_decision(
                workflow_id, decision
            )

            if not result.get("success"):
                return ApprovalFlowResult(
                    success=False,
                    error=result.get("error", "Approval failed"),
                )

            # Notify videographer of completion
            videographer_id = workflow.videographer_id
            if videographer_id:
                await self._notification_service.notify_completion(
                    videographer_id=videographer_id,
                    task_number=workflow.task_number,
                    task_data=workflow.task_data,
                )

            logger.info(
                f"[ApprovalWorkflow] HoS {hos_name} approved task #{workflow.task_number} - COMPLETE"
            )

            return ApprovalFlowResult(
                success=True,
                action="completed",
                task_number=workflow.task_number,
                next_stage="completed",
                message=f"Video approved by {hos_name}. Task #{workflow.task_number} completed!",
            )

        except Exception as e:
            logger.error(f"[ApprovalWorkflow] HoS approval error: {e}")
            return ApprovalFlowResult(success=False, error=str(e))

    async def handle_hos_return(
        self,
        workflow_id: str,
        hos_id: str,
        hos_name: str,
        return_reason: str | None = None,
        return_class: str | None = None,
    ) -> ApprovalFlowResult:
        """
        Handle Head of Sales return action.

        Returns the video for revision and notifies the videographer.

        Args:
            workflow_id: Workflow ID
            hos_id: HoS user ID
            hos_name: HoS display name
            return_reason: Reason for return
            return_class: Category of return

        Returns:
            ApprovalFlowResult
        """
        try:
            # Get workflow
            workflow = await self._approval_service.get_workflow(workflow_id)
            if not workflow:
                return ApprovalFlowResult(
                    success=False,
                    error=f"Workflow {workflow_id} not found",
                )

            # Process return
            decision = ApprovalDecision(
                approved=False,
                rejection_reason=return_reason,
                rejection_class=return_class,
                decided_by=hos_id,
                decided_by_name=hos_name,
            )

            result = await self._approval_service.handle_hos_decision(
                workflow_id, decision
            )

            if not result.get("success"):
                return ApprovalFlowResult(
                    success=False,
                    error=result.get("error", "Return failed"),
                )

            # Notify videographer
            videographer_id = workflow.videographer_id
            if videographer_id:
                await self._notification_service.notify_return(
                    videographer_id=videographer_id,
                    task_number=workflow.task_number,
                    return_reason=return_reason,
                    return_class=return_class,
                    task_data=workflow.task_data,
                )

            logger.info(
                f"[ApprovalWorkflow] HoS {hos_name} returned task #{workflow.task_number}"
            )

            return ApprovalFlowResult(
                success=True,
                action="returned",
                task_number=workflow.task_number,
                next_stage="videographer",
                message=f"Video returned by {hos_name}. Videographer notified.",
            )

        except Exception as e:
            logger.error(f"[ApprovalWorkflow] HoS return error: {e}")
            return ApprovalFlowResult(success=False, error=str(e))

    # ========================================================================
    # WORKFLOW QUERIES
    # ========================================================================

    async def get_workflow_status(
        self,
        workflow_id: str,
    ) -> dict[str, Any]:
        """
        Get the current status of a workflow.

        Args:
            workflow_id: Workflow ID

        Returns:
            Dict with workflow status details
        """
        state = await self._approval_service.get_workflow_state(workflow_id)
        if not state:
            return {"found": False}

        return {
            "found": True,
            "workflow_id": state.workflow_id,
            "task_number": state.task_number,
            "stage": state.stage,
            "reviewer_approved": state.reviewer_approved,
            "hos_approved": state.hos_approved,
            "version": state.version,
            "created_at": state.created_at.isoformat() if state.created_at else None,
        }

    async def get_pending_for_reviewer(
        self,
        reviewer_id: str,
    ) -> list[dict[str, Any]]:
        """
        Get all workflows pending reviewer action.

        Args:
            reviewer_id: Reviewer's user ID

        Returns:
            List of pending workflow summaries
        """
        workflows = await self._approval_service.get_pending_workflows()

        pending = []
        for w in workflows:
            if w.status == "pending_reviewer" and w.reviewer_id == reviewer_id:
                pending.append({
                    "workflow_id": w.workflow_id,
                    "task_number": w.task_number,
                    "folder_name": w.folder_name,
                    "videographer": w.videographer_id,
                    "created_at": w.created_at.isoformat() if w.created_at else None,
                })

        return pending

    async def get_pending_for_hos(
        self,
        hos_id: str,
    ) -> list[dict[str, Any]]:
        """
        Get all workflows pending HoS action.

        Args:
            hos_id: HoS user ID

        Returns:
            List of pending workflow summaries
        """
        workflows = await self._approval_service.get_pending_workflows()

        pending = []
        for w in workflows:
            if w.status == "pending_hos" and w.hos_id == hos_id:
                pending.append({
                    "workflow_id": w.workflow_id,
                    "task_number": w.task_number,
                    "folder_name": w.folder_name,
                    "videographer": w.videographer_id,
                    "created_at": w.created_at.isoformat() if w.created_at else None,
                })

        return pending

    # ========================================================================
    # RECOVERY
    # ========================================================================

    async def recover_pending_workflows(self) -> int:
        """
        Recover pending workflows on service startup.

        Returns:
            Number of recovered workflows
        """
        return await self._approval_service.recover_pending_workflows()
