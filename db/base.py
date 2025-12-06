"""
Abstract base class for database backends.
Each backend implements their own storage-specific syntax.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ProposalLog:
    """Proposal log entry."""
    id: Optional[int] = None
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
    id: Optional[int] = None
    original_file_size: Optional[int] = None
    original_filename: Optional[str] = None
    bo_number: Optional[str] = None
    bo_date: Optional[str] = None
    client: Optional[str] = None
    agency: Optional[str] = None
    brand_campaign: Optional[str] = None
    category: Optional[str] = None
    asset: Optional[str] = None
    net_pre_vat: Optional[float] = None
    vat_value: Optional[float] = None
    gross_amount: Optional[float] = None
    sla_pct: Optional[float] = None
    payment_terms: Optional[str] = None
    sales_person: Optional[str] = None
    commission_pct: Optional[float] = None
    notes: Optional[str] = None
    locations: Optional[List[Dict]] = None
    extraction_method: Optional[str] = None
    extraction_confidence: Optional[str] = None
    warnings: Optional[List[str]] = None
    missing_required: Optional[List[str]] = None
    vat_calc: Optional[float] = None
    gross_calc: Optional[float] = None
    sla_deduction: Optional[float] = None
    net_excl_sla_calc: Optional[float] = None
    parsed_by: Optional[str] = None
    source_classification: Optional[str] = None
    classification_confidence: Optional[str] = None
    needs_review: bool = False


@dataclass
class MockupFrame:
    """Mockup frame data."""
    location_key: str
    photo_filename: str
    frames_data: List[Dict]
    time_of_day: str = "day"
    finish: str = "gold"
    created_at: Optional[str] = None
    created_by: Optional[str] = None
    config: Optional[Dict] = None
    id: Optional[int] = None


@dataclass
class AICostEntry:
    """AI cost tracking entry."""
    call_type: str
    model: str
    input_tokens: int
    output_tokens: int
    total_cost: float
    timestamp: Optional[str] = None
    workflow: Optional[str] = None
    user_id: Optional[str] = None
    context: Optional[str] = None
    reasoning_tokens: int = 0
    cached_input_tokens: int = 0
    input_cost: float = 0.0
    output_cost: float = 0.0
    reasoning_cost: float = 0.0
    metadata_json: Optional[str] = None
    id: Optional[int] = None


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
        date_generated: Optional[str] = None,
    ) -> None:
        """Log a proposal generation."""
        pass

    @abstractmethod
    def get_proposals_summary(self) -> Dict[str, Any]:
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
    def save_booking_order(self, data: Dict[str, Any]) -> str:
        """Save a booking order. Returns bo_ref."""
        pass

    @abstractmethod
    def get_booking_order(self, bo_ref: str) -> Optional[Dict[str, Any]]:
        """Get a booking order by backend reference."""
        pass

    @abstractmethod
    def get_booking_order_by_number(self, bo_number: str) -> Optional[Dict[str, Any]]:
        """Get a booking order by user-facing BO number."""
        pass

    @abstractmethod
    def export_booking_orders_to_excel(self) -> str:
        """Export booking orders to Excel. Returns file path."""
        pass

    # =========================================================================
    # MOCKUP FRAMES
    # =========================================================================

    @abstractmethod
    def save_mockup_frame(
        self,
        location_key: str,
        photo_filename: str,
        frames_data: List[Dict],
        created_by: Optional[str] = None,
        time_of_day: str = "day",
        finish: str = "gold",
        config: Optional[Dict] = None,
    ) -> str:
        """Save mockup frame data. Returns the final filename."""
        pass

    @abstractmethod
    def get_mockup_frames(
        self,
        location_key: str,
        photo_filename: str,
        time_of_day: str = "day",
        finish: str = "gold",
    ) -> Optional[List[Dict]]:
        """Get frame coordinates for a mockup photo."""
        pass

    @abstractmethod
    def get_mockup_config(
        self,
        location_key: str,
        photo_filename: str,
        time_of_day: str = "day",
        finish: str = "gold",
    ) -> Optional[Dict]:
        """Get config for a mockup photo."""
        pass

    @abstractmethod
    def list_mockup_photos(
        self,
        location_key: str,
        time_of_day: str = "day",
        finish: str = "gold",
    ) -> List[str]:
        """List all photos with frames for a location."""
        pass

    @abstractmethod
    def list_mockup_variations(self, location_key: str) -> Dict[str, List[str]]:
        """List all time_of_day/finish combinations for a location."""
        pass

    @abstractmethod
    def delete_mockup_frame(
        self,
        location_key: str,
        photo_filename: str,
        time_of_day: str = "day",
        finish: str = "gold",
    ) -> None:
        """Delete a mockup frame."""
        pass

    # =========================================================================
    # MOCKUP USAGE ANALYTICS
    # =========================================================================

    @abstractmethod
    def log_mockup_usage(
        self,
        location_key: str,
        time_of_day: str,
        finish: str,
        photo_used: str,
        creative_type: str,
        ai_prompt: Optional[str] = None,
        template_selected: bool = False,
        success: bool = True,
        user_ip: Optional[str] = None,
    ) -> None:
        """Log a mockup generation event."""
        pass

    @abstractmethod
    def get_mockup_usage_stats(self) -> Dict[str, Any]:
        """Get mockup usage statistics."""
        pass

    @abstractmethod
    def export_mockup_usage_to_excel(self) -> str:
        """Export mockup usage to Excel. Returns file path."""
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
    def get_bo_workflow(self, workflow_id: str) -> Optional[str]:
        """Get a BO workflow by ID. Returns workflow_data JSON."""
        pass

    @abstractmethod
    def get_all_active_bo_workflows(self) -> List[tuple]:
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
        user_id: Optional[str] = None,
        workflow: Optional[str] = None,
        cached_input_tokens: int = 0,
        context: Optional[str] = None,
        metadata_json: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> None:
        """Log an AI API cost entry."""
        pass

    @abstractmethod
    def get_ai_costs_summary(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        call_type: Optional[str] = None,
        workflow: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
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
        full_name: Optional[str] = None,
        avatar_url: Optional[str] = None,
        created_at: Optional[str] = None,
        last_login: Optional[str] = None,
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
    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get a user by ID."""
        pass

    @abstractmethod
    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get a user by email."""
        pass

    # =========================================================================
    # RBAC: ROLES
    # =========================================================================

    @abstractmethod
    def get_role_by_name(self, role_name: str) -> Optional[Dict[str, Any]]:
        """Get a role by name."""
        pass

    @abstractmethod
    def list_roles(self) -> List[Dict[str, Any]]:
        """List all roles."""
        pass

    @abstractmethod
    def create_role(
        self,
        name: str,
        description: Optional[str] = None,
        is_system: bool = False,
        created_at: Optional[str] = None,
    ) -> Optional[str]:
        """
        Create a new role.

        Returns:
            Role ID if created, None otherwise
        """
        pass

    @abstractmethod
    def update_role(
        self,
        role_id: str,
        description: Optional[str] = None,
    ) -> bool:
        """Update a role."""
        pass

    @abstractmethod
    def delete_role(self, role_id: str) -> bool:
        """Delete a role."""
        pass

    # =========================================================================
    # RBAC: PERMISSIONS
    # =========================================================================

    @abstractmethod
    def list_permissions(self) -> List[Dict[str, Any]]:
        """List all permissions."""
        pass

    @abstractmethod
    def create_permission(
        self,
        name: str,
        resource: str,
        action: str,
        description: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> Optional[str]:
        """
        Create a permission.

        Returns:
            Permission ID if created, None otherwise
        """
        pass

    @abstractmethod
    def get_role_permissions(self, role_id: str) -> List[Dict[str, Any]]:
        """Get all permissions for a role."""
        pass

    @abstractmethod
    def assign_role_permission(
        self,
        role_id: str,
        permission_name: str,
        assigned_at: Optional[str] = None,
    ) -> bool:
        """Assign a permission to a role."""
        pass

    @abstractmethod
    def set_role_permissions(
        self,
        role_id: str,
        permission_names: List[str],
        assigned_at: Optional[str] = None,
    ) -> bool:
        """Set all permissions for a role (replaces existing)."""
        pass

    # =========================================================================
    # RBAC: USER ROLES
    # =========================================================================

    @abstractmethod
    def get_user_roles(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all roles assigned to a user."""
        pass

    @abstractmethod
    def assign_user_role(
        self,
        user_id: str,
        role_id: str,
        granted_by: Optional[str] = None,
        granted_at: Optional[str] = None,
        expires_at: Optional[str] = None,
    ) -> bool:
        """Assign a role to a user."""
        pass

    @abstractmethod
    def revoke_user_role(self, user_id: str, role_name: str) -> bool:
        """Revoke a role from a user."""
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
        scopes: List[str],
        description: Optional[str] = None,
        rate_limit: Optional[int] = None,
        expires_at: Optional[str] = None,
        created_by: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> Optional[int]:
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
    def get_api_key_by_hash(self, key_hash: str) -> Optional[Dict[str, Any]]:
        """Get API key info by hash."""
        pass

    @abstractmethod
    def get_api_key_by_id(self, key_id: int) -> Optional[Dict[str, Any]]:
        """Get API key info by ID."""
        pass

    @abstractmethod
    def list_api_keys(
        self,
        created_by: Optional[str] = None,
        include_inactive: bool = False,
    ) -> List[Dict[str, Any]]:
        """List all API keys, optionally filtered."""
        pass

    @abstractmethod
    def update_api_key(
        self,
        key_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        scopes: Optional[List[str]] = None,
        rate_limit: Optional[int] = None,
        is_active: Optional[bool] = None,
        expires_at: Optional[str] = None,
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
        status_code: Optional[int] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        response_time_ms: Optional[int] = None,
        request_size: Optional[int] = None,
        response_size: Optional[int] = None,
        timestamp: Optional[str] = None,
    ) -> None:
        """Log API key usage for auditing."""
        pass

    @abstractmethod
    def get_api_key_usage_stats(
        self,
        api_key_id: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get API key usage statistics."""
        pass
