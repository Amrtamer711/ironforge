"""
Admin API endpoints for role and permission management.

Provides endpoints for:
- Role management (CRUD)
- Permission listing
- User-role assignment
- System overview

All endpoints require admin role or system:admin permission.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.auth import require_auth, require_permission, require_any_role
from integrations.auth import AuthUser
from integrations.rbac import (
    get_rbac_client,
    Role,
    Permission,
    DEFAULT_ROLES,
    DEFAULT_PERMISSIONS,
)
from utils.logging import get_logger

router = APIRouter(prefix="/api/admin", tags=["admin"])
logger = get_logger("api.admin")


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================


class RoleCreate(BaseModel):
    """Request model for creating a role."""
    name: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-z_]+$")
    description: Optional[str] = Field(None, max_length=200)
    permissions: List[str] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    """Request model for updating a role."""
    description: Optional[str] = Field(None, max_length=200)
    permissions: Optional[List[str]] = None


class RoleResponse(BaseModel):
    """Response model for a role."""
    name: str
    description: Optional[str]
    permissions: List[str]
    is_system: bool


class PermissionResponse(BaseModel):
    """Response model for a permission."""
    name: str
    resource: str
    action: str
    description: Optional[str]


class UserRoleAssign(BaseModel):
    """Request model for assigning a role to a user."""
    user_id: str
    role_name: str


class UserRoleInfo(BaseModel):
    """Response model for user role information."""
    user_id: str
    roles: List[str]
    permissions: List[str]


class AdminDashboard(BaseModel):
    """Response model for admin dashboard."""
    total_roles: int
    total_permissions: int
    system_roles: List[str]
    custom_roles: List[str]


# =============================================================================
# ROLE ENDPOINTS
# =============================================================================


@router.get("/roles", response_model=List[RoleResponse])
async def list_roles(
    user: AuthUser = Depends(require_any_role("admin")),
):
    """
    List all available roles.

    Requires: system:admin permission
    """
    rbac = get_rbac_client()
    roles = await rbac.list_roles()

    return [
        RoleResponse(
            name=role.name,
            description=role.description,
            permissions=[p.name for p in role.permissions],
            is_system=role.is_system,
        )
        for role in roles
    ]


@router.get("/roles/{role_name}", response_model=RoleResponse)
async def get_role(
    role_name: str,
    user: AuthUser = Depends(require_any_role("admin")),
):
    """
    Get a specific role by name.

    Requires: system:admin permission
    """
    rbac = get_rbac_client()
    role = await rbac.get_role(role_name)

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role '{role_name}' not found",
        )

    return RoleResponse(
        name=role.name,
        description=role.description,
        permissions=[p.name for p in role.permissions],
        is_system=role.is_system,
    )


@router.post("/roles", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    role_data: RoleCreate,
    user: AuthUser = Depends(require_any_role("admin")),
):
    """
    Create a new custom role.

    Requires: system:admin permission

    Note: System roles cannot be created via API.
    """
    rbac = get_rbac_client()

    # Check if role already exists
    existing = await rbac.get_role(role_data.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Role '{role_data.name}' already exists",
        )

    # Validate permissions exist
    available_perms = await rbac.list_permissions()
    available_names = {p.name for p in available_perms}

    for perm in role_data.permissions:
        if perm not in available_names and perm != "*:manage":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid permission: {perm}",
            )

    # Create the role
    role = await rbac.create_role(
        name=role_data.name,
        description=role_data.description,
        permissions=role_data.permissions,
    )

    if not role:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create role",
        )

    logger.info(f"[ADMIN] Role created: {role.name} by {user.email}")

    return RoleResponse(
        name=role.name,
        description=role.description,
        permissions=[p.name for p in role.permissions],
        is_system=role.is_system,
    )


@router.put("/roles/{role_name}", response_model=RoleResponse)
async def update_role(
    role_name: str,
    role_data: RoleUpdate,
    user: AuthUser = Depends(require_any_role("admin")),
):
    """
    Update an existing role.

    Requires: system:admin permission

    Note: System roles can have descriptions updated but not permissions.
    """
    rbac = get_rbac_client()

    # Check role exists
    existing = await rbac.get_role(role_name)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role '{role_name}' not found",
        )

    # Prevent modifying system role permissions
    if existing.is_system and role_data.permissions is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify permissions of system roles",
        )

    # Validate permissions if provided
    if role_data.permissions is not None:
        available_perms = await rbac.list_permissions()
        available_names = {p.name for p in available_perms}

        for perm in role_data.permissions:
            if perm not in available_names and perm != "*:manage":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid permission: {perm}",
                )

    # Update the role
    role = await rbac.update_role(
        name=role_name,
        description=role_data.description,
        permissions=role_data.permissions,
    )

    if not role:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update role",
        )

    logger.info(f"[ADMIN] Role updated: {role.name} by {user.email}")

    return RoleResponse(
        name=role.name,
        description=role.description,
        permissions=[p.name for p in role.permissions],
        is_system=role.is_system,
    )


@router.delete("/roles/{role_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_name: str,
    user: AuthUser = Depends(require_any_role("admin")),
):
    """
    Delete a custom role.

    Requires: system:admin permission

    Note: System roles cannot be deleted.
    """
    rbac = get_rbac_client()

    # Check role exists
    existing = await rbac.get_role(role_name)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role '{role_name}' not found",
        )

    if existing.is_system:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete system roles",
        )

    success = await rbac.delete_role(role_name)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete role",
        )

    logger.info(f"[ADMIN] Role deleted: {role_name} by {user.email}")


# =============================================================================
# PERMISSION ENDPOINTS
# =============================================================================


@router.get("/permissions", response_model=List[PermissionResponse])
async def list_permissions(
    user: AuthUser = Depends(require_any_role("admin")),
):
    """
    List all available permissions.

    Requires: system:admin permission
    """
    rbac = get_rbac_client()
    permissions = await rbac.list_permissions()

    return [
        PermissionResponse(
            name=p.name,
            resource=p.resource,
            action=p.action,
            description=p.description,
        )
        for p in permissions
    ]


@router.get("/permissions/grouped")
async def list_permissions_grouped(
    user: AuthUser = Depends(require_any_role("admin")),
):
    """
    List permissions grouped by resource.

    Requires: system:admin permission
    """
    rbac = get_rbac_client()
    permissions = await rbac.list_permissions()

    # Group by resource
    grouped = {}
    for p in permissions:
        if p.resource not in grouped:
            grouped[p.resource] = []
        grouped[p.resource].append({
            "name": p.name,
            "action": p.action,
            "description": p.description,
        })

    return grouped


# =============================================================================
# USER ROLE MANAGEMENT
# =============================================================================


@router.get("/users/{user_id}/roles", response_model=UserRoleInfo)
async def get_user_roles(
    user_id: str,
    user: AuthUser = Depends(require_permission("users:read")),
):
    """
    Get roles and permissions for a specific user.

    Requires: users:read permission
    """
    rbac = get_rbac_client()

    roles = await rbac.get_user_roles(user_id)
    permissions = await rbac.get_user_permissions(user_id)

    return UserRoleInfo(
        user_id=user_id,
        roles=[r.name for r in roles],
        permissions=list(permissions),
    )


@router.post("/users/{user_id}/roles/{role_name}", status_code=status.HTTP_201_CREATED)
async def assign_user_role(
    user_id: str,
    role_name: str,
    user: AuthUser = Depends(require_permission("users:manage")),
):
    """
    Assign a role to a user.

    Requires: users:manage permission
    """
    rbac = get_rbac_client()

    # Verify role exists
    role = await rbac.get_role(role_name)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role '{role_name}' not found",
        )

    # Check if user already has role
    if await rbac.has_role(user_id, role_name):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User already has role '{role_name}'",
        )

    success = await rbac.assign_role(
        user_id=user_id,
        role_name=role_name,
        granted_by=user.id,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to assign role",
        )

    logger.info(f"[ADMIN] Role '{role_name}' assigned to user {user_id} by {user.email}")

    return {"success": True, "message": f"Role '{role_name}' assigned to user"}


@router.delete("/users/{user_id}/roles/{role_name}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_user_role(
    user_id: str,
    role_name: str,
    user: AuthUser = Depends(require_permission("users:manage")),
):
    """
    Revoke a role from a user.

    Requires: users:manage permission
    """
    rbac = get_rbac_client()

    # Check if user has the role
    if not await rbac.has_role(user_id, role_name):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User does not have role '{role_name}'",
        )

    success = await rbac.revoke_role(user_id, role_name)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to revoke role",
        )

    logger.info(f"[ADMIN] Role '{role_name}' revoked from user {user_id} by {user.email}")


# =============================================================================
# DASHBOARD / OVERVIEW
# =============================================================================


@router.get("/dashboard", response_model=AdminDashboard)
async def admin_dashboard(
    user: AuthUser = Depends(require_any_role("admin")),
):
    """
    Get admin dashboard overview.

    Requires: system:admin permission
    """
    rbac = get_rbac_client()

    roles = await rbac.list_roles()
    permissions = await rbac.list_permissions()

    system_roles = [r.name for r in roles if r.is_system]
    custom_roles = [r.name for r in roles if not r.is_system]

    return AdminDashboard(
        total_roles=len(roles),
        total_permissions=len(permissions),
        system_roles=system_roles,
        custom_roles=custom_roles,
    )


@router.post("/initialize", status_code=status.HTTP_200_OK)
async def initialize_rbac(
    user: AuthUser = Depends(require_any_role("admin")),
):
    """
    Initialize default roles and permissions.

    Requires: system:admin permission

    This is idempotent - calling it multiple times won't duplicate data.
    """
    rbac = get_rbac_client()

    success = await rbac.initialize_defaults()

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initialize RBAC defaults",
        )

    logger.info(f"[ADMIN] RBAC defaults initialized by {user.email}")

    return {"success": True, "message": "RBAC defaults initialized"}


# =============================================================================
# API KEY MANAGEMENT ENDPOINTS
# =============================================================================


class APIKeyCreate(BaseModel):
    """Request model for creating an API key."""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    scopes: List[str] = Field(default_factory=lambda: ["read"])
    rate_limit: Optional[int] = Field(None, ge=1, le=10000)
    expires_at: Optional[str] = None


class APIKeyUpdate(BaseModel):
    """Request model for updating an API key."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    scopes: Optional[List[str]] = None
    rate_limit: Optional[int] = Field(None, ge=1, le=10000)
    is_active: Optional[bool] = None
    expires_at: Optional[str] = None


class APIKeyResponse(BaseModel):
    """Response model for an API key (without the raw key)."""
    id: int
    key_prefix: str
    name: str
    description: Optional[str]
    scopes: List[str]
    rate_limit: Optional[int]
    is_active: bool
    created_at: str
    created_by: Optional[str]
    expires_at: Optional[str]
    last_used_at: Optional[str]
    last_rotated_at: Optional[str]


class APIKeyCreateResponse(BaseModel):
    """Response model for API key creation (includes the raw key once)."""
    id: int
    raw_key: str  # Only shown once!
    key_prefix: str
    name: str
    scopes: List[str]
    message: str


@router.get("/api-keys", response_model=List[APIKeyResponse])
async def list_api_keys(
    include_inactive: bool = False,
    user: AuthUser = Depends(require_any_role("admin")),
):
    """
    List all API keys.

    Requires: system:admin permission
    """
    from db import get_db
    db = get_db()

    keys = db.list_api_keys(include_inactive=include_inactive)

    return [
        APIKeyResponse(
            id=k["id"],
            key_prefix=k["key_prefix"],
            name=k["name"],
            description=k.get("description"),
            scopes=k.get("scopes", []),
            rate_limit=k.get("rate_limit"),
            is_active=bool(k.get("is_active", 1)),
            created_at=k["created_at"],
            created_by=k.get("created_by"),
            expires_at=k.get("expires_at"),
            last_used_at=k.get("last_used_at"),
            last_rotated_at=k.get("last_rotated_at"),
        )
        for k in keys
    ]


@router.get("/api-keys/{key_id}", response_model=APIKeyResponse)
async def get_api_key(
    key_id: int,
    user: AuthUser = Depends(require_any_role("admin")),
):
    """
    Get a specific API key by ID.

    Requires: system:admin permission
    """
    from db import get_db
    db = get_db()

    k = db.get_api_key_by_id(key_id)

    if not k:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API key {key_id} not found",
        )

    return APIKeyResponse(
        id=k["id"],
        key_prefix=k["key_prefix"],
        name=k["name"],
        description=k.get("description"),
        scopes=k.get("scopes", []),
        rate_limit=k.get("rate_limit"),
        is_active=bool(k.get("is_active", 1)),
        created_at=k["created_at"],
        created_by=k.get("created_by"),
        expires_at=k.get("expires_at"),
        last_used_at=k.get("last_used_at"),
        last_rotated_at=k.get("last_rotated_at"),
    )


@router.post("/api-keys", response_model=APIKeyCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    key_data: APIKeyCreate,
    user: AuthUser = Depends(require_any_role("admin")),
):
    """
    Create a new API key.

    Requires: system:admin permission

    IMPORTANT: The raw API key is only returned ONCE in this response.
    Store it securely - it cannot be retrieved again.
    """
    from db import get_db
    from api.middleware import generate_api_key

    db = get_db()

    # Generate the key
    raw_key, key_hash = generate_api_key(prefix="sk")
    key_prefix = raw_key[:8]  # First 8 chars for identification

    # Validate scopes
    valid_scopes = ["read", "write", "admin", "proposals", "mockups"]
    for scope in key_data.scopes:
        if scope not in valid_scopes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid scope: {scope}. Valid scopes: {valid_scopes}",
            )

    # Create in database
    key_id = db.create_api_key(
        key_hash=key_hash,
        key_prefix=key_prefix,
        name=key_data.name,
        scopes=key_data.scopes,
        description=key_data.description,
        rate_limit=key_data.rate_limit,
        expires_at=key_data.expires_at,
        created_by=user.id,
    )

    if not key_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create API key",
        )

    logger.info(f"[ADMIN] API key created: {key_data.name} (id={key_id}) by {user.email}")

    return APIKeyCreateResponse(
        id=key_id,
        raw_key=raw_key,
        key_prefix=key_prefix,
        name=key_data.name,
        scopes=key_data.scopes,
        message="API key created successfully. Store this key securely - it won't be shown again!",
    )


@router.put("/api-keys/{key_id}", response_model=APIKeyResponse)
async def update_api_key(
    key_id: int,
    key_data: APIKeyUpdate,
    user: AuthUser = Depends(require_any_role("admin")),
):
    """
    Update an API key.

    Requires: system:admin permission
    """
    from db import get_db
    db = get_db()

    # Check key exists
    existing = db.get_api_key_by_id(key_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API key {key_id} not found",
        )

    # Validate scopes if provided
    if key_data.scopes is not None:
        valid_scopes = ["read", "write", "admin", "proposals", "mockups"]
        for scope in key_data.scopes:
            if scope not in valid_scopes:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid scope: {scope}. Valid scopes: {valid_scopes}",
                )

    # Update
    success = db.update_api_key(
        key_id=key_id,
        name=key_data.name,
        description=key_data.description,
        scopes=key_data.scopes,
        rate_limit=key_data.rate_limit,
        is_active=key_data.is_active,
        expires_at=key_data.expires_at,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update API key",
        )

    logger.info(f"[ADMIN] API key updated: {key_id} by {user.email}")

    # Fetch updated key
    k = db.get_api_key_by_id(key_id)

    return APIKeyResponse(
        id=k["id"],
        key_prefix=k["key_prefix"],
        name=k["name"],
        description=k.get("description"),
        scopes=k.get("scopes", []),
        rate_limit=k.get("rate_limit"),
        is_active=bool(k.get("is_active", 1)),
        created_at=k["created_at"],
        created_by=k.get("created_by"),
        expires_at=k.get("expires_at"),
        last_used_at=k.get("last_used_at"),
        last_rotated_at=k.get("last_rotated_at"),
    )


@router.post("/api-keys/{key_id}/rotate")
async def rotate_api_key(
    key_id: int,
    user: AuthUser = Depends(require_any_role("admin")),
):
    """
    Rotate an API key (generate new secret, invalidate old).

    Requires: system:admin permission

    IMPORTANT: The new raw key is only returned ONCE.
    Store it securely - it cannot be retrieved again.
    """
    from db import get_db
    from api.middleware import generate_api_key
    from utils.time import get_uae_time

    db = get_db()

    # Check key exists
    existing = db.get_api_key_by_id(key_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API key {key_id} not found",
        )

    # Generate new key
    raw_key, key_hash = generate_api_key(prefix="sk")
    key_prefix = raw_key[:8]

    # Rotate
    success = db.rotate_api_key(
        key_id=key_id,
        new_key_hash=key_hash,
        new_key_prefix=key_prefix,
        rotated_at=get_uae_time().isoformat(),
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to rotate API key",
        )

    logger.info(f"[ADMIN] API key rotated: {key_id} by {user.email}")

    return {
        "id": key_id,
        "raw_key": raw_key,
        "key_prefix": key_prefix,
        "message": "API key rotated successfully. Store this new key securely - it won't be shown again!",
    }


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
    key_id: int,
    user: AuthUser = Depends(require_any_role("admin")),
):
    """
    Delete an API key (hard delete).

    Requires: system:admin permission
    """
    from db import get_db
    db = get_db()

    # Check key exists
    existing = db.get_api_key_by_id(key_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API key {key_id} not found",
        )

    success = db.delete_api_key(key_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete API key",
        )

    logger.info(f"[ADMIN] API key deleted: {key_id} by {user.email}")


@router.post("/api-keys/{key_id}/deactivate", status_code=status.HTTP_200_OK)
async def deactivate_api_key(
    key_id: int,
    user: AuthUser = Depends(require_any_role("admin")),
):
    """
    Deactivate an API key (soft delete).

    Requires: system:admin permission
    """
    from db import get_db
    db = get_db()

    # Check key exists
    existing = db.get_api_key_by_id(key_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API key {key_id} not found",
        )

    success = db.deactivate_api_key(key_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to deactivate API key",
        )

    logger.info(f"[ADMIN] API key deactivated: {key_id} by {user.email}")

    return {"success": True, "message": "API key deactivated"}


@router.get("/api-keys/{key_id}/usage")
async def get_api_key_usage(
    key_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user: AuthUser = Depends(require_any_role("admin")),
):
    """
    Get usage statistics for an API key.

    Requires: system:admin permission
    """
    from db import get_db
    db = get_db()

    # Check key exists
    existing = db.get_api_key_by_id(key_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API key {key_id} not found",
        )

    stats = db.get_api_key_usage_stats(
        api_key_id=key_id,
        start_date=start_date,
        end_date=end_date,
    )

    return {
        "api_key_id": key_id,
        "api_key_name": existing["name"],
        **stats,
    }
