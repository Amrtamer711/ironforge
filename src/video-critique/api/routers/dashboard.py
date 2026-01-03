"""
Dashboard Router for Video Critique.

Provides dashboard data endpoints for the unified-ui.
"""

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

import config
from core.services.task_service import TaskService
from core.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# Lazy-initialized service
_task_service: TaskService | None = None


def get_task_service() -> TaskService:
    """Get or create TaskService instance."""
    global _task_service
    if _task_service is None:
        _task_service = TaskService()
    return _task_service


# ============================================================================
# RESPONSE MODELS
# ============================================================================

class DashboardStats(BaseModel):
    """Dashboard statistics."""
    total_tasks: int = 0
    pending_assignment: int = 0
    in_progress: int = 0
    pending_review: int = 0
    pending_hos: int = 0
    completed: int = 0
    rejected: int = 0


class WorkloadItem(BaseModel):
    """Videographer workload item."""
    name: str
    active_tasks: int
    completed_today: int
    pending_review: int


class RecentActivity(BaseModel):
    """Recent activity item."""
    timestamp: str
    action: str
    task_number: int
    user: str
    details: str | None = None


class UpcomingShoot(BaseModel):
    """Upcoming shoot item."""
    date: str
    task_number: int
    brand: str
    location: str
    videographer: str
    time_block: str | None = None


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats():
    """
    Get overall dashboard statistics.
    """
    try:
        service = get_task_service()

        # Get all active tasks
        tasks = await service.list_tasks({"include_history": False})

        stats = DashboardStats()
        stats.total_tasks = len(tasks)

        for task in tasks:
            status = task.get("Status", "")

            if status == "Not assigned yet":
                stats.pending_assignment += 1
            elif status.startswith("Assigned to"):
                stats.in_progress += 1
            elif status in ["Critique", "Raw"]:
                stats.pending_review += 1
            elif status == "Submitted to Sales":
                stats.pending_hos += 1
            elif status == "Done":
                stats.completed += 1
            elif status in ["Returned", "Editing", "Permanently Rejected"]:
                stats.rejected += 1

        return stats

    except Exception as e:
        logger.error(f"[Dashboard] Stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workload")
async def get_workload_data():
    """
    Get videographer workload data.
    """
    try:
        service = get_task_service()

        # Get videographers
        videographers_result = await service.list_videographers()
        if not videographers_result.get("success"):
            raise HTTPException(status_code=500, detail="Failed to get videographers")

        videographers = videographers_result.get("videographers", {})

        # Get all active tasks
        tasks = await service.list_tasks({"include_history": False})

        # Calculate workload per videographer
        workload_data = []
        today = datetime.now(config.UAE_TZ).date()

        for name in videographers.keys():
            videographer_tasks = [
                t for t in tasks
                if t.get("Videographer") == name
            ]

            active = len([
                t for t in videographer_tasks
                if t.get("Status", "").startswith("Assigned") or
                   t.get("Status") in ["Editing", "Returned"]
            ])

            completed_today = len([
                t for t in videographer_tasks
                if t.get("Status") == "Done" and
                   _parse_date(t.get("Updated At", "")) == today
            ])

            pending_review = len([
                t for t in videographer_tasks
                if t.get("Status") in ["Critique", "Submitted to Sales"]
            ])

            workload_data.append(WorkloadItem(
                name=name,
                active_tasks=active,
                completed_today=completed_today,
                pending_review=pending_review,
            ))

        # Sort by active tasks descending
        workload_data.sort(key=lambda x: x.active_tasks, reverse=True)

        return {
            "videographers": [w.model_dump() for w in workload_data],
            "total_videographers": len(workload_data),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Dashboard] Workload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/upcoming-shoots")
async def get_upcoming_shoots(
    days: int = Query(7, description="Number of days to look ahead"),
):
    """
    Get upcoming filming dates.
    """
    try:
        service = get_task_service()

        # Get all active tasks
        tasks = await service.list_tasks({"include_history": False})

        today = datetime.now(config.UAE_TZ).date()
        end_date = today + timedelta(days=days)

        upcoming = []
        for task in tasks:
            filming_date_str = task.get("Filming Date", "")
            if not filming_date_str:
                continue

            filming_date = _parse_date(filming_date_str)
            if filming_date and today <= filming_date <= end_date:
                upcoming.append(UpcomingShoot(
                    date=filming_date.strftime("%Y-%m-%d"),
                    task_number=task.get("Task #", 0),
                    brand=task.get("Brand", ""),
                    location=task.get("Location", ""),
                    videographer=task.get("Videographer", "Unassigned"),
                    time_block=task.get("Time Block"),
                ))

        # Sort by date
        upcoming.sort(key=lambda x: x.date)

        return {
            "shoots": [s.model_dump() for s in upcoming],
            "count": len(upcoming),
        }

    except Exception as e:
        logger.error(f"[Dashboard] Upcoming shoots error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/by-status")
async def get_tasks_by_status():
    """
    Get task counts grouped by status.
    """
    try:
        service = get_task_service()

        tasks = await service.list_tasks({"include_history": False})

        status_counts: dict[str, int] = {}
        for task in tasks:
            status = task.get("Status", "Unknown")
            status_counts[status] = status_counts.get(status, 0) + 1

        return {
            "by_status": status_counts,
            "total": len(tasks),
        }

    except Exception as e:
        logger.error(f"[Dashboard] By status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/by-location")
async def get_tasks_by_location():
    """
    Get task counts grouped by location.
    """
    try:
        service = get_task_service()

        tasks = await service.list_tasks({"include_history": False})

        location_counts: dict[str, int] = {}
        for task in tasks:
            location = task.get("Location", "Unknown")
            location_counts[location] = location_counts.get(location, 0) + 1

        # Sort by count descending
        sorted_locations = sorted(
            location_counts.items(),
            key=lambda x: x[1],
            reverse=True,
        )

        return {
            "by_location": dict(sorted_locations),
            "total": len(tasks),
        }

    except Exception as e:
        logger.error(f"[Dashboard] By location error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/by-videographer")
async def get_tasks_by_videographer():
    """
    Get task counts grouped by videographer.
    """
    try:
        service = get_task_service()

        tasks = await service.list_tasks({"include_history": False})

        videographer_counts: dict[str, int] = {}
        for task in tasks:
            videographer = task.get("Videographer", "Unassigned") or "Unassigned"
            videographer_counts[videographer] = videographer_counts.get(videographer, 0) + 1

        # Sort by count descending
        sorted_videographers = sorted(
            videographer_counts.items(),
            key=lambda x: x[1],
            reverse=True,
        )

        return {
            "by_videographer": dict(sorted_videographers),
            "total": len(tasks),
        }

    except Exception as e:
        logger.error(f"[Dashboard] By videographer error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/calendar")
async def get_calendar_data(
    month: int = Query(..., ge=1, le=12, description="Month (1-12)"),
    year: int = Query(..., description="Year"),
):
    """
    Get calendar data for a specific month.

    Returns filming dates and campaign periods.
    """
    try:
        service = get_task_service()

        tasks = await service.list_tasks({"include_history": False})

        # Calculate month boundaries
        month_start = datetime(year, month, 1).date()
        if month == 12:
            month_end = datetime(year + 1, 1, 1).date() - timedelta(days=1)
        else:
            month_end = datetime(year, month + 1, 1).date() - timedelta(days=1)

        calendar_data: dict[str, list[dict]] = {}

        for task in tasks:
            # Check filming date
            filming_date = _parse_date(task.get("Filming Date", ""))
            if filming_date and month_start <= filming_date <= month_end:
                date_key = filming_date.strftime("%Y-%m-%d")
                if date_key not in calendar_data:
                    calendar_data[date_key] = []

                calendar_data[date_key].append({
                    "type": "filming",
                    "task_number": task.get("Task #"),
                    "brand": task.get("Brand"),
                    "location": task.get("Location"),
                    "videographer": task.get("Videographer"),
                })

            # Check campaign dates
            campaign_start = _parse_date(task.get("Campaign Start Date", ""))
            campaign_end = _parse_date(task.get("Campaign End Date", ""))

            if campaign_start and campaign_end:
                # Check if campaign overlaps with month
                if campaign_start <= month_end and campaign_end >= month_start:
                    start_key = max(campaign_start, month_start).strftime("%Y-%m-%d")
                    if start_key not in calendar_data:
                        calendar_data[start_key] = []

                    calendar_data[start_key].append({
                        "type": "campaign_start",
                        "task_number": task.get("Task #"),
                        "brand": task.get("Brand"),
                        "campaign_end": campaign_end.strftime("%Y-%m-%d"),
                    })

        return {
            "month": month,
            "year": year,
            "events": calendar_data,
        }

    except Exception as e:
        logger.error(f"[Dashboard] Calendar error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def _parse_date(date_str: str) -> datetime.date | None:
    """Parse a date string in DD-MM-YYYY or YYYY-MM-DD format."""
    if not date_str:
        return None

    # Try DD-MM-YYYY
    try:
        return datetime.strptime(date_str, "%d-%m-%Y").date()
    except ValueError:
        pass

    # Try YYYY-MM-DD
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        pass

    return None
