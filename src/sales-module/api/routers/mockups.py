"""
Mockup generator endpoints.
"""

import json
import os
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response

import config
from core.services.asset_service import get_asset_service
from core.services.mockup_frame_service import MockupFrameService
from core.utils import sanitize_path_component  # ✅ Use shared utility (removed duplicate)
from crm_security import require_permission_user as require_permission, AuthUser
from api.schemas import (
    validate_image_upload,
)
from db.database import db

logger = config.logger

router = APIRouter(tags=["mockups"])

# Valid enum values for form parameters
VALID_TIME_OF_DAY = {"day", "night", "all"}
VALID_SIDE = {"gold", "silver", "all"}


@router.get("/mockup")
async def mockup_setup_page(user: AuthUser = Depends(require_permission("sales:mockups:setup"))):
    """Serve the mockup setup/generate interface. Requires admin role."""
    html_path = Path(__file__).parent.parent / "templates" / "mockup_setup.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Mockup setup page not found")
    return HTMLResponse(content=html_path.read_text())


@router.get("/api/mockup/locations")
async def get_mockup_locations(user: AuthUser = Depends(require_permission("sales:mockups:read"))):
    """Get list of available locations for mockup. Requires sales:mockups:read permission."""
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
            "company": loc.get("company") or loc.get("company_schema"),
        })

    return {"locations": sorted(locations, key=lambda x: x["name"])}


@router.post("/api/mockup/save-frame")
async def save_mockup_frame(
    location_key: str = Form(..., min_length=1, max_length=100),
    time_of_day: str = Form("day"),
    side: str = Form("gold"),
    frames_data: str = Form(..., max_length=50000),
    photo: UploadFile = File(...),
    config_json: str | None = Form(None, max_length=10000),
    user: AuthUser = Depends(require_permission("sales:mockups:setup"))
):
    """Save a billboard photo with multiple frame coordinates and optional config. Requires admin role."""
    from generators import mockup as mockup_generator

    # Validate enum parameters
    if time_of_day not in VALID_TIME_OF_DAY:
        raise HTTPException(status_code=400, detail=f"Invalid time_of_day: {time_of_day}. Must be one of: {VALID_TIME_OF_DAY}")
    if side not in VALID_SIDE:
        raise HTTPException(status_code=400, detail=f"Invalid side: {side}. Must be one of: {VALID_SIDE}")

    # Validate file upload
    try:
        # Check file size (read content to get size)
        photo_data = await photo.read()
        await photo.seek(0)  # Reset for later read
        validate_image_upload(photo.content_type, len(photo_data))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Log EXACTLY what was received from the form
    logger.info("[MOCKUP API] ====== SAVE FRAME REQUEST ======")
    logger.info(f"[MOCKUP API] RECEIVED location_key: '{location_key}'")
    logger.info(f"[MOCKUP API] RECEIVED time_of_day: '{time_of_day}'")
    logger.info(f"[MOCKUP API] RECEIVED side: '{side}'")
    logger.info(f"[MOCKUP API] RECEIVED photo filename: '{photo.filename}' ({len(photo_data)} bytes)")
    logger.info("[MOCKUP API] ====================================")

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

        # Validate location exists and user has access (using singleton AssetService)
        asset_service = get_asset_service()
        has_access, error_msg = await asset_service.validate_location_access(location_key, user.companies)
        if not has_access:
            raise HTTPException(status_code=403, detail=error_msg or f"Location '{location_key}' not found or not accessible")

        # Read photo data
        logger.info(f"[MOCKUP API] Reading photo data from upload: {photo.filename}")
        photo_data = await photo.read()
        logger.info(f"[MOCKUP API] ✓ Read {len(photo_data)} bytes from upload")

        # Determine which company schema to save to - based on which company owns the location
        location_data = await asset_service.get_location_by_key(location_key, user.companies)
        if not location_data:
            raise HTTPException(status_code=403, detail=f"Location '{location_key}' not found in your accessible companies")
        # Asset-Management API returns "company", some internal code uses "company_schema"
        company_schema = location_data.get("company") or location_data.get("company_schema")
        if not company_schema:
            raise HTTPException(status_code=500, detail=f"Location '{location_key}' has no company assigned")

        # Save via Asset-Management API (handles database + storage)
        logger.info(f"[MOCKUP API] Saving {len(frames)} frame(s) via asset-management for {company_schema}.{location_key}/{time_of_day}/{side}")
        from integrations.asset_management import asset_mgmt_client
        result = await asset_mgmt_client.save_mockup_frame(
            company=company_schema,
            location_key=location_key,
            photo_data=photo_data,
            photo_filename=photo.filename,
            frames_data=frames,
            time_of_day=time_of_day,
            side=side,
            created_by=user.email,
            config=config_dict,
        )
        if not result or not result.get("success"):
            raise HTTPException(status_code=500, detail="Failed to save mockup frame via asset-management")
        final_filename = result.get("photo_filename")
        logger.info(f"[MOCKUP API] ✓ Asset-management save complete, filename: {final_filename}")

        # Save photo to disk with the final auto-numbered filename
        logger.info(f"[MOCKUP API] Saving photo to disk: {final_filename}")
        photo_path = mockup_generator.save_location_photo(company_schema, location_key, final_filename, photo_data, time_of_day, side)
        logger.info(f"[MOCKUP API] ✓ Photo saved to disk at: {photo_path}")

        # Verify the file exists immediately after saving
        if os.path.exists(photo_path):
            file_size = os.path.getsize(photo_path)
            logger.info(f"[MOCKUP API] ✓ VERIFICATION: File exists on disk, size: {file_size} bytes")
        else:
            logger.error(f"[MOCKUP API] ✗ VERIFICATION FAILED: File does not exist at {photo_path}")

        logger.info(f"[MOCKUP API] ✓ Complete: Saved {len(frames)} frame(s) for {location_key}/{time_of_day}/{side}/{final_filename}")

        return {"success": True, "photo": final_filename, "time_of_day": time_of_day, "side": side, "frames_count": len(frames)}

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
        from core.utils.memory import cleanup_memory
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
            from core.utils.memory import cleanup_memory
            cleanup_memory(context="mockup_preview_error", aggressive=False, log_stats=False)
        except NameError:
            pass  # Some variables may not have been assigned
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/mockup/photos/{location_key}")
async def list_mockup_photos(
    location_key: str,
    time_of_day: str = "all",
    side: str = "all",
    venue_type: str = "all",
    user: AuthUser = Depends(require_permission("sales:mockups:read"))
):
    """
    List all photos for a location with proper standalone/traditional handling.

    Args:
        location_key: Network key
        time_of_day: Filter by "day", "night", or "all" (only applies to outdoor)
        side: Filter by "gold", "silver", "single_side", or "all" (only applies to outdoor)
        venue_type: Filter by "indoor", "outdoor", or "all"

    Requires sales:mockups:read permission.
    """
    try:
        service = MockupFrameService(companies=user.companies)

        # Get storage info with ALL assets for traditional networks
        storage_info = await service.get_storage_info(location_key, include_all_assets=True)

        if not storage_info:
            storage_keys = [location_key]
            company = None
        else:
            storage_keys = storage_info.get("storage_keys", [location_key])
            company = storage_info.get("company")

        all_photos = set()

        # Fetch frames from EACH storage key
        for storage_key in storage_keys:
            frames, _ = await service.get_all_frames(storage_key, company_hint=company)

            for frame in frames:
                env = frame.get("environment", "outdoor")
                tod = frame.get("time_of_day", "day")
                frame_side = frame.get("side", "gold")
                photo = frame.get("photo_filename")

                if not photo:
                    continue

                # Filter by venue_type (environment) FIRST
                if venue_type != "all" and env != venue_type:
                    continue

                # For outdoor, apply time_of_day and side filters
                # For indoor, skip these filters (meaningless)
                if env == "outdoor":
                    if time_of_day != "all" and tod != time_of_day:
                        continue
                    if side != "all" and frame_side != side:
                        continue

                all_photos.add(photo)

        return {"photos": sorted(all_photos)}

    except Exception as e:
        logger.error(f"[MOCKUP API] Error listing photos: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/mockup/templates/{location_key}")
async def list_mockup_templates(
    location_key: str,
    time_of_day: str = "all",
    side: str = "all",
    venue_type: str = "all",
    user: AuthUser = Depends(require_permission("sales:mockups:read"))
):
    """
    List all templates (photos with frame configs) for a location.

    Handles both standalone and traditional networks:
    - Standalone: mockups stored at network level
    - Traditional: mockups stored at asset level (network_key/type_key/asset_key)

    Args:
        location_key: Network key
        time_of_day: Filter by "day", "night", or "all" (only applies to outdoor)
        side: Filter by "gold", "silver", "single_side", or "all" (only applies to outdoor)
        venue_type: Filter by "indoor", "outdoor", or "all"

    Requires sales:mockups:read permission.
    """
    try:
        service = MockupFrameService(companies=user.companies)

        # Step 1: Get storage info with ALL assets for traditional networks
        storage_info = await service.get_storage_info(location_key, include_all_assets=True)

        if not storage_info:
            # Fallback: try location_key directly (backward compatibility)
            storage_keys = [location_key]
            company = None
        else:
            storage_keys = storage_info.get("storage_keys", [location_key])
            company = storage_info.get("company")

        templates = []
        seen = set()  # Dedupe: (photo, storage_key, env, tod, side)

        # Step 2: Fetch frames from EACH storage key
        # storage_key is "{network_key}/{type_key}/{asset_key}" for traditional, "{network_key}" for standalone
        for storage_key in storage_keys:
            frames, _ = await service.get_all_frames(storage_key, company_hint=company)

            for frame in frames:
                env = frame.get("environment", "outdoor")
                tod = frame.get("time_of_day", "day")
                frame_side = frame.get("side", "gold")
                photo = frame.get("photo_filename")

                if not photo:
                    continue

                # Step 3: Filter by venue_type (environment) FIRST
                if venue_type != "all" and env != venue_type:
                    continue

                # Step 4: For OUTDOOR frames, apply time_of_day and side filters
                # For INDOOR frames, skip these filters (meaningless)
                if env == "outdoor":
                    if time_of_day != "all" and tod != time_of_day:
                        continue
                    if side != "all" and frame_side != side:
                        continue

                # Dedupe by unique key
                key = (photo, storage_key, env, tod, frame_side)
                if key in seen:
                    continue
                seen.add(key)

                # Get frame count and config from frames_data
                frames_data = frame.get("frames_data", [])
                frame_config = frames_data[0].get("config", {}) if frames_data else {}

                templates.append({
                    "photo": photo,
                    "storage_key": storage_key,  # "{network_key}/{type_key}/{asset_key}" or "{network_key}"
                    "environment": env,
                    "time_of_day": tod,
                    "side": frame_side,
                    "frame_count": len(frames_data) if frames_data else 1,
                    "config": frame_config,
                })

        return {"templates": templates}

    except Exception as e:
        logger.error(f"[MOCKUP API] Error listing templates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/mockup/photo/{photo_filename}/{location_key:path}")
async def get_mockup_photo(
    photo_filename: str,
    location_key: str,
    time_of_day: str = "all",
    side: str = "all",
    background_tasks: BackgroundTasks = None,
    user: AuthUser = Depends(require_permission("sales:mockups:read")),
):
    """
    Get a specific photo file from Asset-Management storage.

    NOTE: location_key is last with :path modifier to support traditional network storage keys
    that contain slashes (e.g., "dubai_mall/digital_screens/mall_screen_a").

    Requires sales:mockups:read permission.
    """
    # Sanitize path components to prevent path traversal attacks
    # For location_key with slashes, sanitize each segment
    location_key = "/".join(sanitize_path_component(seg) for seg in location_key.split("/"))
    photo_filename = sanitize_path_component(photo_filename)

    logger.info(f"[PHOTO GET] Request for photo: {location_key}/{photo_filename} (time_of_day={time_of_day}, side={side})")

    # Use MockupFrameService to fetch from Asset-Management (searches all companies)
    service = MockupFrameService(companies=user.companies)

    if time_of_day == "all" or side == "all":
        # Search across all variations
        variations = await service.list_variations(location_key)
        logger.info(f"[PHOTO GET] Available variations: {variations}")

        for tod in variations:
            for sid in variations[tod]:
                # Check if this photo exists in this variation
                photos = await service.list_photos(location_key, tod, sid)
                if photo_filename in photos:
                    # Download the photo
                    photo_path = await service.download_photo(location_key, tod, sid, photo_filename)
                    if photo_path and photo_path.exists():
                        file_size = os.path.getsize(photo_path)
                        logger.info(f"[PHOTO GET] ✓ FOUND: {photo_path} ({file_size} bytes)")

                        # Schedule cleanup after response is sent
                        if background_tasks:
                            background_tasks.add_task(os.unlink, photo_path)

                        return FileResponse(photo_path, filename=photo_filename)
    else:
        # Direct lookup with specific time_of_day and side
        photo_path = await service.download_photo(location_key, time_of_day, side, photo_filename)
        if photo_path and photo_path.exists():
            file_size = os.path.getsize(photo_path)
            logger.info(f"[PHOTO GET] ✓ FOUND: {photo_path} ({file_size} bytes)")

            # Schedule cleanup after response is sent
            if background_tasks:
                background_tasks.add_task(os.unlink, photo_path)

            return FileResponse(photo_path, filename=photo_filename)

    logger.error(f"[PHOTO GET] ✗ Photo not found: {location_key}/{photo_filename}")
    raise HTTPException(status_code=404, detail=f"Photo not found: {photo_filename}")


@router.delete("/api/mockup/photo/{photo_filename}/{location_key:path}")
async def delete_mockup_photo(photo_filename: str, location_key: str, time_of_day: str = "all", side: str = "all", user: AuthUser = Depends(require_permission("sales:mockups:setup"))):
    """
    Delete a photo and its frame.

    NOTE: location_key is last with :path modifier to support traditional network storage keys
    that contain slashes (e.g., "dubai_mall/digital_screens/mall_screen_a").

    Requires admin role.
    """
    from generators import mockup as mockup_generator

    # Sanitize path components to prevent path traversal attacks
    # For location_key with slashes, sanitize each segment
    location_key = "/".join(sanitize_path_component(seg) for seg in location_key.split("/"))
    photo_filename = sanitize_path_component(photo_filename)

    try:
        # Get the location to find which company schema owns it
        location_data = db.get_location_by_key(location_key, user.companies)
        if not location_data:
            raise HTTPException(status_code=403, detail=f"Location '{location_key}' not found in your accessible companies")
        company_schema = location_data.get("company") or location_data.get("company_schema")

        # If "all" is specified, find and delete the photo from whichever variation it's in
        if time_of_day == "all" or side == "all":
            # Use MockupFrameService to find the photo's variation (searches all companies)
            service = MockupFrameService(companies=user.companies)
            variations = await service.list_variations(location_key)
            for tod in variations:
                for sid in variations[tod]:
                    photos = await service.list_photos(location_key, tod, sid)
                    if photo_filename in photos:
                        success = await mockup_generator.delete_location_photo(location_key, photo_filename, company_schema, tod, sid)
                        if success:
                            return {"success": True}
                        else:
                            raise HTTPException(status_code=500, detail="Failed to delete photo")
            raise HTTPException(status_code=404, detail="Photo not found")
        else:
            success = await mockup_generator.delete_location_photo(location_key, photo_filename, company_schema, time_of_day, side)
            if success:
                return {"success": True}
            else:
                raise HTTPException(status_code=500, detail="Failed to delete photo")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[MOCKUP API] Error deleting photo: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/mockup/generate")
async def generate_mockup_api(
    request: Request,
    location_key: str = Form(...),
    time_of_day: str = Form("all"),
    side: str = Form("all"),
    environment: str = Form("outdoor"),
    ai_prompt: str | None = Form(None),
    creative: UploadFile | None = File(None),
    specific_photo: str | None = Form(None),
    storage_key: str | None = Form(None),
    frame_config: str | None = Form(None),
    user: AuthUser = Depends(require_permission("sales:mockups:generate"))
):
    """
    Generate a mockup by warping creative onto billboard (upload or AI-generated).

    NOTE: This REST API endpoint uses generators.mockup directly rather than MockupCoordinator
    because it has REST-specific requirements (specific_photo selection, frame_config override)
    that the coordinator doesn't support. The coordinator is designed for orchestrating
    chat/Slack workflows with automatic strategy selection.

    Args:
        location_key: Network key (e.g., "dubai_mall")
        storage_key: Optional storage key for traditional networks
                    (e.g., "dubai_mall/digital_screens/mall_screen_a").
                    If not provided, defaults to location_key.
        environment: "indoor" or "outdoor" (default "outdoor")

    Requires sales:mockups:generate permission.
    """
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
                logger.warning("[MOCKUP API] Invalid frame config JSON, ignoring")

        # Determine the actual storage key to use for generation
        # For traditional networks, storage_key comes from templates endpoint
        # For standalone networks, storage_key is same as location_key
        effective_storage_key = storage_key or location_key

        # Extract network_key from storage_key for validation
        # Storage key format: "network_key" (standalone) or "network_key/type_key/asset_key" (traditional)
        network_key = effective_storage_key.split("/")[0]

        # Validate network exists and user has access
        location_data = db.get_location_by_key(network_key, user.companies)
        if not location_data:
            # Fallback: check config.LOCATION_METADATA for backward compatibility
            if network_key not in config.LOCATION_METADATA:
                raise HTTPException(status_code=400, detail=f"Invalid location: {network_key}")
            company_schema = None
        else:
            company_schema = location_data.get("company") or location_data.get("company_schema")

        logger.info(f"[MOCKUP API] Generate request: network={network_key}, storage_key={effective_storage_key}, env={environment}")

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

        # Generate mockup (pass as list) with time_of_day, side, specific_photo, and config override
        # Pass company_hint for O(1) asset lookup (we already know which company owns this location)
        # Use effective_storage_key for traditional networks (e.g., "dubai_mall/digital_screens/mall_screen_a")
        result_path, photo_used = await mockup_generator.generate_mockup_async(
            effective_storage_key,  # Use storage key, not just network key
            [creative_path],
            time_of_day=time_of_day,
            side=side,
            environment=environment,  # Pass environment for indoor/outdoor filtering
            specific_photo=specific_photo,
            config_override=config_dict,
            company_schemas=user.companies,
            company_hint=company_schema,
        )

        if not result_path or not photo_used:
            # Log failed attempt
            db.log_mockup_usage(
                location_key=location_key,
                time_of_day=time_of_day,
                side=side,
                photo_used=specific_photo or "random",
                creative_type=creative_type or "unknown",
                company_schema=company_schema,
                ai_prompt=ai_prompt if ai_prompt else None,
                template_selected=template_selected,
                success=False,
                user_ip=client_ip,
            )
            raise HTTPException(status_code=500, detail="Failed to generate mockup")

        # Log successful generation
        db.log_mockup_usage(
            location_key=location_key,
            time_of_day=time_of_day,
            side=side,
            photo_used=photo_used,
            creative_type=creative_type,
            company_schema=company_schema,
            ai_prompt=ai_prompt if ai_prompt else None,
            template_selected=template_selected,
            success=True,
            user_ip=client_ip,
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
            filename=f"mockup_{location_key}_{time_of_day}_{side}.jpg",
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
                side=side,
                photo_used=specific_photo or "random",
                creative_type=creative_type or "unknown",
                company_schema=company_schema if 'company_schema' in locals() else "unknown",
                ai_prompt=ai_prompt if ai_prompt else None,
                template_selected=template_selected,
                success=False,
                user_ip=client_ip,
            )
        except Exception as log_error:
            logger.error(f"[MOCKUP API] Error logging usage: {log_error}")

        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# ELIGIBILITY ENDPOINTS
# =============================================================================


@router.get("/api/mockup/eligibility/setup")
async def get_setup_eligible_locations(
    user: AuthUser = Depends(require_permission("sales:mockups:read"))
):
    """
    Get locations eligible for mockup setup.

    Setup mode only allows networks (no packages) because frames are
    configured at the network level.

    Returns:
        List of eligible network locations
    """
    from core.services.mockup_eligibility import SetupEligibilityService

    if not user.has_company_access:
        raise HTTPException(
            status_code=403,
            detail="You don't have access to any company data."
        )

    try:
        service = SetupEligibilityService(user_companies=user.companies)
        locations = await service.get_eligible_locations()

        return {
            "locations": [loc.to_dict() for loc in locations],
            "count": len(locations),
        }
    except Exception as e:
        logger.error(f"[ELIGIBILITY API] Error getting setup locations: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/mockup/eligibility/generate")
async def get_generate_eligible_locations(
    user: AuthUser = Depends(require_permission("sales:mockups:read"))
):
    """
    Get locations eligible for mockup generation.

    Generate mode allows networks AND packages, but only those that have
    mockup frames configured.

    Returns:
        List of eligible networks and packages
    """
    from core.services.mockup_eligibility import GenerateFormEligibilityService

    if not user.has_company_access:
        raise HTTPException(
            status_code=403,
            detail="You don't have access to any company data."
        )

    try:
        service = GenerateFormEligibilityService(user_companies=user.companies)
        locations = await service.get_eligible_locations()

        return {
            "locations": [loc.to_dict() for loc in locations],
            "count": len(locations),
        }
    except Exception as e:
        logger.error(f"[ELIGIBILITY API] Error getting generate locations: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/mockup/eligibility/templates/{location_key}")
async def get_location_templates(
    location_key: str,
    user: AuthUser = Depends(require_permission("sales:mockups:read"))
):
    """
    Get all available templates for a location.

    If location is a package, returns templates from ALL networks in the package.
    If location is a network, returns templates for that network only.

    Args:
        location_key: Network key or package key

    Returns:
        List of available templates
    """
    from core.services.mockup_eligibility import GenerateFormEligibilityService

    if not user.has_company_access:
        raise HTTPException(
            status_code=403,
            detail="You don't have access to any company data."
        )

    try:
        service = GenerateFormEligibilityService(user_companies=user.companies)
        templates = await service.get_templates_for_location(location_key)

        return {
            "templates": [t.to_dict() for t in templates],
            "count": len(templates),
            "location_key": location_key,
        }
    except Exception as e:
        logger.error(f"[ELIGIBILITY API] Error getting templates for {location_key}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/mockup/eligibility/check")
async def check_location_eligibility(
    location_key: str = Form(...),
    mode: str = Form("generate"),
    user: AuthUser = Depends(require_permission("sales:mockups:read"))
):
    """
    Check if a location is eligible for a specific mode.

    Args:
        location_key: Network key or package key to check
        mode: "setup" or "generate"

    Returns:
        Eligibility status and reason if not eligible
    """
    from core.services.mockup_eligibility import (
        SetupEligibilityService,
        GenerateFormEligibilityService,
    )

    if not user.has_company_access:
        raise HTTPException(
            status_code=403,
            detail="You don't have access to any company data."
        )

    try:
        if mode == "setup":
            service = SetupEligibilityService(user_companies=user.companies)
        else:
            service = GenerateFormEligibilityService(user_companies=user.companies)

        result = await service.check_eligibility(location_key)

        return {
            "location_key": location_key,
            "mode": mode,
            "eligible": result.eligible,
            "reason": result.reason,
        }
    except Exception as e:
        logger.error(f"[ELIGIBILITY API] Error checking eligibility for {location_key}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# PACKAGE EXPANSION ENDPOINT
# =============================================================================


@router.get("/api/mockup/expand/{location_key}")
async def expand_location(
    location_key: str,
    user: AuthUser = Depends(require_permission("sales:mockups:read"))
):
    """
    Expand a location (package or network) to generation targets.

    For packages: returns all networks with their storage keys
    For networks: returns the single network with its storage keys

    This endpoint is useful for understanding what mockups will be generated
    for a given location.

    Args:
        location_key: Network key or package key

    Returns:
        List of generation targets with storage info
    """
    from core.services.mockup_service import PackageExpander

    if not user.has_company_access:
        raise HTTPException(
            status_code=403,
            detail="You don't have access to any company data."
        )

    try:
        expander = PackageExpander(user_companies=user.companies)
        targets = await expander.expand(location_key)

        return {
            "location_key": location_key,
            "targets": [t.to_dict() for t in targets],
            "count": len(targets),
            "total_storage_keys": sum(len(t.storage_keys) for t in targets),
        }
    except Exception as e:
        logger.error(f"[EXPAND API] Error expanding {location_key}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
