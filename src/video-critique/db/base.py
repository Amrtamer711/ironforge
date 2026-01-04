"""
Abstract base class for database backends.

Each backend implements their own storage-specific syntax.
Video-critique specific interface for tasks, workflows, and configuration.
"""

from abc import ABC, abstractmethod
from typing import Any

from db.models import (
    VideoTask,
    ApprovalWorkflow,
    VideoConfig,
    CompletedTask,
    DuplicateCheckResult,
)


class DatabaseBackend(ABC):
    """
    Abstract base class for database backends.

    Each backend (SQLite, Supabase, etc.) implements this interface
    with their own storage-specific syntax.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Backend name (e.g., 'sqlite', 'supabase')."""
        pass

    @abstractmethod
    def init_db(self) -> None:
        """Initialize database schema."""
        pass

    # =========================================================================
    # VIDEO TASKS
    # =========================================================================

    @abstractmethod
    def get_next_task_number(self) -> int:
        """Get the next available task number."""
        pass

    @abstractmethod
    def insert_task(self, task: VideoTask) -> int:
        """
        Insert a new task.

        Args:
            task: VideoTask model to insert

        Returns:
            Task number of the inserted task
        """
        pass

    @abstractmethod
    def get_task_by_number(self, task_number: int) -> VideoTask | None:
        """
        Get a task by task number.

        Args:
            task_number: Task number to look up

        Returns:
            VideoTask model if found, None otherwise
        """
        pass

    @abstractmethod
    def get_all_tasks(self) -> list[VideoTask]:
        """
        Get all live tasks.

        Returns:
            List of VideoTask models
        """
        pass

    @abstractmethod
    def get_tasks_by_status(self, status: str) -> list[VideoTask]:
        """
        Get tasks filtered by status.

        Args:
            status: Status to filter by

        Returns:
            List of matching VideoTask models
        """
        pass

    @abstractmethod
    def get_tasks_by_videographer(self, videographer: str) -> list[VideoTask]:
        """
        Get tasks assigned to a specific videographer.

        Args:
            videographer: Videographer name

        Returns:
            List of matching VideoTask models
        """
        pass

    @abstractmethod
    def update_task(self, task_number: int, updates: dict[str, Any]) -> bool:
        """
        Update a task by task number.

        Args:
            task_number: Task number to update
            updates: Dictionary of fields to update

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
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
        """
        Update task status with version history and timestamps.

        Args:
            task_number: Task number to update
            new_status: New status value
            folder: Folder name (for version history)
            version: Version number
            rejection_reason: Reason for rejection
            rejection_class: Classification of rejection
            rejected_by: Who rejected

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    def archive_task(self, task_number: int) -> bool:
        """
        Archive a task (move from live to completed).

        Args:
            task_number: Task number to archive

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    def delete_task(self, task_number: int) -> bool:
        """
        Delete a task permanently.

        Args:
            task_number: Task number to delete

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    def check_duplicate_reference(self, reference_number: str) -> DuplicateCheckResult:
        """
        Check if a reference number already exists.

        Args:
            reference_number: Reference number to check

        Returns:
            DuplicateCheckResult with is_duplicate flag and existing entry if found
        """
        pass

    # =========================================================================
    # COMPLETED TASKS
    # =========================================================================

    @abstractmethod
    def get_completed_tasks(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> list[CompletedTask]:
        """
        Get completed/archived tasks.

        Args:
            limit: Maximum number of tasks to return
            offset: Number of tasks to skip

        Returns:
            List of CompletedTask models
        """
        pass

    @abstractmethod
    def get_completed_task_by_number(self, task_number: int) -> CompletedTask | None:
        """
        Get a completed task by task number.

        Args:
            task_number: Task number to look up

        Returns:
            CompletedTask model if found, None otherwise
        """
        pass

    # =========================================================================
    # APPROVAL WORKFLOWS
    # =========================================================================

    @abstractmethod
    def save_workflow(self, workflow: ApprovalWorkflow) -> bool:
        """
        Save or update an approval workflow.

        Args:
            workflow: ApprovalWorkflow model to save

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    def get_workflow(self, workflow_id: str) -> ApprovalWorkflow | None:
        """
        Get a workflow by ID.

        Args:
            workflow_id: Workflow ID to look up

        Returns:
            ApprovalWorkflow model if found, None otherwise
        """
        pass

    @abstractmethod
    def get_workflow_by_task_number(self, task_number: int) -> ApprovalWorkflow | None:
        """
        Get a workflow by task number.

        Args:
            task_number: Task number to look up

        Returns:
            ApprovalWorkflow model if found, None otherwise
        """
        pass

    @abstractmethod
    def get_pending_workflows(self) -> list[ApprovalWorkflow]:
        """
        Get all pending approval workflows.

        Returns:
            List of pending ApprovalWorkflow models
        """
        pass

    @abstractmethod
    def update_workflow(self, workflow_id: str, updates: dict[str, Any]) -> bool:
        """
        Update a workflow.

        Args:
            workflow_id: Workflow ID to update
            updates: Dictionary of fields to update

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    def delete_workflow(self, workflow_id: str) -> bool:
        """
        Delete a workflow.

        Args:
            workflow_id: Workflow ID to delete

        Returns:
            True if successful, False otherwise
        """
        pass

    # =========================================================================
    # CONFIGURATION
    # =========================================================================

    @abstractmethod
    def get_config(self, config_type: str, config_key: str) -> VideoConfig | None:
        """
        Get a configuration entry.

        Args:
            config_type: Type of configuration (from ConfigType enum)
            config_key: Unique key within the config type

        Returns:
            VideoConfig model if found, None otherwise
        """
        pass

    @abstractmethod
    def get_all_configs(self, config_type: str) -> list[VideoConfig]:
        """
        Get all configuration entries of a type.

        Args:
            config_type: Type of configuration to retrieve

        Returns:
            List of VideoConfig models
        """
        pass

    @abstractmethod
    def save_config(self, config: VideoConfig) -> bool:
        """
        Save or update a configuration entry.

        Args:
            config: VideoConfig model to save

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    def delete_config(self, config_type: str, config_key: str) -> bool:
        """
        Delete a configuration entry.

        Args:
            config_type: Type of configuration
            config_key: Key to delete

        Returns:
            True if successful, False otherwise
        """
        pass

    # =========================================================================
    # AI COSTS
    # =========================================================================

    @abstractmethod
    def log_ai_cost(
        self,
        call_type: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        reasoning_tokens: int,
        input_cost: float,
        output_cost: float,
        reasoning_cost: float,
        total_cost: float,
        user_id: str | None = None,
        workflow: str | None = None,
        cached_input_tokens: int = 0,
        context: str | None = None,
        metadata_json: str | None = None,
        timestamp: str | None = None,
    ) -> None:
        """Log an AI API cost entry with full cost breakdown."""
        pass

    @abstractmethod
    def get_ai_costs_summary(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        workflow: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Get AI costs summary with optional filters."""
        pass

    # =========================================================================
    # CHAT SESSIONS (for Web channel)
    # =========================================================================

    @abstractmethod
    def save_chat_session(
        self,
        user_id: str,
        messages: list[dict[str, Any]],
        session_id: str | None = None,
    ) -> bool:
        """
        Save or update a user's chat session.

        Args:
            user_id: User's unique ID
            messages: List of message dictionaries
            session_id: Optional session ID

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    def get_chat_session(self, user_id: str) -> dict[str, Any] | None:
        """
        Get a user's chat session.

        Args:
            user_id: User's unique ID

        Returns:
            Dict with session_id, messages, timestamps or None
        """
        pass

    @abstractmethod
    def delete_chat_session(self, user_id: str) -> bool:
        """
        Delete a user's chat session.

        Args:
            user_id: User's unique ID

        Returns:
            True if deleted, False if not found
        """
        pass

    # =========================================================================
    # EXPORT
    # =========================================================================

    @abstractmethod
    def export_tasks_to_excel(self, include_completed: bool = False) -> str:
        """
        Export tasks to Excel file.

        Args:
            include_completed: Whether to include completed tasks

        Returns:
            Path to the generated Excel file
        """
        pass
