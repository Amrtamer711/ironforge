"""
RBAC (Role-Based Access Control) Models.

Adapted from sales-module/integrations/rbac/base.py.

Enterprise RBAC Architecture:
- Level 1: Profiles (base permission templates)
- Level 2: Permission Sets (additive permissions)
- Level 3: Teams & Hierarchy (organizational structure)
- Level 4: Record-Level Sharing (manual and rule-based)
- Level 5: Company Access (multi-tenant)
"""

from dataclasses import dataclass, field
from enum import Enum

from pydantic import BaseModel, Field


# =============================================================================
# ENUMS
# =============================================================================

class PermissionAction(str, Enum):
    """Standard permission actions."""
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    MANAGE = "manage"  # Full control (implies all others)


class AccessLevel(str, Enum):
    """Access levels for record sharing."""
    READ = "read"
    READ_WRITE = "read_write"
    FULL = "full"  # Includes ability to share with others


class TeamRole(str, Enum):
    """Roles within a team."""
    MEMBER = "member"
    LEADER = "leader"


# =============================================================================
# DATACLASS MODELS (Internal use)
# =============================================================================

@dataclass
class Permission:
    """
    Permission definition.

    Format: "{module}:{resource}:{action}" e.g., "sales:proposals:create"
    """
    id: int | None = None
    name: str = ""
    resource: str = ""
    action: str = ""
    description: str | None = None

    @classmethod
    def from_name(cls, name: str, description: str | None = None) -> "Permission":
        """Create a Permission from a name string."""
        parts = name.split(":")
        module = parts[0] if len(parts) > 0 else ""
        resource = parts[1] if len(parts) > 1 else ""
        action = parts[2] if len(parts) > 2 else ""
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
class Profile:
    """
    Profile definition (Salesforce-style base permission template).

    Users are assigned exactly one profile which defines their base permissions.
    """
    id: int | None = None
    name: str = ""
    display_name: str = ""
    description: str | None = None
    permissions: set[str] = field(default_factory=set)
    is_system: bool = False
    created_at: str | None = None
    updated_at: str | None = None


@dataclass
class PermissionSet:
    """
    Permission Set - additive permissions on top of a profile.

    Users can have multiple permission sets for temporary access or special capabilities.
    """
    id: int | None = None
    name: str = ""
    display_name: str = ""
    description: str | None = None
    permissions: set[str] = field(default_factory=set)
    is_active: bool = True
    created_at: str | None = None
    updated_at: str | None = None


@dataclass
class Team:
    """
    Team/Group for organizational structure.

    Teams can be nested (parent_team_id) to create hierarchies.
    """
    id: int | None = None
    name: str = ""
    display_name: str | None = None
    description: str | None = None
    parent_team_id: int | None = None
    is_active: bool = True
    created_at: str | None = None
    updated_at: str | None = None


@dataclass
class TeamMember:
    """User membership in a team."""
    team_id: int
    user_id: str
    role: TeamRole = TeamRole.MEMBER
    joined_at: str | None = None


@dataclass
class SharingRule:
    """
    Automatic sharing rule (org-wide defaults).

    Defines how records are automatically shared based on ownership,
    profile, or team membership.
    """
    id: int | None = None
    name: str = ""
    description: str | None = None
    object_type: str = ""
    share_from_type: str = ""  # "owner", "profile", "team"
    share_from_id: str | None = None
    share_to_type: str = ""  # "profile", "team", "all"
    share_to_id: str | None = None
    access_level: AccessLevel = AccessLevel.READ
    is_active: bool = True
    created_at: str | None = None
    updated_at: str | None = None


@dataclass
class RecordShare:
    """
    Manual record-level share.

    Grants specific users or teams access to individual records.
    """
    id: int | None = None
    object_type: str = ""
    record_id: str = ""
    shared_with_user_id: str | None = None
    shared_with_team_id: int | None = None
    access_level: AccessLevel = AccessLevel.READ
    shared_by: str = ""
    shared_at: str | None = None
    expires_at: str | None = None
    reason: str | None = None


# =============================================================================
# PYDANTIC MODELS (API Request/Response)
# =============================================================================

class ProfileResponse(BaseModel):
    """Profile info returned from API."""
    id: int | None = None
    name: str
    display_name: str
    description: str | None = None
    permissions: list[str] = Field(default_factory=list)
    is_system: bool = False


class PermissionSetResponse(BaseModel):
    """Permission set info returned from API."""
    id: int | None = None
    name: str
    display_name: str
    description: str | None = None
    permissions: list[str] = Field(default_factory=list)
    is_active: bool = True


class TeamResponse(BaseModel):
    """Team info returned from API."""
    id: int | None = None
    name: str
    display_name: str | None = None
    description: str | None = None
    parent_team_id: int | None = None
    is_active: bool = True


class PermissionResponse(BaseModel):
    """Permission info returned from API."""
    name: str
    description: str | None = None


class UserRBACResponse(BaseModel):
    """Full RBAC info for a user."""
    user_id: str
    profile: ProfileResponse | None = None
    permission_sets: list[PermissionSetResponse] = Field(default_factory=list)
    teams: list[TeamResponse] = Field(default_factory=list)
    effective_permissions: list[str] = Field(default_factory=list)


# =============================================================================
# PERMISSION CONSTANTS
# Adapted from shared/security/rbac.py
# =============================================================================

PERMISSIONS = {
    # Core/Platform
    "core:users:read": "View users",
    "core:users:create": "Create users",
    "core:users:update": "Edit users",
    "core:users:delete": "Delete users",
    "core:users:manage": "Full control over users",
    "core:system:admin": "System administration",
    "core:system:config": "Manage system configuration",
    "core:ai_costs:read": "View AI cost reports",
    "core:ai_costs:manage": "Manage AI cost tracking",
    "core:api:access": "API access",
    "core:api_keys:read": "View API keys",
    "core:api_keys:create": "Create API keys",
    "core:api_keys:delete": "Delete API keys",
    "core:api_keys:manage": "Full control over API keys",
    "core:profiles:read": "View profiles",
    "core:profiles:create": "Create profiles",
    "core:profiles:update": "Update profiles",
    "core:profiles:delete": "Delete profiles",
    "core:profiles:manage": "Full control over profiles",
    "core:permission_sets:read": "View permission sets",
    "core:permission_sets:create": "Create permission sets",
    "core:permission_sets:update": "Update permission sets",
    "core:permission_sets:delete": "Delete permission sets",
    "core:permission_sets:manage": "Full control over permission sets",
    "core:teams:read": "View teams",
    "core:teams:create": "Create teams",
    "core:teams:update": "Update teams",
    "core:teams:delete": "Delete teams",
    "core:teams:manage": "Full control over teams",
    "core:sharing_rules:read": "View sharing rules",
    "core:sharing_rules:create": "Create sharing rules",
    "core:sharing_rules:delete": "Delete sharing rules",
    "core:sharing_rules:manage": "Full control over sharing rules",
    "core:files:read": "Read any user's files (admin)",
    "core:files:manage": "Full control over all files",

    # Asset Management
    "assets:networks:read": "View networks",
    "assets:networks:create": "Create networks",
    "assets:networks:update": "Update networks",
    "assets:networks:delete": "Delete networks",
    "assets:networks:manage": "Full control over networks",
    "assets:locations:read": "View locations",
    "assets:locations:create": "Create locations",
    "assets:locations:update": "Update locations",
    "assets:locations:delete": "Delete locations",
    "assets:locations:manage": "Full control over locations",
    "assets:packages:read": "View packages",
    "assets:packages:create": "Create packages",
    "assets:packages:update": "Update packages",
    "assets:packages:delete": "Delete packages",
    "assets:packages:manage": "Full control over packages",
    "assets:asset_types:read": "View asset types",
    "assets:asset_types:create": "Create asset types",
    "assets:asset_types:update": "Update asset types",
    "assets:asset_types:delete": "Delete asset types",
    "assets:asset_types:manage": "Full control over asset types",

    # Sales Module
    "sales:proposals:read": "View proposals",
    "sales:proposals:create": "Create proposals",
    "sales:proposals:update": "Update proposals",
    "sales:proposals:delete": "Delete proposals",
    "sales:proposals:manage": "Full control over proposals",
    "sales:booking_orders:read": "View booking orders",
    "sales:booking_orders:create": "Create booking orders",
    "sales:booking_orders:update": "Update booking orders",
    "sales:booking_orders:delete": "Delete booking orders",
    "sales:booking_orders:manage": "Full control over booking orders",
    "sales:mockups:read": "View mockups and templates",
    "sales:mockups:create": "Create mockups",
    "sales:mockups:update": "Edit mockups",
    "sales:mockups:delete": "Delete mockups",
    "sales:mockups:manage": "Full control over mockups",
    "sales:mockups:setup": "Configure mockup templates and frames",
    "sales:mockups:generate": "Generate mockup images",
    "sales:templates:read": "View templates",
    "sales:templates:create": "Create templates",
    "sales:templates:update": "Edit templates",
    "sales:templates:delete": "Delete templates",
    "sales:templates:manage": "Full control over templates",
    "sales:clients:read": "View clients",
    "sales:clients:create": "Create clients",
    "sales:clients:update": "Edit clients",
    "sales:clients:delete": "Delete clients",
    "sales:clients:manage": "Full control over clients",
    "sales:products:read": "View products",
    "sales:products:create": "Create products",
    "sales:products:update": "Edit products",
    "sales:products:delete": "Delete products",
    "sales:products:manage": "Full control over products",
    "sales:reports:read": "View reports",
    "sales:reports:export": "Export reports",
    "sales:rate_cards:read": "View rate cards",
    "sales:rate_cards:manage": "Manage rate cards",
    "sales:chat:use": "Use AI chat assistant",

    # Admin
    "admin:users:read": "View users",
    "admin:users:manage": "Manage users",
    "admin:audit:read": "View audit logs",
}


# =============================================================================
# PERMISSION MATCHING FUNCTIONS
# Adapted from shared/security/rbac.py
# =============================================================================

def matches_wildcard(pattern: str, permission: str) -> bool:
    """
    Check if a wildcard pattern matches a permission.

    Supports:
    - "*:*:*" matches everything
    - "sales:*:*" matches all sales permissions
    - "sales:proposals:*" matches all proposal actions
    - "manage" action implies all other actions
    """
    if pattern == "*:*:*":
        return True

    pattern_parts = pattern.split(":")
    perm_parts = permission.split(":")

    if len(pattern_parts) != 3 or len(perm_parts) != 3:
        return False

    for i, (p, t) in enumerate(zip(pattern_parts, perm_parts, strict=False)):
        if p != "*" and p != t:
            # "manage" action implies all other actions
            if i == 2 and p == "manage":
                return True
            return False

    return True


def has_permission(permissions: list[str], required: str) -> bool:
    """Check if user has a permission (direct match or wildcard)."""
    if required in permissions:
        return True
    return any(matches_wildcard(perm, required) for perm in permissions)


def has_any_permission(permissions: list[str], required: list[str]) -> bool:
    """Check if user has any of the specified permissions."""
    return any(has_permission(permissions, r) for r in required)


def has_all_permissions(permissions: list[str], required: list[str]) -> bool:
    """Check if user has all of the specified permissions."""
    return all(has_permission(permissions, r) for r in required)
