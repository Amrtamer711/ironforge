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
VALID_VENUE_TYPE = {"indoor", "outdoor"}


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


@router.get("/api/mockup/asset-types/{network_key}")
async def get_network_asset_types(
    network_key: str,
    user: AuthUser = Depends(require_permission("sales:mockups:read"))
):
    """
    Get asset types for a traditional network.

    Used by the mockup setup UI to show the asset type picker.
    For standalone networks, returns empty list (no asset type selection needed).

    Returns:
        {
            "network_key": str,
            "company": str,
            "is_standalone": bool,
            "asset_types": list[dict] - Type details with type_key, type_name, etc.
        }
    """
    from integrations.asset_management import asset_mgmt_client

    if not user.has_company_access:
        raise HTTPException(
            status_code=403,
            detail="You don't have access to any company data."
        )

    try:
        result = await asset_mgmt_client.get_network_asset_types(
            network_key=network_key,
            companies=user.companies,
        )

        if not result:
            raise HTTPException(status_code=404, detail=f"Network not found: {network_key}")

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[MOCKUP API] Error getting asset types for {network_key}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get asset types")


@router.post("/api/mockup/save-frame")
async def save_mockup_frame(
    location_keys: str = Form(..., max_length=5000),  # JSON array of location keys
    asset_type_key: str | None = Form(None),  # Required for traditional networks, ignored for standalone
    time_of_day: str = Form("day"),
    side: str = Form("gold"),
    venue_type: str = Form("outdoor"),  # indoor or outdoor (maps to environment)
    frames_data: str = Form(..., max_length=50000),
    photo: UploadFile = File(...),
    config_json: str | None = Form(None, max_length=10000),
    user: AuthUser = Depends(require_permission("sales:mockups:setup"))
):
    """Save a billboard photo with multiple frame coordinates to multiple locations.

    Args:
        location_keys: JSON array of location keys (e.g., '["network_a", "network_b"]')
        asset_type_key: Asset type key for traditional networks (e.g., 'digital_screens').
                       Required for traditional networks, ignored for standalone networks.
                       Storage key becomes: {network_key}/{asset_type_key}
        venue_type: "indoor" or "outdoor" - determines environment for storage
    """
    from generators import mockup as mockup_generator

    # Validate enum parameters
    if time_of_day not in VALID_TIME_OF_DAY:
        raise HTTPException(status_code=400, detail=f"Invalid time_of_day: {time_of_day}. Must be one of: {VALID_TIME_OF_DAY}")
    if side not in VALID_SIDE:
        raise HTTPException(status_code=400, detail=f"Invalid side: {side}. Must be one of: {VALID_SIDE}")
    if venue_type not in VALID_VENUE_TYPE:
        raise HTTPException(status_code=400, detail=f"Invalid venue_type: {venue_type}. Must be one of: {VALID_VENUE_TYPE}")

    # Parse location_keys JSON array
    try:
        locations = json.loads(location_keys)
        if not isinstance(locations, list) or len(locations) == 0:
            raise HTTPException(status_code=400, detail="location_keys must be a non-empty JSON array")
        # Validate each location key is a non-empty string
        for i, loc in enumerate(locations):
            if not isinstance(loc, str) or not loc.strip():
                raise HTTPException(status_code=400, detail=f"location_keys[{i}] must be a non-empty string")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid location_keys JSON array")

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
    logger.info(f"[MOCKUP API] RECEIVED location_keys: {locations}")
    logger.info(f"[MOCKUP API] RECEIVED asset_type_key: '{asset_type_key}'")
    logger.info(f"[MOCKUP API] RECEIVED time_of_day: '{time_of_day}'")
    logger.info(f"[MOCKUP API] RECEIVED side: '{side}'")
    logger.info(f"[MOCKUP API] RECEIVED venue_type: '{venue_type}'")
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

        # Read photo data
        logger.info(f"[MOCKUP API] Reading photo data from upload: {photo.filename}")
        photo_data = await photo.read()
        logger.info(f"[MOCKUP API] ✓ Read {len(photo_data)} bytes from upload")

        # Map venue_type to environment parameter
        environment = venue_type  # "indoor" or "outdoor"

        # Process each location
        asset_service = get_asset_service()
        from integrations.asset_management import asset_mgmt_client

        results = []
        failed_locations = []

        for network_key in locations:
            try:
                # Validate location exists and user has access
                has_access, error_msg = await asset_service.validate_location_access(network_key, user.companies)
                if not has_access:
                    failed_locations.append({"location": network_key, "error": error_msg or "Not accessible"})
                    continue

                # Determine which company schema to save to
                location_data = await asset_service.get_location_by_key(network_key, user.companies)
                if not location_data:
                    failed_locations.append({"location": network_key, "error": "Location not found"})
                    continue

                company_schema = location_data.get("company") or location_data.get("company_schema")
                if not company_schema:
                    failed_locations.append({"location": network_key, "error": "No company assigned"})
                    continue

                # Determine storage key based on network type
                # Get storage info to check if standalone or traditional
                storage_info = await asset_mgmt_client.get_mockup_storage_info(
                    network_key=network_key,
                    companies=user.companies,
                )

                is_standalone = storage_info.get("is_standalone", True) if storage_info else True

                if is_standalone:
                    # Standalone network: storage at network level
                    storage_key = network_key
                else:
                    # Traditional network: storage at asset type level
                    if not asset_type_key:
                        failed_locations.append({
                            "location": network_key,
                            "error": "asset_type_key required for traditional network"
                        })
                        continue
                    storage_key = f"{network_key}/{asset_type_key}"

                # Save via Asset-Management API (handles database + storage)
                logger.info(f"[MOCKUP API] Saving {len(frames)} frame(s) via asset-management for {company_schema}.{storage_key}/{time_of_day}/{side}/{environment}")
                result = await asset_mgmt_client.save_mockup_frame(
                    company=company_schema,
                    location_key=storage_key,  # Use storage_key (may include asset_type)
                    photo_data=photo_data,
                    photo_filename=photo.filename,
                    frames_data=frames,
                    time_of_day=time_of_day,
                    side=side,
                    environment=environment,
                    created_by=user.email,
                    config=config_dict,
                )
                if not result or not result.get("success"):
                    failed_locations.append({"location": network_key, "error": "Asset-management save failed"})
                    continue

                final_filename = result.get("photo_filename")
                logger.info(f"[MOCKUP API] ✓ Asset-management save complete for {storage_key}, filename: {final_filename}")

                # Save photo to disk with the final auto-numbered filename
                logger.info(f"[MOCKUP API] Saving photo to disk for {storage_key}: {final_filename}")
                photo_path = mockup_generator.save_location_photo(
                    company_schema, storage_key, final_filename, photo_data,
                    environment=environment, time_of_day=time_of_day, side=side
                )
                logger.info(f"[MOCKUP API] ✓ Photo saved to disk at: {photo_path}")

                # Verify the file exists immediately after saving
                if os.path.exists(photo_path):
                    file_size = os.path.getsize(photo_path)
                    logger.info(f"[MOCKUP API] ✓ VERIFICATION: File exists on disk, size: {file_size} bytes")
                else:
                    logger.error(f"[MOCKUP API] ✗ VERIFICATION FAILED: File does not exist at {photo_path}")

                results.append({
                    "location": network_key,
                    "storage_key": storage_key,
                    "asset_type_key": asset_type_key if not is_standalone else None,
                    "photo": final_filename,
                    "success": True,
                })
                logger.info(f"[MOCKUP API] ✓ Complete: Saved {len(frames)} frame(s) for {storage_key}/{time_of_day}/{side}/{final_filename}")

            except Exception as loc_error:
                logger.error(f"[MOCKUP API] Error saving to {network_key}: {loc_error}")
                failed_locations.append({"location": network_key, "error": str(loc_error)})

        # Return summary
        return {
            "success": len(failed_locations) == 0,
            "saved_count": len(results),
            "failed_count": len(failed_locations),
            "results": results,
            "failed": failed_locations,
            "time_of_day": time_of_day,
            "side": side,
            "venue_type": venue_type,
            "frames_count": len(frames),
        }

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

        # Get storage info - returns all asset types for traditional networks
        storage_info = await service.get_storage_info(location_key)

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
    - Standalone: mockups stored at network level (network_key)
    - Traditional: mockups stored at asset type level (network_key/type_key)

    Args:
        location_key: Network key
        time_of_day: Filter by "day", "night", or "all" (only applies to outdoor)
        side: Filter by "gold", "silver", "single_side", or "all" (only applies to outdoor)
        venue_type: Filter by "indoor", "outdoor", or "all"

    Returns:
        {
            "templates": [...],  # Filtered templates based on query params
            "available_configs": {  # ALL available configs (unfiltered, for dropdown filtering)
                "has_frames": bool,
                "available_venue_types": ["outdoor", "indoor"],
                "available_time_of_days": {"outdoor": ["day", "night"], ...},
                "available_sides": {"outdoor": {"day": ["gold", "silver"], ...}, ...}
            }
        }

    Requires sales:mockups:read permission.
    """
    try:
        service = MockupFrameService(companies=user.companies)

        # Step 1: Get storage info - returns all asset types for traditional networks
        storage_info = await service.get_storage_info(location_key)

        if not storage_info:
            # Fallback: try location_key directly (backward compatibility)
            storage_keys = [location_key]
            company = None
        else:
            storage_keys = storage_info.get("storage_keys", [location_key])
            company = storage_info.get("company")

        templates = []
        seen = set()  # Dedupe: (photo, storage_key, env, tod, side)

        # For available_configs computation (before filtering)
        all_venue_types = set()
        time_of_days_by_venue: dict[str, set[str]] = {}
        sides_by_venue_tod: dict[str, dict[str, set[str]]] = {}
        has_any_frames = False

        # Step 2: Fetch frames from EACH storage key
        # storage_key is "{network_key}/{type_key}" for traditional, "{network_key}" for standalone
        for storage_key in storage_keys:
            frames, frame_company = await service.get_all_frames(storage_key, company_hint=company)

            for frame in frames:
                env = frame.get("environment", "outdoor")
                tod = frame.get("time_of_day", "day")
                frame_side = frame.get("side", "gold")
                photo = frame.get("photo_filename")

                if not photo:
                    continue

                has_any_frames = True

                # === BUILD AVAILABLE_CONFIGS (from ALL frames, before filtering) ===
                all_venue_types.add(env)
                if env not in time_of_days_by_venue:
                    time_of_days_by_venue[env] = set()
                if env == "outdoor":
                    time_of_days_by_venue[env].add(tod)
                if env not in sides_by_venue_tod:
                    sides_by_venue_tod[env] = {}
                if env == "outdoor":
                    if tod not in sides_by_venue_tod[env]:
                        sides_by_venue_tod[env][tod] = set()
                    sides_by_venue_tod[env][tod].add(frame_side)

                # === APPLY FILTERS FOR RETURNED TEMPLATES ===
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
                    "storage_key": storage_key,  # "{network_key}/{type_key}" or "{network_key}"
                    "environment": env,
                    "time_of_day": tod,
                    "side": frame_side,
                    "frame_count": len(frames_data) if frames_data else 1,
                    "config": frame_config,
                    "company": frame_company or company,  # Company that owns this frame (for O(1) photo lookup)
                })

        # Build available_configs response (computed from ALL frames, not filtered)
        available_configs = {
            "has_frames": has_any_frames,
            "available_venue_types": sorted(all_venue_types),
            "available_time_of_days": {env: sorted(tods) for env, tods in time_of_days_by_venue.items()},
            "available_sides": {
                env: {tod: sorted(sides) for tod, sides in tods.items()}
                for env, tods in sides_by_venue_tod.items()
            },
        }

        return {
            "templates": templates,
            "available_configs": available_configs,
        }

    except Exception as e:
        logger.error(f"[MOCKUP API] Error listing templates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/mockup/photo/{location_key:path}")
async def get_mockup_photo(
    location_key: str,
    photo_filename: str,  # Query param - required
    time_of_day: str = "all",
    side: str = "all",
    company: str | None = None,  # Query param - company hint for O(1) lookup (from templates response)
    background_tasks: BackgroundTasks = None,
    user: AuthUser = Depends(require_permission("sales:mockups:read")),
):
    """
    Get a specific photo file from Asset-Management storage.

    Args:
        location_key: Path param - supports slashes for traditional networks
                      (e.g., "dubai_mall/digital_screens/mall_screen_a")
        photo_filename: Query param - the photo file to retrieve
        company: Query param - optional company hint for O(1) lookup (avoids searching all companies)

    Requires sales:mockups:read permission.
    """
    # Sanitize path components to prevent path traversal attacks
    # For location_key with slashes, sanitize each segment
    location_key = "/".join(sanitize_path_component(seg) for seg in location_key.split("/"))
    photo_filename = sanitize_path_component(photo_filename)

    logger.info(f"[PHOTO GET] Request for photo: {location_key}/{photo_filename} (time_of_day={time_of_day}, side={side}, company={company})")

    # Use MockupFrameService to fetch from Asset-Management
    # Pass company hint to avoid searching all companies sequentially
    service = MockupFrameService(companies=user.companies)

    if time_of_day == "all" or side == "all":
        # OPTIMIZED: Fetch all frames once, then do O(1) lookup instead of N API calls
        # Pass company hint for direct lookup (avoids 4 sequential API calls)
        frames, found_company = await service.get_all_frames(location_key, company_hint=company)
        effective_company = found_company or company  # Use found company or fall back to hint

        # Build photo lookup dict for O(1) access
        photo_lookup = {}
        for frame in frames:
            photo = frame.get("photo_filename")
            if photo:
                photo_lookup[photo] = (
                    frame.get("time_of_day", "day"),
                    frame.get("side", "gold")
                )

        logger.info(f"[PHOTO GET] Found {len(photo_lookup)} photos for {location_key} (company={effective_company})")

        # O(1) lookup instead of nested loops with API calls
        if photo_filename in photo_lookup:
            tod, sid = photo_lookup[photo_filename]
            # Pass company hint to download_photo for O(1) storage lookup
            photo_path = await service.download_photo(location_key, tod, sid, photo_filename, company_hint=effective_company)
            if photo_path and photo_path.exists():
                file_size = os.path.getsize(photo_path)
                logger.info(f"[PHOTO GET] ✓ FOUND: {photo_path} ({file_size} bytes)")

                # Schedule cleanup after response is sent
                if background_tasks:
                    background_tasks.add_task(os.unlink, photo_path)

                return FileResponse(photo_path, filename=photo_filename)
    else:
        # Direct lookup with specific time_of_day and side
        # Pass company hint for O(1) storage lookup
        photo_path = await service.download_photo(location_key, time_of_day, side, photo_filename, company_hint=company)
        if photo_path and photo_path.exists():
            file_size = os.path.getsize(photo_path)
            logger.info(f"[PHOTO GET] ✓ FOUND: {photo_path} ({file_size} bytes)")

            # Schedule cleanup after response is sent
            if background_tasks:
                background_tasks.add_task(os.unlink, photo_path)

            return FileResponse(photo_path, filename=photo_filename)

    logger.error(f"[PHOTO GET] ✗ Photo not found: {location_key}/{photo_filename}")
    raise HTTPException(status_code=404, detail=f"Photo not found: {photo_filename}")


@router.delete("/api/mockup/photo/{location_key:path}")
async def delete_mockup_photo(
    location_key: str,
    photo_filename: str,  # Query param - required
    time_of_day: str = "all",
    side: str = "all",
    user: AuthUser = Depends(require_permission("sales:mockups:setup"))
):
    """
    Delete a photo and its frame.

    Args:
        location_key: Path param - supports slashes for traditional networks
                      (e.g., "dubai_mall/digital_screens/mall_screen_a")
        photo_filename: Query param - the photo file to delete

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
            # OPTIMIZED: Fetch all frames once, then do O(1) lookup instead of N API calls
            service = MockupFrameService(companies=user.companies)
            frames, _ = await service.get_all_frames(location_key)

            # Build photo lookup dict for O(1) access
            photo_lookup = {}
            for frame in frames:
                photo = frame.get("photo_filename")
                if photo:
                    photo_lookup[photo] = (
                        frame.get("time_of_day", "day"),
                        frame.get("side", "gold")
                    )

            # O(1) lookup instead of nested loops with API calls
            if photo_filename in photo_lookup:
                tod, sid = photo_lookup[photo_filename]
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

    Unified Architecture Support:
    - If storage_key provided: Generate single mockup for that specific storage path (FileResponse)
    - If storage_key NOT provided AND standalone network: Generate single mockup (FileResponse)
    - If storage_key NOT provided AND traditional network: Auto-iterate all asset types,
      generate one mockup per compatible type, return JSON with multiple images

    Args:
        location_key: Network key (e.g., "dubai_mall")
        storage_key: Optional storage key for specific template
                    (e.g., "dubai_mall/digital_screens" for type-level).
                    If provided, generates single mockup for that storage path.
                    If not provided for traditional networks, auto-generates for all types.
        environment: "indoor" or "outdoor" (default "outdoor")

    Returns:
        FileResponse for single mockup OR JSON for multi-type generation:
        {
            "multi_type": true,
            "mockups": [{"storage_key": ..., "type_key": ..., "image_base64": ..., ...}],
            "skipped_types": [...],
            "creative_type": "ai_generated" | "uploaded"
        }

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

        # Validate network exists and user has access
        network_key = location_key  # location_key IS the network_key
        location_data = db.get_location_by_key(network_key, user.companies)
        if not location_data:
            # Fallback: check config.LOCATION_METADATA for backward compatibility
            if network_key not in config.LOCATION_METADATA:
                raise HTTPException(status_code=400, detail=f"Invalid location: {network_key}")
            company_schema = None
        else:
            company_schema = location_data.get("company") or location_data.get("company_schema")

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

        # Check if this is a multi-type generation scenario
        # Multi-type: traditional network + no storage_key provided + no specific_photo
        from integrations.asset_management import asset_mgmt_client
        import base64

        storage_info_result = await asset_mgmt_client.get_mockup_storage_info(
            network_key=network_key,
            companies=user.companies,
        )

        is_standalone = storage_info_result.get("is_standalone", True) if storage_info_result else True
        asset_types = storage_info_result.get("asset_types", []) if storage_info_result else []

        # Determine if multi-type generation is needed
        # Multi-type: traditional network + no storage_key explicitly provided + no specific_photo
        is_multi_type = (
            not is_standalone
            and not storage_key
            and not specific_photo
            and len(asset_types) > 0
        )

        logger.info(f"[MOCKUP API] Generate request: network={network_key}, is_standalone={is_standalone}, is_multi_type={is_multi_type}, storage_key={storage_key}")

        if is_multi_type:
            # MULTI-TYPE GENERATION: Iterate all asset types and generate one mockup per compatible type
            logger.info(f"[MOCKUP API] Multi-type generation for traditional network {network_key} with {len(asset_types)} asset types")

            service = MockupFrameService(companies=user.companies)
            generated_mockups = []
            skipped_types = []

            for asset_type in asset_types:
                type_key = asset_type.get("type_key")
                type_name = asset_type.get("type_name", type_key)
                type_storage_key = asset_type.get("storage_key")  # "{network_key}/{type_key}"

                logger.info(f"[MOCKUP API] Checking asset type: {type_key} at {type_storage_key}")

                # Get frames for this type and check for compatible config
                frames, _ = await service.get_all_frames(type_storage_key, company_hint=company_schema)

                if not frames:
                    skipped_types.append({
                        "type_key": type_key,
                        "type_name": type_name,
                        "reason": "no_frames"
                    })
                    continue

                # Filter frames by environment, time_of_day, and side
                compatible_frames = []
                for frame in frames:
                    frame_env = frame.get("environment", "outdoor")
                    frame_tod = frame.get("time_of_day", "day")
                    frame_side = frame.get("side", "gold")

                    # Environment must match (or filter is "all")
                    if environment != "all" and frame_env != environment:
                        continue

                    # For outdoor, check time_of_day and side
                    if frame_env == "outdoor":
                        if time_of_day != "all" and frame_tod != time_of_day:
                            continue
                        if side != "all" and frame_side != side:
                            continue

                    compatible_frames.append(frame)

                if not compatible_frames:
                    skipped_types.append({
                        "type_key": type_key,
                        "type_name": type_name,
                        "reason": "no_compatible_frames",
                        "requested_config": {"environment": environment, "time_of_day": time_of_day, "side": side}
                    })
                    continue

                # Generate mockup for this type
                try:
                    result_path, photo_used = await mockup_generator.generate_mockup_async(
                        type_storage_key,
                        [creative_path],
                        time_of_day=time_of_day,
                        side=side,
                        environment=environment,
                        specific_photo=None,  # Let it pick randomly from compatible
                        config_override=config_dict,
                        company_schemas=user.companies,
                        company_hint=company_schema,
                    )

                    if result_path and photo_used:
                        # Read image and encode as base64
                        with open(result_path, "rb") as img_file:
                            image_base64 = base64.b64encode(img_file.read()).decode("utf-8")

                        generated_mockups.append({
                            "storage_key": type_storage_key,
                            "type_key": type_key,
                            "type_name": type_name,
                            "image_base64": image_base64,
                            "photo_used": photo_used,
                        })

                        # Log success
                        db.log_mockup_usage(
                            location_key=location_key,
                            time_of_day=time_of_day,
                            side=side,
                            photo_used=photo_used,
                            creative_type=creative_type,
                            company_schema=company_schema,
                            ai_prompt=ai_prompt if ai_prompt else None,
                            template_selected=False,
                            success=True,
                            user_ip=client_ip,
                        )

                        # Cleanup temp result file
                        if result_path.exists():
                            result_path.unlink()
                    else:
                        skipped_types.append({
                            "type_key": type_key,
                            "type_name": type_name,
                            "reason": "generation_failed"
                        })

                except Exception as gen_error:
                    logger.error(f"[MOCKUP API] Error generating mockup for type {type_key}: {gen_error}")
                    skipped_types.append({
                        "type_key": type_key,
                        "type_name": type_name,
                        "reason": f"error: {str(gen_error)}"
                    })

            # Cleanup creative file
            if creative_path and creative_path.exists():
                creative_path.unlink()

            if not generated_mockups:
                raise HTTPException(
                    status_code=404,
                    detail=f"No compatible frames found for any asset type with config: environment={environment}, time_of_day={time_of_day}, side={side}"
                )

            logger.info(f"[MOCKUP API] Multi-type generation complete: {len(generated_mockups)} mockups, {len(skipped_types)} skipped")

            return {
                "multi_type": True,
                "network_key": network_key,
                "mockups": generated_mockups,
                "skipped_types": skipped_types,
                "creative_type": creative_type,
                "config": {
                    "environment": environment,
                    "time_of_day": time_of_day,
                    "side": side,
                }
            }

        # SINGLE MOCKUP GENERATION (standalone or explicit storage_key provided)
        # Determine the actual storage key to use for generation
        effective_storage_key = storage_key or network_key

        logger.info(f"[MOCKUP API] Single mockup generation: storage_key={effective_storage_key}, env={environment}")

        # Generate mockup (pass as list) with time_of_day, side, specific_photo, and config override
        result_path, photo_used = await mockup_generator.generate_mockup_async(
            effective_storage_key,
            [creative_path],
            time_of_day=time_of_day,
            side=side,
            environment=environment,
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
    Get all available templates for a location with available config combinations.

    If location is a package, returns templates from ALL networks in the package.
    If location is a network, returns templates for that network only.

    Args:
        location_key: Network key or package key

    Returns:
        {
            "templates": [...],
            "count": int,
            "location_key": str,
            "available_configs": {
                "has_frames": bool,
                "available_venue_types": ["outdoor", "indoor"],
                "available_time_of_days": {"outdoor": ["day", "night"], ...},
                "available_sides": {"outdoor": {"day": ["gold", "silver"], ...}, ...}
            }
        }
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
        # Efficient: derive available_configs from already-fetched templates (no duplicate API calls)
        available_configs = service.get_available_configs_from_templates(templates, location_key)

        return {
            "templates": [t.to_dict() for t in templates],
            "count": len(templates),
            "location_key": location_key,
            "available_configs": available_configs,
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
