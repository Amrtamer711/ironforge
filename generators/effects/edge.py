"""
Edge Compositing Effects - Professional edge blending for billboard mockups.

Implements Hollywood VFX-grade compositing techniques:
- Gamma-correct edge blurring
- Distance-based feathering
- Contact shadow / ambient occlusion
- Choke and spread edge refinement
- Luminance-adaptive edges
- Background bleed prevention
"""

import cv2
import numpy as np
import logging
from typing import Tuple, Optional

from generators.effects.config import EffectConfig

logger = logging.getLogger(__name__)


class EdgeCompositor:
    """
    Handles all edge-related compositing effects.

    Creates anti-aliased masks and applies professional edge blending
    to make composited images look natural.
    """

    def __init__(self, config: EffectConfig):
        """
        Initialize with effect configuration.

        Args:
            config: EffectConfig instance with edge parameters
        """
        self.config = config
        self.edge_blur = config.edge_blur
        self.edge_smoother = config.edge_smoother

    def create_antialiased_mask(
        self,
        image_shape: Tuple[int, int],
        dst_pts: np.ndarray,
    ) -> np.ndarray:
        """
        Create high-quality anti-aliased mask using super-sampling.

        Args:
            image_shape: (height, width) of the output mask
            dst_pts: Destination polygon points (4x2 array)

        Returns:
            Float mask (0.0-1.0) with smooth anti-aliased edges
        """
        h, w = image_shape[:2]

        # Super-sample for smooth edges
        supersample_factor = self.edge_smoother
        h_hires = h * supersample_factor
        w_hires = w * supersample_factor

        # Scale destination points to high-res space
        dst_pts_hires = dst_pts * supersample_factor

        # Draw mask at high resolution with anti-aliased lines
        mask_hires = np.zeros((h_hires, w_hires), dtype=np.uint8)
        cv2.fillPoly(mask_hires, [dst_pts_hires.astype(np.int32)], 255, lineType=cv2.LINE_AA)

        # Apply additional Gaussian blur at high-res for extra smoothing
        if self.edge_smoother > 3:
            blur_strength = int((self.edge_smoother - 3) * 2)
            if blur_strength > 0:
                kernel_size = blur_strength * 2 + 1
                mask_hires = cv2.GaussianBlur(
                    mask_hires, (kernel_size, kernel_size), sigmaX=blur_strength / 2
                )
                logger.debug(f"[EDGE] Applied high-res mask blur: {blur_strength}px")

        # Downsample to original resolution with high-quality interpolation
        mask = cv2.resize(mask_hires, (w, h), interpolation=cv2.INTER_AREA)

        # Convert to float
        mask_float = mask.astype(np.float32) / 255.0

        logger.debug(f"[EDGE] Created anti-aliased mask ({self.edge_smoother}x super-sampling)")
        return mask_float

    def apply_gamma_correct_blur(self, mask: np.ndarray) -> np.ndarray:
        """
        Apply gamma-correct edge blurring.

        Linear blur looks unnatural because human vision and light work in gamma space.
        We convert to linear, blur, then convert back for perceptually-correct softness.

        Args:
            mask: Float mask (0.0-1.0)

        Returns:
            Blurred mask with gamma-correct edges
        """
        if self.edge_blur <= 3 or not self.config.enable_gamma_blur:
            return mask

        # Convert to linear space (inverse gamma 2.2)
        mask_linear = np.power(mask, 2.2)

        # Multi-radius blur for natural organic falloff
        kernel_size = self.edge_blur if self.edge_blur % 2 == 1 else self.edge_blur + 1

        # Large blur for soft outer edge
        mask_large = cv2.GaussianBlur(
            mask_linear, (kernel_size, kernel_size), sigmaX=self.edge_blur / 2.5
        )

        # Small blur for core sharpness
        small_kernel = max(3, (kernel_size // 2) | 1)  # Ensure odd and >= 3
        mask_small = cv2.GaussianBlur(
            mask_linear, (small_kernel, small_kernel), sigmaX=self.edge_blur / 6.0
        )

        # Blend: core sharp, edges soft (80% soft blur, 20% sharp)
        mask_linear = mask_large * 0.8 + mask_small * 0.2

        # Convert back to gamma space
        result = np.power(np.clip(mask_linear, 0, 1), 1 / 2.2)

        logger.debug(f"[EDGE] Applied gamma-correct blur (kernel: {kernel_size})")
        return result

    def apply_feathering(self, mask: np.ndarray) -> np.ndarray:
        """
        Apply distance-based feathering with smooth falloff curve.

        Creates natural alpha gradient that mimics how real materials transition.

        Args:
            mask: Float mask (0.0-1.0)

        Returns:
            Feathered mask
        """
        if self.edge_blur < 8 or not self.config.enable_feathering:
            return mask

        mask_binary = (mask > 0.5).astype(np.uint8)
        dist_transform = cv2.distanceTransform(mask_binary, cv2.DIST_L2, 5)

        # Adaptive feather distance based on edge blur strength
        feather_pixels = min(self.edge_blur * 2.0, 40)

        # Smooth falloff curve (ease-in-out) instead of linear
        feather_normalized = np.clip(dist_transform / feather_pixels, 0, 1)

        # Apply smoothstep function: 3t² - 2t³ (ease in-out curve)
        feather_smooth = feather_normalized * feather_normalized * (3 - 2 * feather_normalized)

        # Blend with original (50% feathering for strong effect)
        feather_strength = 0.5
        result = mask * (1 - feather_strength) + feather_smooth * feather_strength

        logger.debug(f"[EDGE] Applied distance feathering ({feather_pixels:.1f}px)")
        return result

    def apply_contact_shadow(self, mask: np.ndarray) -> Tuple[np.ndarray, Optional[np.ndarray]]:
        """
        Create contact shadow / ambient occlusion at edges.

        Simulates how edges darken where creative "meets" billboard surface.
        Creates depth and prevents floating appearance.

        Args:
            mask: Float mask (0.0-1.0)

        Returns:
            Tuple of (mask, shadow_mask) where shadow_mask can be applied to darken edges
        """
        if self.edge_blur < 10 or not self.config.enable_contact_shadow:
            return mask, None

        # Detect edge more aggressively for contact shadow
        eroded = cv2.erode(mask, np.ones((3, 3), np.float32), iterations=2)
        edge_contact = mask - eroded
        edge_contact = np.clip(edge_contact * 4.0, 0, 1)

        # Blur the contact shadow for soft falloff
        edge_contact = cv2.GaussianBlur(edge_contact, (7, 7), sigmaX=2.0)

        # Stronger contact shadow for higher edge blur
        shadow_intensity = min(0.2, self.edge_blur / 50.0)  # Max 20% darkening
        edge_shadow = edge_contact * shadow_intensity

        logger.debug(f"[EDGE] Created contact shadow (intensity: {shadow_intensity:.2f})")
        return mask, edge_shadow

    def apply_choke_spread(self, mask: np.ndarray) -> np.ndarray:
        """
        Apply choke and spread for edge refinement.

        Professional technique to eliminate micro-jaggies and stair-stepping
        while maintaining crisp inner edge.

        Args:
            mask: Float mask (0.0-1.0)

        Returns:
            Refined mask
        """
        if self.edge_blur < 6 or not self.config.enable_choke_spread:
            return mask

        # Choke: Slightly pull in the edge
        kernel_choke = np.ones((2, 2), np.float32) / 4
        mask_choked = cv2.erode(mask, kernel_choke, iterations=1)

        # Spread: Expand back with soft blur
        mask_spread = cv2.GaussianBlur(mask_choked, (5, 5), sigmaX=1.5)

        # Blend between choked and spread
        result = mask_spread * 0.7 + mask_choked * 0.3

        logger.debug("[EDGE] Applied choke/spread refinement")
        return result

    def apply_luminance_adaptation(
        self,
        mask: np.ndarray,
        billboard_image: np.ndarray,
        warped_image: np.ndarray,
    ) -> np.ndarray:
        """
        Adjust edge transparency based on brightness difference.

        Bright edges against dark backgrounds need less feathering.

        Args:
            mask: Float mask (0.0-1.0)
            billboard_image: Original billboard image (BGR)
            warped_image: Warped creative image (BGR)

        Returns:
            Adapted mask
        """
        if self.edge_blur < 8 or not self.config.enable_luminance_adaptation:
            return mask

        # Calculate luminance at edges
        billboard_gray = cv2.cvtColor(billboard_image, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
        warped_gray = cv2.cvtColor(warped_image, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0

        # Find edges for luminance comparison
        edge_mask_binary = (mask > 0.1) & (mask < 0.9)

        # Calculate contrast at edges
        billboard_lum_blur = cv2.GaussianBlur(billboard_gray, (15, 15), sigmaX=5)
        warped_lum_blur = cv2.GaussianBlur(warped_gray, (15, 15), sigmaX=5)

        # High contrast edges can be sharper, low contrast needs more feather
        lum_diff = np.abs(billboard_lum_blur - warped_lum_blur)
        lum_diff_clipped = np.clip(lum_diff, 0, 1)

        # Sharpen high-contrast edges, soften low-contrast edges
        edge_adaptive = np.where(
            edge_mask_binary, 1.0 + (lum_diff_clipped * 0.3), 1.0  # Up to 30% sharper
        )
        result = np.clip(mask * edge_adaptive, 0, 1)

        logger.debug("[EDGE] Applied luminance adaptation")
        return result

    def prevent_background_bleed(
        self,
        billboard_image: np.ndarray,
        warped_image: np.ndarray,
        mask: np.ndarray,
    ) -> np.ndarray:
        """
        Prevent green screen / background bleed-through at high edge blur.

        When mask is heavily blurred, fill billboard frame area with creative
        edge color to prevent adjacent billboards or green screens from showing.

        Args:
            billboard_image: Original billboard image (BGR, float32)
            warped_image: Warped creative image (BGR, float32)
            mask: Float mask (0.0-1.0)

        Returns:
            Billboard image with frame area pre-filled
        """
        if self.edge_blur <= 12 or not self.config.enable_bleed_prevention:
            return billboard_image.astype(np.float32)

        mask_3ch = mask if len(mask.shape) == 3 else mask[:, :, np.newaxis]
        if mask_3ch.shape[2] == 1:
            mask_3ch = np.repeat(mask_3ch, 3, axis=2)

        # Find pixels that are part of the frame
        frame_region = mask_3ch[:, :, 0] > 0.05

        if np.sum(frame_region) == 0:
            return billboard_image.astype(np.float32)

        # Calculate average color from creative edges within frame
        edge_region = (mask_3ch[:, :, 0] > 0.05) & (mask_3ch[:, :, 0] < 0.95)

        if np.sum(edge_region) > 100:
            edge_pixels = warped_image[edge_region]
            fill_color = np.mean(edge_pixels, axis=0)
        else:
            fill_color = np.mean(warped_image[frame_region], axis=0)

        # Create filled billboard
        billboard_filled = billboard_image.copy().astype(np.float32)
        billboard_filled[frame_region] = fill_color

        logger.debug(f"[EDGE] Pre-filled billboard frame to prevent background bleed")
        return billboard_filled

    def process_mask(
        self,
        image_shape: Tuple[int, int],
        dst_pts: np.ndarray,
        billboard_image: Optional[np.ndarray] = None,
        warped_image: Optional[np.ndarray] = None,
    ) -> Tuple[np.ndarray, Optional[np.ndarray]]:
        """
        Full mask processing pipeline.

        Applies all enabled edge effects in the correct order.

        Args:
            image_shape: (height, width) of the output
            dst_pts: Destination polygon points
            billboard_image: Optional billboard for luminance adaptation
            warped_image: Optional warped creative for luminance adaptation

        Returns:
            Tuple of (processed_mask, contact_shadow)
        """
        # Create base mask
        mask = self.create_antialiased_mask(image_shape, dst_pts)

        # NOTE: Base edge blur is applied INSIDE gamma-correct blur technique (when edge_blur > 3)
        # The original mockup.py does NOT apply a separate base blur before gamma blur
        # All blur comes from the gamma-correct blur method which handles kernel sizing

        # Apply gamma-correct blur
        mask = self.apply_gamma_correct_blur(mask)

        # Apply feathering
        mask = self.apply_feathering(mask)

        # Apply choke/spread
        mask = self.apply_choke_spread(mask)

        # Apply luminance adaptation if images provided
        if billboard_image is not None and warped_image is not None:
            mask = self.apply_luminance_adaptation(mask, billboard_image, warped_image)

        # Create contact shadow
        mask, contact_shadow = self.apply_contact_shadow(mask)

        # Final clamp
        mask = np.clip(mask, 0, 1)

        return mask, contact_shadow
