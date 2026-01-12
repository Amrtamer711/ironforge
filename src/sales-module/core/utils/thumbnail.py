"""
Thumbnail generation utilities for image optimization.

Uses Pillow to generate optimized thumbnails with consistent sizing
and quality settings for fast loading in web interfaces.
"""

import io
import logging
from typing import Tuple

from PIL import Image, ImageOps

logger = logging.getLogger("proposal-bot")

# Thumbnail configuration
THUMBNAIL_SIZE = (256, 256)
THUMBNAIL_QUALITY = 75
THUMBNAIL_FORMAT = "JPEG"


async def generate_thumbnail(
    image_bytes: bytes,
    max_size: Tuple[int, int] = THUMBNAIL_SIZE,
    quality: int = THUMBNAIL_QUALITY
) -> Tuple[bytes, int, int]:
    """
    Generate optimized thumbnail from image bytes.

    Features:
    - Maintains aspect ratio (no distortion)
    - Auto-rotates based on EXIF orientation
    - Strips EXIF metadata for privacy and size reduction
    - Converts to RGB for JPEG compatibility
    - Optimizes for web delivery

    Args:
        image_bytes: Raw image data as bytes
        max_size: Maximum dimensions (width, height) - aspect ratio preserved
        quality: JPEG quality (1-100), default 75

    Returns:
        Tuple of (thumbnail_bytes, width, height)

    Raises:
        ValueError: If image cannot be processed
    """
    try:
        # Load image from bytes
        img = Image.open(io.BytesIO(image_bytes))

        # Auto-rotate based on EXIF orientation tag
        # This is critical for mobile-uploaded images
        img = ImageOps.exif_transpose(img)

        # Calculate thumbnail size while preserving aspect ratio
        # thumbnail() modifies in-place
        img.thumbnail(max_size, Image.Resampling.LANCZOS)

        # Convert RGBA/LA/P to RGB for JPEG compatibility
        if img.mode in ('RGBA', 'LA', 'P'):
            # Create white background
            background = Image.new('RGB', img.size, (255, 255, 255))
            # Paste image onto background, using alpha channel as mask if present
            if img.mode == 'RGBA':
                background.paste(img, mask=img.split()[-1])  # Use alpha channel
            else:
                background.paste(img)
            img = background

        # Save as optimized JPEG
        output = io.BytesIO()
        img.save(
            output,
            format=THUMBNAIL_FORMAT,
            quality=quality,
            optimize=True  # Enable JPEG optimization
        )

        # Get final dimensions
        width, height = img.size

        logger.info(
            f"[THUMBNAIL] Generated {width}x{height} thumbnail "
            f"({len(output.getvalue())} bytes) from {len(image_bytes)} bytes original"
        )

        return output.getvalue(), width, height

    except Exception as e:
        logger.error(f"[THUMBNAIL] Failed to generate thumbnail: {e}", exc_info=True)
        raise ValueError(f"Failed to process image: {e}") from e
