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
    """Order points consistently: top-left, top-right, bottom-right, bottom-left."""
    pts = np.array(pts, dtype="float32")

    if pts.shape != (4, 2):
        raise ValueError(f"Expected 4 corner points with shape (4, 2), got {pts.shape}")

    rect = np.zeros((4, 2), dtype="float32")

    # The sum of coordinates identifies the top-left (smallest) and bottom-right (largest)
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]  # top-left
    rect[2] = pts[np.argmax(s)]  # bottom-right

    # The difference identifies the top-right (smallest) and bottom-left (largest)
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]  # top-right
    rect[3] = pts[np.argmax(diff)]  # bottom-left

    # Ensure clockwise ordering (positive area) to avoid inverted transforms
    tl, tr, br, bl = rect
    cross = (tr[0] - tl[0]) * (br[1] - tl[1]) - (tr[1] - tl[1]) * (br[0] - tl[0])
    if cross < 0:
        rect[1], rect[3] = rect[3], rect[1]

    return rect


def warp_creative_to_billboard(
    billboard_image: np.ndarray,
    creative_image: np.ndarray,
    frame_points: List[List[float]],
    config: Optional[dict] = None
) -> np.ndarray:
    """Apply perspective warp to place creative on billboard with optional enhancements."""
    # Order points consistently
    dst_pts = order_points(np.array(frame_points))

    # Creative will stretch to fill the entire frame for maximum realism
    # The perspective transform handles the warping - no black bars/padding

    # Upscale creative before warping for higher quality
    upscale_factor = 2.0  # 2x upscale - good balance of quality and performance
    creative_upscaled = cv2.resize(
        creative_image,
        None,
        fx=upscale_factor,
        fy=upscale_factor,
        interpolation=cv2.INTER_CUBIC
    )
    logger.info(f"[MOCKUP] Upscaled creative {creative_image.shape[:2]} -> {creative_upscaled.shape[:2]}")

    # Apply optional image blur AFTER upscaling (so blur effect is preserved)
    image_blur = config.get('imageBlur', 0) if config else 0
    logger.info(f"[MOCKUP] Config received: {config}")
    logger.info(f"[MOCKUP] Image blur value from config: {image_blur}")

    if image_blur > 0:
        # Use kernel size that scales with blur intensity
        kernel_size = int(image_blur * 2 + 1)
        if kernel_size % 2 == 0:
            kernel_size += 1  # Ensure odd
        creative_upscaled = cv2.GaussianBlur(creative_upscaled, (kernel_size, kernel_size), 0)
        logger.info(f"[MOCKUP] Applied image blur with strength {image_blur} (kernel: {kernel_size})")

    # Source points (corners of upscaled creative image)
    h, w = creative_upscaled.shape[:2]
    src_pts = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)

    # Destination points
    adjusted_dst_pts = dst_pts.copy()

    # Apply depth perception adjustment if configured
    if config and 'depthMultiplier' in config:
        # Range 5-30, default 15
        # Lower values (5-14) = increase perspective (pull corners outward)
        # Higher values (16-30) = flatten perspective (push corners inward)
        depth_value = config['depthMultiplier']

        # Calculate scaling factor: 15 = 1.0 (no change), 5 = 1.2 (more perspective), 30 = 0.7 (flatter)
        scale_factor = 1.0 + (15 - depth_value) * 0.02

        # Calculate the center of the billboard frame
        center_x = np.mean(adjusted_dst_pts[:, 0])
        center_y = np.mean(adjusted_dst_pts[:, 1])

        # Adjust each corner point based on depth perception
        for i in range(4):
            dx = adjusted_dst_pts[i, 0] - center_x
            dy = adjusted_dst_pts[i, 1] - center_y

            # Scale the distance from center
            adjusted_dst_pts[i, 0] = center_x + dx * scale_factor
            adjusted_dst_pts[i, 1] = center_y + dy * scale_factor

        logger.info(f"[MOCKUP] Applied depth perception with value {depth_value} (scale factor: {scale_factor:.2f})")

    # Get perspective transform matrix
    H = cv2.getPerspectiveTransform(src_pts, adjusted_dst_pts)

    # Warp upscaled creative to billboard perspective with high-quality interpolation
    warped = cv2.warpPerspective(
        creative_upscaled,
        H,
        (billboard_image.shape[1], billboard_image.shape[0]),
        flags=cv2.INTER_LANCZOS4,  # High-quality interpolation for smooth edges
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0)
    )

    # Create high-quality anti-aliased mask using super-sampling
    # Super-sample at 4x resolution for smooth edges without jaggies
    supersample_factor = 4
    h_hires = billboard_image.shape[0] * supersample_factor
    w_hires = billboard_image.shape[1] * supersample_factor

    # Scale destination points to high-res space
    dst_pts_hires = adjusted_dst_pts * supersample_factor

    # Draw mask at high resolution with anti-aliased lines
    mask_hires = np.zeros((h_hires, w_hires), dtype=np.uint8)
    cv2.fillPoly(mask_hires, [dst_pts_hires.astype(np.int32)], 255, lineType=cv2.LINE_AA)

    # Downsample to original resolution with high-quality interpolation
    # INTER_AREA is best for downsampling - produces smooth anti-aliased edges
    mask = cv2.resize(mask_hires, (billboard_image.shape[1], billboard_image.shape[0]),
                     interpolation=cv2.INTER_AREA)

    # Apply edge blur for additional smoothing (user-configurable)
    # Use config edge blur if provided
    edge_blur = 8
    if config and 'edgeBlur' in config:
        edge_blur = max(3, min(21, config['edgeBlur']))
        if edge_blur % 2 == 0:
            edge_blur += 1  # Ensure odd number for GaussianBlur

    mask_float = mask.astype(np.float32) / 255.0

    # Use bilateral filter for edge blur to preserve edge sharpness while smoothing noise
    # This is better than Gaussian blur as it preserves the actual edge location
    if edge_blur > 3:
        mask_float = cv2.bilateralFilter(mask_float, edge_blur, edge_blur * 2, edge_blur * 2)

    mask_float = np.clip(mask_float, 0, 1)

    # Convert to 3-channel mask for alpha blending
    mask_3ch = np.stack([mask_float] * 3, axis=-1)

    # Apply config-based enhancements to ONLY the frame region
    if config:
        brightness = config.get('brightness', 100) / 100.0
        contrast = config.get('contrast', 100) / 100.0
        saturation = config.get('saturation', 100) / 100.0
        lighting_adjustment = config.get('lightingAdjustment', 0)
        color_temperature = config.get('colorTemperature', 0)
        vignette_strength = config.get('vignette', 0) / 100.0
        shadow_strength = config.get('shadowIntensity', 0) / 100.0

        # Extract only the frame region from warped creative
        warped_float = warped.astype(np.float32)

        # Apply brightness and contrast to frame region only
        if brightness != 1.0 or contrast != 1.0:
            warped_float = warped_float * contrast + (brightness - 1) * 100
            warped_float = np.clip(warped_float, 0, 255)

        # Apply saturation to frame region only
        if saturation != 1.0:
            # Only process pixels within the mask
            warped_uint = warped_float.astype(np.uint8)
            hsv = cv2.cvtColor(warped_uint, cv2.COLOR_BGR2HSV).astype(np.float32)
            # Apply saturation only where mask exists
            hsv[:, :, 1] = hsv[:, :, 1] * saturation * mask_float + hsv[:, :, 1] * (1 - mask_float)
            hsv[:, :, 1] = np.clip(hsv[:, :, 1], 0, 255)
            warped_float = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR).astype(np.float32)

        # Apply lighting adjustment to frame region only
        if lighting_adjustment != 0:
            warped_float = warped_float + (lighting_adjustment * 2 * mask_3ch)
            warped_float = np.clip(warped_float, 0, 255)

        # Apply color temperature shift to frame region only
        if color_temperature != 0:
            if color_temperature > 0:
                # Warm: increase red and green (yellow) only in frame
                warped_float[:, :, 2] += color_temperature * 2 * mask_float  # Red
                warped_float[:, :, 1] += color_temperature * 1 * mask_float  # Green
            else:
                # Cool: increase blue only in frame
                warped_float[:, :, 0] += abs(color_temperature) * 2 * mask_float  # Blue
            warped_float = np.clip(warped_float, 0, 255)

        # Apply vignette to frame region only
        if vignette_strength > 0:
            # Get bounding box of frame
            x, y, w, h = cv2.boundingRect(dst_pts.astype(int))
            # Create radial gradient centered on frame
            y_coords, x_coords = np.ogrid[:billboard_image.shape[0], :billboard_image.shape[1]]
            center_y, center_x = y + h / 2, x + w / 2
            distances = np.sqrt((x_coords - center_x) ** 2 + (y_coords - center_y) ** 2)
            max_distance = np.sqrt((w / 2) ** 2 + (h / 2) ** 2)
            vignette_mask = 1 - (distances / max_distance) * vignette_strength
            vignette_mask = np.clip(vignette_mask, 0, 1)
            # Apply only within frame region
            vignette_mask = vignette_mask * mask_float + (1 - mask_float)
            vignette_mask_3ch = np.stack([vignette_mask] * 3, axis=-1)
            warped_float = warped_float * vignette_mask_3ch

        # Apply shadow (darken edges) to frame region only
        if shadow_strength > 0:
            # Create edge shadow by using inverse of mask_float
            shadow_mask = 1 - (mask_float ** 0.5)  # Softer falloff
            shadow_mask = shadow_mask * shadow_strength
            shadow_mask_3ch = np.stack([shadow_mask] * 3, axis=-1)
            warped_float = warped_float * (1 - shadow_mask_3ch)

        warped = warped_float.astype(np.uint8)

    # Alpha blend warped creative with billboard using smooth mask
    # Apply overlay opacity to reduce creative opacity and let billboard details show through
    creative_opacity = 1.0
    if config and config.get('overlayOpacity', 0) > 0:
        # Overlay opacity reduces creative opacity, allowing billboard lighting/texture to enhance realism
        # Higher overlay = more transparent creative = more billboard detail shows through
        overlay_opacity = config['overlayOpacity'] / 100.0
        creative_opacity = 1.0 - (overlay_opacity * 0.5)  # Max 50% overlay = 75% creative opacity
        logger.info(f"[MOCKUP] Applying overlay opacity {overlay_opacity:.2f}, creative opacity {creative_opacity:.2f}")

    # Blend with adjusted opacity to let billboard details enhance the creative
    result = (billboard_image.astype(np.float32) * (1 - mask_3ch * creative_opacity) +
              warped.astype(np.float32) * mask_3ch * creative_opacity).astype(np.uint8)

    # Apply unsharp mask to enhance edges and reduce stretching blur
    # This is more effective than simple sharpening for perspective-warped images
    gaussian_blur = cv2.GaussianBlur(result, (0, 0), 2.0)
    unsharp_mask = cv2.addWeighted(result, 1.5, gaussian_blur, -0.5, 0)

    # Apply unsharp mask only within the frame region (using mask)
    result = (result.astype(np.float32) * (1 - mask_3ch) +
              unsharp_mask.astype(np.float32) * mask_3ch).astype(np.uint8)

    logger.info(f"[MOCKUP] Applied unsharp mask to reduce stretching artifacts and enhance detail")

    return result


def get_location_photos_dir(location_key: str, time_of_day: str = "day", finish: str = "gold") -> Path:
    """Get the directory for a location's mockup photos with time_of_day and finish."""
    return MOCKUPS_DIR / location_key / time_of_day / finish


def save_location_photo(location_key: str, photo_filename: str, photo_data: bytes, time_of_day: str = "day", finish: str = "gold") -> Path:
    """Save a location photo to disk with time_of_day and finish."""
    location_dir = get_location_photos_dir(location_key, time_of_day, finish)
    location_dir.mkdir(parents=True, exist_ok=True)

    photo_path = location_dir / photo_filename
    photo_path.write_bytes(photo_data)

    logger.info(f"[MOCKUP] Saved photo for location '{location_key}/{time_of_day}/{finish}': {photo_path}")
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

    # Special handling for "all" - pick from any variation
    if time_of_day == "all" or finish == "all":
        # Get all variations available for this location
        variations = db.list_mockup_variations(location_key)
        if not variations:
            logger.warning(f"[MOCKUP] No variations found for location '{location_key}'")
            return None

        # Build list of all (time_of_day, finish, photo) tuples
        all_photos = []
        for tod in variations:
            for fin in variations[tod]:
                photos = db.list_mockup_photos(location_key, tod, fin)
                for photo in photos:
                    all_photos.append((photo, tod, fin))

        if not all_photos:
            logger.warning(f"[MOCKUP] No photos found for location '{location_key}'")
            return None

        # Pick random from all available
        photo_filename, selected_tod, selected_finish = random.choice(all_photos)
        photo_path = get_location_photos_dir(location_key, selected_tod, selected_finish) / photo_filename

        if not photo_path.exists():
            logger.error(f"[MOCKUP] Photo file not found: {photo_path}")
            return None

        logger.info(f"[MOCKUP] Selected random photo from all variations for '{location_key}': {photo_filename} ({selected_tod}/{selected_finish})")
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


async def generate_ai_creative(prompt: str, size: str = "1536x1024") -> Optional[Path]:
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
            size=size,
            quality='high',
        )

        # Extract base64 image data (automatically returned by gpt-image-1)
        b64_image = img.data[0].b64_json
        image_data = base64.b64decode(b64_image)

        # Apply sharpening and quality enhancement to AI-generated image
        import io
        from PIL import Image

        # Load image from bytes
        pil_img = Image.open(io.BytesIO(image_data))
        img_array = np.array(pil_img)

        # Convert RGB to BGR for OpenCV
        if len(img_array.shape) == 3 and img_array.shape[2] == 3:
            img_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)

        # Apply unsharp mask for sharpening (more aggressive than mockup sharpening)
        gaussian = cv2.GaussianBlur(img_array, (0, 0), 3.0)
        sharpened = cv2.addWeighted(img_array, 1.8, gaussian, -0.8, 0)

        # Apply slight contrast enhancement
        lab = cv2.cvtColor(sharpened, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l = clahe.apply(l)
        enhanced = cv2.merge([l, a, b])
        enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)

        logger.info("[AI_CREATIVE] Applied sharpening and contrast enhancement to AI image")

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
    finish: str = "gold"
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

    Returns:
        Path to the generated mockup image, or None if failed
    """
    logger.info(f"[MOCKUP] Generating mockup for location '{location_key}/{time_of_day}/{finish}' with {len(creative_images)} creative(s)")

    # Get billboard photo
    if specific_photo:
        photo_filename = specific_photo
        photo_path = get_location_photos_dir(location_key, time_of_day, finish) / photo_filename
        if not photo_path.exists():
            logger.error(f"[MOCKUP] Specific photo not found: {photo_path}")
            return None
    else:
        result = get_random_location_photo(location_key, time_of_day, finish)
        if not result:
            return None
        photo_filename, time_of_day, finish, photo_path = result

    # Get all frame coordinates (list of frames)
    frames_data = db.get_mockup_frames(location_key, photo_filename, time_of_day, finish)
    if not frames_data:
        logger.error(f"[MOCKUP] No frame coordinates found for '{location_key}/{time_of_day}/{finish}/{photo_filename}'")
        return None

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
        # New format: {"points": [...], "config": {brightness: 100, blurStrength: 8, ...}}
        frame_points = frame_data["points"]
        frame_config = frame_data.get("config", {})

        logger.info(f"[MOCKUP] Frame {i+1} raw config: {frame_config}")

        # Merge with photo-level config (frame config takes precedence)
        merged_config = photo_config.copy() if photo_config else {}
        merged_config.update(frame_config)

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
                return None
        except Exception as e:
            logger.error(f"[MOCKUP] Error loading creative {i}: {e}")
            return None

        # Warp creative onto this frame with merged config
        try:
            result = warp_creative_to_billboard(result, creative, frame_points, config=merged_config)
            edge_blur = merged_config.get('edgeBlur', 8)
            image_blur = merged_config.get('imageBlur', 0)
            logger.info(f"[MOCKUP] Applied creative {i+1}/{num_frames} to frame {i+1} (edge blur: {edge_blur}px, image blur: {image_blur})")
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
