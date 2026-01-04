"""
Tasks Router for Video Critique.

Handles task CRUD operations and management endpoints.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field

from crm_security import require_permission, AuthUser
import config
from core.services.task_service import TaskService
from core.services.assignment_service import AssignmentService
from core.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

# Lazy-initialized services
_task_service: TaskService | None = None
_assignment_service: AssignmentService | None = None


def get_task_service() -> TaskService:
    """Get or create TaskService instance."""
    global _task_service
    if _task_service is None:
        _task_service = TaskService()
    return _task_service


def get_assignment_service() -> AssignmentService:
    """Get or create AssignmentService instance."""
    global _assignment_service
    if _assignment_service is None:
        _assignment_service = AssignmentService()
    return _assignment_service


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class TaskCreate(BaseModel):
    """Task creation request."""
    brand: str = Field(..., description="Brand/client name")
    reference_number: str = Field(..., description="Reference number")
    location: str = Field(..., description="Campaign location")
    campaign_start_date: str = Field(..., description="Start date (DD-MM-YYYY)")
    campaign_end_date: str = Field(..., description="End date (DD-MM-YYYY)")
    sales_person: str = Field(..., description="Sales person name")
    task_type: str = Field("videography", description="Task type")
    time_block: str = Field("both", description="Time block (day/night/both)")
    submitted_by: str | None = Field(None, description="Submitter name")


class TaskUpdate(BaseModel):
    """Task update request."""
    brand: str | None = None
    reference_number: str | None = None
    location: str | None = None
    campaign_start_date: str | None = None
    campaign_end_date: str | None = None
    sales_person: str | None = None
    status: str | None = None
    filming_date: str | None = None
    videographer: str | None = None
    task_type: str | None = None


class TaskResponse(BaseModel):
    """Task response model."""
    success: bool
    task_number: int | None = None
    message: str | None = None
    error: str | None = None
    data: dict[str, Any] | None = None


class TaskListResponse(BaseModel):
    """Task list response."""
    success: bool
    count: int
    tasks: list[dict[str, Any]]


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("", response_model=TaskListResponse)
@router.get("/", response_model=TaskListResponse)
async def list_tasks(
    status: str | None = Query(None, description="Filter by status"),
    location: str | None = Query(None, description="Filter by location"),
    videographer: str | None = Query(None, description="Filter by videographer"),
    sales_person: str | None = Query(None, description="Filter by sales person"),
    limit: int = Query(100, description="Maximum results"),
    offset: int = Query(0, description="Offset for pagination"),
    include_history: bool = Query(False, description="Include completed tasks"),
    user: AuthUser = Depends(require_permission("video:tasks:read")),
):
    """
    List tasks with optional filters.

    Requires: video:tasks:read permission.
    """
    try:
        service = get_task_service()

        # Build filter dict
        filters: dict[str, Any] = {"limit": limit, "offset": offset}

        if status:
            filters["status"] = status
        if location:
            filters["location"] = location
        if videographer:
            filters["videographer"] = videographer
        if sales_person:
            filters["sales_person"] = sales_person
        if include_history:
            filters["include_history"] = True

        result = await service.list_tasks(filters)

        return TaskListResponse(
            success=True,
            count=len(result),
            tasks=result,
        )

    except Exception as e:
        logger.error(f"[Tasks] List error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_number}")
async def get_task(
    task_number: int,
    user: AuthUser = Depends(require_permission("video:tasks:read")),
):
    """
    Get a specific task by task number.

    Requires: video:tasks:read permission.
    """
    try:
        service = get_task_service()
        task = await service.get_task(task_number)

        if not task:
            raise HTTPException(status_code=404, detail=f"Task #{task_number} not found")

        return {
            "success": True,
            "task": task,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Tasks] Get error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=TaskResponse)
@router.post("/", response_model=TaskResponse)
async def create_task(
    request: TaskCreate,
    user: AuthUser = Depends(require_permission("video:tasks:create")),
):
    """
    Create a new task.

    Requires: video:tasks:create permission.
    """
    try:
        service = get_task_service()

        result = await service.create_task(
            brand=request.brand,
            reference_number=request.reference_number,
            location=request.location,
            campaign_start_date=request.campaign_start_date,
            campaign_end_date=request.campaign_end_date,
            sales_person=request.sales_person,
            submitted_by=request.submitted_by,
            task_type=request.task_type,
            time_block=request.time_block,
        )

        if result.get("success"):
            return TaskResponse(
                success=True,
                task_number=result.get("task_number"),
                message="Task created successfully",
                data=result.get("task_data"),
            )
        else:
            return TaskResponse(
                success=False,
                error=result.get("error", "Failed to create task"),
            )

    except Exception as e:
        logger.error(f"[Tasks] Create error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{task_number}", response_model=TaskResponse)
@router.patch("/{task_number}", response_model=TaskResponse)
async def update_task(
    task_number: int,
    request: TaskUpdate,
    user: AuthUser = Depends(require_permission("video:tasks:edit")),
):
    """
    Update an existing task.

    Requires: video:tasks:edit permission.
    """
    try:
        service = get_task_service()

        # Build updates dict from non-None fields
        updates = {}
        for field, value in request.model_dump().items():
            if value is not None:
                # Convert field names to match database format
                db_field = field.replace("_", " ").title()
                if field == "reference_number":
                    db_field = "Reference Number"
                elif field == "campaign_start_date":
                    db_field = "Campaign Start Date"
                elif field == "campaign_end_date":
                    db_field = "Campaign End Date"
                elif field == "sales_person":
                    db_field = "Sales Person"
                elif field == "filming_date":
                    db_field = "Filming Date"
                elif field == "task_type":
                    db_field = "Task Type"

                updates[db_field] = value

        if not updates:
            return TaskResponse(
                success=False,
                error="No updates provided",
            )

        result = await service.update_task(task_number, updates)

        if result.get("success"):
            return TaskResponse(
                success=True,
                task_number=task_number,
                message="Task updated successfully",
            )
        else:
            return TaskResponse(
                success=False,
                error=result.get("error", "Failed to update task"),
            )

    except Exception as e:
        logger.error(f"[Tasks] Update error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{task_number}", response_model=TaskResponse)
async def delete_task(
    task_number: int,
    user: AuthUser = Depends(require_permission("video:tasks:delete")),
):
    """
    Delete (archive) a task.

    Requires: video:tasks:delete permission.
    """
    try:
        service = get_task_service()

        result = await service.delete_task(task_number)

        if result.get("success"):
            return TaskResponse(
                success=True,
                task_number=task_number,
                message="Task deleted successfully",
                data=result.get("task_data"),
            )
        else:
            return TaskResponse(
                success=False,
                error=result.get("error", "Failed to delete task"),
            )

    except Exception as e:
        logger.error(f"[Tasks] Delete error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ASSIGNMENT ENDPOINTS
# ============================================================================

@router.post("/assignment/run")
async def trigger_assignment(
    background_tasks: BackgroundTasks,
    user: AuthUser = Depends(require_permission("video:admin:assignment")),
):
    """
    Trigger the assignment check process.

    Runs the assignment service to assign unassigned tasks
    to videographers based on location and availability.

    Requires: video:admin:assignment permission.
    """
    try:
        # Run in background
        background_tasks.add_task(run_assignment_check)

        return {
            "success": True,
            "message": "Assignment check started",
            "timestamp": datetime.now(config.UAE_TZ).isoformat(),
        }

    except Exception as e:
        logger.error(f"[Tasks] Assignment trigger error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def run_assignment_check():
    """Run the assignment check in background."""
    try:
        service = get_assignment_service()
        results = await service.run_assignment_check()

        assigned_count = len([r for r in results if r.success])
        logger.info(f"[Tasks] Assignment check completed: {assigned_count} tasks assigned")

    except Exception as e:
        logger.error(f"[Tasks] Assignment check error: {e}")


@router.get("/assignment/pending")
async def get_pending_assignments(
    user: AuthUser = Depends(require_permission("video:tasks:read")),
):
    """
    Get tasks pending assignment.

    Requires: video:tasks:read permission.
    """
    try:
        service = get_task_service()

        tasks = await service.list_tasks({
            "status": "Not assigned yet",
        })

        return {
            "success": True,
            "count": len(tasks),
            "tasks": tasks,
        }

    except Exception as e:
        logger.error(f"[Tasks] Pending assignments error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# EXPORT ENDPOINTS
# ============================================================================

@router.get("/export")
async def export_tasks(
    include_history: bool = Query(False, description="Include historical tasks"),
    format: str = Query("json", description="Export format (json/excel)"),
    user: AuthUser = Depends(require_permission("video:tasks:export")),
):
    """
    Export tasks to JSON or Excel format.

    Requires: video:tasks:export permission.
    """
    try:
        service = get_task_service()

        if format == "excel":
            result = await service.export_tasks(
                include_history=include_history,
                format="excel",
            )

            if result.get("success"):
                files = result.get("files", [])
                return {
                    "success": True,
                    "files": [f.get("name") for f in files],
                    "message": f"Exported {len(files)} file(s)",
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error"),
                }

        else:
            # JSON export
            tasks = await service.list_tasks({
                "include_history": include_history,
            })

            return {
                "success": True,
                "count": len(tasks),
                "tasks": tasks,
            }

    except Exception as e:
        logger.error(f"[Tasks] Export error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# DUPLICATE CHECK ENDPOINT
# ============================================================================

@router.get("/check-duplicate/{reference_number}")
async def check_duplicate(
    reference_number: str,
    user: AuthUser = Depends(require_permission("video:tasks:read")),
):
    """
    Check if a reference number already exists.

    Requires: video:tasks:read permission.
    """
    try:
        service = get_task_service()

        result = await service.check_duplicate_reference(reference_number)

        return {
            "is_duplicate": result.get("is_duplicate", False),
            "existing_entry": result.get("existing_entry"),
        }

    except Exception as e:
        logger.error(f"[Tasks] Duplicate check error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
