"""
Mockup Frames API Router.

Provides access to mockup frame data stored in the database.
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

import config
from db.database import db

logger = logging.getLogger("asset-management")

router = APIRouter(
    prefix="/api/mockup-frames",
    tags=["mockup-frames"],
)


class MockupFrameInfo(BaseModel):
    """Mockup frame info."""
    location_key: str
    time_of_day: str
    finish: str
    photo_filename: str
    frames_data: list[dict[str, Any]]
    config: dict[str, Any] | None = None


class MockupFrameDetail(BaseModel):
    """Detailed mockup frame response."""
    location_key: str
    time_of_day: str
    finish: str
    photo_filename: str
    frames_data: list[dict[str, Any]]
    config: dict[str, Any] | None = None


# =============================================================================
# MOCKUP FRAMES
# =============================================================================


@router.get("/{company}/{location_key}", response_model=list[MockupFrameInfo])
async def list_mockup_frames(company: str, location_key: str) -> list[dict[str, Any]]:
    """
    List all mockup frames for a location.

    Args:
        company: Company schema (e.g., "backlite_dubai")
        location_key: Location identifier

    Returns:
        List of mockup frame info dicts
    """
    logger.info(f"[MOCKUP_FRAMES] Listing frames for {company}/{location_key}")

    try:
        frames = db.list_mockup_frames(location_key, company)
        logger.info(f"[MOCKUP_FRAMES] Found {len(frames)} frames")
        return frames

    except Exception as e:
        logger.error(f"[MOCKUP_FRAMES] Failed to list frames: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{company}/{location_key}/frame", response_model=MockupFrameDetail | None)
async def get_mockup_frame(
    company: str,
    location_key: str,
    time_of_day: str = Query(default="day"),
    finish: str = Query(default="gold"),
    photo_filename: str | None = Query(default=None),
) -> dict[str, Any] | None:
    """
    Get specific mockup frame data.

    If photo_filename is not specified, returns the first matching frame.

    Args:
        company: Company schema
        location_key: Location identifier
        time_of_day: "day" or "night"
        finish: "gold", "silver", or "black"
        photo_filename: Specific photo (optional)

    Returns:
        Mockup frame data or None if not found
    """
    logger.info(
        f"[MOCKUP_FRAMES] Getting frame for {company}/{location_key} "
        f"({time_of_day}/{finish}/{photo_filename or 'any'})"
    )

    try:
        frame = db.get_mockup_frame(
            location_key=location_key,
            company=company,
            time_of_day=time_of_day,
            finish=finish,
            photo_filename=photo_filename,
        )

        if not frame:
            return None

        return frame

    except Exception as e:
        logger.error(f"[MOCKUP_FRAMES] Failed to get frame: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class DeleteResponse(BaseModel):
    """Response for delete operations."""
    success: bool
    message: str


@router.delete("/{company}/{location_key}", response_model=DeleteResponse)
async def delete_mockup_frame(
    company: str,
    location_key: str,
    photo_filename: str = Query(..., description="Photo filename to delete"),
    time_of_day: str = Query(default="day"),
    finish: str = Query(default="gold"),
) -> dict[str, Any]:
    """
    Delete a mockup frame.

    Args:
        company: Company schema
        location_key: Location identifier
        photo_filename: Photo filename to delete
        time_of_day: "day" or "night"
        finish: "gold", "silver", or "black"

    Returns:
        Delete result
    """
    logger.info(
        f"[MOCKUP_FRAMES] Deleting frame for {company}/{location_key} "
        f"({time_of_day}/{finish}/{photo_filename})"
    )

    try:
        success = db.delete_mockup_frame(
            location_key=location_key,
            company=company,
            photo_filename=photo_filename,
            time_of_day=time_of_day,
            finish=finish,
        )

        if success:
            return {
                "success": True,
                "message": f"Deleted frame {photo_filename} for {location_key}",
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to delete frame")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[MOCKUP_FRAMES] Failed to delete frame: {e}")
        raise HTTPException(status_code=500, detail=str(e))