"""
Mockup Frames API Router.

Provides access to mockup frame data stored in the database.
Handles mockup frame CRUD operations and photo storage.
"""

import json
import logging
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
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


class SaveResponse(BaseModel):
    """Response for save operations."""
    success: bool
    photo_filename: str
    location_key: str
    time_of_day: str
    finish: str
    frames_count: int
    storage_url: str | None = None


@router.post("/{company}/{location_key}", response_model=SaveResponse)
async def save_mockup_frame(
    company: str,
    location_key: str,
    frames_data: str = Form(..., description="JSON array of frame data"),
    time_of_day: str = Form(default="day"),
    finish: str = Form(default="gold"),
    photo: UploadFile = File(...),
    config_json: str | None = Form(default=None),
    created_by: str | None = Form(default=None),
) -> dict[str, Any]:
    """
    Save a mockup frame with photo to storage.

    Args:
        company: Company schema (e.g., "backlite_dubai")
        location_key: Location identifier
        frames_data: JSON array of frame coordinate data
        time_of_day: "day" or "night"
        finish: "gold" or "silver"
        photo: The billboard photo file
        config_json: Optional JSON config
        created_by: User email who created this

    Returns:
        Save result with final filename
    """
    logger.info(
        f"[MOCKUP_FRAMES] Saving frame for {company}/{location_key} "
        f"({time_of_day}/{finish}/{photo.filename})"
    )

    # Validate time_of_day and finish
    if time_of_day not in {"day", "night"}:
        raise HTTPException(status_code=400, detail=f"Invalid time_of_day: {time_of_day}")
    if finish not in {"gold", "silver"}:
        raise HTTPException(status_code=400, detail=f"Invalid finish: {finish}")

    try:
        # Parse frames data
        frames = json.loads(frames_data)
        if not isinstance(frames, list) or len(frames) == 0:
            raise HTTPException(status_code=400, detail="frames_data must be a non-empty list")

        # Parse config if provided
        config_dict = None
        if config_json:
            config_dict = json.loads(config_json)

        # Read photo data
        photo_data = await photo.read()

        # Save to database (returns auto-numbered filename)
        final_filename = db.save_mockup_frame(
            location_key=location_key,
            photo_filename=photo.filename,
            frames_data=frames,
            company_schema=company,
            time_of_day=time_of_day,
            finish=finish,
            created_by=created_by,
            config=config_dict,
        )

        # Upload photo to Supabase storage
        storage_url = None
        try:
            from db.database import _backend
            if hasattr(_backend, '_get_client'):
                client = _backend._get_client()
                storage_key = f"{company}/{location_key}/{time_of_day}/{finish}/{final_filename}"
                content_type = photo.content_type or "image/jpeg"

                # Upload to mockups bucket
                result = client.storage.from_("mockups").upload(
                    storage_key,
                    photo_data,
                    {"content-type": content_type},
                )
                if result:
                    # Get public URL
                    url_result = client.storage.from_("mockups").get_public_url(storage_key)
                    storage_url = url_result
                    logger.info(f"[MOCKUP_FRAMES] Photo uploaded to storage: {storage_key}")
        except Exception as storage_err:
            logger.warning(f"[MOCKUP_FRAMES] Storage upload failed (non-critical): {storage_err}")
            # Don't fail the save if storage fails - photo is optional backup

        logger.info(f"[MOCKUP_FRAMES] ✓ Saved frame: {company}/{location_key}/{final_filename}")

        return {
            "success": True,
            "photo_filename": final_filename,
            "location_key": location_key,
            "time_of_day": time_of_day,
            "finish": finish,
            "frames_count": len(frames),
            "storage_url": storage_url,
        }

    except json.JSONDecodeError as e:
        logger.error(f"[MOCKUP_FRAMES] JSON decode error: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON in frames_data or config_json")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[MOCKUP_FRAMES] Failed to save frame: {e}", exc_info=True)
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