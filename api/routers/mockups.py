"""
Mockup generator endpoints.
"""

import json
import os
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form, BackgroundTasks, Depends
from fastapi.responses import HTMLResponse, FileResponse, Response

from api.auth import require_auth, require_permission
from integrations.auth import AuthUser
import config
from db.database import db
from utils.time import get_uae_time
from api.schemas import (
    validate_image_upload,
    MAX_IMAGE_SIZE,
    ALLOWED_IMAGE_TYPES,
)

logger = config.logger

router = APIRouter(tags=["mockups"])

# Valid enum values for form parameters
VALID_TIME_OF_DAY = {"day", "night", "all"}
VALID_FINISH = {"gold", "silver", "all"}


def sanitize_path_component(value: str) -> str:
    """
    Sanitize a path component to prevent path traversal attacks.
    Removes any path separators and parent directory references.
    """
    # Get just the filename/component, strip any path parts
    sanitized = Path(value).name
    # Additional safety: reject if it contains suspicious patterns
    if ".." in sanitized or sanitized.startswith(".") or "/" in sanitized or "\\" in sanitized:
        raise HTTPException(status_code=400, detail=f"Invalid path component: {value}")
    if not sanitized or sanitized != value:
        raise HTTPException(status_code=400, detail=f"Invalid path component: {value}")
    return sanitized


@router.get("/mockup")
async def mockup_setup_page(user: AuthUser = Depends(require_permission("sales:mockups:setup"))):
    """Serve the mockup setup/generate interface. Requires admin role."""
    html_path = Path(__file__).parent.parent / "templates" / "mockup_setup.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Mockup setup page not found")
    return HTMLResponse(content=html_path.read_text())


@router.get("/api/mockup/locations")
async def get_mockup_locations(user: AuthUser = Depends(require_auth)):
    """Get list of available locations for mockup. Requires authentication and company access."""
    # Company access validation (security - no backwards compatibility)
    if not user.has_company_access:
        raise HTTPException(
            status_code=403,
            detail="You don't have access to any company data. Please contact your administrator to be assigned to a company."
        )

    # Query locations from user's accessible company schemas
    db_locations = db.get_locations_for_companies(user.companies)

    locations = []
    for loc in db_locations:
        locations.append({
            "key": loc.get("location_key"),
            "name": loc.get("display_name", loc.get("location_key", "").title()),
            "company": loc.get("company_schema"),
        })

    return {"locations": sorted(locations, key=lambda x: x["name"])}


@router.post("/api/mockup/save-frame")
async def save_mockup_frame(
    location_key: str = Form(..., min_length=1, max_length=100),
    time_of_day: str = Form("day"),
    finish: str = Form("gold"),
    frames_data: str = Form(..., max_length=50000),
    photo: UploadFile = File(...),
    config_json: Optional[str] = Form(None, max_length=10000),
    user: AuthUser = Depends(require_permission("sales:mockups:setup"))
):
    """Save a billboard photo with multiple frame coordinates and optional config. Requires admin role."""
    from generators import mockup as mockup_generator

    # Validate enum parameters
    if time_of_day not in VALID_TIME_OF_DAY:
        raise HTTPException(status_code=400, detail=f"Invalid time_of_day: {time_of_day}. Must be one of: {VALID_TIME_OF_DAY}")
    if finish not in VALID_FINISH:
        raise HTTPException(status_code=400, detail=f"Invalid finish: {finish}. Must be one of: {VALID_FINISH}")

    # Validate file upload
    try:
        # Check file size (read content to get size)
        photo_data = await photo.read()
        await photo.seek(0)  # Reset for later read
        validate_image_upload(photo.content_type, len(photo_data))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Log EXACTLY what was received from the form
    logger.info(f"[MOCKUP API] ====== SAVE FRAME REQUEST ======")
    logger.info(f"[MOCKUP API] RECEIVED location_key: '{location_key}'")
    logger.info(f"[MOCKUP API] RECEIVED time_of_day: '{time_of_day}'")
    logger.info(f"[MOCKUP API] RECEIVED finish: '{finish}'")
    logger.info(f"[MOCKUP API] RECEIVED photo filename: '{photo.filename}' ({len(photo_data)} bytes)")
    logger.info(f"[MOCKUP API] ====================================")

    try:
        # Parse frames data (list of frames, each frame has points and config)
        frames = json.loads(frames_data)
        if not isinstance(frames, list) or len(frames) == 0:
            raise HTTPException(status_code=400, detail="frames_data must be a non-empty list of frames")

        # Validate each frame has points array with 4 points and optional config
        for i, frame in enumerate(frames):
            if not isinstance(frame, dict):
                raise HTTPException(status_code=400, detail=f"Frame {i} must be an object with 'points' and 'config'")
            if 'points' not in frame:
                raise HTTPException(status_code=400, detail=f"Frame {i} missing 'points' field")
            if not isinstance(frame['points'], list) or len(frame['points']) != 4:
                raise HTTPException(status_code=400, detail=f"Frame {i} must have exactly 4 corner points")

        # Parse config if provided
        config_dict = None
        if config_json:
            try:
                config_dict = json.loads(config_json)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid config JSON")

        # Validate location
        if location_key not in config.LOCATION_METADATA:
            raise HTTPException(status_code=400, detail=f"Invalid location: {location_key}")

        # Read photo data
        logger.info(f"[MOCKUP API] Reading photo data from upload: {photo.filename}")
        photo_data = await photo.read()
        logger.info(f"[MOCKUP API] ✓ Read {len(photo_data)} bytes from upload")

        # Save all frames to database with per-frame configs - this returns the auto-numbered filename
        logger.info(f"[MOCKUP API] Saving {len(frames)} frame(s) to database for {location_key}/{time_of_day}/{finish}")
        final_filename = db.save_mockup_frame(location_key, photo.filename, frames, created_by=None, time_of_day=time_of_day, finish=finish, config=config_dict)
        logger.info(f"[MOCKUP API] ✓ Database save complete, filename: {final_filename}")

        # Save photo to disk with the final auto-numbered filename
        logger.info(f"[MOCKUP API] Saving photo to disk: {final_filename}")
        photo_path = mockup_generator.save_location_photo(location_key, final_filename, photo_data, time_of_day, finish)
        logger.info(f"[MOCKUP API] ✓ Photo saved to disk at: {photo_path}")

        # Verify the file exists immediately after saving
        if os.path.exists(photo_path):
            file_size = os.path.getsize(photo_path)
            logger.info(f"[MOCKUP API] ✓ VERIFICATION: File exists on disk, size: {file_size} bytes")
        else:
            logger.error(f"[MOCKUP API] ✗ VERIFICATION FAILED: File does not exist at {photo_path}")

        logger.info(f"[MOCKUP API] ✓ Complete: Saved {len(frames)} frame(s) for {location_key}/{time_of_day}/{finish}/{final_filename}")

        return {"success": True, "photo": final_filename, "time_of_day": time_of_day, "finish": finish, "frames_count": len(frames)}

    except json.JSONDecodeError as e:
        logger.error(f"[MOCKUP API] JSON decode error: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail="Invalid frames_data JSON")
    except Exception as e:
        logger.error(f"[MOCKUP API] Error saving frames: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/mockup/test-preview")
async def test_preview_mockup(
    billboard_photo: UploadFile = File(...),
    creative: UploadFile = File(...),
    frame_points: str = Form(...),
    config: str = Form("{}"),
    time_of_day: str = Form("day"),
    user: AuthUser = Depends(require_permission("sales:mockups:setup"))
):
    """Generate a test preview of how the creative will look on the billboard with current config. Requires admin role."""
    import cv2
    import numpy as np
    from generators import mockup as mockup_generator

    try:
        # Parse frame points (list of 4 [x, y] coordinates)
        points = json.loads(frame_points)
        if not isinstance(points, list) or len(points) != 4:
            raise HTTPException(status_code=400, detail="frame_points must be a list of 4 [x, y] coordinates")

        # Parse config
        config_dict = json.loads(config)

        # Read billboard photo
        billboard_data = await billboard_photo.read()
        billboard_array = np.frombuffer(billboard_data, np.uint8)
        billboard_img = cv2.imdecode(billboard_array, cv2.IMREAD_COLOR)

        if billboard_img is None:
            raise HTTPException(status_code=400, detail="Invalid billboard photo")

        # Read creative
        creative_data = await creative.read()
        creative_array = np.frombuffer(creative_data, np.uint8)
        creative_img = cv2.imdecode(creative_array, cv2.IMREAD_COLOR)

        if creative_img is None:
            raise HTTPException(status_code=400, detail="Invalid creative image")

        # Apply the warp using the same function as real mockup generation
        result = mockup_generator.warp_creative_to_billboard(
            billboard_img,
            creative_img,
            points,
            config=config_dict,
            time_of_day=time_of_day
        )

        # Encode result as JPEG
        success, buffer = cv2.imencode('.jpg', result, [cv2.IMWRITE_JPEG_QUALITY, 85])

        # CRITICAL: Explicitly delete large numpy arrays to free memory immediately
        # Preview endpoint is called repeatedly during setup, causing memory buildup
        del billboard_data, billboard_array, billboard_img
        del creative_data, creative_array, creative_img
        del result
        from utils.memory import cleanup_memory
        cleanup_memory(context="mockup_preview", aggressive=False, log_stats=False)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to encode preview image")

        # Return as image response
        return Response(content=buffer.tobytes(), media_type="image/jpeg")

    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")
    except Exception as e:
        logger.error(f"[TEST PREVIEW] Error generating preview: {e}", exc_info=True)
        # Cleanup on error path too
        try:
            del billboard_data, billboard_array, billboard_img
            del creative_data, creative_array, creative_img
            del result
            from utils.memory import cleanup_memory
            cleanup_memory(context="mockup_preview_error", aggressive=False, log_stats=False)
        except NameError:
            pass  # Some variables may not have been assigned
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/mockup/photos/{location_key}")
async def list_mockup_photos(location_key: str, time_of_day: str = "all", finish: str = "all", user: AuthUser = Depends(require_auth)):
    """List all photos for a location with specific time_of_day and finish. Requires authentication."""
    try:
        # If "all" is specified, we need to aggregate from all variations
        if time_of_day == "all" or finish == "all":
            variations = db.list_mockup_variations(location_key)
            all_photos = set()
            for tod in variations:
                for fin in variations[tod]:
                    photos = db.list_mockup_photos(location_key, tod, fin)
                    all_photos.update(photos)
            return {"photos": sorted(list(all_photos))}
        else:
            photos = db.list_mockup_photos(location_key, time_of_day, finish)
            return {"photos": photos}
    except Exception as e:
        logger.error(f"[MOCKUP API] Error listing photos: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/mockup/templates/{location_key}")
async def list_mockup_templates(location_key: str, time_of_day: str = "all", finish: str = "all", user: AuthUser = Depends(require_auth)):
    """List all templates (photos with frame configs) for a location. Requires authentication."""
    try:
        templates = []

        # If "all" is specified, aggregate from all variations
        if time_of_day == "all" or finish == "all":
            variations = db.list_mockup_variations(location_key)
            for tod in variations:
                for fin in variations[tod]:
                    photos = db.list_mockup_photos(location_key, tod, fin)
                    for photo in photos:
                        # Get frame count and config
                        frames_data = db.get_mockup_frames(location_key, photo, tod, fin)
                        if frames_data:
                            # Get first frame's config (all frames typically share same config in UI)
                            frame_config = frames_data[0].get("config", {}) if frames_data else {}
                            templates.append({
                                "photo": photo,
                                "time_of_day": tod,
                                "finish": fin,
                                "frame_count": len(frames_data),
                                "config": frame_config
                            })
        else:
            photos = db.list_mockup_photos(location_key, time_of_day, finish)
            for photo in photos:
                # Get frame count and config
                frames_data = db.get_mockup_frames(location_key, photo, time_of_day, finish)
                if frames_data:
                    frame_config = frames_data[0].get("config", {}) if frames_data else {}
                    templates.append({
                        "photo": photo,
                        "time_of_day": time_of_day,
                        "finish": finish,
                        "frame_count": len(frames_data),
                        "config": frame_config
                    })

        return {"templates": templates}
    except Exception as e:
        logger.error(f"[MOCKUP API] Error listing templates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/mockup/photo/{location_key}/{photo_filename}")
async def get_mockup_photo(location_key: str, photo_filename: str, time_of_day: str = "all", finish: str = "all", user: AuthUser = Depends(require_auth)):
    """Get a specific photo file. Requires authentication."""
    from generators import mockup as mockup_generator

    # Sanitize path components to prevent path traversal attacks
    location_key = sanitize_path_component(location_key)
    photo_filename = sanitize_path_component(photo_filename)

    logger.info(f"[PHOTO GET] Request for photo: {location_key}/{photo_filename} (time_of_day={time_of_day}, finish={finish})")

    # If "all" is specified, find the photo in any variation
    if time_of_day == "all" or finish == "all":
        logger.info(f"[PHOTO GET] Searching across variations (all mode)")
        variations = db.list_mockup_variations(location_key)
        logger.info(f"[PHOTO GET] Available variations: {variations}")

        all_checked_paths = []
        for tod in variations:
            for fin in variations[tod]:
                photo_path = mockup_generator.get_location_photos_dir(location_key, tod, fin) / photo_filename
                all_checked_paths.append(str(photo_path))
                logger.info(f"[PHOTO GET] Checking: {photo_path}")

                if photo_path.exists():
                    file_size = os.path.getsize(photo_path)
                    logger.info(f"[PHOTO GET] ✓ FOUND: {photo_path} ({file_size} bytes)")
                    return FileResponse(photo_path)
                else:
                    logger.info(f"[PHOTO GET] ✗ NOT FOUND: {photo_path}")

        logger.error(f"[PHOTO GET] ✗ Photo not found in any variation. Checked paths: {all_checked_paths}")

        # Check if directory exists at all
        mockups_base = mockup_generator.MOCKUPS_DIR / location_key
        if mockups_base.exists():
            logger.info(f"[PHOTO GET] Base directory exists: {mockups_base}")
            logger.info(f"[PHOTO GET] Contents: {list(os.walk(mockups_base))}")
        else:
            logger.error(f"[PHOTO GET] Base directory doesn't exist: {mockups_base}")

        raise HTTPException(status_code=404, detail=f"Photo not found: {photo_filename}")
    else:
        photo_path = mockup_generator.get_location_photos_dir(location_key, time_of_day, finish) / photo_filename
        logger.info(f"[PHOTO GET] Direct path request: {photo_path}")

        if not photo_path.exists():
            logger.error(f"[PHOTO GET] ✗ Photo not found: {photo_path}")

            # Check parent directories
            parent_dir = photo_path.parent
            if parent_dir.exists():
                logger.info(f"[PHOTO GET] Parent directory exists: {parent_dir}")
                logger.info(f"[PHOTO GET] Contents: {list(parent_dir.iterdir())}")
            else:
                logger.error(f"[PHOTO GET] Parent directory doesn't exist: {parent_dir}")

            raise HTTPException(status_code=404, detail=f"Photo not found: {photo_filename}")

        file_size = os.path.getsize(photo_path)
        logger.info(f"[PHOTO GET] ✓ Found photo: {photo_path} ({file_size} bytes)")
        return FileResponse(photo_path)


@router.delete("/api/mockup/photo/{location_key}/{photo_filename}")
async def delete_mockup_photo(location_key: str, photo_filename: str, time_of_day: str = "all", finish: str = "all", user: AuthUser = Depends(require_permission("sales:mockups:setup"))):
    """Delete a photo and its frame. Requires admin role."""
    from generators import mockup as mockup_generator

    # Sanitize path components to prevent path traversal attacks
    location_key = sanitize_path_component(location_key)
    photo_filename = sanitize_path_component(photo_filename)

    try:
        # If "all" is specified, find and delete the photo from whichever variation it's in
        if time_of_day == "all" or finish == "all":
            variations = db.list_mockup_variations(location_key)
            for tod in variations:
                for fin in variations[tod]:
                    photos = db.list_mockup_photos(location_key, tod, fin)
                    if photo_filename in photos:
                        success = mockup_generator.delete_location_photo(location_key, photo_filename, tod, fin)
                        if success:
                            return {"success": True}
                        else:
                            raise HTTPException(status_code=500, detail="Failed to delete photo")
            raise HTTPException(status_code=404, detail="Photo not found")
        else:
            success = mockup_generator.delete_location_photo(location_key, photo_filename, time_of_day, finish)
            if success:
                return {"success": True}
            else:
                raise HTTPException(status_code=500, detail="Failed to delete photo")
    except Exception as e:
        logger.error(f"[MOCKUP API] Error deleting photo: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/mockup/generate")
async def generate_mockup_api(
    request: Request,
    location_key: str = Form(...),
    time_of_day: str = Form("all"),
    finish: str = Form("all"),
    ai_prompt: Optional[str] = Form(None),
    creative: Optional[UploadFile] = File(None),
    specific_photo: Optional[str] = Form(None),
    frame_config: Optional[str] = Form(None),
    user: AuthUser = Depends(require_auth)
):
    """Generate a mockup by warping creative onto billboard (upload or AI-generated). Requires authentication."""
    import tempfile
    from generators import mockup as mockup_generator

    creative_path = None
    photo_used = None
    creative_type = None
    template_selected = specific_photo is not None

    # Get client IP for analytics
    client_ip = request.client.host if request.client else None

    try:
        # Parse frame config if provided
        config_dict = None
        if frame_config:
            try:
                config_dict = json.loads(frame_config)
                logger.info(f"[MOCKUP API] Using custom frame config: {config_dict}")
            except json.JSONDecodeError:
                logger.warning(f"[MOCKUP API] Invalid frame config JSON, ignoring")

        # Validate location
        if location_key not in config.LOCATION_METADATA:
            raise HTTPException(status_code=400, detail=f"Invalid location: {location_key}")

        # Determine mode: AI generation or upload
        if ai_prompt:
            # AI MODE: Generate creative using AI
            creative_type = "ai_generated"
            logger.info(f"[MOCKUP API] Generating AI creative with prompt: {ai_prompt[:100]}...")

            creative_path = await mockup_generator.generate_ai_creative(
                prompt=ai_prompt,
                size="1536x1024"  # Landscape format for billboards
            )

            if not creative_path:
                raise HTTPException(status_code=500, detail="Failed to generate AI creative")

        elif creative:
            # UPLOAD MODE: Use uploaded creative
            creative_type = "uploaded"
            logger.info(f"[MOCKUP API] Using uploaded creative: {creative.filename}")

            creative_data = await creative.read()
            creative_temp = tempfile.NamedTemporaryFile(delete=False, suffix=Path(creative.filename).suffix)
            creative_temp.write(creative_data)
            creative_temp.close()
            creative_path = Path(creative_temp.name)

        else:
            raise HTTPException(status_code=400, detail="Either ai_prompt or creative file must be provided")

        # Generate mockup (pass as list) with time_of_day, finish, specific_photo, and config override
        result_path, photo_used = mockup_generator.generate_mockup(
            location_key,
            [creative_path],
            time_of_day=time_of_day,
            finish=finish,
            specific_photo=specific_photo,
            config_override=config_dict
        )

        if not result_path or not photo_used:
            # Log failed attempt
            db.log_mockup_usage(
                location_key=location_key,
                time_of_day=time_of_day,
                finish=finish,
                photo_used=specific_photo or "random",
                creative_type=creative_type or "unknown",
                ai_prompt=ai_prompt if ai_prompt else None,
                template_selected=template_selected,
                success=False,
                user_ip=client_ip
            )
            raise HTTPException(status_code=500, detail="Failed to generate mockup")

        # Log successful generation
        db.log_mockup_usage(
            location_key=location_key,
            time_of_day=time_of_day,
            finish=finish,
            photo_used=photo_used,
            creative_type=creative_type,
            ai_prompt=ai_prompt if ai_prompt else None,
            template_selected=template_selected,
            success=True,
            user_ip=client_ip
        )

        # Return the image with background_tasks to delete after serving
        def cleanup_files():
            """Delete temp files after response is sent"""
            try:
                if creative_path and creative_path.exists():
                    creative_path.unlink()
                    logger.debug(f"[CLEANUP] Deleted temp creative: {creative_path}")
            except Exception as e:
                logger.debug(f"[CLEANUP] Error deleting creative: {e}")

            try:
                if result_path and result_path.exists():
                    result_path.unlink()
                    logger.debug(f"[CLEANUP] Deleted temp mockup: {result_path}")
            except Exception as e:
                logger.debug(f"[CLEANUP] Error deleting mockup: {e}")

        # Schedule cleanup after response is sent
        background_tasks = BackgroundTasks()
        background_tasks.add_task(cleanup_files)

        return FileResponse(
            result_path,
            media_type="image/jpeg",
            filename=f"mockup_{location_key}_{time_of_day}_{finish}.jpg",
            background=background_tasks
        )

    except HTTPException as http_exc:
        # Cleanup temp files on HTTP exceptions (validation errors, etc.)
        try:
            if 'creative_path' in locals() and creative_path and creative_path.exists():
                creative_path.unlink()
                logger.debug(f"[CLEANUP] Deleted temp creative after error: {creative_path}")
        except Exception as cleanup_error:
            logger.debug(f"[CLEANUP] Error deleting creative after error: {cleanup_error}")

        try:
            if 'result_path' in locals() and result_path and result_path.exists():
                result_path.unlink()
                logger.debug(f"[CLEANUP] Deleted temp mockup after error: {result_path}")
        except Exception as cleanup_error:
            logger.debug(f"[CLEANUP] Error deleting mockup after error: {cleanup_error}")

        raise http_exc

    except Exception as e:
        logger.error(f"[MOCKUP API] Error generating mockup: {e}", exc_info=True)

        # Cleanup temp files on unexpected errors
        try:
            if 'creative_path' in locals() and creative_path and creative_path.exists():
                creative_path.unlink()
                logger.debug(f"[CLEANUP] Deleted temp creative after error: {creative_path}")
        except Exception as cleanup_error:
            logger.debug(f"[CLEANUP] Error deleting creative after error: {cleanup_error}")

        try:
            if 'result_path' in locals() and result_path and result_path.exists():
                result_path.unlink()
                logger.debug(f"[CLEANUP] Deleted temp mockup after error: {result_path}")
        except Exception as cleanup_error:
            logger.debug(f"[CLEANUP] Error deleting mockup after error: {cleanup_error}")

        # Log failed attempt
        try:
            db.log_mockup_usage(
                location_key=location_key,
                time_of_day=time_of_day,
                finish=finish,
                photo_used=specific_photo or "random",
                creative_type=creative_type or "unknown",
                ai_prompt=ai_prompt if ai_prompt else None,
                template_selected=template_selected,
                success=False,
                user_ip=client_ip
            )
        except Exception as log_error:
            logger.error(f"[MOCKUP API] Error logging usage: {log_error}")

        raise HTTPException(status_code=500, detail=str(e))
