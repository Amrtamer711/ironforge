"""
RBAC (Role-Based Access Control) API endpoints.

Handles permission checking and RBAC context retrieval.
"""

from fastapi import APIRouter, Depends, Query

from api.dependencies import require_service_auth
from core import rbac_service
from models import (
    PermissionCheckRequest,
    PermissionCheckResponse,
    UserRBACResponse,
)

router = APIRouter(prefix="/api/rbac", tags=["rbac"])


@router.get("/user-context/{user_id}", response_model=UserRBACResponse)
async def get_user_context(
    user_id: str,
    service: str = Depends(require_service_auth),
):
    """
    Get full 5-level RBAC context for a user.

    Returns complete RBAC data including:
    - Level 1: Profile (base role)
    - Level 2: Permission Sets (additional permissions)
    - Level 3: Teams & Hierarchy (manager/subordinates)
    - Level 4: Sharing Rules (record-level access)
    - Level 5: Companies (multi-tenant isolation)

    This data is used by unified-ui to inject X-Trusted-User-* headers.
    """
    context = rbac_service.get_user_context(user_id)

    if not context:
        return UserRBACResponse(
            user_id=user_id,
            found=False,
        )

    return UserRBACResponse(
        user_id=user_id,
        found=True,
        profile=context.get("profile"),
        permissions=context.get("permissions", []),
        permission_sets=context.get("permission_sets", []),
        teams=context.get("teams", []),
        team_ids=context.get("team_ids", []),
        manager_id=context.get("manager_id"),
        subordinate_ids=context.get("subordinate_ids", []),
        sharing_rules=context.get("sharing_rules", []),
        shared_records=context.get("shared_records", {}),
        shared_from_user_ids=context.get("shared_from_user_ids", []),
        companies=context.get("companies", []),
    )


@router.post("/check-permission", response_model=PermissionCheckResponse)
async def check_permission(
    request: PermissionCheckRequest,
    service: str = Depends(require_service_auth),
):
    """
    Check if a user has a specific permission.

    Supports wildcard permissions:
    - "*:*:*" matches everything
    - "sales:*:*" matches all sales permissions
    - "sales:proposals:*" matches all proposal actions
    - "manage" action implies all other actions

    Returns:
        PermissionCheckResponse with:
        - allowed: Whether the permission is granted
        - matched_by: The permission that granted access (if allowed)
    """
    result = rbac_service.check_permission(
        user_id=request.user_id,
        permission=request.permission,
    )

    return PermissionCheckResponse(
        allowed=result.get("allowed", False),
        matched_by=result.get("matched_by"),
    )


@router.post("/check-record-access")
async def check_record_access(
    user_id: str,
    object_type: str,
    record_id: str,
    record_owner_id: str | None = None,
    service: str = Depends(require_service_auth),
):
    """
    Check if a user can access a specific record.

    Uses the 5-level RBAC model:
    1. Admin access (system_admin profile)
    2. Own record (user is the owner)
    3. Subordinate access (manager viewing subordinate's record)
    4. Sharing rules (explicit record/object sharing)
    5. Team access (same team membership)

    Returns:
        {
            "allowed": bool,
            "reason": Reason for access decision
        }
    """
    result = rbac_service.check_record_access(
        user_id=user_id,
        object_type=object_type,
        record_id=record_id,
        record_owner_id=record_owner_id,
    )

    return result


@router.get("/accessible-user-ids/{user_id}")
async def get_accessible_user_ids(
    user_id: str,
    service: str = Depends(require_service_auth),
):
    """
    Get list of user IDs that the given user can access data for.

    Used for filtering queries to show only accessible records.

    Returns:
        {
            "user_ids": List of user IDs, or null if admin (access to all)
        }
    """
    user_ids = rbac_service.get_accessible_user_ids(user_id)

    return {
        "user_ids": user_ids,
        "is_admin": user_ids is None,
    }


@router.post("/check-company-access")
async def check_company_access(
    user_id: str,
    company: str,
    service: str = Depends(require_service_auth),
):
    """
    Check if a user can access a specific company schema.

    Returns:
        {
            "allowed": bool,
            "companies": List of user's accessible companies
        }
    """
    return rbac_service.check_company_access(user_id, company)


@router.get("/user-companies/{user_id}")
async def get_user_companies(
    user_id: str,
    service: str = Depends(require_service_auth),
):
    """
    Get list of company schemas a user can access.

    Returns:
        {
            "companies": List of company schema names
        }
    """
    companies = rbac_service.get_user_companies(user_id)

    return {
        "user_id": user_id,
        "companies": companies,
    }
