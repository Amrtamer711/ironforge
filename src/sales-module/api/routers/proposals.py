"""
Proposal endpoints for Unified UI.

All proposal endpoints require authentication.

Access Control (Team-based):
- Users with sales:proposals:manage see ALL proposals
- Managers/team leaders see their own + subordinates' proposals
- Regular users see only their own proposals
"""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

import config
from db.database import db
from crm_security import (
    AuthUser,
    require_auth_user as require_auth,
    has_permission,
    can_access_user_data,
    get_accessible_user_ids,
)

logger = config.logger

router = APIRouter(prefix="/api/proposals", tags=["proposals"])


# =============================================================================
# RESPONSE MODELS
# =============================================================================

class ProposalLocation(BaseModel):
    id: int
    location_key: str
    location_display_name: str | None = None
    start_date: str | None = None
    duration_weeks: int | None = None
    net_rate: float | None = None
    upload_fee: float | None = None
    production_fee: float | None = None


class ProposalResponse(BaseModel):
    id: int
    user_id: str | None = None
    submitted_by: str | None = None
    client_name: str
    date_generated: str
    package_type: str
    total_amount: str | None = None
    currency: str | None = "AED"
    locations: str | None = None  # Legacy comma-separated
    proposal_data: dict | None = None


class ProposalDetailResponse(ProposalResponse):
    proposal_locations: list[ProposalLocation] = []


class ProposalListResponse(BaseModel):
    proposals: list[ProposalResponse]
    total: int
    limit: int
    offset: int


# =============================================================================
# REQUEST MODELS (for create/update endpoints)
# =============================================================================

def _parse_currency_amount(value: str | float | int | None) -> float | None:
    """
    Parse currency amount from string (e.g., "AED 1,250,000") or number.
    Returns float or None.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        # Remove currency codes and formatting: "AED 1,250,000" -> 1250000.0
        cleaned = value.replace(",", "").strip()
        # Remove common currency codes
        for currency in ["AED", "USD", "EUR", "GBP", "SAR", "QAR", "KWD", "BHD", "OMR"]:
            cleaned = cleaned.replace(currency, "").strip()
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _parse_duration_weeks(duration: str | int) -> int:
    """
    Parse duration from string (e.g., "4 Weeks", "2 weeks") or integer.
    Returns integer weeks.
    """
    if isinstance(duration, int):
        return duration
    if isinstance(duration, str):
        # Extract number from strings like "4 Weeks", "2 weeks", "8"
        cleaned = duration.lower().replace("weeks", "").replace("week", "").strip()
        try:
            return int(cleaned)
        except ValueError:
            return 4  # Default to 4 weeks
    return 4


class ProposalLocationInput(BaseModel):
    """
    Input for a single location in a proposal.

    For SEPARATE proposals: use start_dates[], durations[], net_rates[] (parallel arrays)
    For COMBINED proposals: use start_date, duration (singular values per location)
    """
    location: str = Field(..., description="Location key (e.g., 'dubai_gateway')")

    # Separate proposals: arrays (one per pricing option)
    start_dates: list[str] | None = Field(default=None, description="Start dates for each duration option (e.g., ['1st Dec 2025', '1st Dec 2025'])")
    durations: list[str] | None = Field(default=None, description="Duration options (e.g., ['2 Weeks', '4 Weeks'])")
    net_rates: list[str] | None = Field(default=None, description="Net rates for each duration (e.g., ['AED 1,250,000', 'AED 2,300,000'])")

    # Combined proposals: single values per location
    start_date: str | None = Field(default=None, description="Start date for combined proposal (e.g., '1st December 2025')")
    duration: str | int | None = Field(default=None, description="Single duration for combined (e.g., '4 Weeks' or 4)")
    net_rate: float | str | None = Field(default=None, description="Single net rate (float or 'AED X,XXX')")

    # Fees
    upload_fee: float | str | None = Field(default=None, description="Upload fee (optional)")
    production_fee: float | str | None = Field(default=None, description="Production fee for static locations (e.g., 'AED 5,000')")

    # Additional fields
    spots: int = Field(default=1, description="Number of spots (default: 1)")


class ProposalCreateRequest(BaseModel):
    """
    Request body for creating a new proposal.

    Accepts the same format as the LLM tools (get_separate_proposals, get_combined_proposal).
    """
    proposals: list[ProposalLocationInput] = Field(..., min_length=1, description="List of locations")
    client_name: str = Field(..., min_length=1, description="Client name")
    proposal_type: Literal["separate", "combined"] = Field(default="separate", description="Type of proposal")
    combined_net_rate: float | str | None = Field(default=None, description="Combined rate (e.g., 'AED 2,000,000' or 2000000)")
    payment_terms: str | None = Field(default="100% upfront", description="Payment terms")
    currency: str = Field(default="AED", description="Currency code")


class ProposalCreateResponse(BaseModel):
    """Response from proposal creation."""
    success: bool
    proposal_id: int | None = None
    pdf_url: str | None = None
    pptx_url: str | None = None
    locations: str | None = None
    errors: list[str] | None = None


class ProposalUpdateRequest(BaseModel):
    """Request body for updating proposal metadata."""
    client_name: str | None = None
    payment_terms: str | None = None


class ProposalRegenerateRequest(BaseModel):
    """Request body for regenerating a proposal."""
    proposals: list[ProposalLocationInput] | None = Field(default=None, description="Override locations")
    client_name: str | None = Field(default=None, description="Override client name")
    currency: str | None = Field(default=None, description="Override currency")


class ProposalDownloadResponse(BaseModel):
    """Response with download URL."""
    url: str
    filename: str
    expires_at: str


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _validate_location_access(
    location_key: str,
    user_companies: list[str],
) -> tuple[bool, str, str | None]:
    """
    Validate that a location belongs to user's accessible companies.

    Returns:
        Tuple of (is_valid, error_message, company_schema)
    """
    location = db.get_location_by_key(location_key, user_companies)
    if location is None:
        return False, f"Location '{location_key}' not found in your accessible companies.", None
    company_schema = location.get("company_schema") or location.get("company")
    return True, "", company_schema


async def _get_proposal_processor(user_companies: list[str]):
    """Initialize ProposalProcessor with dependencies."""
    from core.proposals import ProposalProcessor
    from core.proposals.validator import ProposalValidator
    from core.proposals.renderer import ProposalRenderer
    from core.proposals.intro_outro import IntroOutroHandler
    from core.services.template_service import TemplateService

    template_service = TemplateService(companies=user_companies)
    validator = ProposalValidator(user_companies)
    renderer = ProposalRenderer()
    # Fetch available locations (async) before creating IntroOutroHandler
    available_locations = await validator._get_available_locations()
    intro_outro = IntroOutroHandler(available_locations)

    return ProposalProcessor(validator, renderer, intro_outro, template_service)


async def _upload_proposal_files(
    result: dict,
    user_id: str,
    client_name: str,
) -> tuple[str | None, str | None]:
    """
    Upload generated proposal files to storage and return signed URLs.

    Returns:
        Tuple of (pdf_url, pptx_url)
    """
    from integrations.storage.client import store_proposal_file

    pdf_url = None
    pptx_url = None

    try:
        # Upload PDF
        pdf_path = result.get("pdf_path") or result.get("merged_pdf_path")
        pdf_filename = result.get("pdf_filename") or result.get("merged_pdf_filename")

        if pdf_path and os.path.exists(pdf_path):
            tracked = await store_proposal_file(
                data=Path(pdf_path),
                filename=pdf_filename or "proposal.pdf",
                user_id=user_id,
                client_name=client_name,
                file_type="proposal_pdf",
            )
            if tracked.success:
                pdf_url = tracked.url
            # Clean up temp file
            try:
                os.unlink(pdf_path)
            except OSError:
                pass

        # Upload PPTX (if single proposal)
        pptx_path = result.get("pptx_path")
        pptx_filename = result.get("pptx_filename")

        if pptx_path and os.path.exists(pptx_path):
            tracked = await store_proposal_file(
                data=Path(pptx_path),
                filename=pptx_filename or "proposal.pptx",
                user_id=user_id,
                client_name=client_name,
                file_type="proposal_pptx",
            )
            if tracked.success:
                pptx_url = tracked.url
            # Clean up temp file
            try:
                os.unlink(pptx_path)
            except OSError:
                pass

        # Clean up individual files for multi-proposal
        for f in result.get("individual_files", []):
            try:
                if f.get("path") and os.path.exists(f["path"]):
                    os.unlink(f["path"])
            except OSError:
                pass

    except Exception as e:
        logger.error(f"[PROPOSALS API] Error uploading files: {e}")

    return pdf_url, pptx_url


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("", response_model=ProposalListResponse)
async def list_proposals(
    limit: int = Query(default=50, le=100, ge=1),
    offset: int = Query(default=0, ge=0),
    client_name: str | None = Query(default=None, description="Filter by client name"),
    user: AuthUser = Depends(require_auth),
):
    """
    List proposals with pagination and filtering.

    Access levels:
    - sales:proposals:manage permission: see ALL proposals
    - Managers/team leaders: see own + subordinates' proposals
    - Regular users: see only own proposals
    """
    try:
        # Check if user can view all proposals (has manage permission)
        can_view_all = has_permission(user.permissions, "sales:proposals:manage")

        if can_view_all:
            # Admin/manager with full access - no filtering
            user_ids = None
        else:
            # Get accessible user IDs (self + subordinates for managers, just self for regular users)
            user_ids = get_accessible_user_ids()
            if user_ids is None:
                # None means admin access - but we already checked can_view_all
                user_ids = None
            elif not user_ids:
                # Empty list - shouldn't happen, but fallback to own
                user_ids = user.id

        proposals = db.get_proposals(
            limit=limit,
            offset=offset,
            user_ids=user_ids,
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


@router.post("", response_model=ProposalCreateResponse)
async def create_proposal(
    request: ProposalCreateRequest,
    user: AuthUser = Depends(require_auth),
):
    """
    Generate a new proposal.

    Requires: sales:proposals:create permission

    The proposal can be:
    - 'separate': Each location gets its own proposal (merged into single PDF)
    - 'combined': All locations bundled into one package with a combined rate
    """
    # Check permission
    if not has_permission(user.permissions, "sales:proposals:create"):
        raise HTTPException(status_code=403, detail="Permission denied: sales:proposals:create required")

    # Get user's companies (same pattern as mockups.py)
    if not user.has_company_access:
        raise HTTPException(
            status_code=403,
            detail="You don't have access to any company data. Contact your administrator."
        )
    user_companies = user.companies

    # Validate combined proposal requirements
    if request.proposal_type == "combined":
        if request.combined_net_rate is None:
            raise HTTPException(
                status_code=400,
                detail="combined_net_rate is required for combined proposals"
            )
        if len(request.proposals) < 2:
            raise HTTPException(
                status_code=400,
                detail="Combined proposals require at least 2 locations"
            )

    # Validate all locations belong to user's companies
    for proposal in request.proposals:
        location_key = proposal.location.strip().lower().replace(" ", "_")
        is_valid, error_msg, _ = _validate_location_access(location_key, user_companies)
        if not is_valid:
            raise HTTPException(status_code=403, detail=error_msg)

    try:
        # Transform request to processor format (handles both LLM and simple formats)
        proposals_data = []
        for p in request.proposals:
            # Build durations array: prefer durations[], fall back to duration
            if p.durations:
                durations = p.durations  # Already in LLM format ["2 Weeks", "4 Weeks"]
            elif p.duration is not None:
                # Convert single duration to array format
                if isinstance(p.duration, int):
                    durations = [f"{p.duration} Weeks"]
                else:
                    durations = [str(p.duration)]
            else:
                durations = ["4 Weeks"]  # Default

            # Build net_rates array: prefer net_rates[], fall back to net_rate
            if p.net_rates:
                net_rates = p.net_rates  # Already in LLM format ["AED 1,250,000"]
            elif p.net_rate is not None:
                # Convert single net_rate to array format with currency
                parsed = _parse_currency_amount(p.net_rate)
                if parsed is not None:
                    net_rates = [f"{request.currency} {parsed:,.0f}"]
                else:
                    net_rates = [str(p.net_rate)]
            else:
                net_rates = []

            proposal_dict = {
                "location": p.location.strip().lower().replace(" ", "_"),
                "durations": durations,
                "net_rates": net_rates,
                "spots": p.spots,
            }

            # Handle start_dates array (separate) vs start_date (combined)
            if p.start_dates:
                # Separate proposals: use start_dates array
                proposal_dict["start_dates"] = p.start_dates
            elif p.start_date:
                # Combined proposals: use single start_date
                proposal_dict["start_date"] = p.start_date
            else:
                # Default: use current date placeholder
                proposal_dict["start_date"] = "1st December 2025"

            # Add fees (parse string amounts)
            if p.upload_fee is not None:
                parsed = _parse_currency_amount(p.upload_fee)
                if parsed is not None:
                    proposal_dict["upload_fee"] = parsed
            if p.production_fee is not None:
                # Keep as string for processor (it expects "AED 5,000" format)
                if isinstance(p.production_fee, str):
                    proposal_dict["production_fee"] = p.production_fee
                else:
                    proposal_dict["production_fee"] = f"{request.currency} {p.production_fee:,.0f}"

            proposals_data.append(proposal_dict)

        # Initialize processor
        processor = await _get_proposal_processor(user_companies)

        # Parse combined_net_rate (keep as string for processor)
        combined_net_rate_str = None
        if request.combined_net_rate is not None:
            if isinstance(request.combined_net_rate, str):
                combined_net_rate_str = request.combined_net_rate
            else:
                combined_net_rate_str = f"{request.currency} {request.combined_net_rate:,.0f}"

        # Generate proposal
        if request.proposal_type == "combined":
            result = await processor.process_combined(
                proposals_data=proposals_data,
                combined_net_rate=combined_net_rate_str,
                submitted_by=user.id,
                client_name=request.client_name,
                payment_terms=request.payment_terms or "100% upfront",
                currency=request.currency,
            )
        else:
            result = await processor.process_separate(
                proposals_data=proposals_data,
                submitted_by=user.id,
                client_name=request.client_name,
                currency=request.currency,
            )

        if not result.get("success"):
            errors = result.get("errors") or [result.get("error", "Unknown error")]
            return ProposalCreateResponse(success=False, errors=errors)

        # Upload files to storage
        pdf_url, pptx_url = await _upload_proposal_files(result, user.id, request.client_name)

        # Get locations string
        locations_str = result.get("locations") or result.get("location", "")

        return ProposalCreateResponse(
            success=True,
            pdf_url=pdf_url,
            pptx_url=pptx_url,
            locations=locations_str,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PROPOSALS API] Error creating proposal: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate proposal")


@router.get("/history")
async def get_proposals_history(user: AuthUser = Depends(require_auth)):
    """
    Get proposal generation history for the authenticated user.

    Access levels same as list_proposals.

    DEPRECATED: Use GET /api/proposals instead.
    """
    try:
        can_view_all = has_permission(user.permissions, "sales:proposals:manage")

        if can_view_all:
            user_ids = None
        else:
            user_ids = get_accessible_user_ids()
            if user_ids is None:
                user_ids = None
            elif not user_ids:
                user_ids = user.id

        proposals = db.get_proposals(limit=20, user_ids=user_ids)
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

    Access: own proposals, subordinates' proposals (for managers), or sales:proposals:manage permission.
    """
    try:
        proposal = db.get_proposal_by_id(proposal_id)

        if not proposal:
            raise HTTPException(status_code=404, detail="Proposal not found")

        proposal_owner = proposal.get("user_id") or proposal.get("submitted_by")

        # Check access: manage permission OR can access this user's data (self/subordinate)
        can_view_all = has_permission(user.permissions, "sales:proposals:manage")
        can_access = can_view_all or can_access_user_data(proposal_owner)

        if not can_access:
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

    Access: own proposals, subordinates' proposals (for managers), or sales:proposals:delete permission.
    """
    try:
        proposal = db.get_proposal_by_id(proposal_id)

        if not proposal:
            raise HTTPException(status_code=404, detail="Proposal not found")

        proposal_owner = proposal.get("user_id") or proposal.get("submitted_by")

        # Check access: delete permission OR can access this user's data (self/subordinate)
        can_delete_all = has_permission(user.permissions, "sales:proposals:delete")
        can_access = can_delete_all or can_access_user_data(proposal_owner)

        if not can_access:
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


@router.get("/{proposal_id}/locations", response_model=list[ProposalLocation])
async def get_proposal_locations(
    proposal_id: int,
    user: AuthUser = Depends(require_auth),
):
    """
    Get locations for a specific proposal.

    Access: own proposals, subordinates' proposals (for managers), or sales:proposals:manage permission.
    """
    try:
        proposal = db.get_proposal_by_id(proposal_id)

        if not proposal:
            raise HTTPException(status_code=404, detail="Proposal not found")

        proposal_owner = proposal.get("user_id") or proposal.get("submitted_by")

        # Check access: manage permission OR can access this user's data (self/subordinate)
        can_view_all = has_permission(user.permissions, "sales:proposals:manage")
        can_access = can_view_all or can_access_user_data(proposal_owner)

        if not can_access:
            raise HTTPException(status_code=403, detail="Not authorized to view this proposal")

        locations = db.get_proposal_locations(proposal_id)
        return locations
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PROPOSALS API] Error getting locations for proposal {proposal_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get proposal locations")


@router.put("/{proposal_id}")
async def update_proposal(
    proposal_id: int,
    request: ProposalUpdateRequest,
    user: AuthUser = Depends(require_auth),
):
    """
    Update a proposal's metadata.

    Access: own proposals, subordinates' proposals (for managers), or sales:proposals:manage permission.

    Note: This only updates metadata (client_name, payment_terms). To regenerate
    the actual proposal files, use POST /{proposal_id}/regenerate.
    """
    try:
        proposal = db.get_proposal_by_id(proposal_id)

        if not proposal:
            raise HTTPException(status_code=404, detail="Proposal not found")

        proposal_owner = proposal.get("user_id") or proposal.get("submitted_by")

        # Check access
        can_manage = has_permission(user.permissions, "sales:proposals:manage")
        can_access = can_manage or can_access_user_data(proposal_owner)

        if not can_access:
            raise HTTPException(status_code=403, detail="Not authorized to update this proposal")

        # Build update data
        update_data = {}
        if request.client_name is not None:
            update_data["client_name"] = request.client_name

        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        # Update in database
        success = db.update_proposal(proposal_id, update_data)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to update proposal")

        return {"message": "Proposal updated successfully", "id": proposal_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PROPOSALS API] Error updating proposal {proposal_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update proposal")


@router.post("/{proposal_id}/regenerate", response_model=ProposalCreateResponse)
async def regenerate_proposal(
    proposal_id: int,
    request: ProposalRegenerateRequest,
    user: AuthUser = Depends(require_auth),
):
    """
    Regenerate a proposal with updated parameters.

    Access: own proposals, subordinates' proposals (for managers), or sales:proposals:manage permission.

    You can override:
    - proposals: New location data
    - client_name: New client name
    - currency: New currency
    """
    try:
        proposal = db.get_proposal_by_id(proposal_id)

        if not proposal:
            raise HTTPException(status_code=404, detail="Proposal not found")

        proposal_owner = proposal.get("user_id") or proposal.get("submitted_by")

        # Check access
        can_manage = has_permission(user.permissions, "sales:proposals:manage")
        can_access = can_manage or can_access_user_data(proposal_owner)

        if not can_access:
            raise HTTPException(status_code=403, detail="Not authorized to regenerate this proposal")

        # Get user's companies for location validation (same pattern as mockups.py)
        if not user.has_company_access:
            raise HTTPException(
                status_code=403,
                detail="You don't have access to any company data."
            )
        user_companies = user.companies

        # Get existing locations if not overriding
        currency = request.currency or proposal.get("currency", "AED")

        if request.proposals:
            # Validate new locations
            for p in request.proposals:
                location_key = p.location.strip().lower().replace(" ", "_")
                is_valid, error_msg, _ = _validate_location_access(location_key, user_companies)
                if not is_valid:
                    raise HTTPException(status_code=403, detail=error_msg)

            proposals_data = []
            for p in request.proposals:
                # Build durations array: prefer durations[], fall back to duration
                if p.durations:
                    durations = p.durations
                elif p.duration is not None:
                    if isinstance(p.duration, int):
                        durations = [f"{p.duration} Weeks"]
                    else:
                        durations = [str(p.duration)]
                else:
                    durations = ["4 Weeks"]

                # Build net_rates array: prefer net_rates[], fall back to net_rate
                if p.net_rates:
                    net_rates = p.net_rates
                elif p.net_rate is not None:
                    parsed = _parse_currency_amount(p.net_rate)
                    if parsed is not None:
                        net_rates = [f"{currency} {parsed:,.0f}"]
                    else:
                        net_rates = [str(p.net_rate)]
                else:
                    net_rates = []

                proposal_dict = {
                    "location": p.location.strip().lower().replace(" ", "_"),
                    "durations": durations,
                    "net_rates": net_rates,
                    "spots": p.spots,
                }

                # Handle start_dates array (separate) vs start_date (combined)
                if p.start_dates:
                    proposal_dict["start_dates"] = p.start_dates
                elif p.start_date:
                    proposal_dict["start_date"] = p.start_date
                else:
                    proposal_dict["start_date"] = "1st December 2025"

                if p.upload_fee is not None:
                    parsed = _parse_currency_amount(p.upload_fee)
                    if parsed is not None:
                        proposal_dict["upload_fee"] = parsed
                if p.production_fee is not None:
                    if isinstance(p.production_fee, str):
                        proposal_dict["production_fee"] = p.production_fee
                    else:
                        proposal_dict["production_fee"] = f"{currency} {p.production_fee:,.0f}"
                proposals_data.append(proposal_dict)
        else:
            # Use existing locations from proposal
            existing_locations = db.get_proposal_locations(proposal_id)
            if not existing_locations:
                raise HTTPException(
                    status_code=400,
                    detail="No locations found for proposal. Please provide new locations."
                )
            proposals_data = []
            for loc in existing_locations:
                proposals_data.append({
                    "location": loc.get("location_key", ""),
                    "start_date": loc.get("start_date", ""),
                    "durations": [loc.get("duration_weeks", 4)],
                    "net_rates": [str(loc.get("net_rate", 0))],
                })

        # Get other parameters
        client_name = request.client_name or proposal.get("client_name", "Unknown Client")
        currency = request.currency or proposal.get("currency", "AED")
        package_type = proposal.get("package_type", "separate")

        # Initialize processor
        processor = await _get_proposal_processor(user_companies)

        # Regenerate proposal
        if package_type == "combined":
            # For combined, we need a net rate - use from proposal data
            proposal_data = proposal.get("proposal_data") or {}
            combined_net_rate = proposal_data.get("combined_net_rate", "0")
            result = await processor.process_combined(
                proposals_data=proposals_data,
                combined_net_rate=str(combined_net_rate),
                submitted_by=user.id,
                client_name=client_name,
                payment_terms=proposal_data.get("payment_terms", "100% upfront"),
                currency=currency,
            )
        else:
            result = await processor.process_separate(
                proposals_data=proposals_data,
                submitted_by=user.id,
                client_name=client_name,
                currency=currency,
            )

        if not result.get("success"):
            errors = result.get("errors") or [result.get("error", "Unknown error")]
            return ProposalCreateResponse(success=False, errors=errors)

        # Upload files to storage
        pdf_url, pptx_url = await _upload_proposal_files(result, user.id, client_name)

        # Get locations string
        locations_str = result.get("locations") or result.get("location", "")

        return ProposalCreateResponse(
            success=True,
            proposal_id=proposal_id,
            pdf_url=pdf_url,
            pptx_url=pptx_url,
            locations=locations_str,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PROPOSALS API] Error regenerating proposal {proposal_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to regenerate proposal")


@router.get("/{proposal_id}/download", response_model=ProposalDownloadResponse)
async def download_proposal(
    proposal_id: int,
    format: Literal["pdf", "pptx"] = Query(default="pdf", description="File format"),
    user: AuthUser = Depends(require_auth),
):
    """
    Get a signed download URL for a proposal file.

    Access: own proposals, subordinates' proposals (for managers), or sales:proposals:read permission.

    Returns a signed URL that expires in 1 hour.
    """
    try:
        proposal = db.get_proposal_by_id(proposal_id)

        if not proposal:
            raise HTTPException(status_code=404, detail="Proposal not found")

        proposal_owner = proposal.get("user_id") or proposal.get("submitted_by")

        # Check access
        can_read = has_permission(user.permissions, "sales:proposals:read")
        can_manage = has_permission(user.permissions, "sales:proposals:manage")
        can_access = can_read or can_manage or can_access_user_data(proposal_owner)

        if not can_access:
            raise HTTPException(status_code=403, detail="Not authorized to download this proposal")

        # Get file info from proposal_files table
        from integrations.storage.client import get_storage_client

        storage = get_storage_client()
        client = db._get_client()

        # Look for proposal files
        file_type = f"proposal_{format}"
        response = client.table("proposal_files").select("*").eq(
            "proposal_id", proposal_id
        ).ilike(
            "original_filename", f"%.{format}"
        ).order(
            "created_at", desc=True
        ).limit(1).execute()

        if not response.data:
            # Try without proposal_id filter (older proposals might not have it)
            client_name = proposal.get("client_name", "").replace(" ", "_")
            response = client.table("proposal_files").select("*").ilike(
                "client_name", f"%{client_name}%"
            ).ilike(
                "original_filename", f"%.{format}"
            ).order(
                "created_at", desc=True
            ).limit(1).execute()

        if not response.data:
            raise HTTPException(
                status_code=404,
                detail=f"No {format.upper()} file found for this proposal"
            )

        file_record = response.data[0]
        bucket = file_record.get("storage_bucket")
        key = file_record.get("storage_key")
        filename = file_record.get("original_filename", f"proposal.{format}")

        if not bucket or not key:
            raise HTTPException(
                status_code=404,
                detail="File storage information not found"
            )

        # Generate signed URL (1 hour expiry)
        signed_url = await storage.get_signed_url(bucket, key, expires_in=3600)

        if not signed_url:
            raise HTTPException(
                status_code=500,
                detail="Failed to generate download URL"
            )

        # Calculate expiration time
        uae_tz = timezone(timedelta(hours=4))
        expires_at = datetime.now(uae_tz) + timedelta(hours=1)

        return ProposalDownloadResponse(
            url=signed_url,
            filename=filename,
            expires_at=expires_at.isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PROPOSALS API] Error downloading proposal {proposal_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get download URL")
