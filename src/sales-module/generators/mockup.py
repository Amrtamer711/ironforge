import logging
import os
from pathlib import Path

import cv2
import numpy as np

# Import compositing from effects module
from generators.effects import warp_creative_to_billboard
from core.utils.memory import cleanup_memory

logger = logging.getLogger("proposal-bot")

# Mockups storage directory
if os.path.exists("/data/"):
    MOCKUPS_DIR = Path("/data/mockups")
    logger.info(f"[MOCKUP INIT] Using PRODUCTION mockups directory: {MOCKUPS_DIR}")
else:
    MOCKUPS_DIR = Path(__file__).parent / "data" / "mockups"
    logger.info(f"[MOCKUP INIT] Using DEVELOPMENT mockups directory: {MOCKUPS_DIR}")

MOCKUPS_DIR.mkdir(parents=True, exist_ok=True)
logger.info(f"[MOCKUP INIT] Mockups directory exists: {MOCKUPS_DIR.exists()}, writable: {os.access(MOCKUPS_DIR, os.W_OK)}")


def get_location_photos_dir(
    company: str,
    location_key: str,
    environment: str = "outdoor",
    time_of_day: str = "day",
    side: str = "gold"
) -> Path:
    """Get the directory for a location's mockup photos.

    Structure:
    - Outdoor: mockups/{company}/{location_key}/outdoor/{time_of_day}/{side}
    - Indoor: mockups/{company}/{location_key}/indoor

    Example: mockups/backlite_dubai/triple_crown/outdoor/day/gold
    """
    if environment == "indoor":
        return MOCKUPS_DIR / company / location_key / "indoor"
    else:
        return MOCKUPS_DIR / company / location_key / "outdoor" / time_of_day / side


def save_location_photo(
    company: str,
    location_key: str,
    photo_filename: str,
    photo_data: bytes,
    environment: str = "outdoor",
    time_of_day: str = "day",
    side: str = "gold"
) -> Path:
    """Save a location photo to disk.

    Structure:
    - Outdoor: mockups/{company}/{location_key}/outdoor/{time_of_day}/{side}/{photo_filename}
    - Indoor: mockups/{company}/{location_key}/indoor/{photo_filename}
    """
    location_dir = get_location_photos_dir(company, location_key, environment, time_of_day, side)

    logger.info(f"[MOCKUP] Creating directory: {location_dir}")
    location_dir.mkdir(parents=True, exist_ok=True)

    photo_path = location_dir / photo_filename
    logger.info(f"[MOCKUP] Writing {len(photo_data)} bytes to: {photo_path}")

    try:
        photo_path.write_bytes(photo_data)

        # Verify the file was written correctly
        if photo_path.exists():
            actual_size = photo_path.stat().st_size
            logger.info(f"[MOCKUP] ✓ Photo saved successfully: {photo_path} ({actual_size} bytes)")

            # Verify we can read it back
            test_read = photo_path.read_bytes()
            if len(test_read) == len(photo_data):
                logger.info("[MOCKUP] ✓ Photo verified readable")
            else:
                logger.error(f"[MOCKUP] ✗ Photo size mismatch! Written: {len(photo_data)}, Read: {len(test_read)}")
        else:
            logger.error(f"[MOCKUP] ✗ Photo path does not exist after write: {photo_path}")

        # Note: Storage upload is now handled by asset-management service
        # Photo is saved locally here for fallback/caching, but primary storage
        # goes through the asset-management API

    except Exception as e:
        logger.error(f"[MOCKUP] ✗ Failed to save photo: {e}", exc_info=True)
        raise

    return photo_path


def list_location_photos(
    company: str,
    location_key: str,
    environment: str = "outdoor",
    time_of_day: str = "day",
    side: str = "gold"
) -> list[str]:
    """List all photo files for a location."""
    location_dir = get_location_photos_dir(company, location_key, environment, time_of_day, side)
    if not location_dir.exists():
        return []

    # Get all image files
    photos = []
    for ext in ['*.jpg', '*.jpeg', '*.png']:
        photos.extend([p.name for p in location_dir.glob(ext)])

    return sorted(photos)


async def generate_ai_creative(
    prompt: str,
    size: str = "1536x1024",
    location_key: str | None = None,
    user_id: str | None = None,
    provider: str | None = None,
    company_schemas: list[str] | None = None,
    company_hint: str | None = None,
) -> Path | None:
    """Generate a creative using AI image generation.

    Uses the unified LLMClient which supports multiple providers:
    - OpenAI: gpt-image-1 (default)
    - Google: gemini-2.5-flash-image, gemini-3-pro-image-preview

    Provider selection is controlled by config.IMAGE_PROVIDER or the provider arg.

    This function always applies the mockup system prompt to ensure the AI
    generates flat artwork (not billboards/mockups). Callers should pass
    just the user's creative brief - the system prompt is applied here.

    Args:
        prompt: User's creative brief (e.g., "Nike shoe ad with red background")
        size: Image size (default landscape "1536x1024")
        location_key: Optional location key to auto-detect portrait orientation
        user_id: Optional Slack user ID for cost tracking (None for website mockup)
        provider: Which provider to use ("openai" or "google").
                  If None, uses config.IMAGE_PROVIDER or defaults to "openai".
        company_schemas: List of company schemas to search
        company_hint: Optional company to try first for O(1) lookup

    Returns:
        Path to generated image, or None if failed
    """
    import tempfile

    from integrations.llm import LLMClient
    from integrations.llm.prompts.mockup import get_mockup_prompt

    # Get the image provider client (uses config.IMAGE_PROVIDER or falls back to LLM_PROVIDER)
    client = LLMClient.for_images(provider_name=provider)

    # Determine orientation from location (use async service for Asset-Management)
    is_portrait = False
    if location_key and company_schemas:
        from core.services.mockup_frame_service import MockupFrameService
        service = MockupFrameService(companies=company_schemas)
        is_portrait = await service.is_portrait(location_key, company_hint=company_hint)
    orientation = "portrait" if is_portrait else "landscape"

    # Apply the mockup system prompt with user's creative brief
    # This ensures AI generates flat artwork, not billboard mockups
    full_prompt = get_mockup_prompt(is_portrait=is_portrait, user_prompt=prompt)

    logger.info(f"[AI_CREATIVE] Generating {orientation} image with {client.provider_name}: {prompt[:100]}...")

    # Convert user_id to user_name for cost tracking
    from core.bo_messaging import get_user_real_name
    user_name = await get_user_real_name(user_id) if user_id and user_id != "website_mockup" else user_id

    temp_file_path = None
    try:
        # Generate image using unified client with standardized interface
        # Provider handles quality/orientation internally (Google: 4K, OpenAI: HD)
        response = await client.generate_image(
            prompt=full_prompt,
            quality="high",
            orientation=orientation,
            n=1,
            user_id=user_name,
            workflow="mockup_ai",
            context=f"location:{location_key}" if location_key else None,
        )

        if not response.images:
            logger.error("[AI_CREATIVE] No images returned from generation")
            return None

        image_data = response.images[0]
        logger.info(f"[AI_CREATIVE] Generated image: {len(image_data)} bytes")

        # Apply sharpening and quality enhancement to AI-generated image
        import io

        from PIL import Image

        # Load image from bytes
        pil_img = Image.open(io.BytesIO(image_data))
        img_array = np.array(pil_img)

        # Convert RGB to BGR for OpenCV
        if len(img_array.shape) == 3 and img_array.shape[2] == 3:
            img_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)

        # Apply strong sharpening to enhance detail after upscaling
        # Increased from 1.2x to 1.8x for much crisper output
        gaussian = cv2.GaussianBlur(img_array, (0, 0), 2.0)
        sharpened = cv2.addWeighted(img_array, 1.8, gaussian, -0.8, 0)

        # Apply stronger contrast enhancement for more vibrant images
        lab = cv2.cvtColor(sharpened, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        l = clahe.apply(l)
        enhanced = cv2.merge([l, a, b])
        enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)

        logger.info("[AI_CREATIVE] Applied strong sharpening (1.8x) and contrast enhancement (2.5 CLAHE) to AI image")

        # Save enhanced image to temp file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        temp_file_path = temp_file.name
        cv2.imwrite(temp_file_path, enhanced, [cv2.IMWRITE_PNG_COMPRESSION, 3])
        temp_file.close()

        logger.info(f"[AI_CREATIVE] Enhanced image saved to: {temp_file_path}")

        return Path(temp_file_path)

    except Exception as e:
        logger.error(f"[AI_CREATIVE] Error generating image: {e}", exc_info=True)
        # Clean up temp file on error
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except OSError as cleanup_err:
                logger.debug(f"[AI_CREATIVE] Failed to cleanup temp file {temp_file_path}: {cleanup_err}")
        return None


async def delete_location_photo(
    location_key: str,
    photo_filename: str,
    company_schema: str,
    time_of_day: str = "day",
    side: str = "gold",
) -> bool:
    """Delete a location photo and its frame data.

    Deletes frame data from Asset-Management database and local file.
    Also soft-deletes from storage system for audit purposes.

    Args:
        location_key: Location identifier
        photo_filename: Name of the photo file
        company_schema: Company schema to delete from (e.g., "backlite_dubai")
        time_of_day: Time of day variation
        side: Side type ("gold", "silver", or "single_side")

    Returns:
        True if deleted successfully
    """
    from integrations.asset_management import asset_mgmt_client

    try:
        # Delete from Asset-Management database (frame data)
        success = await asset_mgmt_client.delete_mockup_frame(
            company=company_schema,
            location_key=location_key,
            photo_filename=photo_filename,
            time_of_day=time_of_day,
            side=side,
        )

        if not success:
            logger.warning(f"[MOCKUP] Failed to delete frame from Asset-Management: {location_key}/{photo_filename}")

        # Delete local file if exists
        photo_path = get_location_photos_dir(company_schema, location_key, "outdoor", time_of_day, side) / photo_filename
        if photo_path.exists():
            photo_path.unlink()

        # Soft-delete from storage system if tracked
        try:
            from integrations.storage import soft_delete_mockup_by_location

            await soft_delete_mockup_by_location(
                location_key=location_key,
                photo_filename=photo_filename,
                time_of_day=time_of_day,
                side=side,
            )
        except Exception as track_err:
            logger.debug(f"[MOCKUP] Storage soft-delete skipped: {track_err}")

        logger.info(f"[MOCKUP] Deleted photo '{photo_filename}' for location '{location_key}/{time_of_day}/{side}'")
        return True
    except Exception as e:
        logger.error(f"[MOCKUP] Error deleting photo: {e}")
        return False


# =============================================================================
# ASYNC WRAPPER FOR ASSET-MANAGEMENT INTEGRATION
# =============================================================================


async def generate_mockup_async(
    location_key: str,
    creative_images: list[Path],
    output_path: Path | None = None,
    specific_photo: str | None = None,
    time_of_day: str = "all",
    side: str = "all",
    environment: str = "all",
    config_override: dict | None = None,
    company_schemas: list[str] | None = None,
    company_hint: str | None = None,
) -> tuple[Path | None, str | None]:
    """
    Async mockup generator that fetches data from Asset-Management.

    This wrapper:
    1. Fetches mockup photo from Asset-Management storage
    2. Gets frame data from Asset-Management API
    3. Calls the sync generator with the fetched data

    Args:
        location_key: The location identifier
        creative_images: List of creative/ad image paths
        output_path: Optional output path
        specific_photo: Optional specific photo filename
        time_of_day: Time of day variation ("day", "night", "all") - ignored for indoor
        side: Billboard side ("gold", "silver", "single_side", "all") - ignored for indoor
        environment: Environment ("indoor", "outdoor", "all")
        config_override: Optional config dict to override saved frame config
        company_schemas: List of company schemas to search
        company_hint: Optional company to try first for O(1) lookup (from WorkflowContext)

    Returns:
        Tuple of (Path to generated mockup, photo_filename used), or (None, None)
    """
    from core.services.mockup_frame_service import MockupFrameService

    # Require company_schemas - no fallback to hardcoded company
    if not company_schemas:
        raise ValueError("company_schemas is required for generate_mockup_async")
    companies = company_schemas
    service = MockupFrameService(companies=companies)

    logger.info(f"[MOCKUP_ASYNC] Generating mockup for {location_key} via Asset-Management")

    try:
        # Get photo and frame data from Asset-Management
        if specific_photo:
            # Use specific photo
            selected_tod = time_of_day if time_of_day != "all" else "day"
            selected_side = side if side != "all" else "gold"
            selected_env = environment if environment != "all" else "outdoor"

            photo_path = await service.download_photo(
                location_key, selected_tod, selected_side, specific_photo,
                environment=selected_env,
                company_hint=company_hint,
            )
            if not photo_path:
                logger.error(f"[MOCKUP_ASYNC] Failed to download specific photo: {specific_photo}")
                return None, None

            photo_filename = specific_photo
        else:
            # Get random photo
            result = await service.get_random_photo(
                location_key, time_of_day, side, environment=environment, company_hint=company_hint
            )
            if not result:
                logger.error(f"[MOCKUP_ASYNC] No photos available for {location_key}")
                return None, None

            photo_filename, selected_tod, selected_side, selected_env, photo_path = result

        # Get frame data
        frames_data = await service.get_frames(
            location_key, selected_tod, selected_side, photo_filename,
            environment=selected_env,
            company_hint=company_hint,
        )
        if not frames_data:
            logger.error(f"[MOCKUP_ASYNC] No frame data for {location_key}/{photo_filename}")
            # Cleanup downloaded photo
            if photo_path and photo_path.exists():
                photo_path.unlink()
            return None, None

        # Get config if available
        photo_config = await service.get_config(
            location_key, selected_tod, selected_side, photo_filename,
            environment=selected_env,
            company_hint=company_hint,
        )

        logger.info(
            f"[MOCKUP_ASYNC] Fetched photo and {len(frames_data)} frame(s) from Asset-Management"
        )

        # Now generate the mockup using the sync generator
        result_path = _generate_mockup_with_data(
            photo_path=photo_path,
            frames_data=frames_data,
            creative_images=creative_images,
            output_path=output_path,
            photo_config=photo_config,
            config_override=config_override,
            time_of_day=selected_tod,
        )

        # Cleanup downloaded photo temp file
        if photo_path and photo_path.exists():
            try:
                photo_path.unlink()
            except OSError:
                pass

        if result_path:
            return result_path, photo_filename
        return None, None

    except Exception as e:
        logger.error(f"[MOCKUP_ASYNC] Error generating mockup: {e}", exc_info=True)
        return None, None


def _generate_mockup_with_data(
    photo_path: Path,
    frames_data: list[dict],
    creative_images: list[Path],
    output_path: Path | None = None,
    photo_config: dict | None = None,
    config_override: dict | None = None,
    time_of_day: str = "day",
) -> Path | None:
    """
    Core mockup generation with pre-fetched photo and frame data.

    Args:
        photo_path: Path to the background photo
        frames_data: List of frame dicts with "points" and optional "config"
        creative_images: List of creative image paths
        output_path: Optional output path
        photo_config: Optional photo-level config
        config_override: Optional config override
        time_of_day: Time of day for effects

    Returns:
        Path to the generated mockup, or None
    """
    num_frames = len(frames_data)
    num_creatives = len(creative_images)

    logger.info(f"[MOCKUP] Using {num_frames} frame(s), {num_creatives} creative(s)")

    # Validate creative count
    if num_creatives != 1 and num_creatives != num_frames:
        logger.error(
            f"[MOCKUP] Invalid creative count: need 1 or {num_frames}, got {num_creatives}"
        )
        return None

    # Load billboard
    try:
        billboard = cv2.imread(str(photo_path))
        if billboard is None:
            logger.error(f"[MOCKUP] Failed to load billboard image: {photo_path}")
            return None
    except Exception as e:
        logger.error(f"[MOCKUP] Error loading billboard: {e}")
        return None

    # Start with the billboard as the result
    result = billboard.copy()

    # Apply each creative to each frame
    for i, frame_data in enumerate(frames_data):
        frame_points = frame_data["points"]
        frame_config = frame_data.get("config", {})

        # Merge configs: photo_config < frame_config < config_override
        merged_config = photo_config.copy() if photo_config else {}
        merged_config.update(frame_config)
        if config_override:
            merged_config.update(config_override)

        # Determine which creative to use
        creative_path = creative_images[0] if num_creatives == 1 else creative_images[i]

        # Load creative
        try:
            creative = cv2.imread(str(creative_path))
            if creative is None:
                logger.error(f"[MOCKUP] Failed to load creative: {creative_path}")
                return None
        except Exception as e:
            logger.error(f"[MOCKUP] Error loading creative {i}: {e}")
            return None

        # Warp creative onto this frame
        try:
            result = warp_creative_to_billboard(
                result, creative, frame_points, config=merged_config, time_of_day=time_of_day
            )
            logger.info(f"[MOCKUP] Applied creative {i+1}/{num_frames}")
        except Exception as e:
            logger.error(f"[MOCKUP] Error warping creative {i}: {e}")
            del billboard, result, creative
            cleanup_memory(context="mockup_warp_error", aggressive=False, log_stats=False)
            return None

        del creative

    # Save result
    if not output_path:
        import tempfile
        output_path = Path(tempfile.mktemp(suffix=".jpg"))

    try:
        cv2.imwrite(str(output_path), result)
        logger.info(f"[MOCKUP] Generated mockup saved to: {output_path}")

        del billboard, result
        cleanup_memory(context="mockup_save", aggressive=False, log_stats=False)

        return output_path
    except Exception as e:
        logger.error(f"[MOCKUP] Error saving mockup: {e}")
        try:
            del billboard, result
        except NameError:
            pass
        cleanup_memory(context="mockup_save_error", aggressive=False, log_stats=False)
        return None
