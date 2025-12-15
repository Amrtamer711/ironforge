"""
Shared Pydantic models for RBAC endpoints.
"""

from typing import List, Optional
from pydantic import BaseModel


# =============================================================================
# PROFILE MODELS
# =============================================================================

class CreateProfileRequest(BaseModel):
    name: str
    display_name: str
    description: Optional[str] = None
    permissions: Optional[List[str]] = None


class UpdateProfileRequest(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    permissions: Optional[List[str]] = None


# =============================================================================
# PERMISSION SET MODELS
# =============================================================================

class CreatePermissionSetRequest(BaseModel):
    name: str
    display_name: str
    description: Optional[str] = None
    permissions: Optional[List[str]] = None


class UpdatePermissionSetRequest(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    permissions: Optional[List[str]] = None


class AssignPermissionSetRequest(BaseModel):
    permission_set_id: int
    expires_at: Optional[str] = None


# =============================================================================
# TEAM MODELS
# =============================================================================

class CreateTeamRequest(BaseModel):
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    parent_team_id: Optional[int] = None


class UpdateTeamRequest(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    parent_team_id: Optional[int] = None
    is_active: Optional[bool] = None


class AddTeamMemberRequest(BaseModel):
    user_id: str
    role: Optional[str] = "member"


class UpdateTeamMemberRequest(BaseModel):
    role: str


class SetManagerRequest(BaseModel):
    manager_id: Optional[str] = None


# =============================================================================
# SHARING MODELS
# =============================================================================

class CreateSharingRuleRequest(BaseModel):
    name: str
    description: Optional[str] = None
    object_type: str
    share_from_type: str
    share_from_id: Optional[str] = None
    share_to_type: str
    share_to_id: Optional[str] = None
    access_level: str


class UpdateSharingRuleRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    share_from_type: Optional[str] = None
    share_from_id: Optional[str] = None
    share_to_type: Optional[str] = None
    share_to_id: Optional[str] = None
    access_level: Optional[str] = None
    is_active: Optional[bool] = None


class CreateShareRequest(BaseModel):
    object_type: str
    record_id: str
    shared_with_user_id: Optional[str] = None
    shared_with_team_id: Optional[int] = None
    access_level: Optional[str] = "read"
    expires_at: Optional[str] = None
    reason: Optional[str] = None


class UpdateRecordShareRequest(BaseModel):
    access_level: Optional[str] = None
    expires_at: Optional[str] = None


# =============================================================================
# USER MODELS
# =============================================================================

class UpdateUserRequest(BaseModel):
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: Optional[bool] = None
    profile_id: Optional[int] = None
    profile_name: Optional[str] = None
