import os
import random
import cv2
import numpy as np
from pathlib import Path
from typing import Optional, Tuple, List
import logging

import config
from db.database import db
from utils.memory import cleanup_memory

# Import compositing from effects module
from generators.effects import warp_creative_to_billboard, order_points

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


def get_location_photos_dir(location_key: str, time_of_day: str = "day", finish: str = "gold") -> Path:
    """Get the directory for a location's mockup photos with time_of_day and finish."""
    return MOCKUPS_DIR / location_key / time_of_day / finish


def save_location_photo(location_key: str, photo_filename: str, photo_data: bytes, time_of_day: str = "day", finish: str = "gold") -> Path:
    """Save a location photo to disk with time_of_day and finish."""
    location_dir = get_location_photos_dir(location_key, time_of_day, finish)

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
                logger.info(f"[MOCKUP] ✓ Photo verified readable")
            else:
                logger.error(f"[MOCKUP] ✗ Photo size mismatch! Written: {len(photo_data)}, Read: {len(test_read)}")
        else:
            logger.error(f"[MOCKUP] ✗ Photo path does not exist after write: {photo_path}")
    except Exception as e:
        logger.error(f"[MOCKUP] ✗ Failed to save photo: {e}", exc_info=True)
        raise

    return photo_path


def list_location_photos(location_key: str, time_of_day: str = "day", finish: str = "gold") -> List[str]:
    """List all photo files for a location with time_of_day and finish."""
    location_dir = get_location_photos_dir(location_key, time_of_day, finish)
    if not location_dir.exists():
        return []

    # Get all image files
    photos = []
    for ext in ['*.jpg', '*.jpeg', '*.png']:
        photos.extend([p.name for p in location_dir.glob(ext)])

    return sorted(photos)


def get_random_location_photo(location_key: str, time_of_day: str = "all", finish: str = "all") -> Optional[Tuple[str, str, str, Path]]:
    """Get a random photo for a location that has a frame configured. Returns (photo_filename, time_of_day, finish, photo_path)."""

    # Special handling for "all" - pick from filtered variations
    if time_of_day == "all" or finish == "all":
        # Get all variations available for this location
        variations = db.list_mockup_variations(location_key)
        if not variations:
            logger.warning(f"[MOCKUP] No variations found for location '{location_key}'")
            return None

        # Build list of all (time_of_day, finish, photo) tuples, filtered by specified dimension
        all_photos = []
        for tod in variations:
            # If user specified time_of_day, only use that one
            if time_of_day != "all" and tod != time_of_day:
                continue

            for fin in variations[tod]:
                # If user specified finish, only use that one
                if finish != "all" and fin != finish:
                    continue

                photos = db.list_mockup_photos(location_key, tod, fin)
                for photo in photos:
                    all_photos.append((photo, tod, fin))

        if not all_photos:
            filter_info = ""
            if time_of_day != "all":
                filter_info += f" time_of_day={time_of_day}"
            if finish != "all":
                filter_info += f" finish={finish}"
            logger.warning(f"[MOCKUP] No photos found for location '{location_key}'{filter_info}")
            return None

        # Pick random from filtered available photos
        photo_filename, selected_tod, selected_finish = random.choice(all_photos)
        photo_path = get_location_photos_dir(location_key, selected_tod, selected_finish) / photo_filename

        if not photo_path.exists():
            logger.error(f"[MOCKUP] Photo file not found: {photo_path}")
            return None

        filter_desc = []
        if time_of_day != "all":
            filter_desc.append(f"time={time_of_day}")
        if finish != "all":
            filter_desc.append(f"finish={finish}")
        filter_str = f" (filtered: {', '.join(filter_desc)})" if filter_desc else " (all variations)"
        logger.info(f"[MOCKUP] Selected random photo for '{location_key}'{filter_str}: {photo_filename} ({selected_tod}/{selected_finish})")
        return photo_filename, selected_tod, selected_finish, photo_path

    # Specific variation requested
    photos_with_frames = db.list_mockup_photos(location_key, time_of_day, finish)

    if not photos_with_frames:
        logger.warning(f"[MOCKUP] No photos with frames found for location '{location_key}/{time_of_day}/{finish}'")
        return None

    # Pick a random photo
    photo_filename = random.choice(photos_with_frames)
    photo_path = get_location_photos_dir(location_key, time_of_day, finish) / photo_filename

    if not photo_path.exists():
        logger.error(f"[MOCKUP] Photo file not found: {photo_path}")
        return None

    logger.info(f"[MOCKUP] Selected random photo for '{location_key}/{time_of_day}/{finish}': {photo_filename}")
    return photo_filename, time_of_day, finish, photo_path


def is_portrait_location(location_key: str) -> bool:
    """Check if a location has portrait orientation based on actual frame dimensions from database.

    Args:
        location_key: Location identifier

    Returns:
        True if height > width (portrait), False otherwise (landscape or unknown)
    """
    # Get any frame from this location to check dimensions
    variations = db.list_mockup_variations(location_key)
    if not variations:
        logger.warning(f"[ORIENTATION] No mockup frames found for '{location_key}'")
        return False  # Default to landscape if no frames

    # Get first available variation
    for time_of_day, finishes in variations.items():
        if finishes:
            finish = finishes[0]
            # Get any photo for this location
            photos = db.list_mockup_photos(location_key, time_of_day, finish)
            if photos:
                # Get frames from first photo
                frames_data = db.get_mockup_frames(location_key, photos[0], time_of_day, finish)
                if frames_data and len(frames_data) > 0:
                    # Extract first frame points: [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]
                    points = frames_data[0]["points"]

                    # Calculate width and height from the 4 corner points
                    # Width = average of top edge and bottom edge
                    # Height = average of left edge and right edge
                    import math

                    # Top edge length (point 0 to point 1)
                    top_width = math.sqrt((points[1][0] - points[0][0])**2 + (points[1][1] - points[0][1])**2)
                    # Bottom edge length (point 3 to point 2)
                    bottom_width = math.sqrt((points[2][0] - points[3][0])**2 + (points[2][1] - points[3][1])**2)
                    # Left edge length (point 0 to point 3)
                    left_height = math.sqrt((points[3][0] - points[0][0])**2 + (points[3][1] - points[0][1])**2)
                    # Right edge length (point 1 to point 2)
                    right_height = math.sqrt((points[2][0] - points[1][0])**2 + (points[2][1] - points[1][1])**2)

                    avg_width = (top_width + bottom_width) / 2
                    avg_height = (left_height + right_height) / 2

                    is_portrait = avg_height > avg_width
                    logger.info(f"[ORIENTATION] Location '{location_key}': frame dimensions {avg_width:.0f}x{avg_height:.0f}px → {'PORTRAIT' if is_portrait else 'LANDSCAPE'}")
                    return is_portrait

    logger.warning(f"[ORIENTATION] Could not determine orientation for '{location_key}'")
    return False  # Default to landscape if can't determine


async def generate_ai_creative(
    prompt: str,
    size: str = "1536x1024",
    location_key: Optional[str] = None,
    user_id: Optional[str] = None,
    provider: Optional[str] = None
) -> Optional[Path]:
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

    Returns:
        Path to generated image, or None if failed
    """
    import tempfile
    from integrations.llm import LLMClient
    from integrations.llm.prompts.mockup import get_mockup_prompt

    # Get the image provider client (uses config.IMAGE_PROVIDER or falls back to LLM_PROVIDER)
    client = LLMClient.for_images(provider_name=provider)

    # Determine orientation from location
    is_portrait = location_key and is_portrait_location(location_key)
    orientation = "portrait" if is_portrait else "landscape"

    # Apply the mockup system prompt with user's creative brief
    # This ensures AI generates flat artwork, not billboard mockups
    full_prompt = get_mockup_prompt(is_portrait=is_portrait, user_prompt=prompt)

    logger.info(f"[AI_CREATIVE] Generating {orientation} image with {client.provider_name}: {prompt[:100]}...")

    # Convert user_id to user_name for cost tracking
    from core.bo_messaging import get_user_real_name
    user_name = await get_user_real_name(user_id) if user_id and user_id != "website_mockup" else user_id

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
        cv2.imwrite(temp_file.name, enhanced, [cv2.IMWRITE_PNG_COMPRESSION, 3])
        temp_file.close()

        logger.info(f"[AI_CREATIVE] Enhanced image saved to: {temp_file.name}")

        return Path(temp_file.name)

    except Exception as e:
        logger.error(f"[AI_CREATIVE] Error generating image: {e}", exc_info=True)
        return None


def generate_mockup(
    location_key: str,
    creative_images: List[Path],
    output_path: Optional[Path] = None,
    specific_photo: Optional[str] = None,
    time_of_day: str = "day",
    finish: str = "gold",
    config_override: Optional[dict] = None
) -> Optional[Path]:
    """
    Generate a mockup by warping creatives onto a location billboard.

    Args:
        location_key: The location identifier
        creative_images: List of creative/ad image paths (1 image = duplicate across frames, N images = 1 per frame)
        output_path: Optional output path (generates temp file if not provided)
        specific_photo: Optional specific photo filename to use (random if not provided)
        time_of_day: Time of day variation (default: "day")
        finish: Billboard finish (default: "gold")
        config_override: Optional config dict to override saved frame config

    Returns:
        Tuple of (Path to the generated mockup image, photo_filename used), or (None, None) if failed
    """
    logger.info(f"[MOCKUP] Generating mockup for location '{location_key}/{time_of_day}/{finish}' with {len(creative_images)} creative(s)")

    # Get billboard photo
    if specific_photo:
        photo_filename = specific_photo
        photo_path = get_location_photos_dir(location_key, time_of_day, finish) / photo_filename
        if not photo_path.exists():
            logger.error(f"[MOCKUP] Specific photo not found: {photo_path}")
            return None, None
    else:
        result = get_random_location_photo(location_key, time_of_day, finish)
        if not result:
            return None, None
        photo_filename, time_of_day, finish, photo_path = result

    # Get all frame coordinates (list of frames)
    frames_data = db.get_mockup_frames(location_key, photo_filename, time_of_day, finish)
    if not frames_data:
        logger.error(f"[MOCKUP] No frame coordinates found for '{location_key}/{time_of_day}/{finish}/{photo_filename}'")
        return None, None

    # Get config for this photo (if any)
    photo_config = db.get_mockup_config(location_key, photo_filename, time_of_day, finish)
    if photo_config:
        logger.info(f"[MOCKUP] Using saved config: {photo_config}")

    num_frames = len(frames_data)
    num_creatives = len(creative_images)

    logger.info(f"[MOCKUP] Using {num_frames} frame(s), {num_creatives} creative(s)")

    # Validate creative count
    if num_creatives != 1 and num_creatives != num_frames:
        logger.error(f"[MOCKUP] Invalid creative count: need 1 (duplicate) or {num_frames} (one per frame), got {num_creatives}")
        return None, None

    # Load billboard
    try:
        billboard = cv2.imread(str(photo_path))
        if billboard is None:
            logger.error(f"[MOCKUP] Failed to load billboard image: {photo_path}")
            return None, None
    except Exception as e:
        logger.error(f"[MOCKUP] Error loading billboard: {e}")
        return None, None

    # Start with the billboard as the result
    result = billboard.copy()

    # Apply each creative to each frame
    for i, frame_data in enumerate(frames_data):
        # New format: {"points": [...], "config": {brightness: 100, blurStrength: 8, ...}}
        frame_points = frame_data["points"]
        frame_config = frame_data.get("config", {})

        logger.info(f"[MOCKUP] Frame {i+1} raw config: {frame_config}")

        # Merge configs: photo_config < frame_config < config_override (highest priority)
        merged_config = photo_config.copy() if photo_config else {}
        merged_config.update(frame_config)
        if config_override:
            merged_config.update(config_override)
            logger.info(f"[MOCKUP] Frame {i+1} applying config override: {config_override}")

        logger.info(f"[MOCKUP] Frame {i+1} merged config: {merged_config}")

        # Determine which creative to use
        if num_creatives == 1:
            creative_path = creative_images[0]  # Duplicate the same creative
        else:
            creative_path = creative_images[i]  # Use corresponding creative

        # Load creative
        try:
            creative = cv2.imread(str(creative_path))
            if creative is None:
                logger.error(f"[MOCKUP] Failed to load creative image: {creative_path}")
                return None, None
        except Exception as e:
            logger.error(f"[MOCKUP] Error loading creative {i}: {e}")
            return None, None

        # Warp creative onto this frame with merged config
        try:
            result = warp_creative_to_billboard(result, creative, frame_points, config=merged_config, time_of_day=time_of_day)
            edge_blur = merged_config.get('edgeBlur', 8)
            image_blur = merged_config.get('imageBlur', 0)
            logger.info(f"[MOCKUP] Applied creative {i+1}/{num_frames} to frame {i+1} (edge blur: {edge_blur}px, image blur: {image_blur})")
        except Exception as e:
            logger.error(f"[MOCKUP] Error warping creative {i}: {e}")
            # Cleanup on error
            del billboard, result, creative
            cleanup_memory(context="mockup_warp_error", aggressive=False, log_stats=False)
            return None, None

        # Explicitly delete creative image to free memory after each frame
        del creative

    # Save result
    if not output_path:
        import tempfile
        output_path = Path(tempfile.mktemp(suffix=".jpg"))

    try:
        cv2.imwrite(str(output_path), result)
        logger.info(f"[MOCKUP] Generated mockup saved to: {output_path}")

        # Cleanup large numpy arrays to free memory immediately
        del billboard, result
        cleanup_memory(context="mockup_save", aggressive=False, log_stats=False)

        return output_path, photo_filename
    except Exception as e:
        logger.error(f"[MOCKUP] Error saving mockup: {e}")
        # Cleanup on error
        try:
            del billboard, result
        except:
            pass
        cleanup_memory(context="mockup_save_error", aggressive=False, log_stats=False)
        return None, None


def delete_location_photo(location_key: str, photo_filename: str, time_of_day: str = "day", finish: str = "gold") -> bool:
    """Delete a location photo and its frame data."""
    try:
        # Delete from database
        db.delete_mockup_frame(location_key, photo_filename, time_of_day, finish)

        # Delete file
        photo_path = get_location_photos_dir(location_key, time_of_day, finish) / photo_filename
        if photo_path.exists():
            photo_path.unlink()

        logger.info(f"[MOCKUP] Deleted photo '{photo_filename}' for location '{location_key}/{time_of_day}/{finish}'")
        return True
    except Exception as e:
        logger.error(f"[MOCKUP] Error deleting photo: {e}")
        return False
