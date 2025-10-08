import os
import random
import cv2
import numpy as np
from pathlib import Path
from typing import Optional, Tuple, List
import logging

import config
import db

logger = logging.getLogger("proposal-bot")

# Mockups storage directory
if os.path.exists("/data/"):
    MOCKUPS_DIR = Path("/data/mockups")
else:
    MOCKUPS_DIR = Path(__file__).parent / "data" / "mockups"

MOCKUPS_DIR.mkdir(parents=True, exist_ok=True)


def order_points(pts: np.ndarray) -> np.ndarray:
    """Order points consistently: top-left, top-right, bottom-right, bottom-left"""
    pts = np.array(pts, dtype="float32")

    # Sort by y-coordinate (top to bottom)
    sorted_by_y = pts[np.argsort(pts[:, 1])]

    # Top two points
    top_points = sorted_by_y[:2]
    top_points = top_points[np.argsort(top_points[:, 0])]
    top_left, top_right = top_points

    # Bottom two points
    bottom_points = sorted_by_y[2:]
    bottom_points = bottom_points[np.argsort(bottom_points[:, 0])]
    bottom_left, bottom_right = bottom_points

    return np.array([top_left, top_right, bottom_right, bottom_left], dtype="float32")


def warp_creative_to_billboard(
    billboard_image: np.ndarray,
    creative_image: np.ndarray,
    frame_points: List[List[float]],
    config: Optional[dict] = None
) -> np.ndarray:
    """Apply perspective warp to place creative on billboard with optional enhancements."""
    # Apply config-based enhancements to creative before warping
    if config:
        brightness = config.get('brightness', 100) / 100.0
        contrast = config.get('contrast', 100) / 100.0
        saturation = config.get('saturation', 100) / 100.0
        lighting_adjustment = config.get('lightingAdjustment', 0)
        color_temperature = config.get('colorTemperature', 0)

        # Apply brightness and contrast
        creative_image = cv2.convertScaleAbs(creative_image, alpha=contrast, beta=(brightness - 1) * 100)

        # Apply saturation
        if saturation != 1.0:
            hsv = cv2.cvtColor(creative_image, cv2.COLOR_BGR2HSV).astype(np.float32)
            hsv[:, :, 1] = np.clip(hsv[:, :, 1] * saturation, 0, 255)
            creative_image = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

        # Apply lighting adjustment to match billboard
        if lighting_adjustment != 0:
            creative_image = cv2.convertScaleAbs(creative_image, alpha=1.0, beta=lighting_adjustment * 2)

        # Apply color temperature shift
        if color_temperature != 0:
            # Warm (positive): increase red/yellow, Cool (negative): increase blue
            creative_float = creative_image.astype(np.float32)
            if color_temperature > 0:
                # Warm: increase red and green (yellow)
                creative_float[:, :, 2] += color_temperature * 2  # Red
                creative_float[:, :, 1] += color_temperature * 1  # Green
            else:
                # Cool: increase blue
                creative_float[:, :, 0] += abs(color_temperature) * 2  # Blue
            creative_image = np.clip(creative_float, 0, 255).astype(np.uint8)

    # Order points consistently
    dst_pts = order_points(np.array(frame_points))

    # Source points (corners of creative image)
    h, w = creative_image.shape[:2]
    src_pts = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)

    # Get perspective transform matrix
    H = cv2.getPerspectiveTransform(src_pts, dst_pts)

    # Warp creative to billboard perspective with high-quality interpolation
    warped = cv2.warpPerspective(
        creative_image,
        H,
        (billboard_image.shape[1], billboard_image.shape[0]),
        flags=cv2.INTER_LANCZOS4,  # High-quality interpolation for smooth edges
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0)
    )

    # Create mask for the billboard area with anti-aliased edges
    mask = np.zeros(billboard_image.shape[:2], dtype=np.uint8)
    cv2.fillConvexPoly(mask, dst_pts.astype(int), 255)

    # Apply morphological operations for smoother edges
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    # Apply Gaussian blur to the mask for smooth anti-aliased blending
    # Use config blur strength if provided
    blur_strength = 15
    if config and 'blurStrength' in config:
        blur_strength = max(3, min(21, config['blurStrength']))  # Clamp to odd numbers between 3-21
        if blur_strength % 2 == 0:
            blur_strength += 1  # Ensure odd number for GaussianBlur

    mask_float = mask.astype(np.float32) / 255.0
    mask_float = cv2.GaussianBlur(mask_float, (blur_strength, blur_strength), 0)
    mask_float = np.clip(mask_float, 0, 1)

    # Convert to 3-channel mask for alpha blending
    mask_3ch = np.stack([mask_float] * 3, axis=-1)

    # Apply vignette to warped creative if configured
    if config and config.get('vignette', 0) > 0:
        vignette_strength = config['vignette'] / 100.0
        h, w = warped.shape[:2]
        # Create radial gradient mask
        y_coords, x_coords = np.ogrid[:h, :w]
        center_y, center_x = h / 2, w / 2
        distances = np.sqrt((x_coords - center_x) ** 2 + (y_coords - center_y) ** 2)
        max_distance = np.sqrt(center_x ** 2 + center_y ** 2)
        vignette_mask = 1 - (distances / max_distance) * vignette_strength
        vignette_mask = np.clip(vignette_mask, 0, 1)
        vignette_mask_3ch = np.stack([vignette_mask] * 3, axis=-1)
        warped = (warped.astype(np.float32) * vignette_mask_3ch).astype(np.uint8)

    # Apply shadow (darken edges) if configured
    if config and config.get('shadowIntensity', 0) > 0:
        shadow_strength = config['shadowIntensity'] / 100.0
        # Create edge shadow by using inverse of mask_float
        shadow_mask = 1 - (mask_float ** 0.5)  # Softer falloff
        shadow_mask = shadow_mask * shadow_strength
        shadow_mask_3ch = np.stack([shadow_mask] * 3, axis=-1)
        warped = (warped.astype(np.float32) * (1 - shadow_mask_3ch)).astype(np.uint8)

    # Alpha blend warped creative with billboard using smooth mask
    result = (billboard_image.astype(np.float32) * (1 - mask_3ch) +
              warped.astype(np.float32) * mask_3ch).astype(np.uint8)

    # Apply billboard overlay on top for realism if configured
    if config and config.get('overlayOpacity', 0) > 0:
        overlay_opacity = config['overlayOpacity'] / 100.0
        # Extract just the billboard region to overlay
        billboard_region = billboard_image.astype(np.float32) * mask_3ch
        # Blend billboard region on top of result with reduced opacity
        result = (result.astype(np.float32) * (1 - overlay_opacity * mask_3ch) +
                  billboard_region * overlay_opacity).astype(np.uint8)

    return result


def get_location_photos_dir(location_key: str, subfolder: str = "all") -> Path:
    """Get the directory for a location's mockup photos in a specific subfolder."""
    return MOCKUPS_DIR / location_key / subfolder


def save_location_photo(location_key: str, photo_filename: str, photo_data: bytes, subfolder: str = "all") -> Path:
    """Save a location photo to disk in a specific subfolder."""
    location_dir = get_location_photos_dir(location_key, subfolder)
    location_dir.mkdir(parents=True, exist_ok=True)

    photo_path = location_dir / photo_filename
    photo_path.write_bytes(photo_data)

    logger.info(f"[MOCKUP] Saved photo for location '{location_key}/{subfolder}': {photo_path}")
    return photo_path


def list_location_photos(location_key: str, subfolder: str = "all") -> List[str]:
    """List all photo files for a location in a specific subfolder."""
    location_dir = get_location_photos_dir(location_key, subfolder)
    if not location_dir.exists():
        return []

    # Get all image files
    photos = []
    for ext in ['*.jpg', '*.jpeg', '*.png']:
        photos.extend([p.name for p in location_dir.glob(ext)])

    return sorted(photos)


def get_random_location_photo(location_key: str, subfolder: str = "all") -> Optional[Tuple[str, str, Path]]:
    """Get a random photo for a location that has a frame configured. Returns (photo_filename, subfolder, photo_path)."""
    # Get photos with frames from database
    photos_with_frames = db.list_mockup_photos(location_key, subfolder)

    if not photos_with_frames:
        logger.warning(f"[MOCKUP] No photos with frames found for location '{location_key}/{subfolder}'")
        return None

    # Pick a random photo
    photo_filename = random.choice(photos_with_frames)
    photo_path = get_location_photos_dir(location_key, subfolder) / photo_filename

    if not photo_path.exists():
        logger.error(f"[MOCKUP] Photo file not found: {photo_path}")
        return None

    logger.info(f"[MOCKUP] Selected random photo for '{location_key}/{subfolder}': {photo_filename}")
    return photo_filename, subfolder, photo_path


async def generate_ai_creative(prompt: str, size: str = "1024x1024") -> Optional[Path]:
    """Generate a creative using OpenAI gpt-image-1 API."""
    import tempfile
    import base64
    from openai import AsyncOpenAI

    logger.info(f"[AI_CREATIVE] Generating image from prompt: {prompt[:100]}...")

    api_key = config.OPENAI_API_KEY
    if not api_key:
        logger.error("[AI_CREATIVE] No OpenAI API key configured")
        return None

    try:
        client = AsyncOpenAI(api_key=api_key)

        # Generate image
        img = await client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            n=1,
            size=size
        )

        # Extract base64 image data (automatically returned by gpt-image-1)
        b64_image = img.data[0].b64_json
        image_data = base64.b64decode(b64_image)

        # Save to temp file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        temp_file.write(image_data)
        temp_file.close()

        logger.info(f"[AI_CREATIVE] Generated image saved to: {temp_file.name}")

        return Path(temp_file.name)

    except Exception as e:
        logger.error(f"[AI_CREATIVE] Error generating image: {e}", exc_info=True)
        return None


def generate_mockup(
    location_key: str,
    creative_images: List[Path],
    output_path: Optional[Path] = None,
    specific_photo: Optional[str] = None,
    subfolder: str = "all"
) -> Optional[Path]:
    """
    Generate a mockup by warping creatives onto a location billboard.

    Args:
        location_key: The location identifier
        creative_images: List of creative/ad image paths (1 image = duplicate across frames, N images = 1 per frame)
        output_path: Optional output path (generates temp file if not provided)
        specific_photo: Optional specific photo filename to use (random if not provided)
        subfolder: Subfolder within location (default: "all")

    Returns:
        Path to the generated mockup image, or None if failed
    """
    logger.info(f"[MOCKUP] Generating mockup for location '{location_key}/{subfolder}' with {len(creative_images)} creative(s)")

    # Get billboard photo
    if specific_photo:
        photo_filename = specific_photo
        photo_path = get_location_photos_dir(location_key, subfolder) / photo_filename
        if not photo_path.exists():
            logger.error(f"[MOCKUP] Specific photo not found: {photo_path}")
            return None
    else:
        result = get_random_location_photo(location_key, subfolder)
        if not result:
            return None
        photo_filename, subfolder, photo_path = result

    # Get all frame coordinates (list of frames)
    frames_data = db.get_mockup_frames(location_key, photo_filename, subfolder)
    if not frames_data:
        logger.error(f"[MOCKUP] No frame coordinates found for '{location_key}/{subfolder}/{photo_filename}'")
        return None

    # Get config for this photo (if any)
    photo_config = db.get_mockup_config(location_key, photo_filename, subfolder)
    if photo_config:
        logger.info(f"[MOCKUP] Using saved config: {photo_config}")

    num_frames = len(frames_data)
    num_creatives = len(creative_images)

    logger.info(f"[MOCKUP] Using {num_frames} frame(s), {num_creatives} creative(s)")

    # Validate creative count
    if num_creatives != 1 and num_creatives != num_frames:
        logger.error(f"[MOCKUP] Invalid creative count: need 1 (duplicate) or {num_frames} (one per frame), got {num_creatives}")
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
    for i, frame_points in enumerate(frames_data):
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
                return None
        except Exception as e:
            logger.error(f"[MOCKUP] Error loading creative {i}: {e}")
            return None

        # Warp creative onto this frame
        try:
            result = warp_creative_to_billboard(result, creative, frame_points, config=photo_config)
            logger.info(f"[MOCKUP] Applied creative {i+1}/{num_frames} to frame {i+1}")
        except Exception as e:
            logger.error(f"[MOCKUP] Error warping creative {i}: {e}")
            return None

    # Save result
    if not output_path:
        import tempfile
        output_path = Path(tempfile.mktemp(suffix=".jpg"))

    try:
        cv2.imwrite(str(output_path), result)
        logger.info(f"[MOCKUP] Generated mockup saved to: {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"[MOCKUP] Error saving mockup: {e}")
        return None


def delete_location_photo(location_key: str, photo_filename: str, subfolder: str = "all") -> bool:
    """Delete a location photo and its frame data."""
    try:
        # Delete from database
        db.delete_mockup_frame(location_key, photo_filename, subfolder)

        # Delete file
        photo_path = get_location_photos_dir(location_key, subfolder) / photo_filename
        if photo_path.exists():
            photo_path.unlink()

        logger.info(f"[MOCKUP] Deleted photo '{photo_filename}' for location '{location_key}/{subfolder}'")
        return True
    except Exception as e:
        logger.error(f"[MOCKUP] Error deleting photo: {e}")
        return False
