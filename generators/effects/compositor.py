"""
Compositor - Main orchestrator for billboard mockup compositing.

This module provides the main compositing pipeline that:
1. Prepares the creative (upscale, blur, border extension)
2. Warps the creative to billboard perspective
3. Creates and processes the mask
4. Applies all effects (depth, color, edge)
5. Composites the final result
"""

import cv2
import numpy as np
import logging
from typing import Optional, Tuple, List

from generators.effects.config import EffectConfig
from generators.effects.edge import EdgeCompositor
from generators.effects.depth import DepthEffect, VignetteEffect, ShadowEffect
from generators.effects.color import ColorAdjustment, ImageBlur, Sharpening, OverlayBlending

logger = logging.getLogger(__name__)


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


def extend_image_borders_smart(image: np.ndarray, extend_pixels: int, method: str = 'inpaint') -> np.ndarray:
    """
    Intelligently extend image borders to prevent warp artifacts.

    Args:
        image: Input image (BGR)
        extend_pixels: Pixels to extend on each side
        method: 'reflect' or 'inpaint'

    Returns:
        Extended image
    """
    if extend_pixels < 10 or method == 'reflect':
        return cv2.copyMakeBorder(
            image,
            extend_pixels, extend_pixels, extend_pixels, extend_pixels,
            cv2.BORDER_REFLECT_101
        )

    h, w = image.shape[:2]

    # Create extended canvas
    extended = cv2.copyMakeBorder(
        image,
        extend_pixels, extend_pixels, extend_pixels, extend_pixels,
        cv2.BORDER_REPLICATE
    )

    # Create mask for inpainting (only outermost border)
    mask = np.zeros((h + 2 * extend_pixels, w + 2 * extend_pixels), dtype=np.uint8)
    border_inpaint = min(extend_pixels, 15)

    mask[0:border_inpaint, :] = 255
    mask[-border_inpaint:, :] = 255
    mask[:, 0:border_inpaint] = 255
    mask[:, -border_inpaint:] = 255

    # Inpaint with Telea algorithm
    inpaint_radius = min(10, extend_pixels // 2)
    result = cv2.inpaint(extended, mask, inpaint_radius, cv2.INPAINT_TELEA)

    logger.debug(f"[COMPOSITOR] Extended borders by {extend_pixels}px using inpainting")
    return result


class BillboardCompositor:
    """
    Main compositor for placing creatives onto billboard photos.

    Handles the entire pipeline from creative preparation to final output.
    All effects are configurable through EffectConfig.
    """

    def __init__(self, config: Optional[EffectConfig] = None, time_of_day: str = "day"):
        """
        Initialize compositor.

        Args:
            config: EffectConfig instance (uses defaults if None)
            time_of_day: "day" or "night" for depth effects
        """
        self.config = config or EffectConfig()
        self.time_of_day = time_of_day

        # Initialize effect processors
        self.edge_compositor = EdgeCompositor(self.config)
        self.depth_effect = DepthEffect(self.config, time_of_day)
        self.vignette_effect = VignetteEffect(self.config)
        self.shadow_effect = ShadowEffect(self.config)
        self.color_adjustment = ColorAdjustment(self.config)
        self.image_blur = ImageBlur(self.config)
        self.sharpening = Sharpening(self.config)
        self.overlay = OverlayBlending(self.config)

    def prepare_creative(self, creative_image: np.ndarray) -> np.ndarray:
        """
        Prepare creative for warping (upscale, blur, border extension).

        Args:
            creative_image: Original creative image (BGR)

        Returns:
            Prepared creative ready for warping
        """
        # Upscale for higher quality warping
        upscale_factor = 2.0
        creative = cv2.resize(
            creative_image,
            None,
            fx=upscale_factor,
            fy=upscale_factor,
            interpolation=cv2.INTER_CUBIC
        )
        logger.info(f"[COMPOSITOR] Upscaled creative {creative_image.shape[:2]} -> {creative.shape[:2]}")

        # Apply image blur if configured
        creative = self.image_blur.apply(creative)

        # Extend borders for high edge blur to prevent artifacts
        if self.config.edge_blur > 10:
            extend_amount = int(self.config.edge_blur * 2.5)
            method = 'inpaint' if self.config.edge_blur > 14 else 'reflect'
            creative = extend_image_borders_smart(creative, extend_amount, method)
            logger.info(f"[COMPOSITOR] Extended borders by {extend_amount}px (method: {method})")

        return creative

    def warp_creative(
        self,
        creative: np.ndarray,
        billboard_shape: Tuple[int, int, int],
        dst_pts: np.ndarray,
    ) -> np.ndarray:
        """
        Warp creative to billboard perspective.

        Args:
            creative: Prepared creative image
            billboard_shape: Shape of billboard image (h, w, c)
            dst_pts: Destination polygon points

        Returns:
            Warped creative
        """
        h, w = creative.shape[:2]
        src_pts = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)

        # Get perspective transform matrix
        H = cv2.getPerspectiveTransform(src_pts, dst_pts)

        # Use highest quality interpolation (LANCZOS4 is consistently better than CUBIC)
        interp = cv2.INTER_LANCZOS4

        # Warp with mirror border
        warped = cv2.warpPerspective(
            creative,
            H,
            (billboard_shape[1], billboard_shape[0]),
            flags=interp,
            borderMode=cv2.BORDER_REFLECT_101
        )

        return warped

    def composite(
        self,
        billboard_image: np.ndarray,
        creative_image: np.ndarray,
        frame_points: List[List[float]],
    ) -> np.ndarray:
        """
        Full compositing pipeline.

        Args:
            billboard_image: Billboard photo (BGR)
            creative_image: Creative to place (BGR)
            frame_points: 4 corner points defining the billboard frame

        Returns:
            Composited result (BGR, uint8)
        """
        # Order points consistently
        dst_pts = order_points(np.array(frame_points))

        # Step 1: Prepare creative
        creative_prepared = self.prepare_creative(creative_image)

        # Step 2: Warp to billboard perspective
        warped = self.warp_creative(creative_prepared, billboard_image.shape, dst_pts)

        # Step 3: Create and process mask
        mask, contact_shadow = self.edge_compositor.process_mask(
            billboard_image.shape[:2],
            dst_pts,
            billboard_image,
            warped
        )

        # Step 4: Apply depth effect FIRST (original order from mockup.py)
        # Depth effect modifies saturation/contrast, so must come before user color adjustments
        warped_float = warped.astype(np.float32)
        warped_float = self.depth_effect.apply(warped_float, mask, dst_pts)

        # Step 5: Apply color adjustments AFTER depth
        warped_float = self.color_adjustment.apply_all(warped_float, mask)

        # Step 6: Apply vignette
        warped_float = self.vignette_effect.apply(warped_float, mask, dst_pts)

        # Step 7: Apply edge shadow
        warped_float = self.shadow_effect.apply(warped_float, mask)

        # Step 8: Apply contact shadow for depth
        if contact_shadow is not None:
            shadow_3ch = np.stack([contact_shadow] * 3, axis=-1)
            warped_float = warped_float * (1 - shadow_3ch)
            logger.debug(f"[COMPOSITOR] Applied contact shadow")

        # Step 9: Prepare billboard (prevent background bleed)
        billboard_prepared = self.edge_compositor.prevent_background_bleed(
            billboard_image, warped_float, mask
        )

        # Step 10: Final compositing
        mask_3ch = np.stack([mask] * 3, axis=-1)
        creative_opacity = self.overlay.get_creative_opacity()

        if self.overlay.enabled:
            logger.info(f"[COMPOSITOR] Overlay opacity: {self.config.overlay_opacity}%, creative opacity: {creative_opacity:.2f}")

        result = (
            billboard_prepared * (1 - mask_3ch * creative_opacity) +
            warped_float * mask_3ch * creative_opacity
        ).astype(np.uint8)

        # Step 11: Apply sharpening
        result = self.sharpening.apply(result, mask)

        logger.info("[COMPOSITOR] Compositing complete")
        return result


def warp_creative_to_billboard(
    billboard_image: np.ndarray,
    creative_image: np.ndarray,
    frame_points: List[List[float]],
    config: Optional[dict] = None,
    time_of_day: str = "day"
) -> np.ndarray:
    """
    Apply perspective warp to place creative on billboard with optional enhancements.

    This is the main entry point, maintaining backward compatibility with the old API.

    Args:
        billboard_image: Billboard photo (BGR)
        creative_image: Creative to place (BGR)
        frame_points: 4 corner points defining the billboard frame
        config: Optional dict with effect parameters (converted to EffectConfig)
        time_of_day: "day" or "night" for depth effects

    Returns:
        Composited result (BGR, uint8)
    """
    # Convert dict config to EffectConfig
    effect_config = EffectConfig.from_dict(config)

    logger.info(f"[COMPOSITOR] Config: edge_blur={effect_config.edge_blur}, "
                f"edge_smoother={effect_config.edge_smoother}, "
                f"image_blur={effect_config.image_blur}, "
                f"depth={effect_config.depth_multiplier}")

    # Create compositor and run pipeline
    compositor = BillboardCompositor(effect_config, time_of_day)
    return compositor.composite(billboard_image, creative_image, frame_points)
