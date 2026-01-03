"""
Supabase database backend implementation for Video Critique Service.

This module implements the DatabaseBackend interface using Supabase
as the storage backend.
"""

import json
import os
import uuid
from datetime import datetime
from typing import Any

from supabase import create_client, Client

from db.base import DatabaseBackend
from db.models import (
    VideoTask,
    ApprovalWorkflow,
    VideoConfig,
    CompletedTask,
    DuplicateCheckResult,
    TaskStatus,
    ApprovalStatus,
)
from core.utils.logging import get_logger
from core.utils.time import get_uae_time, UAE_TZ

logger = get_logger(__name__)


class SupabaseBackend(DatabaseBackend):
    """
    Supabase implementation of the database backend.

    Uses Supabase client to interact with PostgreSQL database.
    """

    def __init__(self):
        """Initialize Supabase client."""
        self._client: Client | None = None

    def _get_client(self) -> Client:
        """Get or create Supabase client (lazy initialization)."""
        if self._client is None:
            # Import config here to avoid circular imports
            import config

            url = config.SUPABASE_URL
            key = config.SUPABASE_SERVICE_ROLE_KEY

            if not url or not key:
                raise RuntimeError(
                    "Supabase credentials not configured. "
                    "Set VIDEOCRITIQUE_DEV_SUPABASE_URL and VIDEOCRITIQUE_DEV_SUPABASE_SERVICE_ROLE_KEY"
                )

            self._client = create_client(url, key)
            logger.info("[SUPABASE] Client initialized")

        return self._client

    @property
    def name(self) -> str:
        return "supabase"

    def init_db(self) -> None:
        """
        Initialize database schema.

        For Supabase, schema is managed via migrations in the Supabase dashboard
        or migration files. This method just verifies connectivity.
        """
        try:
            client = self._get_client()
            # Test connectivity by doing a simple query
            result = client.table("video_tasks").select("count", count="exact").limit(0).execute()
            logger.info(f"[SUPABASE] Database initialized - video_tasks table accessible")
        except Exception as e:
            logger.error(f"[SUPABASE] Failed to initialize database: {e}")
            raise

    # =========================================================================
    # VIDEO TASKS
    # =========================================================================

    def get_next_task_number(self) -> int:
        """Get the next available task number."""
        try:
            client = self._get_client()

            # Get max from live tasks
            live_result = (
                client.table("video_tasks")
                .select("task_number")
                .order("task_number", desc=True)
                .limit(1)
                .execute()
            )
            live_max = live_result.data[0]["task_number"] if live_result.data else 0

            # Get max from completed tasks
            completed_result = (
                client.table("completed_tasks")
                .select("task_number")
                .order("task_number", desc=True)
                .limit(1)
                .execute()
            )
            completed_max = completed_result.data[0]["task_number"] if completed_result.data else 0

            return max(live_max, completed_max) + 1
        except Exception as e:
            logger.error(f"[SUPABASE] Error getting next task number: {e}")
            return 1

    def insert_task(self, task: VideoTask) -> int:
        """Insert a new task."""
        try:
            client = self._get_client()

            # Get task number if not provided
            if task.task_number is None:
                task.task_number = self.get_next_task_number()

            # Prepare data
            data = {
                "task_number": task.task_number,
                "brand": task.brand,
                "campaign_start_date": task.campaign_start_date,
                "campaign_end_date": task.campaign_end_date,
                "reference_number": task.reference_number,
                "location": task.location,
                "sales_person": task.sales_person,
                "submitted_by": task.submitted_by,
                "status": task.status,
                "filming_date": task.filming_date,
                "videographer": task.videographer,
                "task_type": task.task_type,
                "time_block": task.time_block,
                "submission_folder": task.submission_folder,
                "current_version": task.current_version,
                "version_history": json.dumps(task.version_history) if task.version_history else "[]",
                "timestamp": task.timestamp or get_uae_time().strftime("%d-%m-%Y %H:%M:%S"),
                "pending_timestamps": task.pending_timestamps,
                "submitted_timestamps": task.submitted_timestamps,
                "returned_timestamps": task.returned_timestamps,
                "rejected_timestamps": task.rejected_timestamps,
                "accepted_timestamps": task.accepted_timestamps,
            }

            result = client.table("video_tasks").insert(data).execute()
            logger.info(f"[SUPABASE] Inserted task #{task.task_number}")
            return task.task_number

        except Exception as e:
            logger.error(f"[SUPABASE] Error inserting task: {e}")
            raise

    def get_task_by_number(self, task_number: int) -> VideoTask | None:
        """Get a task by task number."""
        try:
            client = self._get_client()
            result = (
                client.table("video_tasks")
                .select("*")
                .eq("task_number", task_number)
                .execute()
            )

            if not result.data:
                return None

            return VideoTask.from_dict(result.data[0])
        except Exception as e:
            logger.error(f"[SUPABASE] Error getting task {task_number}: {e}")
            return None

    def get_all_tasks(self) -> list[VideoTask]:
        """Get all live tasks."""
        try:
            client = self._get_client()
            result = (
                client.table("video_tasks")
                .select("*")
                .order("task_number", desc=False)
                .execute()
            )

            return [VideoTask.from_dict(row) for row in result.data]
        except Exception as e:
            logger.error(f"[SUPABASE] Error getting all tasks: {e}")
            return []

    def get_tasks_by_status(self, status: str) -> list[VideoTask]:
        """Get tasks filtered by status."""
        try:
            client = self._get_client()

            # Handle "Assigned to X" pattern
            if status.startswith("Assigned"):
                result = (
                    client.table("video_tasks")
                    .select("*")
                    .like("status", "Assigned%")
                    .execute()
                )
            else:
                result = (
                    client.table("video_tasks")
                    .select("*")
                    .eq("status", status)
                    .execute()
                )

            return [VideoTask.from_dict(row) for row in result.data]
        except Exception as e:
            logger.error(f"[SUPABASE] Error getting tasks by status: {e}")
            return []

    def get_tasks_by_videographer(self, videographer: str) -> list[VideoTask]:
        """Get tasks assigned to a specific videographer."""
        try:
            client = self._get_client()
            result = (
                client.table("video_tasks")
                .select("*")
                .eq("videographer", videographer)
                .execute()
            )

            return [VideoTask.from_dict(row) for row in result.data]
        except Exception as e:
            logger.error(f"[SUPABASE] Error getting tasks for videographer: {e}")
            return []

    def update_task(self, task_number: int, updates: dict[str, Any]) -> bool:
        """Update a task by task number."""
        try:
            client = self._get_client()

            # Handle version_history if present
            if "version_history" in updates and isinstance(updates["version_history"], list):
                updates["version_history"] = json.dumps(updates["version_history"])

            # Add updated_at timestamp
            updates["updated_at"] = get_uae_time().isoformat()

            client.table("video_tasks").update(updates).eq("task_number", task_number).execute()
            logger.info(f"[SUPABASE] Updated task #{task_number}")
            return True
        except Exception as e:
            logger.error(f"[SUPABASE] Error updating task {task_number}: {e}")
            return False

    def update_task_status(
        self,
        task_number: int,
        new_status: str,
        folder: str | None = None,
        version: int | None = None,
        rejection_reason: str | None = None,
        rejection_class: str | None = None,
        rejected_by: str | None = None,
    ) -> bool:
        """Update task status with version history and timestamps."""
        try:
            # Get current task
            task = self.get_task_by_number(task_number)
            if not task:
                return False

            updates = {"status": new_status}

            # Update version history if version provided
            if version is not None and folder:
                timestamp = get_uae_time().strftime("%d-%m-%Y %H:%M:%S")
                task.add_version_entry(
                    version=version,
                    folder=folder,
                    timestamp=timestamp,
                    rejection_class=rejection_class,
                    rejection_reason=rejection_reason,
                    rejected_by=rejected_by,
                )
                updates["version_history"] = json.dumps(task.version_history)

            # Update timestamp columns based on folder/status
            timestamp = get_uae_time().strftime("%d-%m-%Y %H:%M:%S")
            stamp = f"v{version}:{timestamp}" if version else timestamp

            folder_to_column = {
                "Pending": "pending_timestamps",
                "Critique": "pending_timestamps",
                "Submitted to Sales": "submitted_timestamps",
                "Returned": "returned_timestamps",
                "Rejected": "rejected_timestamps",
                "Editing": "rejected_timestamps",
                "Accepted": "accepted_timestamps",
                "Done": "accepted_timestamps",
            }

            col = folder_to_column.get(folder) or folder_to_column.get(new_status)
            if col:
                existing = getattr(task, col, "") or ""
                updated = (existing + ("; " if existing else "") + stamp)
                updates[col] = updated

            return self.update_task(task_number, updates)
        except Exception as e:
            logger.error(f"[SUPABASE] Error updating task status: {e}")
            return False

    def archive_task(self, task_number: int) -> bool:
        """Archive a task (move from live to completed)."""
        try:
            client = self._get_client()

            # Get the task first
            task = self.get_task_by_number(task_number)
            if not task:
                return False

            # Create completed task entry
            completed_data = {
                "task_number": task.task_number,
                "brand": task.brand,
                "campaign_start_date": task.campaign_start_date,
                "campaign_end_date": task.campaign_end_date,
                "reference_number": task.reference_number,
                "location": task.location,
                "sales_person": task.sales_person,
                "submitted_by": task.submitted_by,
                "status": task.status,
                "filming_date": task.filming_date,
                "videographer": task.videographer,
                "task_type": task.task_type,
                "time_block": task.time_block,
                "submission_folder": task.submission_folder,
                "current_version": task.current_version,
                "version_history": json.dumps(task.version_history) if task.version_history else "[]",
                "pending_timestamps": task.pending_timestamps,
                "submitted_timestamps": task.submitted_timestamps,
                "returned_timestamps": task.returned_timestamps,
                "rejected_timestamps": task.rejected_timestamps,
                "accepted_timestamps": task.accepted_timestamps,
                "completed_at": get_uae_time().isoformat(),
            }

            # Insert into completed_tasks
            client.table("completed_tasks").insert(completed_data).execute()

            # Delete from video_tasks
            client.table("video_tasks").delete().eq("task_number", task_number).execute()

            logger.info(f"[SUPABASE] Archived task #{task_number}")
            return True
        except Exception as e:
            logger.error(f"[SUPABASE] Error archiving task {task_number}: {e}")
            return False

    def delete_task(self, task_number: int) -> bool:
        """Delete a task permanently."""
        try:
            client = self._get_client()
            client.table("video_tasks").delete().eq("task_number", task_number).execute()
            logger.info(f"[SUPABASE] Deleted task #{task_number}")
            return True
        except Exception as e:
            logger.error(f"[SUPABASE] Error deleting task {task_number}: {e}")
            return False

    def check_duplicate_reference(self, reference_number: str) -> DuplicateCheckResult:
        """Check if a reference number already exists."""
        try:
            client = self._get_client()
            clean_ref = reference_number.replace("_", "-")

            # Check live tasks
            live_result = (
                client.table("video_tasks")
                .select("*")
                .eq("reference_number", clean_ref)
                .execute()
            )

            if live_result.data:
                row = live_result.data[0]
                return DuplicateCheckResult(
                    is_duplicate=True,
                    existing_entry={
                        "task_number": str(row["task_number"]),
                        "brand": row.get("brand", ""),
                        "start_date": row.get("campaign_start_date", ""),
                        "end_date": row.get("campaign_end_date", ""),
                        "location": row.get("location", ""),
                        "submitted_by": row.get("submitted_by", ""),
                        "timestamp": row.get("timestamp", ""),
                        "status": "Active",
                    }
                )

            # Check completed tasks
            completed_result = (
                client.table("completed_tasks")
                .select("*")
                .eq("reference_number", clean_ref)
                .execute()
            )

            if completed_result.data:
                row = completed_result.data[0]
                return DuplicateCheckResult(
                    is_duplicate=True,
                    existing_entry={
                        "task_number": str(row["task_number"]),
                        "brand": row.get("brand", ""),
                        "start_date": row.get("campaign_start_date", ""),
                        "end_date": row.get("campaign_end_date", ""),
                        "location": row.get("location", ""),
                        "submitted_by": row.get("submitted_by", ""),
                        "timestamp": row.get("completed_at", ""),
                        "status": "Archived (Completed)",
                    }
                )

            return DuplicateCheckResult(is_duplicate=False)
        except Exception as e:
            logger.error(f"[SUPABASE] Error checking duplicate reference: {e}")
            return DuplicateCheckResult(is_duplicate=False)

    # =========================================================================
    # COMPLETED TASKS
    # =========================================================================

    def get_completed_tasks(self, limit: int = 100, offset: int = 0) -> list[CompletedTask]:
        """Get completed/archived tasks."""
        try:
            client = self._get_client()
            result = (
                client.table("completed_tasks")
                .select("*")
                .order("completed_at", desc=True)
                .range(offset, offset + limit - 1)
                .execute()
            )

            return [CompletedTask.from_dict(row) for row in result.data]
        except Exception as e:
            logger.error(f"[SUPABASE] Error getting completed tasks: {e}")
            return []

    def get_completed_task_by_number(self, task_number: int) -> CompletedTask | None:
        """Get a completed task by task number."""
        try:
            client = self._get_client()
            result = (
                client.table("completed_tasks")
                .select("*")
                .eq("task_number", task_number)
                .execute()
            )

            if not result.data:
                return None

            return CompletedTask.from_dict(result.data[0])
        except Exception as e:
            logger.error(f"[SUPABASE] Error getting completed task: {e}")
            return None

    # =========================================================================
    # APPROVAL WORKFLOWS
    # =========================================================================

    def save_workflow(self, workflow: ApprovalWorkflow) -> bool:
        """Save or update an approval workflow."""
        try:
            client = self._get_client()

            data = {
                "workflow_id": workflow.workflow_id or str(uuid.uuid4()),
                "task_number": workflow.task_number,
                "folder_name": workflow.folder_name,
                "dropbox_path": workflow.dropbox_path,
                "videographer_id": workflow.videographer_id,
                "reviewer_id": workflow.reviewer_id,
                "hos_id": workflow.hos_id,
                "reviewer_msg_ts": workflow.reviewer_msg_ts,
                "hos_msg_ts": workflow.hos_msg_ts,
                "reviewer_notification_id": workflow.reviewer_notification_id,
                "hos_notification_id": workflow.hos_notification_id,
                "reviewer_approved": workflow.reviewer_approved,
                "hos_approved": workflow.hos_approved,
                "status": workflow.status,
                "task_data": json.dumps(workflow.task_data) if workflow.task_data else "{}",
                "version_info": json.dumps(workflow.version_info) if workflow.version_info else "{}",
                "updated_at": get_uae_time().isoformat(),
            }

            # Use upsert
            client.table("approval_workflows").upsert(data, on_conflict="workflow_id").execute()
            logger.info(f"[SUPABASE] Saved workflow {workflow.workflow_id}")
            return True
        except Exception as e:
            logger.error(f"[SUPABASE] Error saving workflow: {e}")
            return False

    def get_workflow(self, workflow_id: str) -> ApprovalWorkflow | None:
        """Get a workflow by ID."""
        try:
            client = self._get_client()
            result = (
                client.table("approval_workflows")
                .select("*")
                .eq("workflow_id", workflow_id)
                .execute()
            )

            if not result.data:
                return None

            return ApprovalWorkflow.from_dict(result.data[0])
        except Exception as e:
            logger.error(f"[SUPABASE] Error getting workflow: {e}")
            return None

    def get_workflow_by_task_number(self, task_number: int) -> ApprovalWorkflow | None:
        """Get a workflow by task number."""
        try:
            client = self._get_client()
            result = (
                client.table("approval_workflows")
                .select("*")
                .eq("task_number", task_number)
                .eq("status", ApprovalStatus.PENDING.value)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )

            if not result.data:
                return None

            return ApprovalWorkflow.from_dict(result.data[0])
        except Exception as e:
            logger.error(f"[SUPABASE] Error getting workflow by task: {e}")
            return None

    def get_pending_workflows(self) -> list[ApprovalWorkflow]:
        """Get all pending approval workflows."""
        try:
            client = self._get_client()
            result = (
                client.table("approval_workflows")
                .select("*")
                .eq("status", ApprovalStatus.PENDING.value)
                .order("created_at", desc=False)
                .execute()
            )

            return [ApprovalWorkflow.from_dict(row) for row in result.data]
        except Exception as e:
            logger.error(f"[SUPABASE] Error getting pending workflows: {e}")
            return []

    def update_workflow(self, workflow_id: str, updates: dict[str, Any]) -> bool:
        """Update a workflow."""
        try:
            client = self._get_client()

            # Handle JSON fields
            if "task_data" in updates and isinstance(updates["task_data"], dict):
                updates["task_data"] = json.dumps(updates["task_data"])
            if "version_info" in updates and isinstance(updates["version_info"], dict):
                updates["version_info"] = json.dumps(updates["version_info"])

            updates["updated_at"] = get_uae_time().isoformat()

            client.table("approval_workflows").update(updates).eq("workflow_id", workflow_id).execute()
            logger.info(f"[SUPABASE] Updated workflow {workflow_id}")
            return True
        except Exception as e:
            logger.error(f"[SUPABASE] Error updating workflow: {e}")
            return False

    def delete_workflow(self, workflow_id: str) -> bool:
        """Delete a workflow."""
        try:
            client = self._get_client()
            client.table("approval_workflows").delete().eq("workflow_id", workflow_id).execute()
            logger.info(f"[SUPABASE] Deleted workflow {workflow_id}")
            return True
        except Exception as e:
            logger.error(f"[SUPABASE] Error deleting workflow: {e}")
            return False

    # =========================================================================
    # CONFIGURATION
    # =========================================================================

    def get_config(self, config_type: str, config_key: str) -> VideoConfig | None:
        """Get a configuration entry."""
        try:
            client = self._get_client()
            result = (
                client.table("video_config")
                .select("*")
                .eq("config_type", config_type)
                .eq("config_key", config_key)
                .execute()
            )

            if not result.data:
                return None

            return VideoConfig.from_dict(result.data[0])
        except Exception as e:
            logger.error(f"[SUPABASE] Error getting config: {e}")
            return None

    def get_all_configs(self, config_type: str) -> list[VideoConfig]:
        """Get all configuration entries of a type."""
        try:
            client = self._get_client()
            result = (
                client.table("video_config")
                .select("*")
                .eq("config_type", config_type)
                .execute()
            )

            return [VideoConfig.from_dict(row) for row in result.data]
        except Exception as e:
            logger.error(f"[SUPABASE] Error getting configs: {e}")
            return []

    def save_config(self, config: VideoConfig) -> bool:
        """Save or update a configuration entry."""
        try:
            client = self._get_client()

            data = {
                "config_type": config.config_type,
                "config_key": config.config_key,
                "config_data": json.dumps(config.config_data) if config.config_data else "{}",
                "updated_at": get_uae_time().isoformat(),
            }

            # Use upsert with conflict on (config_type, config_key)
            client.table("video_config").upsert(
                data, on_conflict="config_type,config_key"
            ).execute()
            logger.info(f"[SUPABASE] Saved config {config.config_type}/{config.config_key}")
            return True
        except Exception as e:
            logger.error(f"[SUPABASE] Error saving config: {e}")
            return False

    def delete_config(self, config_type: str, config_key: str) -> bool:
        """Delete a configuration entry."""
        try:
            client = self._get_client()
            client.table("video_config").delete().eq("config_type", config_type).eq("config_key", config_key).execute()
            logger.info(f"[SUPABASE] Deleted config {config_type}/{config_key}")
            return True
        except Exception as e:
            logger.error(f"[SUPABASE] Error deleting config: {e}")
            return False

    # =========================================================================
    # AI COSTS
    # =========================================================================

    def log_ai_cost(
        self,
        call_type: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        total_cost: float,
        user_id: str | None = None,
        workflow: str | None = None,
        context: str | None = None,
        timestamp: str | None = None,
    ) -> None:
        """Log an AI API cost entry."""
        try:
            client = self._get_client()

            data = {
                "call_type": call_type,
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_cost": total_cost,
                "user_id": user_id,
                "workflow": workflow,
                "context": context,
                "timestamp": timestamp or get_uae_time().isoformat(),
            }

            client.table("ai_costs").insert(data).execute()
        except Exception as e:
            logger.error(f"[SUPABASE] Error logging AI cost: {e}")

    def get_ai_costs_summary(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        workflow: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Get AI costs summary with optional filters."""
        try:
            client = self._get_client()
            query = client.table("ai_costs").select("*")

            if start_date:
                query = query.gte("timestamp", start_date)
            if end_date:
                query = query.lte("timestamp", end_date)
            if workflow:
                query = query.eq("workflow", workflow)
            if user_id:
                query = query.eq("user_id", user_id)

            result = query.execute()

            # Calculate summary
            total_cost = sum(row.get("total_cost", 0) for row in result.data)
            total_input = sum(row.get("input_tokens", 0) for row in result.data)
            total_output = sum(row.get("output_tokens", 0) for row in result.data)

            return {
                "total_cost": total_cost,
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "total_calls": len(result.data),
                "entries": result.data,
            }
        except Exception as e:
            logger.error(f"[SUPABASE] Error getting AI costs summary: {e}")
            return {
                "total_cost": 0,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_calls": 0,
                "entries": [],
            }

    # =========================================================================
    # CHAT SESSIONS
    # =========================================================================

    def save_chat_session(
        self,
        user_id: str,
        messages: list[dict[str, Any]],
        session_id: str | None = None,
    ) -> bool:
        """Save or update a user's chat session."""
        try:
            client = self._get_client()

            data = {
                "user_id": user_id,
                "session_id": session_id or str(uuid.uuid4()),
                "messages": json.dumps(messages),
                "updated_at": get_uae_time().isoformat(),
            }

            # Use upsert with user_id as conflict key
            client.table("chat_sessions").upsert(data, on_conflict="user_id").execute()
            return True
        except Exception as e:
            logger.error(f"[SUPABASE] Error saving chat session: {e}")
            return False

    def get_chat_session(self, user_id: str) -> dict[str, Any] | None:
        """Get a user's chat session."""
        try:
            client = self._get_client()
            result = (
                client.table("chat_sessions")
                .select("*")
                .eq("user_id", user_id)
                .execute()
            )

            if not result.data:
                return None

            row = result.data[0]
            messages = row.get("messages", "[]")
            if isinstance(messages, str):
                messages = json.loads(messages)

            return {
                "session_id": row.get("session_id"),
                "messages": messages,
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
            }
        except Exception as e:
            logger.error(f"[SUPABASE] Error getting chat session: {e}")
            return None

    def delete_chat_session(self, user_id: str) -> bool:
        """Delete a user's chat session."""
        try:
            client = self._get_client()
            client.table("chat_sessions").delete().eq("user_id", user_id).execute()
            return True
        except Exception as e:
            logger.error(f"[SUPABASE] Error deleting chat session: {e}")
            return False

    # =========================================================================
    # EXPORT
    # =========================================================================

    def export_tasks_to_excel(self, include_completed: bool = False) -> str:
        """Export tasks to Excel file."""
        try:
            import pandas as pd
            from tempfile import NamedTemporaryFile

            # Get live tasks
            tasks = self.get_all_tasks()
            live_df = pd.DataFrame([t.to_dict() for t in tasks])

            if include_completed:
                completed = self.get_completed_tasks(limit=10000)
                completed_df = pd.DataFrame([t.to_dict() for t in completed])

            # Create Excel file
            timestamp = get_uae_time().strftime("%Y%m%d_%H%M%S")
            with NamedTemporaryFile(suffix=".xlsx", delete=False, prefix=f"tasks_{timestamp}_") as tmp:
                with pd.ExcelWriter(tmp.name, engine="openpyxl") as writer:
                    live_df.to_excel(writer, sheet_name="Live Tasks", index=False)
                    if include_completed:
                        completed_df.to_excel(writer, sheet_name="Completed Tasks", index=False)
                return tmp.name
        except Exception as e:
            logger.error(f"[SUPABASE] Error exporting to Excel: {e}")
            raise
