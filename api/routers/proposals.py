"""
Proposal history endpoints for Unified UI.

All proposal endpoints require authentication.
"""

from typing import Optional

from fastapi import APIRouter, Depends

from db.database import db
from api.auth import require_auth
from integrations.auth import AuthUser
import config

logger = config.logger

router = APIRouter(prefix="/api/proposals", tags=["proposals"])


@router.get("/history")
async def get_proposals_history(user: AuthUser = Depends(require_auth)):
    """
    Get proposal generation history for the authenticated user.

    Returns proposals owned by the user. Admins can see all proposals.
    """
    try:
        # Get proposals for this user
        # TODO: Check if user is admin to show all proposals
        proposals = db.get_recent_proposals(limit=20, user_id=user.id)
        return proposals
    except Exception as e:
        logger.error(f"[PROPOSALS API] Error getting history: {e}")
        return []
