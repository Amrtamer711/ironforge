"""
Video Upload Workflow for Video Critique.

Orchestrates the complete video upload process:
1. Validate upload request
2. Process files (videos or ZIP archives)
3. Upload to Dropbox
4. Update task status
5. Start approval workflow
6. Notify reviewer
"""

from dataclasses import dataclass
from typing import Any

from core.services.approval_service import ApprovalService
from core.services.notification_service import NotificationService
from core.services.task_service import TaskService
from core.services.video_service import VideoService, UploadResult
from core.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class WorkflowResult:
    """Result of a video upload workflow execution."""
    success: bool
    task_number: int | None = None
    version: int = 0
    folder_name: str = ""
    workflow_id: str = ""
    files_uploaded: int = 0
    error: str = ""
    message: str = ""


class VideoUploadWorkflow:
    """
    Orchestrates the video upload workflow.

    Coordinates between VideoService, ApprovalService, and
    NotificationService to handle the complete upload process.
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

    async def execute(
        self,
        task_number: int,
        files: list[dict[str, Any]],
        uploader_id: str,
        uploader_name: str,
        reviewer_id: str | None = None,
    ) -> WorkflowResult:
        """
        Execute the complete video upload workflow.

        Steps:
        1. Validate task exists and can accept uploads
        2. Process and upload files to Dropbox
        3. Update task status to pending review
        4. Start approval workflow
        5. Notify reviewer

        Args:
            task_number: Task number
            files: List of file dicts with 'content', 'name', 'size' keys
            uploader_id: Uploader's user ID
            uploader_name: Uploader's display name
            reviewer_id: Optional reviewer ID for notifications

        Returns:
            WorkflowResult with workflow status
        """
        try:
            # Step 1: Validate task
            task = await self._task_service.get_task(task_number)
            if not task:
                return WorkflowResult(
                    success=False,
                    task_number=task_number,
                    error=f"Task #{task_number} not found",
                )

            # Check if task can accept uploads
            allowed_statuses = [
                "Assigned to",  # Will be checked with startswith
                "Editing",
                "Returned",
            ]

            task_status = task.status or ""
            can_upload = any(
                task_status.startswith(s) if s == "Assigned to" else task_status == s
                for s in allowed_statuses
            )

            if not can_upload:
                return WorkflowResult(
                    success=False,
                    task_number=task_number,
                    error=f"Task #{task_number} cannot accept uploads in status '{task_status}'",
                )

            # Step 2: Process and upload files
            upload_result = await self._video_service.process_upload(
                task_number=task_number,
                files=files,
                uploader_id=uploader_id,
                uploader_name=uploader_name,
            )

            if not upload_result.success:
                return WorkflowResult(
                    success=False,
                    task_number=task_number,
                    error=upload_result.error,
                )

            # Step 3: Update task status
            await self._task_service.update_status(
                task_number=task_number,
                new_status="Critique",
                version=upload_result.version,
            )

            # Step 4: Start approval workflow
            task_dict = await self._task_service.get_task_dict(task_number)

            workflow_id = await self._approval_service.start_workflow(
                task_number=task_number,
                folder_name=upload_result.folder_name,
                dropbox_path=upload_result.folder_path,
                videographer_id=uploader_id,
                videographer_name=uploader_name,
                version=upload_result.version,
                uploaded_files=[
                    {
                        "name": f.dropbox_name,
                        "path": f.dropbox_path,
                        "size": f.size,
                    }
                    for f in upload_result.uploaded_files
                ],
                task_data=task_dict,
            )

            # Step 5: Notify reviewer
            if reviewer_id:
                folder_url = await self._video_service.get_folder_shared_link(
                    task_number, "pending"
                )

                await self._notification_service.notify_reviewer(
                    reviewer_id=reviewer_id,
                    task_number=task_number,
                    folder_name=upload_result.folder_name,
                    folder_url=folder_url,
                    videographer_name=uploader_name,
                    task_data=task_dict,
                    uploaded_files=[f.dropbox_name for f in upload_result.uploaded_files],
                    workflow_id=workflow_id,
                )

            logger.info(
                f"[VideoUploadWorkflow] Completed for task #{task_number} v{upload_result.version}"
            )

            return WorkflowResult(
                success=True,
                task_number=task_number,
                version=upload_result.version,
                folder_name=upload_result.folder_name,
                workflow_id=workflow_id,
                files_uploaded=len(upload_result.uploaded_files),
                message=f"Uploaded {len(upload_result.uploaded_files)} files for Task #{task_number} (v{upload_result.version})",
            )

        except Exception as e:
            logger.error(f"[VideoUploadWorkflow] Error for task #{task_number}: {e}")
            return WorkflowResult(
                success=False,
                task_number=task_number,
                error=str(e),
            )

    async def execute_resubmission(
        self,
        task_number: int,
        files: list[dict[str, Any]],
        uploader_id: str,
        uploader_name: str,
        reviewer_id: str | None = None,
    ) -> WorkflowResult:
        """
        Execute workflow for a video resubmission after rejection/return.

        Similar to execute() but handles the resubmission context.

        Args:
            task_number: Task number
            files: List of file dicts
            uploader_id: Uploader's user ID
            uploader_name: Uploader's display name
            reviewer_id: Reviewer ID for notifications

        Returns:
            WorkflowResult
        """
        # For resubmissions, the flow is the same
        # The version number will auto-increment in VideoService
        result = await self.execute(
            task_number=task_number,
            files=files,
            uploader_id=uploader_id,
            uploader_name=uploader_name,
            reviewer_id=reviewer_id,
        )

        if result.success:
            result.message = f"Resubmitted {result.files_uploaded} files for Task #{task_number} (v{result.version})"

        return result
