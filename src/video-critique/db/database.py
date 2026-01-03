"""
Database Router - Selects and exposes the appropriate database backend.

This module provides a unified interface to the database, automatically
selecting between SQLite (legacy) and Supabase based on environment configuration.

Usage:
    from db.database import db

    # All methods are exposed directly:
    db.insert_task(task)
    db.get_task_by_number(123)
    db.save_workflow(workflow)

Configuration:
    Set DB_BACKEND environment variable:
    - "supabase" (default): Use Supabase cloud database
    - "sqlite": Use legacy SQLite database (deprecated)

    For Supabase, also set:
    - VIDEOCRITIQUE_DEV_SUPABASE_URL: Development Supabase URL
    - VIDEOCRITIQUE_DEV_SUPABASE_SERVICE_ROLE_KEY: Development service key
    - VIDEOCRITIQUE_PROD_SUPABASE_URL: Production Supabase URL
    - VIDEOCRITIQUE_PROD_SUPABASE_SERVICE_ROLE_KEY: Production service key
"""

import os
from typing import Any

from db.base import DatabaseBackend
from db.models import (
    VideoTask,
    ApprovalWorkflow,
    VideoConfig,
    CompletedTask,
    DuplicateCheckResult,
)
from core.utils.logging import get_logger

logger = get_logger("video-critique.db")

# Backend selection from environment
DB_BACKEND = os.getenv("DB_BACKEND", "supabase").lower()


def _get_backend() -> DatabaseBackend:
    """
    Get the configured database backend.

    Returns:
        DatabaseBackend instance based on DB_BACKEND environment variable.

    Raises:
        RuntimeError: In production if Supabase credentials are missing
    """
    environment = os.getenv("ENVIRONMENT", "development")
    is_production = environment == "production"

    if DB_BACKEND == "supabase":
        # Check if credentials are available
        import config as app_config

        supabase_url = app_config.SUPABASE_URL
        supabase_key = app_config.SUPABASE_SERVICE_ROLE_KEY

        if not supabase_url or not supabase_key:
            if is_production:
                raise RuntimeError(
                    "[DB] FATAL: Supabase credentials missing in production. "
                    "Set VIDEOCRITIQUE_PROD_SUPABASE_URL and VIDEOCRITIQUE_PROD_SUPABASE_SERVICE_ROLE_KEY"
                )
            logger.warning("[DB] Supabase credentials not set")
            raise RuntimeError(
                "[DB] Supabase credentials not configured. "
                "Set VIDEOCRITIQUE_DEV_SUPABASE_URL and VIDEOCRITIQUE_DEV_SUPABASE_SERVICE_ROLE_KEY"
            )

        try:
            from db.backends.supabase import SupabaseBackend
            logger.info("[DB] Using Supabase backend")
            return SupabaseBackend()
        except ImportError as e:
            if is_production:
                raise RuntimeError(f"[DB] FATAL: Supabase package not installed: {e}")
            raise RuntimeError(f"[DB] Supabase package not installed: {e}")
        except Exception as e:
            if is_production:
                raise RuntimeError(f"[DB] FATAL: Failed to initialize Supabase: {e}")
            raise RuntimeError(f"[DB] Failed to initialize Supabase: {e}")
    else:
        raise RuntimeError(f"[DB] Unknown backend: {DB_BACKEND}. Use 'supabase'.")


# Create the backend instance (lazy initialization)
_backend: DatabaseBackend | None = None


def get_backend() -> DatabaseBackend:
    """Get the database backend (lazy initialization)."""
    global _backend
    if _backend is None:
        _backend = _get_backend()
        _backend.init_db()
    return _backend


class _DatabaseNamespace:
    """
    Namespace wrapper to expose backend methods as db.method() calls.

    This provides a clean interface:
        from db.database import db
        db.insert_task(task)
    """

    @property
    def backend_name(self) -> str:
        """Get the name of the current backend."""
        return get_backend().name

    # =========================================================================
    # VIDEO TASKS
    # =========================================================================

    def get_next_task_number(self) -> int:
        """Get the next available task number."""
        return get_backend().get_next_task_number()

    def insert_task(self, task: VideoTask) -> int:
        """Insert a new task. Returns task number."""
        return get_backend().insert_task(task)

    def get_task_by_number(self, task_number: int) -> VideoTask | None:
        """Get a task by task number."""
        return get_backend().get_task_by_number(task_number)

    def get_all_tasks(self) -> list[VideoTask]:
        """Get all live tasks."""
        return get_backend().get_all_tasks()

    def get_tasks_by_status(self, status: str) -> list[VideoTask]:
        """Get tasks filtered by status."""
        return get_backend().get_tasks_by_status(status)

    def get_tasks_by_videographer(self, videographer: str) -> list[VideoTask]:
        """Get tasks assigned to a specific videographer."""
        return get_backend().get_tasks_by_videographer(videographer)

    def update_task(self, task_number: int, updates: dict[str, Any]) -> bool:
        """Update a task by task number."""
        return get_backend().update_task(task_number, updates)

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
        return get_backend().update_task_status(
            task_number, new_status, folder, version,
            rejection_reason, rejection_class, rejected_by
        )

    def archive_task(self, task_number: int) -> bool:
        """Archive a task (move from live to completed)."""
        return get_backend().archive_task(task_number)

    def delete_task(self, task_number: int) -> bool:
        """Delete a task permanently."""
        return get_backend().delete_task(task_number)

    def check_duplicate_reference(self, reference_number: str) -> DuplicateCheckResult:
        """Check if a reference number already exists."""
        return get_backend().check_duplicate_reference(reference_number)

    # =========================================================================
    # COMPLETED TASKS
    # =========================================================================

    def get_completed_tasks(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> list[CompletedTask]:
        """Get completed/archived tasks."""
        return get_backend().get_completed_tasks(limit, offset)

    def get_completed_task_by_number(self, task_number: int) -> CompletedTask | None:
        """Get a completed task by task number."""
        return get_backend().get_completed_task_by_number(task_number)

    # =========================================================================
    # APPROVAL WORKFLOWS
    # =========================================================================

    def save_workflow(self, workflow: ApprovalWorkflow) -> bool:
        """Save or update an approval workflow."""
        return get_backend().save_workflow(workflow)

    def get_workflow(self, workflow_id: str) -> ApprovalWorkflow | None:
        """Get a workflow by ID."""
        return get_backend().get_workflow(workflow_id)

    def get_workflow_by_task_number(self, task_number: int) -> ApprovalWorkflow | None:
        """Get a workflow by task number."""
        return get_backend().get_workflow_by_task_number(task_number)

    def get_pending_workflows(self) -> list[ApprovalWorkflow]:
        """Get all pending approval workflows."""
        return get_backend().get_pending_workflows()

    def update_workflow(self, workflow_id: str, updates: dict[str, Any]) -> bool:
        """Update a workflow."""
        return get_backend().update_workflow(workflow_id, updates)

    def delete_workflow(self, workflow_id: str) -> bool:
        """Delete a workflow."""
        return get_backend().delete_workflow(workflow_id)

    # =========================================================================
    # CONFIGURATION
    # =========================================================================

    def get_config(self, config_type: str, config_key: str) -> VideoConfig | None:
        """Get a configuration entry."""
        return get_backend().get_config(config_type, config_key)

    def get_all_configs(self, config_type: str) -> list[VideoConfig]:
        """Get all configuration entries of a type."""
        return get_backend().get_all_configs(config_type)

    def save_config(self, config: VideoConfig) -> bool:
        """Save or update a configuration entry."""
        return get_backend().save_config(config)

    def delete_config(self, config_type: str, config_key: str) -> bool:
        """Delete a configuration entry."""
        return get_backend().delete_config(config_type, config_key)

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
        return get_backend().log_ai_cost(
            call_type, model, input_tokens, output_tokens, total_cost,
            user_id, workflow, context, timestamp
        )

    def get_ai_costs_summary(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        workflow: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Get AI costs summary with optional filters."""
        return get_backend().get_ai_costs_summary(
            start_date, end_date, workflow, user_id
        )

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
        return get_backend().save_chat_session(user_id, messages, session_id)

    def get_chat_session(self, user_id: str) -> dict[str, Any] | None:
        """Get a user's chat session."""
        return get_backend().get_chat_session(user_id)

    def delete_chat_session(self, user_id: str) -> bool:
        """Delete a user's chat session."""
        return get_backend().delete_chat_session(user_id)

    # =========================================================================
    # EXPORT
    # =========================================================================

    def export_tasks_to_excel(self, include_completed: bool = False) -> str:
        """Export tasks to Excel file."""
        return get_backend().export_tasks_to_excel(include_completed)


# Create the singleton database interface
db = _DatabaseNamespace()
