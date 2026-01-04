"""
Task Service for Video Critique.

Handles all task CRUD operations, including:
- Creating design requests from parsed campaign data
- Retrieving and listing tasks
- Updating task fields
- Deleting/archiving tasks
- Duplicate reference checking
- Exporting task data
"""

from dataclasses import asdict
from datetime import date, datetime
from typing import Any

from core.utils.logging import get_logger
from core.utils.time import UAE_TZ, format_date, now_uae
from db.database import db
from db.models import CompletedTask, VideoTask

logger = get_logger(__name__)


class TaskService:
    """
    Service for managing video production tasks.

    Provides business logic layer between API/handlers and database,
    handling data validation, transformations, and cross-cutting concerns.
    """

    def __init__(self):
        """Initialize task service."""
        self._db = db

    # ========================================================================
    # CREATE OPERATIONS
    # ========================================================================

    async def create_task(
        self,
        brand: str,
        reference_number: str,
        location: str,
        campaign_start_date: date | str,
        campaign_end_date: date | str | None = None,
        sales_person: str | None = None,
        submitted_by: str | None = None,
        task_type: str = "videography",
        time_block: str | None = None,
        calculate_filming_date_func=None,
    ) -> dict[str, Any]:
        """
        Create a new video production task.

        Args:
            brand: Brand name
            reference_number: Campaign reference number
            location: Location key
            campaign_start_date: Campaign start date
            campaign_end_date: Campaign end date (optional)
            sales_person: Sales person name
            submitted_by: User who submitted the request
            task_type: Type of task (videography, photography)
            time_block: Time block for Abu Dhabi scheduling
            calculate_filming_date_func: Optional function to calculate filming date

        Returns:
            Dict with success status and task_number
        """
        try:
            # Normalize reference number
            reference_number = reference_number.replace("_", "-")

            # Check for duplicate
            duplicate = await self.check_duplicate_reference(reference_number)
            if duplicate.get("is_duplicate"):
                return {
                    "success": False,
                    "error": "duplicate",
                    "existing_entry": duplicate.get("existing_entry"),
                }

            # Convert date strings if needed
            if isinstance(campaign_start_date, str):
                campaign_start_date = self._parse_date(campaign_start_date)
            if isinstance(campaign_end_date, str):
                campaign_end_date = self._parse_date(campaign_end_date)

            # Calculate filming date if function provided
            filming_date = None
            if calculate_filming_date_func:
                filming_date = calculate_filming_date_func(
                    campaign_start_date,
                    campaign_end_date,
                    location=location,
                    task_type=task_type,
                    time_block=time_block,
                )

            # Get next task number
            next_num = await self._db.get_next_task_number()

            # Build task model
            task = VideoTask(
                task_number=next_num,
                brand=brand.replace("_", "-"),
                campaign_start_date=campaign_start_date,
                campaign_end_date=campaign_end_date,
                reference_number=reference_number,
                location=location.replace("_", "-") if location else None,
                sales_person=sales_person.replace("_", "-") if sales_person else None,
                submitted_by=submitted_by.replace("_", "-") if submitted_by else None,
                status="Not assigned yet",
                filming_date=filming_date,
                videographer=None,
                task_type=task_type,
                time_block=time_block,
                submission_folder=None,
                current_version=None,
                version_history=[],
                created_at=now_uae(),
                updated_at=now_uae(),
            )

            # Insert into database
            task_number = await self._db.create_task(task)

            logger.info(f"[TaskService] Created task #{task_number}")
            return {"success": True, "task_number": task_number}

        except Exception as e:
            logger.error(f"[TaskService] Error creating task: {e}")
            return {"success": False, "error": str(e)}

    # ========================================================================
    # READ OPERATIONS
    # ========================================================================

    async def get_task(self, task_number: int) -> VideoTask | None:
        """
        Get a task by its number.

        Args:
            task_number: Task number to retrieve

        Returns:
            VideoTask model or None if not found
        """
        return await self._db.get_task(task_number)

    async def get_task_dict(self, task_number: int) -> dict[str, Any] | None:
        """
        Get a task as a dictionary with formatted fields.

        Args:
            task_number: Task number to retrieve

        Returns:
            Task data dict or None if not found
        """
        task = await self._db.get_task(task_number)
        if not task:
            return None

        return self._task_to_dict(task)

    async def list_tasks(
        self,
        status: str | None = None,
        videographer: str | None = None,
        location: str | None = None,
        user_companies: list[str] | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        List tasks with optional filters.

        Args:
            status: Filter by status
            videographer: Filter by videographer
            location: Filter by location
            user_companies: Filter by user's accessible companies (RBAC filtering)
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of task dicts
        """
        filters = {}
        if status:
            filters["status"] = status
        if videographer:
            filters["videographer"] = videographer
        if location:
            filters["location"] = location

        tasks = await self._db.list_tasks(filters, limit, offset)
        task_dicts = [self._task_to_dict(t) for t in tasks]

        # Company filtering: filter tasks by location -> company mapping
        # This requires WorkflowContext or AssetService to resolve locations to companies
        if user_companies:
            logger.debug(
                f"[TaskService] Company filtering requested for {len(user_companies)} companies "
                f"(full implementation pending location->company mapping)"
            )
            # TODO: When location->company mapping is available:
            # 1. Get locations for user_companies from AssetService
            # 2. Filter task_dicts to only include those with matching locations

        return task_dicts

    async def list_all_tasks(self) -> list[dict[str, Any]]:
        """
        Get all active tasks.

        Returns:
            List of all task dicts
        """
        tasks = await self._db.list_tasks()
        return [self._task_to_dict(t) for t in tasks]

    async def get_tasks_for_assignment(self) -> list[VideoTask]:
        """
        Get tasks that need assignment.

        Returns tasks with status 'Not assigned yet'.

        Returns:
            List of VideoTask models
        """
        return await self._db.list_tasks({"status": "Not assigned yet"})

    async def get_tasks_by_videographer(
        self,
        videographer: str,
    ) -> list[dict[str, Any]]:
        """
        Get all tasks assigned to a videographer.

        Args:
            videographer: Videographer name

        Returns:
            List of task dicts
        """
        tasks = await self._db.list_tasks({"videographer": videographer})
        return [self._task_to_dict(t) for t in tasks]

    async def get_tasks_by_status(self, status: str) -> list[dict[str, Any]]:
        """
        Get all tasks with a specific status.

        Args:
            status: Status to filter by

        Returns:
            List of task dicts
        """
        tasks = await self._db.list_tasks({"status": status})
        return [self._task_to_dict(t) for t in tasks]

    # ========================================================================
    # UPDATE OPERATIONS
    # ========================================================================

    async def update_task(
        self,
        task_number: int,
        updates: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Update a task's fields.

        Args:
            task_number: Task number to update
            updates: Dict of fields to update

        Returns:
            Dict with success status
        """
        try:
            # Get current task
            task = await self._db.get_task(task_number)
            if not task:
                return {"success": False, "error": "Task not found"}

            # Apply updates
            for key, value in updates.items():
                if hasattr(task, key):
                    setattr(task, key, value)

            task.updated_at = now_uae()

            # Save to database
            success = await self._db.update_task(task_number, updates)

            if success:
                logger.info(f"[TaskService] Updated task #{task_number}")
                return {"success": True, "updates": updates}
            else:
                return {"success": False, "error": "Database update failed"}

        except Exception as e:
            logger.error(f"[TaskService] Error updating task #{task_number}: {e}")
            return {"success": False, "error": str(e)}

    async def update_status(
        self,
        task_number: int,
        new_status: str,
        version: int | None = None,
        rejection_reason: str | None = None,
        rejection_class: str | None = None,
        rejected_by: str | None = None,
    ) -> bool:
        """
        Update task status with version history tracking.

        Args:
            task_number: Task number to update
            new_status: New status value
            version: Version number for this status change
            rejection_reason: Reason for rejection (if applicable)
            rejection_class: Category of rejection
            rejected_by: Who rejected (Reviewer, HoS, etc.)

        Returns:
            True if successful
        """
        try:
            task = await self._db.get_task(task_number)
            if not task:
                return False

            # Build version history entry
            history_entry = None
            if version is not None:
                history_entry = {
                    "version": version,
                    "status": new_status,
                    "at": now_uae().strftime("%d-%m-%Y %H:%M:%S"),
                }
                if rejection_class:
                    history_entry["rejection_class"] = rejection_class
                    history_entry["rejection_comments"] = rejection_reason or ""
                if rejected_by:
                    history_entry["rejected_by"] = rejected_by

                # Append to version history
                task.version_history.append(history_entry)

            # Update status
            updates = {
                "status": new_status,
                "version_history": task.version_history,
                "updated_at": now_uae(),
            }

            success = await self._db.update_task(task_number, updates)
            if success:
                logger.info(f"[TaskService] Updated task #{task_number} status to {new_status}")
            return success

        except Exception as e:
            logger.error(f"[TaskService] Error updating status for task #{task_number}: {e}")
            return False

    async def assign_videographer(
        self,
        task_number: int,
        videographer: str,
        filming_date: date | None = None,
    ) -> dict[str, Any]:
        """
        Assign a videographer to a task.

        Args:
            task_number: Task number
            videographer: Videographer name
            filming_date: Optional filming date override

        Returns:
            Dict with success status
        """
        updates = {
            "videographer": videographer,
            "status": f"Assigned to {videographer}",
        }

        if filming_date:
            updates["filming_date"] = filming_date

        return await self.update_task(task_number, updates)

    async def update_submission_folder(
        self,
        task_number: int,
        folder_name: str,
    ) -> bool:
        """
        Update the submission folder for a task.

        Args:
            task_number: Task number
            folder_name: Dropbox folder name

        Returns:
            True if successful
        """
        result = await self.update_task(task_number, {"submission_folder": folder_name})
        return result.get("success", False)

    # ========================================================================
    # DELETE/ARCHIVE OPERATIONS
    # ========================================================================

    async def delete_task(self, task_number: int) -> dict[str, Any]:
        """
        Delete a task by archiving it.

        Args:
            task_number: Task number to delete

        Returns:
            Dict with success status and archived task data
        """
        try:
            # Get task data first
            task = await self._db.get_task(task_number)
            if not task:
                return {"success": False, "error": "Task not found"}

            # Update status to archived
            await self.update_task(task_number, {"status": "Archived"})

            # Archive the task
            success = await self._db.archive_task(task_number)

            if success:
                logger.info(f"[TaskService] Archived task #{task_number}")
                return {
                    "success": True,
                    "task_data": self._task_to_dict(task),
                }
            else:
                return {"success": False, "error": "Failed to archive task"}

        except Exception as e:
            logger.error(f"[TaskService] Error deleting task #{task_number}: {e}")
            return {"success": False, "error": str(e)}

    async def permanently_reject_task(
        self,
        task_number: int,
        rejection_reason: str | None = None,
    ) -> dict[str, Any]:
        """
        Permanently reject and archive a task.

        Args:
            task_number: Task number
            rejection_reason: Reason for permanent rejection

        Returns:
            Dict with success status
        """
        try:
            # Update status
            await self.update_status(
                task_number,
                "Permanently Rejected",
                rejection_reason=rejection_reason,
                rejection_class="Permanent Rejection",
            )

            # Archive the task
            success = await self._db.archive_task(task_number)

            if success:
                logger.info(f"[TaskService] Permanently rejected task #{task_number}")
                return {"success": True, "archived": True}
            else:
                return {"success": False, "error": "Failed to archive task"}

        except Exception as e:
            logger.error(f"[TaskService] Error permanently rejecting task #{task_number}: {e}")
            return {"success": False, "error": str(e)}

    # ========================================================================
    # DUPLICATE CHECKING
    # ========================================================================

    async def check_duplicate_reference(
        self,
        reference_number: str,
    ) -> dict[str, Any]:
        """
        Check if a reference number already exists.

        Args:
            reference_number: Reference number to check

        Returns:
            Dict with is_duplicate flag and existing entry if found
        """
        clean_ref = reference_number.replace("_", "-")

        # Check active tasks
        tasks = await self._db.list_tasks({"reference_number": clean_ref})
        if tasks:
            task = tasks[0]
            return {
                "is_duplicate": True,
                "existing_entry": {
                    "task_number": str(task.task_number),
                    "brand": task.brand,
                    "start_date": format_date(task.campaign_start_date),
                    "end_date": format_date(task.campaign_end_date),
                    "location": task.location,
                    "submitted_by": task.submitted_by,
                    "status": "Active",
                },
            }

        # Check completed tasks
        completed = await self._db.get_completed_task_by_reference(clean_ref)
        if completed:
            return {
                "is_duplicate": True,
                "existing_entry": {
                    "task_number": str(completed.task_number),
                    "brand": completed.brand,
                    "start_date": format_date(completed.campaign_start_date),
                    "end_date": format_date(completed.campaign_end_date),
                    "location": completed.location,
                    "submitted_by": completed.submitted_by,
                    "status": "Archived (Completed)",
                },
            }

        return {"is_duplicate": False}

    # ========================================================================
    # VERSION TRACKING
    # ========================================================================

    async def get_current_version(self, task_number: int) -> int:
        """
        Get the current version number for a task.

        Args:
            task_number: Task number

        Returns:
            Current version number (defaults to 1)
        """
        task = await self._db.get_task(task_number)
        if not task or not task.version_history:
            return 1

        # Find max version in history
        max_version = 0
        for entry in task.version_history:
            version = entry.get("version", 0)
            if version > max_version:
                max_version = version

        return max_version if max_version > 0 else 1

    async def get_rejection_history(
        self,
        task_number: int,
    ) -> list[dict[str, Any]]:
        """
        Get rejection/return history for a task.

        Args:
            task_number: Task number

        Returns:
            List of rejection entries
        """
        task = await self._db.get_task(task_number)
        if not task or not task.version_history:
            return []

        rejections = []
        for entry in task.version_history:
            status = entry.get("status", "").lower()
            if status in ["rejected", "returned", "editing"]:
                rejections.append({
                    "version": entry.get("version", 1),
                    "class": entry.get("rejection_class", "Other"),
                    "comments": entry.get("rejection_comments", ""),
                    "at": entry.get("at", ""),
                    "rejected_by": entry.get("rejected_by", "Unknown"),
                })

        return rejections

    # ========================================================================
    # EXPORT OPERATIONS
    # ========================================================================

    async def export_to_dataframe(self) -> "pd.DataFrame":
        """
        Export all tasks to a pandas DataFrame.

        Returns:
            DataFrame with all task data
        """
        import pandas as pd

        tasks = await self.list_all_tasks()
        if not tasks:
            return pd.DataFrame()

        return pd.DataFrame(tasks)

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    def _task_to_dict(self, task: VideoTask) -> dict[str, Any]:
        """Convert VideoTask model to dict with formatted fields."""
        data = asdict(task)

        # Format dates
        if task.campaign_start_date:
            data["Campaign Start Date"] = format_date(task.campaign_start_date)
        if task.campaign_end_date:
            data["Campaign End Date"] = format_date(task.campaign_end_date)
        if task.filming_date:
            data["Filming Date"] = format_date(task.filming_date)
        if task.created_at:
            data["Timestamp"] = task.created_at.strftime("%d-%m-%Y %H:%M:%S")

        # Map to expected field names
        data["Task #"] = task.task_number
        data["Brand"] = task.brand
        data["Reference Number"] = task.reference_number
        data["Location"] = task.location
        data["Sales Person"] = task.sales_person
        data["Submitted By"] = task.submitted_by
        data["Status"] = task.status
        data["Videographer"] = task.videographer
        data["Task Type"] = task.task_type
        data["Time Block"] = task.time_block
        data["Submission Folder"] = task.submission_folder
        data["Version History"] = task.version_history

        return data

    def _parse_date(self, date_str: str) -> date | None:
        """Parse a date string to date object."""
        if not date_str:
            return None

        # Try different formats
        formats = ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"]
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue

        logger.warning(f"[TaskService] Could not parse date: {date_str}")
        return None
