"""
Abstract base class for database backends.
Each backend implements their own storage-specific syntax.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ProposalLog:
    """Proposal log entry."""
    id: int | None = None
    submitted_by: str = ""
    client_name: str = ""
    date_generated: str = ""
    package_type: str = ""
    locations: str = ""
    total_amount: str = ""


@dataclass
class BookingOrder:
    """Booking order data."""
    bo_ref: str
    company: str
    original_file_path: str
    original_file_type: str
    parsed_excel_path: str
    parsed_at: str
    # Optional fields
    id: int | None = None
    original_file_size: int | None = None
    original_filename: str | None = None
    bo_number: str | None = None
    bo_date: str | None = None
    client: str | None = None
    agency: str | None = None
    brand_campaign: str | None = None
    category: str | None = None
    asset: str | None = None
    net_pre_vat: float | None = None
    vat_value: float | None = None
    gross_amount: float | None = None
    sla_pct: float | None = None
    payment_terms: str | None = None
    sales_person: str | None = None
    commission_pct: float | None = None
    notes: str | None = None
    locations: list[dict] | None = None
    extraction_method: str | None = None
    extraction_confidence: str | None = None
    warnings: list[str] | None = None
    missing_required: list[str] | None = None
    vat_calc: float | None = None
    gross_calc: float | None = None
    sla_deduction: float | None = None
    net_excl_sla_calc: float | None = None
    parsed_by: str | None = None
    source_classification: str | None = None
    classification_confidence: str | None = None
    needs_review: bool = False


@dataclass
class MockupFrame:
    """Mockup frame data."""
    location_key: str
    photo_filename: str
    frames_data: list[dict]
    time_of_day: str = "day"
    side: str = "gold"
    created_at: str | None = None
    created_by: str | None = None
    config: dict | None = None
    id: int | None = None


@dataclass
class AICostEntry:
    """AI cost tracking entry."""
    call_type: str
    model: str
    input_tokens: int
    output_tokens: int
    total_cost: float
    timestamp: str | None = None
    workflow: str | None = None
    user_id: str | None = None
    context: str | None = None
    reasoning_tokens: int = 0
    cached_input_tokens: int = 0
    input_cost: float = 0.0
    output_cost: float = 0.0
    reasoning_cost: float = 0.0
    metadata_json: str | None = None
    id: int | None = None


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
    # PROPOSALS
    # =========================================================================

    @abstractmethod
    def log_proposal(
        self,
        submitted_by: str,
        client_name: str,
        package_type: str,
        locations: str,
        total_amount: str,
        date_generated: str | None = None,
    ) -> None:
        """Log a proposal generation."""
        pass

    @abstractmethod
    def get_proposals(
        self,
        limit: int = 50,
        offset: int = 0,
        user_ids: str | list[str] | None = None,
        client_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get proposals with optional filtering.

        Args:
            limit: Maximum number of proposals to return
            offset: Number of proposals to skip
            user_ids: Filter by user ID(s) - can be single ID or list for team access
            client_name: Filter by client name (partial match)

        Returns:
            List of proposal dictionaries
        """
        pass

    @abstractmethod
    def get_proposal_by_id(self, proposal_id: int) -> dict[str, Any] | None:
        """Get a single proposal by ID."""
        pass

    @abstractmethod
    def get_proposal_locations(self, proposal_id: int) -> list[dict[str, Any]]:
        """Get locations for a proposal."""
        pass

    @abstractmethod
    def delete_proposal(self, proposal_id: int) -> bool:
        """Delete a proposal. Returns True if successful."""
        pass

    @abstractmethod
    def get_proposals_summary(self) -> dict[str, Any]:
        """Get summary statistics for proposals."""
        pass

    @abstractmethod
    def export_to_excel(self) -> str:
        """Export proposals to Excel. Returns file path."""
        pass

    # =========================================================================
    # BOOKING ORDERS
    # =========================================================================

    @abstractmethod
    def generate_next_bo_ref(self) -> str:
        """Generate the next booking order reference number."""
        pass

    @abstractmethod
    def save_booking_order(self, data: dict[str, Any]) -> str:
        """Save a booking order. Returns bo_ref."""
        pass

    @abstractmethod
    def get_booking_order(self, bo_ref: str) -> dict[str, Any] | None:
        """Get a booking order by backend reference."""
        pass

    @abstractmethod
    def get_booking_order_by_number(self, bo_number: str) -> dict[str, Any] | None:
        """Get a booking order by user-facing BO number."""
        pass

    @abstractmethod
    def export_booking_orders_to_excel(self) -> str:
        """Export booking orders to Excel. Returns file path."""
        pass

    # =========================================================================
    # MOCKUP FRAMES (Company-scoped)
    # =========================================================================

    @abstractmethod
    def save_mockup_frame(
        self,
        location_key: str,
        photo_filename: str,
        frames_data: list[dict],
        company_schema: str,
        created_by: str | None = None,
        time_of_day: str = "day",
        side: str = "gold",
        config: dict | None = None,
    ) -> str:
        """Save mockup frame data to company-specific schema. Returns the final filename."""
        pass

    @abstractmethod
    def delete_mockup_frame(
        self,
        location_key: str,
        photo_filename: str,
        company_schema: str,
        time_of_day: str = "day",
        side: str = "gold",
    ) -> None:
        """Delete a mockup frame from company-specific schema."""
        pass

    # =========================================================================
    # MOCKUP USAGE ANALYTICS (Company-scoped)
    # =========================================================================

    @abstractmethod
    def log_mockup_usage(
        self,
        location_key: str,
        time_of_day: str,
        side: str,
        photo_used: str,
        creative_type: str,
        company_schema: str,
        ai_prompt: str | None = None,
        template_selected: bool = False,
        success: bool = True,
        user_ip: str | None = None,
    ) -> None:
        """Log a mockup generation event to company-specific schema."""
        pass

    @abstractmethod
    def get_mockup_usage_stats(
        self,
        company_schemas: list[str],
    ) -> dict[str, Any]:
        """Get mockup usage statistics from user's accessible company schemas."""
        pass

    @abstractmethod
    def export_mockup_usage_to_excel(
        self,
        company_schemas: list[str],
    ) -> str:
        """Export mockup usage from user's accessible company schemas to Excel. Returns file path."""
        pass

    # =========================================================================
    # BO WORKFLOWS
    # =========================================================================

    @abstractmethod
    def save_bo_workflow(
        self,
        workflow_id: str,
        workflow_data: str,
        updated_at: str,
    ) -> None:
        """Save or update a BO approval workflow."""
        pass

    @abstractmethod
    def get_bo_workflow(self, workflow_id: str) -> str | None:
        """Get a BO workflow by ID. Returns workflow_data JSON."""
        pass

    @abstractmethod
    def get_all_active_bo_workflows(self) -> list[tuple]:
        """Get all active BO workflows. Returns list of (workflow_id, workflow_data)."""
        pass

    @abstractmethod
    def delete_bo_workflow(self, workflow_id: str) -> None:
        """Delete a BO workflow."""
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
        """Log an AI API cost entry."""
        pass

    @abstractmethod
    def get_ai_costs_summary(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        call_type: str | None = None,
        workflow: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Get AI costs summary with optional filters."""
        pass

    @abstractmethod
    def clear_ai_costs(self) -> None:
        """Clear all AI cost tracking data."""
        pass

    # =========================================================================
    # USER MANAGEMENT
    # =========================================================================

    @abstractmethod
    def upsert_user(
        self,
        user_id: str,
        email: str,
        full_name: str | None = None,
        avatar_url: str | None = None,
        created_at: str | None = None,
        last_login: str | None = None,
    ) -> bool:
        """
        Create or update a user.

        Args:
            user_id: User's unique ID (from auth provider)
            email: User's email address
            full_name: User's display name
            avatar_url: URL to user's avatar
            created_at: When user was created
            last_login: Last login timestamp

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    def get_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        """Get a user by ID."""
        pass

    @abstractmethod
    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        """Get a user by email."""
        pass

    # =========================================================================
    # RBAC: PERMISSIONS
    # =========================================================================

    @abstractmethod
    def list_permissions(self) -> list[dict[str, Any]]:
        """List all permissions."""
        pass

    @abstractmethod
    def create_permission(
        self,
        name: str,
        resource: str,
        action: str,
        description: str | None = None,
        created_at: str | None = None,
    ) -> str | None:
        """
        Create a permission.

        Returns:
            Permission ID if created, None otherwise
        """
        pass

    # =========================================================================
    # API KEYS
    # =========================================================================

    @abstractmethod
    def create_api_key(
        self,
        key_hash: str,
        key_prefix: str,
        name: str,
        scopes: list[str],
        description: str | None = None,
        rate_limit: int | None = None,
        expires_at: str | None = None,
        created_by: str | None = None,
        metadata: dict | None = None,
    ) -> int | None:
        """
        Create a new API key.

        Args:
            key_hash: SHA256 hash of the raw key
            key_prefix: First 8 chars of the key for identification
            name: Client/app name
            scopes: List of scope strings
            description: Optional description
            rate_limit: Optional rate limit (requests/minute)
            expires_at: Optional expiration timestamp
            created_by: User ID who created the key
            metadata: Optional additional metadata

        Returns:
            Key ID if created, None otherwise
        """
        pass

    @abstractmethod
    def get_api_key_by_hash(self, key_hash: str) -> dict[str, Any] | None:
        """Get API key info by hash."""
        pass

    @abstractmethod
    def get_api_key_by_id(self, key_id: int) -> dict[str, Any] | None:
        """Get API key info by ID."""
        pass

    @abstractmethod
    def list_api_keys(
        self,
        created_by: str | None = None,
        include_inactive: bool = False,
    ) -> list[dict[str, Any]]:
        """List all API keys, optionally filtered."""
        pass

    @abstractmethod
    def update_api_key(
        self,
        key_id: int,
        name: str | None = None,
        description: str | None = None,
        scopes: list[str] | None = None,
        rate_limit: int | None = None,
        is_active: bool | None = None,
        expires_at: str | None = None,
    ) -> bool:
        """Update an API key."""
        pass

    @abstractmethod
    def update_api_key_last_used(self, key_id: int, timestamp: str) -> bool:
        """Update the last_used_at timestamp for an API key."""
        pass

    @abstractmethod
    def rotate_api_key(
        self,
        key_id: int,
        new_key_hash: str,
        new_key_prefix: str,
        rotated_at: str,
    ) -> bool:
        """Rotate an API key (replace hash)."""
        pass

    @abstractmethod
    def delete_api_key(self, key_id: int) -> bool:
        """Delete an API key (hard delete)."""
        pass

    @abstractmethod
    def deactivate_api_key(self, key_id: int) -> bool:
        """Deactivate an API key (soft delete)."""
        pass

    # =========================================================================
    # API KEY USAGE LOGGING
    # =========================================================================

    @abstractmethod
    def log_api_key_usage(
        self,
        api_key_id: int,
        endpoint: str,
        method: str,
        status_code: int | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        response_time_ms: int | None = None,
        request_size: int | None = None,
        response_size: int | None = None,
        timestamp: str | None = None,
    ) -> None:
        """Log API key usage for auditing."""
        pass

    @abstractmethod
    def get_api_key_usage_stats(
        self,
        api_key_id: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """Get API key usage statistics."""
        pass

    # =========================================================================
    # AUDIT LOGGING
    # =========================================================================

    @abstractmethod
    def log_audit_event(
        self,
        timestamp: str,
        action: str,
        user_id: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        details_json: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        """
        Log an audit event.

        Args:
            timestamp: ISO format timestamp
            action: Action performed (e.g., 'user.login', 'role.assign')
            user_id: ID of user who performed the action
            resource_type: Type of resource affected
            resource_id: ID of resource affected
            details_json: JSON string with additional details
            ip_address: Client IP address
            user_agent: Client user agent
        """
        pass

    @abstractmethod
    def query_audit_log(
        self,
        user_id: str | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        Query audit log entries.

        Args:
            user_id: Filter by user ID
            action: Filter by action type
            resource_type: Filter by resource type
            resource_id: Filter by resource ID
            start_date: Filter by start date (ISO format)
            end_date: Filter by end date (ISO format)
            limit: Maximum results
            offset: Number to skip

        Returns:
            List of audit log entries
        """
        pass

    # =========================================================================
    # CHAT SESSIONS
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
            messages: List of message dictionaries with role, content, timestamp
            session_id: Optional session ID (generated if not provided)

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
            Dict with session_id, messages, created_at, updated_at or None
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
    # DOCUMENT MANAGEMENT (File Storage Tracking)
    # =========================================================================

    @abstractmethod
    def create_document(
        self,
        file_id: str,
        user_id: str,
        original_filename: str,
        file_type: str,
        storage_provider: str,
        storage_bucket: str,
        storage_key: str,
        file_size: int | None = None,
        file_extension: str | None = None,
        file_hash: str | None = None,
        document_type: str | None = None,
        bo_id: int | None = None,
        proposal_id: int | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> int | None:
        """
        Create a new document record.

        Args:
            file_id: Unique file identifier (UUID)
            user_id: User who uploaded the file
            original_filename: Original filename
            file_type: MIME type
            storage_provider: 'local', 'supabase', or 's3'
            storage_bucket: Storage bucket name
            storage_key: Path within bucket
            file_size: File size in bytes
            file_extension: File extension (e.g., '.pdf')
            file_hash: SHA256 hash of file contents
            document_type: Classification ('bo_pdf', 'creative', etc.)
            bo_id: Link to booking order
            proposal_id: Link to proposal
            metadata_json: Additional metadata

        Returns:
            Document ID if created, None if failed
        """
        pass

    @abstractmethod
    def get_document(self, file_id: str) -> dict[str, Any] | None:
        """
        Get a document by file_id.

        Args:
            file_id: Unique file identifier

        Returns:
            Document record or None if not found
        """
        pass

    @abstractmethod
    def get_document_by_hash(self, file_hash: str) -> dict[str, Any] | None:
        """
        Get a document by file hash (for deduplication).

        Args:
            file_hash: SHA256 hash

        Returns:
            Document record or None if not found
        """
        pass

    @abstractmethod
    def soft_delete_document(self, file_id: str) -> bool:
        """
        Soft delete a document (set is_deleted=true and deleted_at=now()).

        Args:
            file_id: Unique file identifier

        Returns:
            True if deleted, False if not found
        """
        pass

    @abstractmethod
    def list_documents(
        self,
        user_id: str | None = None,
        document_type: str | None = None,
        bo_id: int | None = None,
        proposal_id: int | None = None,
        include_deleted: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        List documents with optional filters.

        Args:
            user_id: Filter by user
            document_type: Filter by type
            bo_id: Filter by booking order
            proposal_id: Filter by proposal
            include_deleted: Include soft-deleted documents
            limit: Maximum results
            offset: Number to skip

        Returns:
            List of document records
        """
        pass

    @abstractmethod
    def get_soft_deleted_documents(
        self,
        older_than_days: int = 30,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Get soft-deleted documents older than specified days.

        Used by cleanup job to find files to permanently delete.

        Args:
            older_than_days: Minimum days since deletion
            limit: Maximum results

        Returns:
            List of document records ready for permanent deletion
        """
        pass

    @abstractmethod
    def hard_delete_document(self, file_id: str) -> bool:
        """
        Permanently delete a document record.

        Only call this after deleting the actual file from storage.

        Args:
            file_id: Unique file identifier

        Returns:
            True if deleted, False if not found
        """
        pass
