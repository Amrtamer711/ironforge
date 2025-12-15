"""
Proposal endpoints for Unified UI.

All proposal endpoints require authentication.
"""

from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from db.database import db
from api.auth import require_auth, require_profile
from integrations.auth import AuthUser
from integrations.rbac import get_rbac_client, has_permission
import config

logger = config.logger

router = APIRouter(prefix="/api/proposals", tags=["proposals"])


# =============================================================================
# RESPONSE MODELS
# =============================================================================

class ProposalLocation(BaseModel):
    id: int
    location_key: str
    location_display_name: Optional[str] = None
    start_date: Optional[str] = None
    duration_weeks: Optional[int] = None
    net_rate: Optional[float] = None
    upload_fee: Optional[float] = None
    production_fee: Optional[float] = None


class ProposalResponse(BaseModel):
    id: int
    user_id: Optional[str] = None
    submitted_by: Optional[str] = None
    client_name: str
    date_generated: str
    package_type: str
    total_amount: Optional[str] = None
    currency: Optional[str] = "AED"
    locations: Optional[str] = None  # Legacy comma-separated
    proposal_data: Optional[dict] = None


class ProposalDetailResponse(ProposalResponse):
    proposal_locations: List[ProposalLocation] = []


class ProposalListResponse(BaseModel):
    proposals: List[ProposalResponse]
    total: int
    limit: int
    offset: int


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("", response_model=ProposalListResponse)
async def list_proposals(
    limit: int = Query(default=50, le=100, ge=1),
    offset: int = Query(default=0, ge=0),
    client_name: Optional[str] = Query(default=None, description="Filter by client name"),
    user: AuthUser = Depends(require_auth),
):
    """
    List proposals with pagination and filtering.

    Regular users see only their own proposals.
    Users with sales:proposals:manage permission can see all proposals.
    """
    try:
        # Check if user can view all proposals (has manage permission)
        can_view_all = await has_permission(user.id, "sales:proposals:manage")

        # Filter by user_id unless user has manage permission
        user_filter = None if can_view_all else user.id

        proposals = db.get_proposals(
            limit=limit,
            offset=offset,
            user_id=user_filter,
            client_name=client_name,
        )

        return ProposalListResponse(
            proposals=proposals,
            total=len(proposals),  # TODO: Add proper count query
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        logger.error(f"[PROPOSALS API] Error listing proposals: {e}")
        raise HTTPException(status_code=500, detail="Failed to list proposals")


@router.get("/history")
async def get_proposals_history(user: AuthUser = Depends(require_auth)):
    """
    Get proposal generation history for the authenticated user.

    Returns proposals owned by the user. Users with manage permission can see all.

    DEPRECATED: Use GET /api/proposals instead.
    """
    try:
        can_view_all = await has_permission(user.id, "sales:proposals:manage")
        user_filter = None if can_view_all else user.id

        proposals = db.get_proposals(limit=20, user_id=user_filter)
        return proposals
    except Exception as e:
        logger.error(f"[PROPOSALS API] Error getting history: {e}")
        return []


@router.get("/{proposal_id}", response_model=ProposalDetailResponse)
async def get_proposal(
    proposal_id: int,
    user: AuthUser = Depends(require_auth),
):
    """
    Get a single proposal by ID with its locations.

    Users can only view their own proposals unless they have manage permission.
    """
    try:
        proposal = db.get_proposal_by_id(proposal_id)

        if not proposal:
            raise HTTPException(status_code=404, detail="Proposal not found")

        # Check ownership unless user has manage permission
        can_view_all = await has_permission(user.id, "sales:proposals:manage")
        proposal_owner = proposal.get("user_id") or proposal.get("submitted_by")

        if not can_view_all and proposal_owner != user.id:
            raise HTTPException(status_code=403, detail="Not authorized to view this proposal")

        # Get locations
        locations = db.get_proposal_locations(proposal_id)

        return ProposalDetailResponse(
            **proposal,
            proposal_locations=locations,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PROPOSALS API] Error getting proposal {proposal_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get proposal")


@router.delete("/{proposal_id}")
async def delete_proposal(
    proposal_id: int,
    user: AuthUser = Depends(require_auth),
):
    """
    Delete a proposal by ID.

    Users can only delete their own proposals unless they have delete permission.
    """
    try:
        proposal = db.get_proposal_by_id(proposal_id)

        if not proposal:
            raise HTTPException(status_code=404, detail="Proposal not found")

        # Check ownership unless user has delete permission
        can_delete_all = await has_permission(user.id, "sales:proposals:delete")
        proposal_owner = proposal.get("user_id") or proposal.get("submitted_by")

        if not can_delete_all and proposal_owner != user.id:
            raise HTTPException(status_code=403, detail="Not authorized to delete this proposal")

        success = db.delete_proposal(proposal_id)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete proposal")

        return {"message": "Proposal deleted successfully", "id": proposal_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PROPOSALS API] Error deleting proposal {proposal_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete proposal")


@router.get("/{proposal_id}/locations", response_model=List[ProposalLocation])
async def get_proposal_locations(
    proposal_id: int,
    user: AuthUser = Depends(require_auth),
):
    """
    Get locations for a specific proposal.

    Users can only view their own proposal locations unless they have manage permission.
    """
    try:
        proposal = db.get_proposal_by_id(proposal_id)

        if not proposal:
            raise HTTPException(status_code=404, detail="Proposal not found")

        # Check ownership unless user has manage permission
        can_view_all = await has_permission(user.id, "sales:proposals:manage")
        proposal_owner = proposal.get("user_id") or proposal.get("submitted_by")

        if not can_view_all and proposal_owner != user.id:
            raise HTTPException(status_code=403, detail="Not authorized to view this proposal")

        locations = db.get_proposal_locations(proposal_id)
        return locations
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PROPOSALS API] Error getting locations for proposal {proposal_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get proposal locations")
