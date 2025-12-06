"""
Abstract base class for RBAC (Role-Based Access Control) providers.

Each provider implements their own storage-specific syntax.
Follows the same pattern as integrations/llm/base.py and integrations/auth/base.py.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class PermissionAction(str, Enum):
    """Standard permission actions."""
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    MANAGE = "manage"  # Full control (implies all others)


@dataclass
class Permission:
    """
    Permission definition.

    Format: "{resource}:{action}" e.g., "proposals:create", "users:manage"
    """
    id: Optional[int] = None
    name: str = ""  # Full permission name (e.g., "proposals:create")
    resource: str = ""  # Resource type (e.g., "proposals")
    action: str = ""  # Action (e.g., "create")
    description: Optional[str] = None

    @classmethod
    def from_name(cls, name: str, description: Optional[str] = None) -> "Permission":
        """Create a Permission from a name string."""
        parts = name.split(":", 1)
        resource = parts[0] if parts else ""
        action = parts[1] if len(parts) > 1 else ""
        return cls(name=name, resource=resource, action=action, description=description)

    def __str__(self) -> str:
        return self.name

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other) -> bool:
        if isinstance(other, Permission):
            return self.name == other.name
        if isinstance(other, str):
            return self.name == other
        return False


@dataclass
class Role:
    """
    Role definition with associated permissions.
    """
    id: Optional[int] = None
    name: str = ""
    description: Optional[str] = None
    permissions: List[Permission] = field(default_factory=list)
    is_system: bool = False  # System roles can't be deleted

    def has_permission(self, permission: str) -> bool:
        """Check if role has a specific permission."""
        # Wildcard check: if role has "proposals:manage", it implies all proposals:*
        for perm in self.permissions:
            if perm.name == permission:
                return True
            # Check resource wildcard
            if perm.action == "manage":
                target_parts = permission.split(":", 1)
                if target_parts[0] == perm.resource:
                    return True
            # Check global admin wildcard
            if perm.name == "*:*" or perm.name == "*:manage":
                return True
        return False

    def __str__(self) -> str:
        return self.name


@dataclass
class UserRole:
    """
    User-role assignment.
    """
    user_id: str
    role: Role
    granted_by: Optional[str] = None
    granted_at: Optional[str] = None
    expires_at: Optional[str] = None


@dataclass
class RBACContext:
    """
    Context for RBAC decisions.

    Provides additional context for permission checks (e.g., resource ownership).
    """
    user_id: str
    resource_id: Optional[str] = None
    resource_owner_id: Optional[str] = None
    resource_type: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_owner(self) -> bool:
        """Check if user owns the resource."""
        return self.resource_owner_id == self.user_id


# =============================================================================
# DEFAULT ROLES AND PERMISSIONS
# =============================================================================

DEFAULT_PERMISSIONS = [
    # Proposals
    Permission.from_name("proposals:create", "Create new proposals"),
    Permission.from_name("proposals:read", "View proposals"),
    Permission.from_name("proposals:update", "Edit proposals"),
    Permission.from_name("proposals:delete", "Delete proposals"),
    Permission.from_name("proposals:manage", "Full control over proposals"),

    # Booking Orders
    Permission.from_name("booking_orders:create", "Create booking orders"),
    Permission.from_name("booking_orders:read", "View booking orders"),
    Permission.from_name("booking_orders:update", "Edit booking orders"),
    Permission.from_name("booking_orders:delete", "Delete booking orders"),
    Permission.from_name("booking_orders:manage", "Full control over booking orders"),

    # Mockups
    Permission.from_name("mockups:create", "Create mockups"),
    Permission.from_name("mockups:read", "View mockups"),
    Permission.from_name("mockups:update", "Edit mockups"),
    Permission.from_name("mockups:delete", "Delete mockups"),
    Permission.from_name("mockups:manage", "Full control over mockups"),

    # Users
    Permission.from_name("users:read", "View users"),
    Permission.from_name("users:create", "Create users"),
    Permission.from_name("users:update", "Edit users"),
    Permission.from_name("users:delete", "Delete users"),
    Permission.from_name("users:manage", "Full control over users"),

    # AI Costs
    Permission.from_name("ai_costs:read", "View AI cost reports"),
    Permission.from_name("ai_costs:manage", "Manage AI cost tracking"),

    # System
    Permission.from_name("system:admin", "System administration"),
]

DEFAULT_ROLES = {
    "admin": Role(
        name="admin",
        description="Full system access",
        permissions=[Permission.from_name("*:manage", "All permissions")],
        is_system=True,
    ),
    "hos": Role(
        name="hos",
        description="Head of Sales - Team oversight",
        permissions=[
            Permission.from_name("proposals:manage"),
            Permission.from_name("booking_orders:manage"),
            Permission.from_name("mockups:manage"),
            Permission.from_name("users:read"),
            Permission.from_name("ai_costs:read"),
        ],
        is_system=True,
    ),
    "sales_person": Role(
        name="sales_person",
        description="Sales team member",
        permissions=[
            Permission.from_name("proposals:create"),
            Permission.from_name("proposals:read"),
            Permission.from_name("booking_orders:create"),
            Permission.from_name("booking_orders:read"),
            Permission.from_name("mockups:create"),
            Permission.from_name("mockups:read"),
        ],
        is_system=True,
    ),
    "coordinator": Role(
        name="coordinator",
        description="Operations coordinator",
        permissions=[
            Permission.from_name("booking_orders:create"),
            Permission.from_name("booking_orders:read"),
            Permission.from_name("booking_orders:update"),
        ],
        is_system=True,
    ),
    "finance": Role(
        name="finance",
        description="Finance team member",
        permissions=[
            Permission.from_name("booking_orders:read"),
            Permission.from_name("ai_costs:read"),
        ],
        is_system=True,
    ),
}


class RBACProvider(ABC):
    """
    Abstract base class for RBAC providers.

    Each provider (Database, Static, etc.) implements this interface
    with their own storage-specific syntax.

    Pattern follows:
    - integrations/llm/base.py (LLMProvider)
    - integrations/auth/base.py (AuthProvider)
    - db/base.py (DatabaseBackend)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'database', 'static')."""
        pass

    # =========================================================================
    # ROLE OPERATIONS
    # =========================================================================

    @abstractmethod
    async def get_user_roles(self, user_id: str) -> List[Role]:
        """
        Get all roles assigned to a user.

        Args:
            user_id: User's unique identifier

        Returns:
            List of Role objects
        """
        pass

    @abstractmethod
    async def assign_role(
        self,
        user_id: str,
        role_name: str,
        granted_by: Optional[str] = None,
        expires_at: Optional[str] = None,
    ) -> bool:
        """
        Assign a role to a user.

        Args:
            user_id: User's ID
            role_name: Name of the role to assign
            granted_by: ID of user granting the role
            expires_at: Optional expiration datetime

        Returns:
            True if assigned successfully
        """
        pass

    @abstractmethod
    async def revoke_role(self, user_id: str, role_name: str) -> bool:
        """
        Revoke a role from a user.

        Args:
            user_id: User's ID
            role_name: Name of the role to revoke

        Returns:
            True if revoked successfully
        """
        pass

    @abstractmethod
    async def has_role(self, user_id: str, role_name: str) -> bool:
        """
        Check if user has a specific role.

        Args:
            user_id: User's ID
            role_name: Role to check

        Returns:
            True if user has the role
        """
        pass

    # =========================================================================
    # PERMISSION OPERATIONS
    # =========================================================================

    @abstractmethod
    async def get_user_permissions(self, user_id: str) -> Set[str]:
        """
        Get all permissions for a user (from all their roles).

        Args:
            user_id: User's unique identifier

        Returns:
            Set of permission names (e.g., {"proposals:create", "users:read"})
        """
        pass

    @abstractmethod
    async def has_permission(
        self,
        user_id: str,
        permission: str,
        context: Optional[RBACContext] = None,
    ) -> bool:
        """
        Check if user has a specific permission.

        Args:
            user_id: User's ID
            permission: Permission to check (e.g., "proposals:create")
            context: Optional context for ownership-based checks

        Returns:
            True if user has the permission
        """
        pass

    # =========================================================================
    # ROLE MANAGEMENT
    # =========================================================================

    @abstractmethod
    async def get_role(self, role_name: str) -> Optional[Role]:
        """
        Get a role by name.

        Args:
            role_name: Role name

        Returns:
            Role object or None
        """
        pass

    @abstractmethod
    async def list_roles(self) -> List[Role]:
        """
        List all available roles.

        Returns:
            List of Role objects
        """
        pass

    @abstractmethod
    async def create_role(
        self,
        name: str,
        description: Optional[str] = None,
        permissions: Optional[List[str]] = None,
    ) -> Optional[Role]:
        """
        Create a new role.

        Args:
            name: Role name
            description: Role description
            permissions: List of permission names

        Returns:
            Created Role or None
        """
        pass

    @abstractmethod
    async def update_role(
        self,
        name: str,
        description: Optional[str] = None,
        permissions: Optional[List[str]] = None,
    ) -> Optional[Role]:
        """
        Update an existing role.

        Args:
            name: Role name
            description: New description
            permissions: New list of permissions

        Returns:
            Updated Role or None
        """
        pass

    @abstractmethod
    async def delete_role(self, name: str) -> bool:
        """
        Delete a role (system roles cannot be deleted).

        Args:
            name: Role name

        Returns:
            True if deleted
        """
        pass

    # =========================================================================
    # PERMISSION MANAGEMENT
    # =========================================================================

    @abstractmethod
    async def list_permissions(self) -> List[Permission]:
        """
        List all available permissions.

        Returns:
            List of Permission objects
        """
        pass

    # =========================================================================
    # INITIALIZATION
    # =========================================================================

    @abstractmethod
    async def initialize_defaults(self) -> bool:
        """
        Initialize default roles and permissions.

        Should be called on first run to set up standard roles.

        Returns:
            True if initialized successfully
        """
        pass
