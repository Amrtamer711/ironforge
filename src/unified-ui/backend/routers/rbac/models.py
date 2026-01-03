"""
Shared Pydantic models for RBAC endpoints.
"""


from pydantic import BaseModel

# =============================================================================
# PROFILE MODELS
# =============================================================================

class CreateProfileRequest(BaseModel):
    name: str
    display_name: str
    description: str | None = None
    permissions: list[str] | None = None


class UpdateProfileRequest(BaseModel):
    display_name: str | None = None
    description: str | None = None
    permissions: list[str] | None = None


# =============================================================================
# PERMISSION SET MODELS
# =============================================================================

class CreatePermissionSetRequest(BaseModel):
    name: str
    display_name: str
    description: str | None = None
    permissions: list[str] | None = None


class UpdatePermissionSetRequest(BaseModel):
    display_name: str | None = None
    description: str | None = None
    is_active: bool | None = None
    permissions: list[str] | None = None


class AssignPermissionSetRequest(BaseModel):
    permission_set_id: int
    expires_at: str | None = None


# =============================================================================
# TEAM MODELS
# =============================================================================

class CreateTeamRequest(BaseModel):
    name: str
    display_name: str | None = None
    description: str | None = None
    parent_team_id: int | None = None


class UpdateTeamRequest(BaseModel):
    name: str | None = None
    display_name: str | None = None
    description: str | None = None
    parent_team_id: int | None = None
    is_active: bool | None = None


class AddTeamMemberRequest(BaseModel):
    user_id: str
    role: str | None = "member"


class UpdateTeamMemberRequest(BaseModel):
    role: str


class SetManagerRequest(BaseModel):
    manager_id: str | None = None


# =============================================================================
# SHARING MODELS
# =============================================================================

class CreateSharingRuleRequest(BaseModel):
    name: str
    description: str | None = None
    object_type: str
    share_from_type: str
    share_from_id: str | None = None
    share_to_type: str
    share_to_id: str | None = None
    access_level: str


class UpdateSharingRuleRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    share_from_type: str | None = None
    share_from_id: str | None = None
    share_to_type: str | None = None
    share_to_id: str | None = None
    access_level: str | None = None
    is_active: bool | None = None


class CreateShareRequest(BaseModel):
    object_type: str
    record_id: str
    shared_with_user_id: str | None = None
    shared_with_team_id: int | None = None
    access_level: str | None = "read"
    expires_at: str | None = None
    reason: str | None = None


class UpdateRecordShareRequest(BaseModel):
    access_level: str | None = None
    expires_at: str | None = None


# =============================================================================
# USER MODELS
# =============================================================================

class UpdateUserRequest(BaseModel):
    name: str | None = None
    avatar_url: str | None = None
    is_active: bool | None = None
    profile_id: int | None = None
    profile_name: str | None = None


class AssignUserProfileRequest(BaseModel):
    profile_name: str
