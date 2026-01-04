"""
Videos Router for Video Critique.

Handles video upload, approval workflow, and review endpoints.
"""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from pydantic import BaseModel, Field

from crm_security import require_permission, AuthUser
import config
from core.services.video_service import VideoService
from core.services.approval_service import ApprovalService
from core.workflows.video_upload import VideoUploadWorkflow
from core.workflows.approval_flow import ApprovalWorkflow
from core.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/videos", tags=["videos"])

# Lazy-initialized services
_video_service: VideoService | None = None
_approval_service: ApprovalService | None = None
_upload_workflow: VideoUploadWorkflow | None = None
_approval_workflow: ApprovalWorkflow | None = None


def get_video_service() -> VideoService:
    """Get or create VideoService instance."""
    global _video_service
    if _video_service is None:
        _video_service = VideoService()
    return _video_service


def get_approval_service() -> ApprovalService:
    """Get or create ApprovalService instance."""
    global _approval_service
    if _approval_service is None:
        _approval_service = ApprovalService()
    return _approval_service


def get_upload_workflow() -> VideoUploadWorkflow:
    """Get or create VideoUploadWorkflow instance."""
    global _upload_workflow
    if _upload_workflow is None:
        _upload_workflow = VideoUploadWorkflow()
    return _upload_workflow


def get_approval_workflow() -> ApprovalWorkflow:
    """Get or create ApprovalWorkflow instance."""
    global _approval_workflow
    if _approval_workflow is None:
        _approval_workflow = ApprovalWorkflow()
    return _approval_workflow


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class VideoUploadResponse(BaseModel):
    """Video upload response."""
    success: bool
    file_id: str | None = None
    workflow_id: str | None = None
    version: int | None = None
    message: str | None = None
    error: str | None = None


class ApprovalRequest(BaseModel):
    """Approval action request."""
    workflow_id: str = Field(..., description="Workflow ID")


class RejectionRequest(ApprovalRequest):
    """Rejection action request."""
    reason: str | None = Field(None, description="Rejection reason")
    category: str | None = Field(None, description="Rejection category")


class ApprovalResponse(BaseModel):
    """Approval action response."""
    success: bool
    action: str | None = None
    task_number: int | None = None
    next_stage: str | None = None
    message: str | None = None
    error: str | None = None


class WorkflowStatus(BaseModel):
    """Workflow status response."""
    found: bool
    workflow_id: str | None = None
    task_number: int | None = None
    stage: str | None = None
    reviewer_approved: bool | None = None
    hos_approved: bool | None = None
    version: int | None = None
    created_at: str | None = None


# ============================================================================
# UPLOAD ENDPOINTS
# ============================================================================

@router.post("/upload", response_model=VideoUploadResponse)
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="Video file to upload"),
    task_number: int = Form(..., description="Task number for this video"),
    user: AuthUser = Depends(require_permission("video:upload")),
):
    """
    Upload a video file for a task.

    Starts the approval workflow after successful upload.
    Requires: video:upload permission.
    """
    logger.info(f"[Videos] Upload for task #{task_number} from {user.email}")

    try:
        # Read file content
        content = await file.read()

        # Create file info dict
        file_info = {
            "id": str(uuid.uuid4()),
            "name": file.filename,
            "content": content,
            "content_type": file.content_type,
            "size": len(content),
        }

        # Process through workflow
        workflow = get_upload_workflow()
        result = await workflow.execute(
            task_number=task_number,
            files=[file_info],
            uploader_id=user.id,
            uploader_name=user.name or user.email,
        )

        if result.success:
            return VideoUploadResponse(
                success=True,
                file_id=file_info["id"],
                workflow_id=result.workflow_id,
                version=result.version,
                message=f"Video uploaded successfully (v{result.version})",
            )
        else:
            return VideoUploadResponse(
                success=False,
                error=result.error or "Upload failed",
            )

    except Exception as e:
        logger.error(f"[Videos] Upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload/zip", response_model=VideoUploadResponse)
async def upload_zip(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="ZIP file containing videos"),
    task_number: int = Form(..., description="Task number"),
    user: AuthUser = Depends(require_permission("video:upload")),
):
    """
    Upload a ZIP file containing multiple videos.

    Extracts and processes all video files in the archive.
    Requires: video:upload permission.
    """
    logger.info(f"[Videos] ZIP upload for task #{task_number} from {user.email}")

    try:
        # Read file content
        content = await file.read()

        # Create file info dict
        file_info = {
            "id": str(uuid.uuid4()),
            "name": file.filename,
            "content": content,
            "content_type": "application/zip",
            "size": len(content),
        }

        # Process through workflow (will handle ZIP extraction)
        workflow = get_upload_workflow()
        result = await workflow.execute(
            task_number=task_number,
            files=[file_info],
            uploader_id=user.id,
            uploader_name=user.name or user.email,
        )

        if result.success:
            return VideoUploadResponse(
                success=True,
                file_id=file_info["id"],
                workflow_id=result.workflow_id,
                version=result.version,
                message=f"ZIP uploaded and processed successfully",
            )
        else:
            return VideoUploadResponse(
                success=False,
                error=result.error or "Upload failed",
            )

    except Exception as e:
        logger.error(f"[Videos] ZIP upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# APPROVAL ENDPOINTS
# ============================================================================

@router.post("/approve/reviewer", response_model=ApprovalResponse)
async def reviewer_approve(
    request: ApprovalRequest,
    user: AuthUser = Depends(require_permission("video:review:approve")),
):
    """
    Reviewer approves a video.

    Forwards to Head of Sales for final approval.
    Requires: video:review:approve permission.
    """
    try:
        workflow = get_approval_workflow()

        result = await workflow.handle_reviewer_approve(
            workflow_id=request.workflow_id,
            reviewer_id=user.id,
            reviewer_name=user.name or user.email,
        )

        return ApprovalResponse(
            success=result.success,
            action=result.action,
            task_number=result.task_number,
            next_stage=result.next_stage,
            message=result.message,
            error=result.error,
        )

    except Exception as e:
        logger.error(f"[Videos] Reviewer approve error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reject/reviewer", response_model=ApprovalResponse)
async def reviewer_reject(
    request: RejectionRequest,
    user: AuthUser = Depends(require_permission("video:review:approve")),
):
    """
    Reviewer rejects a video.

    Notifies videographer with rejection reason.
    Requires: video:review:approve permission.
    """
    try:
        workflow = get_approval_workflow()

        result = await workflow.handle_reviewer_reject(
            workflow_id=request.workflow_id,
            reviewer_id=user.id,
            reviewer_name=user.name or user.email,
            rejection_reason=request.reason,
            rejection_class=request.category,
        )

        return ApprovalResponse(
            success=result.success,
            action=result.action,
            task_number=result.task_number,
            next_stage=result.next_stage,
            message=result.message,
            error=result.error,
        )

    except Exception as e:
        logger.error(f"[Videos] Reviewer reject error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/approve/hos", response_model=ApprovalResponse)
async def hos_approve(
    request: ApprovalRequest,
    user: AuthUser = Depends(require_permission("video:review:final")),
):
    """
    Head of Sales approves a video.

    Completes the task workflow.
    Requires: video:review:final permission.
    """
    try:
        workflow = get_approval_workflow()

        result = await workflow.handle_hos_approve(
            workflow_id=request.workflow_id,
            hos_id=user.id,
            hos_name=user.name or user.email,
        )

        return ApprovalResponse(
            success=result.success,
            action=result.action,
            task_number=result.task_number,
            next_stage=result.next_stage,
            message=result.message,
            error=result.error,
        )

    except Exception as e:
        logger.error(f"[Videos] HoS approve error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/return/hos", response_model=ApprovalResponse)
async def hos_return(
    request: RejectionRequest,
    user: AuthUser = Depends(require_permission("video:review:final")),
):
    """
    Head of Sales returns a video for revision.

    Notifies videographer with return reason.
    Requires: video:review:final permission.
    """
    try:
        workflow = get_approval_workflow()

        result = await workflow.handle_hos_return(
            workflow_id=request.workflow_id,
            hos_id=user.id,
            hos_name=user.name or user.email,
            return_reason=request.reason,
            return_class=request.category,
        )

        return ApprovalResponse(
            success=result.success,
            action=result.action,
            task_number=result.task_number,
            next_stage=result.next_stage,
            message=result.message,
            error=result.error,
        )

    except Exception as e:
        logger.error(f"[Videos] HoS return error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# WORKFLOW STATUS ENDPOINTS
# ============================================================================

@router.get("/workflow/{workflow_id}", response_model=WorkflowStatus)
async def get_workflow_status(
    workflow_id: str,
    user: AuthUser = Depends(require_permission("video:tasks:read")),
):
    """
    Get the status of an approval workflow.

    Requires: video:tasks:read permission.
    """
    try:
        workflow = get_approval_workflow()
        status = await workflow.get_workflow_status(workflow_id)

        return WorkflowStatus(**status)

    except Exception as e:
        logger.error(f"[Videos] Workflow status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pending/reviewer/{reviewer_id}")
async def get_pending_for_reviewer(
    reviewer_id: str,
    user: AuthUser = Depends(require_permission("video:review:approve")),
):
    """
    Get workflows pending reviewer action.

    Requires: video:review:approve permission.
    """
    try:
        workflow = get_approval_workflow()
        pending = await workflow.get_pending_for_reviewer(reviewer_id)

        return {
            "count": len(pending),
            "workflows": pending,
        }

    except Exception as e:
        logger.error(f"[Videos] Pending for reviewer error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pending/hos/{hos_id}")
async def get_pending_for_hos(
    hos_id: str,
    user: AuthUser = Depends(require_permission("video:review:final")),
):
    """
    Get workflows pending Head of Sales action.

    Requires: video:review:final permission.
    """
    try:
        workflow = get_approval_workflow()
        pending = await workflow.get_pending_for_hos(hos_id)

        return {
            "count": len(pending),
            "workflows": pending,
        }

    except Exception as e:
        logger.error(f"[Videos] Pending for HoS error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# FOLDER/FILE ENDPOINTS
# ============================================================================

@router.get("/folder/{task_number}")
async def get_task_folder(
    task_number: int,
    folder_type: str = "submitted",
    user: AuthUser = Depends(require_permission("video:tasks:read")),
):
    """
    Get the Dropbox folder URL for a task.

    Requires: video:tasks:read permission.
    """
    try:
        service = get_video_service()
        url = await service.get_folder_url(task_number, folder_type)

        return {
            "task_number": task_number,
            "folder_type": folder_type,
            "url": url,
        }

    except Exception as e:
        logger.error(f"[Videos] Get folder error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/versions/{task_number}")
async def get_task_versions(
    task_number: int,
    user: AuthUser = Depends(require_permission("video:tasks:read")),
):
    """
    Get all versions of videos for a task.

    Requires: video:tasks:read permission.
    """
    try:
        service = get_video_service()
        versions = await service.get_task_versions(task_number)

        return {
            "task_number": task_number,
            "versions": versions,
        }

    except Exception as e:
        logger.error(f"[Videos] Get versions error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
