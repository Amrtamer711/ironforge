"""
AI cost tracking endpoints.

Cost endpoints require authentication, with admin role required for
sensitive operations like clearing costs.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app_settings import settings
from db.database import db
from api.auth import require_auth, require_any_role
from api.schemas import CallType, Workflow
from integrations.auth import AuthUser
from integrations.rbac import get_rbac_client
from utils.time import get_uae_time
from utils.logging import get_logger

router = APIRouter(prefix="/costs", tags=["costs"])
logger = get_logger("api.costs")


@router.get("")
async def get_costs(
    user: AuthUser = Depends(require_auth),
    start_date: Optional[str] = Query(
        None,
        description="Start date (YYYY-MM-DD format)",
        pattern=r"^\d{4}-\d{2}-\d{2}$"
    ),
    end_date: Optional[str] = Query(
        None,
        description="End date (YYYY-MM-DD format)",
        pattern=r"^\d{4}-\d{2}-\d{2}$"
    ),
    call_type: Optional[CallType] = Query(None, description="Filter by call type"),
    workflow: Optional[Workflow] = Query(None, description="Filter by workflow"),
    filter_user_id: Optional[str] = Query(None, max_length=100, description="Filter by user ID (admin only)")
):
    """
    Get AI costs summary with optional filters.

    Requires authentication. Non-admin users can only see their own costs.
    """
    logger.info(f"[COSTS] Get costs request from {user.email}, filters: start={start_date}, end={end_date}, type={call_type}, workflow={workflow}")

    # Non-admins can only see their own costs
    rbac = get_rbac_client()
    is_admin = await rbac.has_role(user.id, "admin")
    logger.debug(f"[COSTS] User {user.email} is_admin: {is_admin}")

    # If filter_user_id is provided but user is not admin, reject
    if filter_user_id and not is_admin:
        logger.warning(f"[COSTS] Non-admin {user.email} attempted to filter by user_id")
        raise HTTPException(
            status_code=403,
            detail="Only admins can filter by user_id"
        )

    # Admins can see any user's costs, non-admins only see their own
    effective_user_id = filter_user_id if (filter_user_id and is_admin) else (None if is_admin else user.id)

    # Convert enums to string values for database query
    call_type_str = call_type.value if call_type else None
    workflow_str = workflow.value if workflow else None

    summary = db.get_ai_costs_summary(
        start_date=start_date,
        end_date=end_date,
        call_type=call_type_str,
        workflow=workflow_str,
        user_id=effective_user_id
    )

    logger.info(f"[COSTS] Returned costs summary for {user.email}: total_cost=${summary.get('total_cost', 0):.4f}")

    return {
        "summary": summary,
        "filters": {
            "start_date": start_date,
            "end_date": end_date,
            "call_type": call_type_str,
            "workflow": workflow_str,
            "user_id": effective_user_id
        },
        "timestamp": get_uae_time().isoformat()
    }


@router.delete("/clear")
async def clear_costs(
    user: AuthUser = Depends(require_any_role("admin")),
    auth_code: Optional[str] = Query(None, min_length=1, max_length=100, description="Authorization code")
):
    """
    Clear all AI cost tracking data (useful for testing/resetting).
    WARNING: This will delete all cost history!

    Requires admin role AND authentication code in query parameter:
    DELETE /costs/clear?auth_code=YOUR_CODE
    """
    logger.warning(f"[COSTS] CLEAR COSTS REQUEST from admin {user.email}")

    # Check authentication code as additional safety
    required_code = settings.costs_clear_auth_code or "nour2024"
    if not auth_code or auth_code != required_code:
        logger.error(f"[COSTS] CLEAR COSTS REJECTED - Invalid auth code from {user.email}")
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Invalid or missing authentication code"
        )

    logger.warning(f"[COSTS] !!! CLEARING ALL COST DATA !!! Initiated by {user.email}")
    db.clear_ai_costs()
    logger.warning(f"[COSTS] All cost data cleared by {user.email} at {get_uae_time().isoformat()}")

    return {
        "status": "success",
        "message": "All AI cost data cleared",
        "cleared_by": user.email,
        "timestamp": get_uae_time().isoformat()
    }
