"""
Permissions definitions and database sync.

This is the source of truth for all permissions in the system.
Permissions are defined here in code (version controlled) and synced
to the database on startup for admin UI queries.

Permission format: {module}:{resource}:{action}
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger("unified-ui")


@dataclass
class Permission:
    """Permission definition."""
    name: str
    description: str
    module: str
    resource: str
    action: str

    @classmethod
    def from_name(cls, name: str, description: str) -> "Permission":
        """Create a Permission from a name string like 'module:resource:action'."""
        parts = name.split(":")
        if len(parts) != 3:
            raise ValueError(f"Invalid permission format: {name}")
        return cls(
            name=name,
            description=description,
            module=parts[0],
            resource=parts[1],
            action=parts[2],
        )


# =============================================================================
# CORE PLATFORM PERMISSIONS
# =============================================================================

CORE_PERMISSIONS = [
    # User Management
    Permission.from_name("core:users:read", "View users"),
    Permission.from_name("core:users:create", "Create users"),
    Permission.from_name("core:users:update", "Edit users"),
    Permission.from_name("core:users:delete", "Delete users"),
    Permission.from_name("core:users:manage", "Full control over users"),

    # System Administration
    Permission.from_name("core:system:admin", "System administration"),
    Permission.from_name("core:system:config", "Manage system configuration"),

    # AI Cost Tracking
    Permission.from_name("core:ai_costs:read", "View AI cost reports"),
    Permission.from_name("core:ai_costs:manage", "Manage AI cost tracking"),

    # API Keys / API Access
    Permission.from_name("core:api:access", "API access"),
    Permission.from_name("core:api_keys:read", "View API keys"),
    Permission.from_name("core:api_keys:create", "Create API keys"),
    Permission.from_name("core:api_keys:delete", "Delete API keys"),
    Permission.from_name("core:api_keys:manage", "Full control over API keys"),

    # Profile Management
    Permission.from_name("core:profiles:read", "View profiles"),
    Permission.from_name("core:profiles:create", "Create profiles"),
    Permission.from_name("core:profiles:update", "Update profiles"),
    Permission.from_name("core:profiles:delete", "Delete profiles"),
    Permission.from_name("core:profiles:manage", "Full control over profiles"),

    # Permission Set Management
    Permission.from_name("core:permission_sets:read", "View permission sets"),
    Permission.from_name("core:permission_sets:create", "Create permission sets"),
    Permission.from_name("core:permission_sets:update", "Update permission sets"),
    Permission.from_name("core:permission_sets:delete", "Delete permission sets"),
    Permission.from_name("core:permission_sets:manage", "Full control over permission sets"),

    # Team Management
    Permission.from_name("core:teams:read", "View teams"),
    Permission.from_name("core:teams:create", "Create teams"),
    Permission.from_name("core:teams:update", "Update teams"),
    Permission.from_name("core:teams:delete", "Delete teams"),
    Permission.from_name("core:teams:manage", "Full control over teams"),

    # Sharing Rules Management
    Permission.from_name("core:sharing_rules:read", "View sharing rules"),
    Permission.from_name("core:sharing_rules:create", "Create sharing rules"),
    Permission.from_name("core:sharing_rules:delete", "Delete sharing rules"),
    Permission.from_name("core:sharing_rules:manage", "Full control over sharing rules"),

    # File Management
    Permission.from_name("core:files:read", "Read any user's files (admin)"),
    Permission.from_name("core:files:manage", "Full control over all files"),
]


# =============================================================================
# SALES MODULE PERMISSIONS
# =============================================================================

SALES_PERMISSIONS = [
    # Proposals
    Permission.from_name("sales:proposals:create", "Create new proposals"),
    Permission.from_name("sales:proposals:read", "View proposals"),
    Permission.from_name("sales:proposals:update", "Edit proposals"),
    Permission.from_name("sales:proposals:delete", "Delete proposals"),
    Permission.from_name("sales:proposals:manage", "Full control over proposals"),

    # Booking Orders
    Permission.from_name("sales:booking_orders:create", "Create booking orders"),
    Permission.from_name("sales:booking_orders:read", "View booking orders"),
    Permission.from_name("sales:booking_orders:update", "Edit booking orders"),
    Permission.from_name("sales:booking_orders:delete", "Delete booking orders"),
    Permission.from_name("sales:booking_orders:manage", "Full control over booking orders"),

    # Mockups
    Permission.from_name("sales:mockups:create", "Create mockups"),
    Permission.from_name("sales:mockups:read", "View mockups and templates"),
    Permission.from_name("sales:mockups:update", "Edit mockups"),
    Permission.from_name("sales:mockups:delete", "Delete mockups"),
    Permission.from_name("sales:mockups:manage", "Full control over mockups"),
    Permission.from_name("sales:mockups:setup", "Configure mockup templates and frames"),
    Permission.from_name("sales:mockups:generate", "Generate mockup images"),

    # Templates
    Permission.from_name("sales:templates:read", "View templates"),
    Permission.from_name("sales:templates:create", "Create templates"),
    Permission.from_name("sales:templates:update", "Edit templates"),
    Permission.from_name("sales:templates:delete", "Delete templates"),
    Permission.from_name("sales:templates:manage", "Full control over templates"),

    # Clients
    Permission.from_name("sales:clients:read", "View clients"),
    Permission.from_name("sales:clients:create", "Create clients"),
    Permission.from_name("sales:clients:update", "Edit clients"),
    Permission.from_name("sales:clients:delete", "Delete clients"),
    Permission.from_name("sales:clients:manage", "Full control over clients"),

    # Products
    Permission.from_name("sales:products:read", "View products"),
    Permission.from_name("sales:products:create", "Create products"),
    Permission.from_name("sales:products:update", "Edit products"),
    Permission.from_name("sales:products:delete", "Delete products"),
    Permission.from_name("sales:products:manage", "Full control over products"),

    # Reports
    Permission.from_name("sales:reports:read", "View reports"),
    Permission.from_name("sales:reports:export", "Export reports"),

    # Chat (AI Assistant)
    Permission.from_name("sales:chat:use", "Use AI chat assistant"),
]


# =============================================================================
# ASSET MANAGEMENT PERMISSIONS
# =============================================================================

ASSET_PERMISSIONS = [
    # Locations
    Permission.from_name("assets:locations:read", "View locations"),
    Permission.from_name("assets:locations:create", "Create locations"),
    Permission.from_name("assets:locations:update", "Update locations"),
    Permission.from_name("assets:locations:delete", "Delete locations"),
    Permission.from_name("assets:locations:manage", "Full control over locations"),

    # Networks
    Permission.from_name("assets:networks:read", "View networks"),
    Permission.from_name("assets:networks:create", "Create networks"),
    Permission.from_name("assets:networks:update", "Update networks"),
    Permission.from_name("assets:networks:delete", "Delete networks"),
    Permission.from_name("assets:networks:manage", "Full control over networks"),

    # Network Assets
    Permission.from_name("assets:network_assets:read", "View network assets"),
    Permission.from_name("assets:network_assets:create", "Create network assets"),
    Permission.from_name("assets:network_assets:update", "Update network assets"),
    Permission.from_name("assets:network_assets:delete", "Delete network assets"),
    Permission.from_name("assets:network_assets:manage", "Full control over network assets"),

    # Packages
    Permission.from_name("assets:packages:read", "View packages"),
    Permission.from_name("assets:packages:create", "Create packages"),
    Permission.from_name("assets:packages:update", "Update packages"),
    Permission.from_name("assets:packages:delete", "Delete packages"),
    Permission.from_name("assets:packages:manage", "Full control over packages"),
]


# =============================================================================
# ALL PERMISSIONS
# =============================================================================

ALL_PERMISSIONS = CORE_PERMISSIONS + SALES_PERMISSIONS + ASSET_PERMISSIONS


def get_all_permissions() -> list[Permission]:
    """Get all defined permissions."""
    return ALL_PERMISSIONS


def get_permissions_by_module(module: str) -> list[Permission]:
    """Get permissions for a specific module."""
    return [p for p in ALL_PERMISSIONS if p.module == module]


# =============================================================================
# DATABASE SYNC
# =============================================================================

async def sync_permissions_to_database() -> int:
    """
    Sync permissions from code to database.

    Uses upsert (insert or update on conflict) to ensure database
    matches code definitions. Returns count of permissions synced.
    """
    from backend.services.supabase_client import get_supabase

    supabase = get_supabase()
    if not supabase:
        logger.warning("[PERMISSIONS] Supabase not configured, skipping sync")
        return 0

    try:
        # Prepare permission records for upsert
        records = [
            {
                "name": p.name,
                "description": p.description,
                "module": p.module,
                "resource": p.resource,
                "action": p.action,
            }
            for p in ALL_PERMISSIONS
        ]

        # Upsert all permissions (insert or update on name conflict)
        result = (
            supabase.table("permissions")
            .upsert(records, on_conflict="name")
            .execute()
        )

        count = len(result.data) if result.data else 0
        logger.info(f"[PERMISSIONS] Synced {count} permissions to database")
        return count

    except Exception as e:
        logger.error(f"[PERMISSIONS] Failed to sync permissions: {e}")
        return 0
