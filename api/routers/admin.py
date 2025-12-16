"""
Admin API endpoints for RBAC and user management.

Enterprise RBAC with 4 levels:
- Level 1: Profiles (base permission templates)
- Level 2: Permission Sets (additive permissions)
- Level 3: Teams & Hierarchy
- Level 4: Record-Level Sharing

All endpoints require system_admin profile or appropriate permissions.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.auth import require_permission
from integrations.auth import AuthUser, get_auth_client
from integrations.rbac import (
    AccessLevel,
    TeamRole,
    get_rbac_client,
)
from utils.logging import get_logger

router = APIRouter(prefix="/api/admin", tags=["admin"])
logger = get_logger("api.admin")


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================


class PermissionResponse(BaseModel):
    """Response model for a permission."""
    name: str
    resource: str
    action: str
    description: Optional[str]


class UserPermissionsInfo(BaseModel):
    """Response model for user permission information."""
    user_id: str
    profile: Optional[str]
    permission_sets: list[str]
    permissions: list[str]


class UserResponse(BaseModel):
    """Response model for a user."""
    id: str
    email: str
    name: Optional[str]
    is_active: bool
    created_at: str
    last_login_at: Optional[str]
    profile: Optional[str] = None


class UserCreate(BaseModel):
    """Request model for creating a user."""
    email: str = Field(..., min_length=5)
    name: Optional[str] = Field(None, max_length=100)
    password: str = Field(..., min_length=6)
    profile: str = Field(default="sales_user")


class UserUpdate(BaseModel):
    """Request model for updating a user."""
    name: Optional[str] = Field(None, max_length=100)
    is_active: Optional[bool] = None


class AdminDashboard(BaseModel):
    """Response model for admin dashboard."""
    total_profiles: int
    total_permission_sets: int
    total_permissions: int
    system_profiles: list[str]
    custom_profiles: list[str]


# =============================================================================
# PERMISSION ENDPOINTS
# =============================================================================


@router.get("/permissions", response_model=list[PermissionResponse])
async def list_permissions(
    user: AuthUser = Depends(require_permission("core:system:admin")),
):
    """
    List all available permissions.

    Requires: system_admin profile
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
    user: AuthUser = Depends(require_permission("core:system:admin")),
):
    """
    List permissions grouped by resource.

    Requires: system_admin profile
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
# USER PERMISSIONS INFO
# =============================================================================


@router.get("/users/{user_id}/permissions", response_model=UserPermissionsInfo)
async def get_user_permissions_info(
    user_id: str,
    user: AuthUser = Depends(require_permission("core:users:read")),
):
    """
    Get profile, permission sets, and permissions for a specific user.

    Requires: core:users:read permission
    """
    rbac = get_rbac_client()

    profile = await rbac.get_user_profile(user_id)
    permission_sets = await rbac.get_user_permission_sets(user_id)
    permissions = await rbac.get_user_permissions(user_id)

    return UserPermissionsInfo(
        user_id=user_id,
        profile=profile.name if profile else None,
        permission_sets=[ps.name for ps in permission_sets],
        permissions=list(permissions),
    )


# =============================================================================
# DASHBOARD / OVERVIEW
# =============================================================================


@router.get("/dashboard", response_model=AdminDashboard)
async def admin_dashboard(
    user: AuthUser = Depends(require_permission("core:system:admin")),
):
    """
    Get admin dashboard overview.

    Requires: system_admin profile
    """
    rbac = get_rbac_client()

    profiles = await rbac.list_profiles()
    permission_sets = await rbac.list_permission_sets()
    permissions = await rbac.list_permissions()

    system_profiles = [p.name for p in profiles if p.is_system]
    custom_profiles = [p.name for p in profiles if not p.is_system]

    return AdminDashboard(
        total_profiles=len(profiles),
        total_permission_sets=len(permission_sets),
        total_permissions=len(permissions),
        system_profiles=system_profiles,
        custom_profiles=custom_profiles,
    )


@router.post("/initialize", status_code=status.HTTP_200_OK)
async def initialize_rbac(
    user: AuthUser = Depends(require_permission("core:system:admin")),
):
    """
    Initialize default profiles and permissions.

    Requires: system_admin profile

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
    scopes: list[str] = Field(default_factory=lambda: ["read"])
    rate_limit: Optional[int] = Field(None, ge=1, le=10000)
    expires_at: Optional[str] = None


class APIKeyUpdate(BaseModel):
    """Request model for updating an API key."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    scopes: Optional[list[str]] = None
    rate_limit: Optional[int] = Field(None, ge=1, le=10000)
    is_active: Optional[bool] = None
    expires_at: Optional[str] = None


class APIKeyResponse(BaseModel):
    """Response model for an API key (without the raw key)."""
    id: int
    key_prefix: str
    name: str
    description: Optional[str]
    scopes: list[str]
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
    scopes: list[str]
    message: str


@router.get("/api-keys", response_model=list[APIKeyResponse])
async def list_api_keys(
    include_inactive: bool = False,
    user: AuthUser = Depends(require_permission("core:system:admin")),
):
    """
    List all API keys.

    Requires: system:admin permission
    """
    from db.database import db


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
    user: AuthUser = Depends(require_permission("core:system:admin")),
):
    """
    Get a specific API key by ID.

    Requires: system:admin permission
    """
    from db.database import db


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
    user: AuthUser = Depends(require_permission("core:system:admin")),
):
    """
    Create a new API key.

    Requires: system:admin permission

    IMPORTANT: The raw API key is only returned ONCE in this response.
    Store it securely - it cannot be retrieved again.
    """
    from api.middleware import generate_api_key
    from db.database import db



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
    user: AuthUser = Depends(require_permission("core:system:admin")),
):
    """
    Update an API key.

    Requires: system:admin permission
    """
    from db.database import db


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
    user: AuthUser = Depends(require_permission("core:system:admin")),
):
    """
    Rotate an API key (generate new secret, invalidate old).

    Requires: system:admin permission

    IMPORTANT: The new raw key is only returned ONCE.
    Store it securely - it cannot be retrieved again.
    """
    from api.middleware import generate_api_key
    from db.database import db
    from utils.time import get_uae_time



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
    user: AuthUser = Depends(require_permission("core:system:admin")),
):
    """
    Delete an API key (hard delete).

    Requires: system:admin permission
    """
    from db.database import db


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
    user: AuthUser = Depends(require_permission("core:system:admin")),
):
    """
    Deactivate an API key (soft delete).

    Requires: system:admin permission
    """
    from db.database import db


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
    user: AuthUser = Depends(require_permission("core:system:admin")),
):
    """
    Get usage statistics for an API key.

    Requires: system:admin permission
    """
    from db.database import db


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


# =============================================================================
# USER MANAGEMENT ENDPOINTS
# =============================================================================


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    limit: int = 100,
    offset: int = 0,
    is_active: Optional[bool] = None,
    user: AuthUser = Depends(require_permission("core:users:read")),
):
    """
    List all users with pagination.

    Requires: core:users:read permission
    """
    auth = get_auth_client()
    rbac = get_rbac_client()

    users = await auth.list_users(limit=limit, offset=offset, is_active=is_active)

    result = []
    for u in users:
        # Get profile for each user using RBAC client
        profile = await rbac.get_user_profile(u.id)
        result.append(
            UserResponse(
                id=u.id,
                email=u.email,
                name=u.name,
                is_active=u.is_active,
                created_at=u.metadata.get("created_at", ""),
                last_login_at=u.metadata.get("last_login_at"),
                profile=profile.name if profile else None,
            )
        )

    return result


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    user: AuthUser = Depends(require_permission("core:users:read")),
):
    """
    Get a specific user by ID.

    Requires: core:users:read permission
    """
    auth = get_auth_client()
    rbac = get_rbac_client()

    target_user = await auth.get_user_by_id(user_id)

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{user_id}' not found",
        )

    profile = await rbac.get_user_profile(user_id)

    return UserResponse(
        id=target_user.id,
        email=target_user.email,
        name=target_user.name,
        is_active=target_user.is_active,
        created_at=target_user.metadata.get("created_at", ""),
        last_login_at=target_user.metadata.get("last_login_at"),
        profile=profile.name if profile else None,
    )


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    user: AuthUser = Depends(require_permission("core:users:create")),
):
    """
    Create a new user.

    Requires: core:users:create permission

    Creates user in auth system and assigns initial profile.
    """
    auth = get_auth_client()
    rbac = get_rbac_client()

    # Check if email already exists
    existing = await auth.get_user_by_email(user_data.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User with email '{user_data.email}' already exists",
        )

    # Validate profile exists
    profile = await rbac.get_profile(user_data.profile)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid profile: {user_data.profile}",
        )

    # Create user via auth provider
    # Note: password handling depends on the auth provider
    # For Supabase: Creates user in auth.users with password
    # For Local: Creates user in local database
    new_user = await auth.create_user(
        email=user_data.email,
        name=user_data.name,
        metadata={"password": user_data.password},  # Provider handles hashing
    )

    if not new_user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user",
        )

    # Assign profile via RBAC provider
    await rbac.assign_profile(new_user.id, user_data.profile)

    logger.info(f"[ADMIN] User created: {new_user.email} (id={new_user.id}) by {user.email}")

    return UserResponse(
        id=new_user.id,
        email=new_user.email,
        name=new_user.name,
        is_active=new_user.is_active,
        created_at=new_user.metadata.get("created_at", ""),
        last_login_at=None,
        profile=user_data.profile,
    )


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    user_data: UserUpdate,
    user: AuthUser = Depends(require_permission("core:users:update")),
):
    """
    Update a user's information.

    Requires: core:users:update permission
    """
    auth = get_auth_client()
    rbac = get_rbac_client()

    # Check user exists
    target_user = await auth.get_user_by_id(user_id)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{user_id}' not found",
        )

    # Update via auth provider
    updated_user = await auth.update_user(
        user_id=user_id,
        name=user_data.name,
        is_active=user_data.is_active,
    )

    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user",
        )

    profile = await rbac.get_user_profile(user_id)

    logger.info(f"[ADMIN] User updated: {user_id} by {user.email}")

    return UserResponse(
        id=updated_user.id,
        email=updated_user.email,
        name=updated_user.name,
        is_active=updated_user.is_active,
        created_at=updated_user.metadata.get("created_at", ""),
        last_login_at=updated_user.metadata.get("last_login_at"),
        profile=profile.name if profile else None,
    )


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    user: AuthUser = Depends(require_permission("core:users:delete")),
):
    """
    Delete a user.

    Requires: core:users:delete permission

    Note: This permanently removes the user from the auth system.
    """
    auth = get_auth_client()

    # Check user exists
    target_user = await auth.get_user_by_id(user_id)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{user_id}' not found",
        )

    # Prevent self-deletion
    if user_id == user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete your own account",
        )

    # Delete via auth provider
    success = await auth.delete_user(user_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete user",
        )

    logger.info(f"[ADMIN] User deleted: {user_id} by {user.email}")


# =============================================================================
# ENTERPRISE RBAC: PROFILE MANAGEMENT
# =============================================================================


class ProfileCreate(BaseModel):
    """Request model for creating a profile."""
    name: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-z_]+$")
    display_name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    permissions: list[str] = Field(default_factory=list)


class ProfileUpdate(BaseModel):
    """Request model for updating a profile."""
    display_name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    permissions: Optional[list[str]] = None


class ProfileResponse(BaseModel):
    """Response model for a profile."""
    id: int
    name: str
    display_name: str
    description: Optional[str]
    permissions: list[str]
    is_system: bool
    created_at: Optional[str]
    updated_at: Optional[str]


@router.get("/profiles", response_model=list[ProfileResponse])
async def list_profiles(
    user: AuthUser = Depends(require_permission("core:system:admin")),
):
    """
    List all available profiles.

    Requires: admin role
    """
    rbac = get_rbac_client()
    profiles = await rbac.list_profiles()

    return [
        ProfileResponse(
            id=p.id,
            name=p.name,
            display_name=p.display_name,
            description=p.description,
            permissions=list(p.permissions),
            is_system=p.is_system,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p in profiles
    ]


@router.get("/profiles/{profile_name}", response_model=ProfileResponse)
async def get_profile(
    profile_name: str,
    user: AuthUser = Depends(require_permission("core:system:admin")),
):
    """
    Get a specific profile by name.

    Requires: admin role
    """
    rbac = get_rbac_client()
    profile = await rbac.get_profile(profile_name)

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile '{profile_name}' not found",
        )

    return ProfileResponse(
        id=profile.id,
        name=profile.name,
        display_name=profile.display_name,
        description=profile.description,
        permissions=list(profile.permissions),
        is_system=profile.is_system,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


@router.post("/profiles", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_profile(
    profile_data: ProfileCreate,
    user: AuthUser = Depends(require_permission("core:system:admin")),
):
    """
    Create a new profile.

    Requires: admin role
    """
    rbac = get_rbac_client()

    # Check if profile already exists
    existing = await rbac.get_profile(profile_data.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Profile '{profile_data.name}' already exists",
        )

    profile = await rbac.create_profile(
        name=profile_data.name,
        display_name=profile_data.display_name,
        description=profile_data.description,
        permissions=profile_data.permissions,
    )

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create profile",
        )

    logger.info(f"[ADMIN] Profile created: {profile.name} by {user.email}")

    return ProfileResponse(
        id=profile.id,
        name=profile.name,
        display_name=profile.display_name,
        description=profile.description,
        permissions=list(profile.permissions),
        is_system=profile.is_system,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


@router.put("/profiles/{profile_name}", response_model=ProfileResponse)
async def update_profile(
    profile_name: str,
    profile_data: ProfileUpdate,
    user: AuthUser = Depends(require_permission("core:system:admin")),
):
    """
    Update an existing profile.

    Requires: admin role

    Note: System profiles cannot have their permissions modified.
    """
    rbac = get_rbac_client()

    existing = await rbac.get_profile(profile_name)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile '{profile_name}' not found",
        )

    if existing.is_system and profile_data.permissions is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify permissions of system profiles",
        )

    profile = await rbac.update_profile(
        name=profile_name,
        display_name=profile_data.display_name,
        description=profile_data.description,
        permissions=profile_data.permissions,
    )

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update profile",
        )

    logger.info(f"[ADMIN] Profile updated: {profile.name} by {user.email}")

    return ProfileResponse(
        id=profile.id,
        name=profile.name,
        display_name=profile.display_name,
        description=profile.description,
        permissions=list(profile.permissions),
        is_system=profile.is_system,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


@router.delete("/profiles/{profile_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(
    profile_name: str,
    user: AuthUser = Depends(require_permission("core:system:admin")),
):
    """
    Delete a profile.

    Requires: admin role

    Note: System profiles cannot be deleted.
    """
    rbac = get_rbac_client()

    existing = await rbac.get_profile(profile_name)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile '{profile_name}' not found",
        )

    if existing.is_system:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete system profiles",
        )

    success = await rbac.delete_profile(profile_name)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete profile",
        )

    logger.info(f"[ADMIN] Profile deleted: {profile_name} by {user.email}")


@router.put("/users/{user_id}/profile", status_code=status.HTTP_200_OK)
async def assign_user_profile(
    user_id: str,
    profile_name: str,
    user: AuthUser = Depends(require_permission("core:users:manage")),
):
    """
    Assign a profile to a user.

    Requires: core:users:manage permission
    """
    rbac = get_rbac_client()

    # Verify profile exists
    profile = await rbac.get_profile(profile_name)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile '{profile_name}' not found",
        )

    success = await rbac.assign_profile(user_id, profile_name)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to assign profile",
        )

    logger.info(f"[ADMIN] Profile '{profile_name}' assigned to user {user_id} by {user.email}")

    return {"success": True, "message": f"Profile '{profile_name}' assigned to user"}


# =============================================================================
# ENTERPRISE RBAC: PERMISSION SET MANAGEMENT
# =============================================================================


class PermissionSetCreate(BaseModel):
    """Request model for creating a permission set."""
    name: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-z_]+$")
    display_name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    permissions: list[str] = Field(default_factory=list)


class PermissionSetUpdate(BaseModel):
    """Request model for updating a permission set."""
    display_name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    permissions: Optional[list[str]] = None
    is_active: Optional[bool] = None


class PermissionSetResponse(BaseModel):
    """Response model for a permission set."""
    id: int
    name: str
    display_name: str
    description: Optional[str]
    permissions: list[str]
    is_active: bool
    created_at: Optional[str]
    updated_at: Optional[str]


class UserPermissionSetAssign(BaseModel):
    """Request model for assigning a permission set to a user."""
    expires_at: Optional[str] = None  # ISO datetime or None for permanent


@router.get("/permission-sets", response_model=list[PermissionSetResponse])
async def list_permission_sets(
    user: AuthUser = Depends(require_permission("core:system:admin")),
):
    """
    List all available permission sets.

    Requires: admin role
    """
    rbac = get_rbac_client()
    permission_sets = await rbac.list_permission_sets()

    return [
        PermissionSetResponse(
            id=ps.id,
            name=ps.name,
            display_name=ps.display_name,
            description=ps.description,
            permissions=list(ps.permissions),
            is_active=ps.is_active,
            created_at=ps.created_at,
            updated_at=ps.updated_at,
        )
        for ps in permission_sets
    ]


@router.get("/permission-sets/{ps_name}", response_model=PermissionSetResponse)
async def get_permission_set(
    ps_name: str,
    user: AuthUser = Depends(require_permission("core:system:admin")),
):
    """
    Get a specific permission set by name.

    Requires: admin role
    """
    rbac = get_rbac_client()
    ps = await rbac.get_permission_set(ps_name)

    if not ps:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Permission set '{ps_name}' not found",
        )

    return PermissionSetResponse(
        id=ps.id,
        name=ps.name,
        display_name=ps.display_name,
        description=ps.description,
        permissions=list(ps.permissions),
        is_active=ps.is_active,
        created_at=ps.created_at,
        updated_at=ps.updated_at,
    )


@router.post("/permission-sets", response_model=PermissionSetResponse, status_code=status.HTTP_201_CREATED)
async def create_permission_set(
    ps_data: PermissionSetCreate,
    user: AuthUser = Depends(require_permission("core:system:admin")),
):
    """
    Create a new permission set.

    Requires: admin role
    """
    rbac = get_rbac_client()

    existing = await rbac.get_permission_set(ps_data.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Permission set '{ps_data.name}' already exists",
        )

    ps = await rbac.create_permission_set(
        name=ps_data.name,
        display_name=ps_data.display_name,
        description=ps_data.description,
        permissions=ps_data.permissions,
    )

    if not ps:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create permission set",
        )

    logger.info(f"[ADMIN] Permission set created: {ps.name} by {user.email}")

    return PermissionSetResponse(
        id=ps.id,
        name=ps.name,
        display_name=ps.display_name,
        description=ps.description,
        permissions=list(ps.permissions),
        is_active=ps.is_active,
        created_at=ps.created_at,
        updated_at=ps.updated_at,
    )


@router.put("/permission-sets/{ps_name}", response_model=PermissionSetResponse)
async def update_permission_set(
    ps_name: str,
    ps_data: PermissionSetUpdate,
    user: AuthUser = Depends(require_permission("core:system:admin")),
):
    """
    Update an existing permission set.

    Requires: admin role
    """
    rbac = get_rbac_client()

    existing = await rbac.get_permission_set(ps_name)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Permission set '{ps_name}' not found",
        )

    ps = await rbac.update_permission_set(
        name=ps_name,
        display_name=ps_data.display_name,
        description=ps_data.description,
        permissions=ps_data.permissions,
        is_active=ps_data.is_active,
    )

    if not ps:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update permission set",
        )

    logger.info(f"[ADMIN] Permission set updated: {ps.name} by {user.email}")

    return PermissionSetResponse(
        id=ps.id,
        name=ps.name,
        display_name=ps.display_name,
        description=ps.description,
        permissions=list(ps.permissions),
        is_active=ps.is_active,
        created_at=ps.created_at,
        updated_at=ps.updated_at,
    )


@router.delete("/permission-sets/{ps_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_permission_set(
    ps_name: str,
    user: AuthUser = Depends(require_permission("core:system:admin")),
):
    """
    Delete a permission set.

    Requires: admin role
    """
    rbac = get_rbac_client()

    existing = await rbac.get_permission_set(ps_name)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Permission set '{ps_name}' not found",
        )

    success = await rbac.delete_permission_set(ps_name)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete permission set",
        )

    logger.info(f"[ADMIN] Permission set deleted: {ps_name} by {user.email}")


@router.post("/users/{user_id}/permission-sets/{ps_name}", status_code=status.HTTP_201_CREATED)
async def assign_user_permission_set(
    user_id: str,
    ps_name: str,
    data: UserPermissionSetAssign = None,
    user: AuthUser = Depends(require_permission("core:users:manage")),
):
    """
    Grant a permission set to a user.

    Requires: core:users:manage permission
    """
    rbac = get_rbac_client()

    ps = await rbac.get_permission_set(ps_name)
    if not ps:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Permission set '{ps_name}' not found",
        )

    expires_at = data.expires_at if data else None

    success = await rbac.assign_permission_set(
        user_id=user_id,
        permission_set_name=ps_name,
        granted_by=user.id,
        expires_at=expires_at,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to assign permission set",
        )

    logger.info(f"[ADMIN] Permission set '{ps_name}' granted to user {user_id} by {user.email}")

    return {"success": True, "message": f"Permission set '{ps_name}' granted to user"}


@router.delete("/users/{user_id}/permission-sets/{ps_name}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_user_permission_set(
    user_id: str,
    ps_name: str,
    user: AuthUser = Depends(require_permission("core:users:manage")),
):
    """
    Revoke a permission set from a user.

    Requires: core:users:manage permission
    """
    rbac = get_rbac_client()

    success = await rbac.revoke_permission_set(user_id, ps_name)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to revoke permission set",
        )

    logger.info(f"[ADMIN] Permission set '{ps_name}' revoked from user {user_id} by {user.email}")


# =============================================================================
# ENTERPRISE RBAC: TEAM MANAGEMENT
# =============================================================================


class TeamCreate(BaseModel):
    """Request model for creating a team."""
    name: str = Field(..., min_length=1, max_length=100)
    display_name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    parent_team_id: Optional[int] = None


class TeamUpdate(BaseModel):
    """Request model for updating a team."""
    name: Optional[str] = Field(None, max_length=100)
    display_name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    parent_team_id: Optional[int] = None
    is_active: Optional[bool] = None


class TeamResponse(BaseModel):
    """Response model for a team."""
    id: int
    name: str
    display_name: Optional[str]
    description: Optional[str]
    parent_team_id: Optional[int]
    is_active: bool
    created_at: Optional[str]
    updated_at: Optional[str]


class TeamMemberAdd(BaseModel):
    """Request model for adding a member to a team."""
    user_id: str
    role: str = Field(default="member", pattern=r"^(member|leader)$")


class TeamMemberResponse(BaseModel):
    """Response model for a team member."""
    team_id: int
    user_id: str
    role: str
    joined_at: Optional[str]


@router.get("/teams", response_model=list[TeamResponse])
async def list_teams(
    user: AuthUser = Depends(require_permission("core:system:admin")),
):
    """
    List all teams.

    Requires: admin role
    """
    rbac = get_rbac_client()
    teams = await rbac.list_teams()

    return [
        TeamResponse(
            id=t.id,
            name=t.name,
            display_name=t.display_name,
            description=t.description,
            parent_team_id=t.parent_team_id,
            is_active=t.is_active,
            created_at=t.created_at,
            updated_at=t.updated_at,
        )
        for t in teams
    ]


@router.get("/teams/{team_id}", response_model=TeamResponse)
async def get_team(
    team_id: int,
    user: AuthUser = Depends(require_permission("core:system:admin")),
):
    """
    Get a specific team by ID.

    Requires: admin role
    """
    rbac = get_rbac_client()
    team = await rbac.get_team(team_id)

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team {team_id} not found",
        )

    return TeamResponse(
        id=team.id,
        name=team.name,
        display_name=team.display_name,
        description=team.description,
        parent_team_id=team.parent_team_id,
        is_active=team.is_active,
        created_at=team.created_at,
        updated_at=team.updated_at,
    )


@router.post("/teams", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
async def create_team(
    team_data: TeamCreate,
    user: AuthUser = Depends(require_permission("core:system:admin")),
):
    """
    Create a new team.

    Requires: admin role
    """
    rbac = get_rbac_client()

    existing = await rbac.get_team_by_name(team_data.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Team '{team_data.name}' already exists",
        )

    team = await rbac.create_team(
        name=team_data.name,
        display_name=team_data.display_name,
        description=team_data.description,
        parent_team_id=team_data.parent_team_id,
    )

    if not team:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create team",
        )

    logger.info(f"[ADMIN] Team created: {team.name} by {user.email}")

    return TeamResponse(
        id=team.id,
        name=team.name,
        display_name=team.display_name,
        description=team.description,
        parent_team_id=team.parent_team_id,
        is_active=team.is_active,
        created_at=team.created_at,
        updated_at=team.updated_at,
    )


@router.put("/teams/{team_id}", response_model=TeamResponse)
async def update_team(
    team_id: int,
    team_data: TeamUpdate,
    user: AuthUser = Depends(require_permission("core:system:admin")),
):
    """
    Update an existing team.

    Requires: admin role
    """
    rbac = get_rbac_client()

    existing = await rbac.get_team(team_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team {team_id} not found",
        )

    team = await rbac.update_team(
        team_id=team_id,
        name=team_data.name,
        display_name=team_data.display_name,
        description=team_data.description,
        parent_team_id=team_data.parent_team_id,
        is_active=team_data.is_active,
    )

    if not team:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update team",
        )

    logger.info(f"[ADMIN] Team updated: {team_id} by {user.email}")

    return TeamResponse(
        id=team.id,
        name=team.name,
        display_name=team.display_name,
        description=team.description,
        parent_team_id=team.parent_team_id,
        is_active=team.is_active,
        created_at=team.created_at,
        updated_at=team.updated_at,
    )


@router.delete("/teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(
    team_id: int,
    user: AuthUser = Depends(require_permission("core:system:admin")),
):
    """
    Delete a team.

    Requires: admin role
    """
    rbac = get_rbac_client()

    existing = await rbac.get_team(team_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team {team_id} not found",
        )

    success = await rbac.delete_team(team_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete team",
        )

    logger.info(f"[ADMIN] Team deleted: {team_id} by {user.email}")


@router.get("/teams/{team_id}/members", response_model=list[TeamMemberResponse])
async def get_team_members(
    team_id: int,
    user: AuthUser = Depends(require_permission("core:system:admin")),
):
    """
    Get all members of a team.

    Requires: admin role
    """
    rbac = get_rbac_client()

    team = await rbac.get_team(team_id)
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team {team_id} not found",
        )

    members = await rbac.get_team_members(team_id)

    return [
        TeamMemberResponse(
            team_id=m.team_id,
            user_id=m.user_id,
            role=m.role.value,
            joined_at=m.joined_at,
        )
        for m in members
    ]


@router.post("/teams/{team_id}/members", status_code=status.HTTP_201_CREATED)
async def add_team_member(
    team_id: int,
    member_data: TeamMemberAdd,
    user: AuthUser = Depends(require_permission("core:users:manage")),
):
    """
    Add a member to a team.

    Requires: core:users:manage permission
    """
    rbac = get_rbac_client()

    team = await rbac.get_team(team_id)
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team {team_id} not found",
        )

    role = TeamRole.LEADER if member_data.role == "leader" else TeamRole.MEMBER

    success = await rbac.add_user_to_team(
        user_id=member_data.user_id,
        team_id=team_id,
        role=role,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add member to team",
        )

    logger.info(f"[ADMIN] User {member_data.user_id} added to team {team_id} as {role.value} by {user.email}")

    return {"success": True, "message": f"User added to team as {role.value}"}


@router.delete("/teams/{team_id}/members/{member_user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_team_member(
    team_id: int,
    member_user_id: str,
    user: AuthUser = Depends(require_permission("core:users:manage")),
):
    """
    Remove a member from a team.

    Requires: core:users:manage permission
    """
    rbac = get_rbac_client()

    success = await rbac.remove_user_from_team(member_user_id, team_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove member from team",
        )

    logger.info(f"[ADMIN] User {member_user_id} removed from team {team_id} by {user.email}")


@router.put("/users/{user_id}/manager", status_code=status.HTTP_200_OK)
async def set_user_manager(
    user_id: str,
    manager_id: Optional[str] = None,
    user: AuthUser = Depends(require_permission("core:users:manage")),
):
    """
    Set or remove a user's manager.

    Requires: core:users:manage permission
    """
    from db.database import db
    from utils.time import get_uae_time


    now = get_uae_time().isoformat()

    try:
        db._backend.execute_query(
            "UPDATE users SET manager_id = %s, updated_at = %s WHERE id = %s",
            (manager_id, now, user_id)
        )

        logger.info(f"[ADMIN] Manager set for user {user_id}: {manager_id or 'None'} by {user.email}")

        return {"success": True, "message": f"Manager {'set' if manager_id else 'removed'} for user"}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to set manager: {str(e)}",
        )


# =============================================================================
# ENTERPRISE RBAC: SHARING RULES & RECORD SHARING
# =============================================================================


class SharingRuleCreate(BaseModel):
    """Request model for creating a sharing rule."""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    object_type: str = Field(..., min_length=1, max_length=50)
    share_from_type: str = Field(..., pattern=r"^(owner|profile|team)$")
    share_from_id: Optional[str] = None
    share_to_type: str = Field(..., pattern=r"^(profile|team|all)$")
    share_to_id: Optional[str] = None
    access_level: str = Field(..., pattern=r"^(read|read_write|full)$")


class SharingRuleResponse(BaseModel):
    """Response model for a sharing rule."""
    id: int
    name: str
    description: Optional[str]
    object_type: str
    share_from_type: str
    share_from_id: Optional[str]
    share_to_type: str
    share_to_id: Optional[str]
    access_level: str
    is_active: bool
    created_at: Optional[str]
    updated_at: Optional[str]


@router.get("/sharing-rules", response_model=list[SharingRuleResponse])
async def list_sharing_rules(
    object_type: Optional[str] = None,
    user: AuthUser = Depends(require_permission("core:system:admin")),
):
    """
    List all sharing rules, optionally filtered by object type.

    Requires: admin role
    """
    rbac = get_rbac_client()
    rules = await rbac.list_sharing_rules(object_type)

    return [
        SharingRuleResponse(
            id=r.id,
            name=r.name,
            description=r.description,
            object_type=r.object_type,
            share_from_type=r.share_from_type,
            share_from_id=r.share_from_id,
            share_to_type=r.share_to_type,
            share_to_id=r.share_to_id,
            access_level=r.access_level.value,
            is_active=r.is_active,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rules
    ]


@router.post("/sharing-rules", response_model=SharingRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_sharing_rule(
    rule_data: SharingRuleCreate,
    user: AuthUser = Depends(require_permission("core:system:admin")),
):
    """
    Create a new sharing rule.

    Requires: admin role
    """
    rbac = get_rbac_client()

    access_level = AccessLevel(rule_data.access_level)

    rule = await rbac.create_sharing_rule(
        name=rule_data.name,
        object_type=rule_data.object_type,
        share_from_type=rule_data.share_from_type,
        share_to_type=rule_data.share_to_type,
        access_level=access_level,
        share_from_id=rule_data.share_from_id,
        share_to_id=rule_data.share_to_id,
        description=rule_data.description,
    )

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create sharing rule",
        )

    logger.info(f"[ADMIN] Sharing rule created: {rule.name} by {user.email}")

    return SharingRuleResponse(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        object_type=rule.object_type,
        share_from_type=rule.share_from_type,
        share_from_id=rule.share_from_id,
        share_to_type=rule.share_to_type,
        share_to_id=rule.share_to_id,
        access_level=rule.access_level.value,
        is_active=rule.is_active,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


@router.delete("/sharing-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sharing_rule(
    rule_id: int,
    user: AuthUser = Depends(require_permission("core:system:admin")),
):
    """
    Delete a sharing rule.

    Requires: admin role
    """
    rbac = get_rbac_client()

    success = await rbac.delete_sharing_rule(rule_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete sharing rule",
        )

    logger.info(f"[ADMIN] Sharing rule deleted: {rule_id} by {user.email}")
