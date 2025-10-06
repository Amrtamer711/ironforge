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
    frame_points: List[List[float]]
) -> np.ndarray:
    """Apply perspective warp to place creative on billboard."""
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

    # Create mask for the billboard area
    mask = np.zeros(billboard_image.shape[:2], dtype=np.uint8)
    cv2.fillConvexPoly(mask, dst_pts.astype(int), 255)
    mask_inv = cv2.bitwise_not(mask)

    # Mask out the billboard area from the background
    bg_masked = cv2.bitwise_and(billboard_image, billboard_image, mask=mask_inv)

    # Combine background and warped creative
    result = cv2.add(bg_masked, warped)

    return result


def get_location_photos_dir(location_key: str) -> Path:
    """Get the directory for a location's mockup photos."""
    return MOCKUPS_DIR / location_key


def save_location_photo(location_key: str, photo_filename: str, photo_data: bytes) -> Path:
    """Save a location photo to disk."""
    location_dir = get_location_photos_dir(location_key)
    location_dir.mkdir(parents=True, exist_ok=True)

    photo_path = location_dir / photo_filename
    photo_path.write_bytes(photo_data)

    logger.info(f"[MOCKUP] Saved photo for location '{location_key}': {photo_path}")
    return photo_path


def list_location_photos(location_key: str) -> List[str]:
    """List all photo files for a location."""
    location_dir = get_location_photos_dir(location_key)
    if not location_dir.exists():
        return []

    # Get all image files
    photos = []
    for ext in ['*.jpg', '*.jpeg', '*.png']:
        photos.extend([p.name for p in location_dir.glob(ext)])

    return sorted(photos)


def get_random_location_photo(location_key: str) -> Optional[Tuple[str, Path]]:
    """Get a random photo for a location that has a frame configured."""
    # Get photos with frames from database
    photos_with_frames = db.list_mockup_photos(location_key)

    if not photos_with_frames:
        logger.warning(f"[MOCKUP] No photos with frames found for location '{location_key}'")
        return None

    # Pick a random photo
    photo_filename = random.choice(photos_with_frames)
    photo_path = get_location_photos_dir(location_key) / photo_filename

    if not photo_path.exists():
        logger.error(f"[MOCKUP] Photo file not found: {photo_path}")
        return None

    logger.info(f"[MOCKUP] Selected random photo for '{location_key}': {photo_filename}")
    return photo_filename, photo_path


async def generate_ai_creative(prompt: str, size: str = "1024x1024") -> Optional[Path]:
    """Generate a creative using OpenAI gpt-image-1 API."""
    import tempfile
    import aiohttp
    import base64

    logger.info(f"[AI_CREATIVE] Generating image from prompt: {prompt[:100]}...")

    api_key = config.OPENAI_API_KEY
    if not api_key:
        logger.error("[AI_CREATIVE] No OpenAI API key configured")
        return None

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.openai.com/v1/images/generations",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}"
                },
                json={
                    "model": "gpt-image-1",
                    "prompt": prompt,
                    "n": 1,
                    "size": size,
                    "quality": "high",
                    "response_format": "b64_json"
                }
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"[AI_CREATIVE] API error: {error_text}")
                    return None

                data = await resp.json()

                # Extract base64 image data
                b64_image = data["data"][0]["b64_json"]
                image_data = base64.b64decode(b64_image)

                # Save to temp file
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
                temp_file.write(image_data)
                temp_file.close()

                logger.info(f"[AI_CREATIVE] Generated image saved to: {temp_file.name}")

                # Log usage stats if available
                if "usage" in data:
                    usage = data["usage"]
                    logger.info(f"[AI_CREATIVE] Token usage - Total: {usage.get('total_tokens')}, "
                               f"Input: {usage.get('input_tokens')}, Output: {usage.get('output_tokens')}")

                return Path(temp_file.name)

    except Exception as e:
        logger.error(f"[AI_CREATIVE] Error generating image: {e}", exc_info=True)
        return None


def generate_mockup(
    location_key: str,
    creative_images: List[Path],
    output_path: Optional[Path] = None,
    specific_photo: Optional[str] = None
) -> Optional[Path]:
    """
    Generate a mockup by warping creatives onto a location billboard.

    Args:
        location_key: The location identifier
        creative_images: List of creative/ad image paths (1 image = duplicate across frames, N images = 1 per frame)
        output_path: Optional output path (generates temp file if not provided)
        specific_photo: Optional specific photo filename to use (random if not provided)

    Returns:
        Path to the generated mockup image, or None if failed
    """
    logger.info(f"[MOCKUP] Generating mockup for location '{location_key}' with {len(creative_images)} creative(s)")

    # Get billboard photo
    if specific_photo:
        photo_filename = specific_photo
        photo_path = get_location_photos_dir(location_key) / photo_filename
        if not photo_path.exists():
            logger.error(f"[MOCKUP] Specific photo not found: {photo_path}")
            return None
    else:
        result = get_random_location_photo(location_key)
        if not result:
            return None
        photo_filename, photo_path = result

    # Get all frame coordinates (list of frames)
    frames_data = db.get_mockup_frames(location_key, photo_filename)
    if not frames_data:
        logger.error(f"[MOCKUP] No frame coordinates found for '{location_key}/{photo_filename}'")
        return None

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
            result = warp_creative_to_billboard(result, creative, frame_points)
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


def delete_location_photo(location_key: str, photo_filename: str) -> bool:
    """Delete a location photo and its frame data."""
    try:
        # Delete from database
        db.delete_mockup_frame(location_key, photo_filename)

        # Delete file
        photo_path = get_location_photos_dir(location_key) / photo_filename
        if photo_path.exists():
            photo_path.unlink()

        logger.info(f"[MOCKUP] Deleted photo '{photo_filename}' for location '{location_key}'")
        return True
    except Exception as e:
        logger.error(f"[MOCKUP] Error deleting photo: {e}")
        return False
