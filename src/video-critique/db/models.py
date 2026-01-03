"""
Database models for the Video Critique Service.

This module defines dataclass models for all database entities:
- VideoTask: Design request/video task
- ApprovalWorkflow: Multi-stage approval workflow
- VideoConfig: Configuration storage (replaces JSON files)
- Videographer: Videographer configuration
- CompletedTask: Archived/completed tasks

These models are used by the database backends (Supabase) and services.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from typing import Any, Optional
from enum import Enum
import json


class TaskStatus(str, Enum):
    """Task status values."""
    NOT_ASSIGNED = "Not assigned yet"
    ASSIGNED = "Assigned"  # Will be "Assigned to {videographer}"
    RAW = "Raw"
    CRITIQUE = "Critique"
    EDITING = "Editing"
    SUBMITTED_TO_SALES = "Submitted to Sales"
    RETURNED = "Returned"
    DONE = "Done"
    ARCHIVED = "Archived"
    PERMANENTLY_REJECTED = "Permanently Rejected"


class TaskType(str, Enum):
    """Task type values."""
    VIDEOGRAPHY = "videography"
    PHOTOGRAPHY = "photography"
    EDITING = "editing"


class ApprovalStatus(str, Enum):
    """Approval workflow status values."""
    PENDING = "pending"
    REVIEWER_APPROVED = "reviewer_approved"
    HOS_APPROVED = "hos_approved"
    REJECTED = "rejected"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ConfigType(str, Enum):
    """Configuration types for video_config table."""
    VIDEOGRAPHER = "videographer"
    LOCATION = "location"
    SALESPERSON = "salesperson"
    REVIEWER = "reviewer"
    HEAD_OF_SALES = "head_of_sales"
    HEAD_OF_DEPT = "head_of_dept"
    GENERAL = "general"


@dataclass
class VersionEntry:
    """Version history entry for a task."""
    version: int
    folder: str
    at: str  # Timestamp string
    rejection_class: str | None = None
    rejection_comments: str | None = None
    rejected_by: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary, excluding None values."""
        result = {
            "version": self.version,
            "folder": self.folder,
            "at": self.at,
        }
        if self.rejection_class:
            result["rejection_class"] = self.rejection_class
        if self.rejection_comments:
            result["rejection_comments"] = self.rejection_comments
        if self.rejected_by:
            result["rejected_by"] = self.rejected_by
        return result


@dataclass
class VideoTask:
    """
    Video task model representing a design request or video assignment.

    Maps to the `video_tasks` table in Supabase.
    """
    # Primary key
    task_number: int | None = None

    # Task details
    brand: str = ""
    campaign_start_date: str = ""  # DD-MM-YYYY format
    campaign_end_date: str = ""    # DD-MM-YYYY format
    reference_number: str = ""
    location: str = ""
    sales_person: str = ""
    submitted_by: str = ""

    # Status and assignment
    status: str = TaskStatus.NOT_ASSIGNED.value
    filming_date: str = ""  # DD-MM-YYYY format
    videographer: str = ""
    task_type: str = TaskType.VIDEOGRAPHY.value
    time_block: str | None = None  # For Abu Dhabi scheduling

    # Submission tracking
    submission_folder: str = ""
    current_version: int = 0
    version_history: list[dict] = field(default_factory=list)

    # Timestamps
    timestamp: str = ""  # Creation timestamp
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # Status change timestamps
    pending_timestamps: str = ""
    submitted_timestamps: str = ""
    returned_timestamps: str = ""
    rejected_timestamps: str = ""
    accepted_timestamps: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database operations."""
        return {
            "task_number": self.task_number,
            "brand": self.brand,
            "campaign_start_date": self.campaign_start_date,
            "campaign_end_date": self.campaign_end_date,
            "reference_number": self.reference_number,
            "location": self.location,
            "sales_person": self.sales_person,
            "submitted_by": self.submitted_by,
            "status": self.status,
            "filming_date": self.filming_date,
            "videographer": self.videographer,
            "task_type": self.task_type,
            "time_block": self.time_block,
            "submission_folder": self.submission_folder,
            "current_version": self.current_version,
            "version_history": json.dumps(self.version_history) if self.version_history else "[]",
            "timestamp": self.timestamp,
            "pending_timestamps": self.pending_timestamps,
            "submitted_timestamps": self.submitted_timestamps,
            "returned_timestamps": self.returned_timestamps,
            "rejected_timestamps": self.rejected_timestamps,
            "accepted_timestamps": self.accepted_timestamps,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VideoTask":
        """Create from dictionary (database row)."""
        # Handle version_history JSON
        version_history = data.get("version_history", "[]")
        if isinstance(version_history, str):
            try:
                version_history = json.loads(version_history)
            except json.JSONDecodeError:
                version_history = []

        return cls(
            task_number=data.get("task_number"),
            brand=data.get("brand", "") or data.get("Brand", ""),
            campaign_start_date=data.get("campaign_start_date", "") or data.get("Campaign Start Date", ""),
            campaign_end_date=data.get("campaign_end_date", "") or data.get("Campaign End Date", ""),
            reference_number=data.get("reference_number", "") or data.get("Reference Number", ""),
            location=data.get("location", "") or data.get("Location", ""),
            sales_person=data.get("sales_person", "") or data.get("Sales Person", ""),
            submitted_by=data.get("submitted_by", "") or data.get("Submitted By", ""),
            status=data.get("status", "") or data.get("Status", TaskStatus.NOT_ASSIGNED.value),
            filming_date=data.get("filming_date", "") or data.get("Filming Date", ""),
            videographer=data.get("videographer", "") or data.get("Videographer", ""),
            task_type=data.get("task_type", "") or data.get("Task Type", TaskType.VIDEOGRAPHY.value),
            time_block=data.get("time_block") or data.get("Time Block"),
            submission_folder=data.get("submission_folder", "") or data.get("Submission Folder", ""),
            current_version=int(data.get("current_version") or data.get("Current Version") or 0),
            version_history=version_history,
            timestamp=data.get("timestamp", "") or data.get("Timestamp", ""),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            pending_timestamps=data.get("pending_timestamps", "") or data.get("Pending Timestamps", ""),
            submitted_timestamps=data.get("submitted_timestamps", "") or data.get("Submitted Timestamps", ""),
            returned_timestamps=data.get("returned_timestamps", "") or data.get("Returned Timestamps", ""),
            rejected_timestamps=data.get("rejected_timestamps", "") or data.get("Rejected Timestamps", ""),
            accepted_timestamps=data.get("accepted_timestamps", "") or data.get("Accepted Timestamps", ""),
        )

    def add_version_entry(self, version: int, folder: str, timestamp: str,
                          rejection_class: str | None = None,
                          rejection_reason: str | None = None,
                          rejected_by: str | None = None) -> None:
        """Add a version history entry."""
        entry = VersionEntry(
            version=version,
            folder=folder,
            at=timestamp,
            rejection_class=rejection_class,
            rejection_comments=rejection_reason,
            rejected_by=rejected_by,
        )
        self.version_history.append(entry.to_dict())

    def get_latest_version(self) -> int:
        """Get the latest version number from history."""
        if not self.version_history:
            return 1
        return max(entry.get("version", 1) for entry in self.version_history)


@dataclass
class ApprovalWorkflow:
    """
    Approval workflow model for multi-stage video approval.

    Maps to the `approval_workflows` table in Supabase.
    """
    # Primary key
    workflow_id: str = ""

    # Task reference
    task_number: int | None = None

    # Dropbox info
    folder_name: str = ""
    dropbox_path: str = ""

    # Participants
    videographer_id: str = ""
    reviewer_id: str = ""
    hos_id: str = ""

    # Slack message timestamps (for updating messages)
    reviewer_msg_ts: str = ""
    hos_msg_ts: str = ""

    # Web notification IDs (for unified-ui)
    reviewer_notification_id: str = ""
    hos_notification_id: str = ""

    # Approval status
    reviewer_approved: bool = False
    hos_approved: bool = False
    status: str = ApprovalStatus.PENDING.value

    # Stored data
    task_data: dict = field(default_factory=dict)
    version_info: dict = field(default_factory=dict)

    # Timestamps
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database operations."""
        return {
            "workflow_id": self.workflow_id,
            "task_number": self.task_number,
            "folder_name": self.folder_name,
            "dropbox_path": self.dropbox_path,
            "videographer_id": self.videographer_id,
            "reviewer_id": self.reviewer_id,
            "hos_id": self.hos_id,
            "reviewer_msg_ts": self.reviewer_msg_ts,
            "hos_msg_ts": self.hos_msg_ts,
            "reviewer_notification_id": self.reviewer_notification_id,
            "hos_notification_id": self.hos_notification_id,
            "reviewer_approved": self.reviewer_approved,
            "hos_approved": self.hos_approved,
            "status": self.status,
            "task_data": json.dumps(self.task_data) if self.task_data else "{}",
            "version_info": json.dumps(self.version_info) if self.version_info else "{}",
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApprovalWorkflow":
        """Create from dictionary (database row)."""
        # Handle JSON fields
        task_data = data.get("task_data", "{}")
        if isinstance(task_data, str):
            try:
                task_data = json.loads(task_data)
            except json.JSONDecodeError:
                task_data = {}

        version_info = data.get("version_info", "{}")
        if isinstance(version_info, str):
            try:
                version_info = json.loads(version_info)
            except json.JSONDecodeError:
                version_info = {}

        return cls(
            workflow_id=data.get("workflow_id", ""),
            task_number=data.get("task_number"),
            folder_name=data.get("folder_name", ""),
            dropbox_path=data.get("dropbox_path", ""),
            videographer_id=data.get("videographer_id", ""),
            reviewer_id=data.get("reviewer_id", ""),
            hos_id=data.get("hos_id", ""),
            reviewer_msg_ts=data.get("reviewer_msg_ts", ""),
            hos_msg_ts=data.get("hos_msg_ts", ""),
            reviewer_notification_id=data.get("reviewer_notification_id", ""),
            hos_notification_id=data.get("hos_notification_id", ""),
            reviewer_approved=bool(data.get("reviewer_approved")),
            hos_approved=bool(data.get("hos_approved")),
            status=data.get("status", ApprovalStatus.PENDING.value),
            task_data=task_data,
            version_info=version_info,
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


@dataclass
class VideoConfig:
    """
    Configuration model for storing various settings.

    Replaces JSON-based configuration files (videographer_config.json, etc.)
    Maps to the `video_config` table in Supabase.
    """
    id: int | None = None
    config_type: str = ""  # ConfigType enum value
    config_key: str = ""   # Unique key within the config type
    config_data: dict = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database operations."""
        return {
            "config_type": self.config_type,
            "config_key": self.config_key,
            "config_data": json.dumps(self.config_data) if self.config_data else "{}",
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VideoConfig":
        """Create from dictionary (database row)."""
        config_data = data.get("config_data", "{}")
        if isinstance(config_data, str):
            try:
                config_data = json.loads(config_data)
            except json.JSONDecodeError:
                config_data = {}

        return cls(
            id=data.get("id"),
            config_type=data.get("config_type", ""),
            config_key=data.get("config_key", ""),
            config_data=config_data,
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


@dataclass
class Videographer:
    """
    Videographer configuration model.

    This is a specialized view of VideoConfig for videographer settings.
    """
    name: str = ""
    user_id: str = ""  # User ID for notifications
    channel_id: str = ""  # Channel ID for notifications
    active: bool = True
    location: str = ""  # Primary location
    locations: list[str] = field(default_factory=list)  # All supported locations
    max_tasks: int = 5  # Maximum concurrent tasks
    current_tasks: int = 0

    def to_config(self) -> VideoConfig:
        """Convert to VideoConfig for storage."""
        return VideoConfig(
            config_type=ConfigType.VIDEOGRAPHER.value,
            config_key=self.name,
            config_data={
                "name": self.name,
                "user_id": self.user_id,
                "channel_id": self.channel_id,
                "active": self.active,
                "location": self.location,
                "locations": self.locations,
                "max_tasks": self.max_tasks,
            }
        )

    @classmethod
    def from_config(cls, config: VideoConfig) -> "Videographer":
        """Create from VideoConfig."""
        data = config.config_data
        return cls(
            name=data.get("name", config.config_key),
            user_id=data.get("user_id", data.get("slack_user_id", "")),  # Fallback for legacy
            channel_id=data.get("channel_id", data.get("slack_channel_id", "")),  # Fallback for legacy
            active=data.get("active", True),
            location=data.get("location", ""),
            locations=data.get("locations", []),
            max_tasks=data.get("max_tasks", 5),
        )


@dataclass
class CompletedTask:
    """
    Completed/archived task model.

    Maps to the `completed_tasks` table in Supabase.
    Similar to VideoTask but with completion timestamp.
    """
    id: int | None = None
    task_number: int | None = None
    brand: str = ""
    campaign_start_date: str = ""
    campaign_end_date: str = ""
    reference_number: str = ""
    location: str = ""
    sales_person: str = ""
    submitted_by: str = ""
    status: str = ""
    filming_date: str = ""
    videographer: str = ""
    task_type: str = TaskType.VIDEOGRAPHY.value
    time_block: str | None = None
    submission_folder: str = ""
    current_version: int = 0
    version_history: list[dict] = field(default_factory=list)
    pending_timestamps: str = ""
    submitted_timestamps: str = ""
    returned_timestamps: str = ""
    rejected_timestamps: str = ""
    accepted_timestamps: str = ""
    completed_at: datetime | None = None

    @classmethod
    def from_video_task(cls, task: VideoTask, completed_at: datetime) -> "CompletedTask":
        """Create a CompletedTask from a VideoTask."""
        return cls(
            task_number=task.task_number,
            brand=task.brand,
            campaign_start_date=task.campaign_start_date,
            campaign_end_date=task.campaign_end_date,
            reference_number=task.reference_number,
            location=task.location,
            sales_person=task.sales_person,
            submitted_by=task.submitted_by,
            status=task.status,
            filming_date=task.filming_date,
            videographer=task.videographer,
            task_type=task.task_type,
            time_block=task.time_block,
            submission_folder=task.submission_folder,
            current_version=task.current_version,
            version_history=task.version_history,
            pending_timestamps=task.pending_timestamps,
            submitted_timestamps=task.submitted_timestamps,
            returned_timestamps=task.returned_timestamps,
            rejected_timestamps=task.rejected_timestamps,
            accepted_timestamps=task.accepted_timestamps,
            completed_at=completed_at,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database operations."""
        return {
            "task_number": self.task_number,
            "brand": self.brand,
            "campaign_start_date": self.campaign_start_date,
            "campaign_end_date": self.campaign_end_date,
            "reference_number": self.reference_number,
            "location": self.location,
            "sales_person": self.sales_person,
            "submitted_by": self.submitted_by,
            "status": self.status,
            "filming_date": self.filming_date,
            "videographer": self.videographer,
            "task_type": self.task_type,
            "time_block": self.time_block,
            "submission_folder": self.submission_folder,
            "current_version": self.current_version,
            "version_history": json.dumps(self.version_history) if self.version_history else "[]",
            "pending_timestamps": self.pending_timestamps,
            "submitted_timestamps": self.submitted_timestamps,
            "returned_timestamps": self.returned_timestamps,
            "rejected_timestamps": self.rejected_timestamps,
            "accepted_timestamps": self.accepted_timestamps,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CompletedTask":
        """Create from dictionary (database row)."""
        version_history = data.get("version_history", "[]")
        if isinstance(version_history, str):
            try:
                version_history = json.loads(version_history)
            except json.JSONDecodeError:
                version_history = []

        completed_at = data.get("completed_at")
        if isinstance(completed_at, str):
            try:
                completed_at = datetime.fromisoformat(completed_at)
            except ValueError:
                completed_at = None

        return cls(
            id=data.get("id"),
            task_number=data.get("task_number"),
            brand=data.get("brand", ""),
            campaign_start_date=data.get("campaign_start_date", ""),
            campaign_end_date=data.get("campaign_end_date", ""),
            reference_number=data.get("reference_number", ""),
            location=data.get("location", ""),
            sales_person=data.get("sales_person", ""),
            submitted_by=data.get("submitted_by", ""),
            status=data.get("status", ""),
            filming_date=data.get("filming_date", ""),
            videographer=data.get("videographer", ""),
            task_type=data.get("task_type", TaskType.VIDEOGRAPHY.value),
            time_block=data.get("time_block"),
            submission_folder=data.get("submission_folder", ""),
            current_version=int(data.get("current_version") or 0),
            version_history=version_history,
            pending_timestamps=data.get("pending_timestamps", ""),
            submitted_timestamps=data.get("submitted_timestamps", ""),
            returned_timestamps=data.get("returned_timestamps", ""),
            rejected_timestamps=data.get("rejected_timestamps", ""),
            accepted_timestamps=data.get("accepted_timestamps", ""),
            completed_at=completed_at,
        )


@dataclass
class DuplicateCheckResult:
    """Result of a duplicate reference number check."""
    is_duplicate: bool
    existing_entry: dict | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {"is_duplicate": self.is_duplicate}
        if self.existing_entry:
            result["existing_entry"] = self.existing_entry
        return result
