"""
Depth & Lighting Effects - 3D depth perception for billboard mockups.

Implements time-of-day aware depth effects:
- Night: Directional spotlight effect (billboard lit from above)
- Day: Atmospheric perspective (haze, reduced saturation/contrast)
"""

import cv2
import numpy as np
import logging
from typing import Tuple

from generators.effects.config import EffectConfig

logger = logging.getLogger(__name__)


class DepthEffect:
    """
    Applies 3D depth perception effects based on time of day.

    Night mode simulates billboard spotlights (top lit, bottom darker).
    Day mode simulates atmospheric perspective (slight haze/desaturation).
    """

    def __init__(self, config: EffectConfig, time_of_day: str = "day"):
        """
        Initialize depth effect.

        Args:
            config: EffectConfig with depth_multiplier
            time_of_day: "day" or "night"
        """
        self.config = config
        self.time_of_day = time_of_day
        self.depth_multiplier = config.depth_multiplier

        # Calculate intensity: 0 at depth=15 (neutral), increases as it moves away
        self.intensity = abs(self.depth_multiplier - 15) / 15.0  # 0.0 to 1.0
        self.enabled = self.depth_multiplier != 15

    def apply(
        self,
        image: np.ndarray,
        mask: np.ndarray,
        dst_pts: np.ndarray,
    ) -> np.ndarray:
        """
        Apply depth effect to image.

        Args:
            image: Image to modify (BGR, float32)
            mask: Float mask (0.0-1.0) defining the creative region
            dst_pts: Destination polygon points for bounding box

        Returns:
            Modified image (float32)
        """
        if not self.enabled:
            return image

        if self.time_of_day == "night":
            return self._apply_night_spotlight(image, mask, dst_pts)
        else:
            return self._apply_day_atmosphere(image, mask)

    def _apply_night_spotlight(
        self,
        image: np.ndarray,
        mask: np.ndarray,
        dst_pts: np.ndarray,
    ) -> np.ndarray:
        """
        Apply directional spotlight effect for night scenes.

        Simulates billboard illuminated by spotlights from above.
        Top of billboard is brighter, bottom is darker.

        Args:
            image: Image to modify (BGR, float32)
            mask: Float mask (0.0-1.0)
            dst_pts: Destination polygon points

        Returns:
            Modified image
        """
        # Get bounding box of frame
        x, y, w, h = cv2.boundingRect(dst_pts.astype(int))
        y_coords = np.arange(image.shape[0])[:, np.newaxis]

        # Vertical gradient: top (lit) to bottom (shadow)
        y_norm = np.clip((y_coords - y) / max(h, 1), 0, 1)

        # Up to 35% darker at bottom based on intensity
        lighting_gradient = 1.0 - (y_norm * self.intensity * 0.35)

        # Apply only within mask
        lighting_gradient = lighting_gradient * mask + (1 - mask)
        lighting_gradient_3ch = np.stack([lighting_gradient] * 3, axis=-1)

        result = image * lighting_gradient_3ch
        result = np.clip(result, 0, 255)

        logger.info(f"[DEPTH] Applied night spotlight (intensity: {self.intensity:.2f})")
        return result

    def _apply_day_atmosphere(
        self,
        image: np.ndarray,
        mask: np.ndarray,
    ) -> np.ndarray:
        """
        Apply atmospheric perspective for day scenes.

        Things appear hazier, less saturated, and lower contrast
        when further away (simulates aerial perspective).

        Args:
            image: Image to modify (BGR, float32)
            mask: Float mask (0.0-1.0)

        Returns:
            Modified image
        """
        # Convert to HSV for saturation adjustment
        image_uint = image.astype(np.uint8)
        hsv = cv2.cvtColor(image_uint, cv2.COLOR_BGR2HSV).astype(np.float32)

        # Reduce saturation (up to 15% at max intensity)
        desaturation = 1.0 - (self.intensity * 0.15)
        hsv[:, :, 1] = hsv[:, :, 1] * desaturation * mask + hsv[:, :, 1] * (1 - mask)
        hsv[:, :, 1] = np.clip(hsv[:, :, 1], 0, 255)

        result = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR).astype(np.float32)

        # Reduce contrast (up to 12% at max intensity)
        masked_pixels = mask > 0.5
        if np.any(masked_pixels):
            mean = np.mean(result[masked_pixels])
            contrast_factor = 1.0 - (self.intensity * 0.12)
            result = mean + (result - mean) * contrast_factor
            result = np.clip(result, 0, 255)

        logger.info(f"[DEPTH] Applied daytime atmospheric depth (intensity: {self.intensity:.2f})")
        return result


class VignetteEffect:
    """
    Applies vignette (edge darkening) effect to creative region.
    """

    def __init__(self, config: EffectConfig):
        """
        Initialize vignette effect.

        Args:
            config: EffectConfig with vignette strength
        """
        self.strength = config.vignette / 100.0
        self.enabled = config.vignette > 0

    def apply(
        self,
        image: np.ndarray,
        mask: np.ndarray,
        dst_pts: np.ndarray,
    ) -> np.ndarray:
        """
        Apply vignette effect.

        Args:
            image: Image to modify (BGR, float32)
            mask: Float mask (0.0-1.0)
            dst_pts: Destination polygon points

        Returns:
            Modified image
        """
        if not self.enabled:
            return image

        # Get bounding box of frame
        x, y, w, h = cv2.boundingRect(dst_pts.astype(int))

        # Create radial gradient centered on frame
        y_coords, x_coords = np.ogrid[:image.shape[0], :image.shape[1]]
        center_y, center_x = y + h / 2, x + w / 2

        distances = np.sqrt((x_coords - center_x) ** 2 + (y_coords - center_y) ** 2)
        max_distance = np.sqrt((w / 2) ** 2 + (h / 2) ** 2)

        vignette_mask = 1 - (distances / max(max_distance, 1)) * self.strength
        vignette_mask = np.clip(vignette_mask, 0, 1)

        # Apply only within frame region
        vignette_mask = vignette_mask * mask + (1 - mask)
        vignette_mask_3ch = np.stack([vignette_mask] * 3, axis=-1)

        result = image * vignette_mask_3ch

        logger.debug(f"[DEPTH] Applied vignette (strength: {self.strength:.2f})")
        return result


class ShadowEffect:
    """
    Applies edge shadow/darkening effect.
    """

    def __init__(self, config: EffectConfig):
        """
        Initialize shadow effect.

        Args:
            config: EffectConfig with shadow_intensity
        """
        self.strength = config.shadow_intensity / 100.0
        self.enabled = config.shadow_intensity > 0

    def apply(self, image: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """
        Apply shadow effect to edges.

        Args:
            image: Image to modify (BGR, float32)
            mask: Float mask (0.0-1.0)

        Returns:
            Modified image
        """
        if not self.enabled:
            return image

        # Create edge shadow using inverse of mask with softer falloff
        shadow_mask = 1 - (mask ** 0.5)
        shadow_mask = shadow_mask * self.strength
        shadow_mask_3ch = np.stack([shadow_mask] * 3, axis=-1)

        result = image * (1 - shadow_mask_3ch)

        logger.debug(f"[DEPTH] Applied edge shadow (strength: {self.strength:.2f})")
        return result
