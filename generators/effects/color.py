"""
Color Adjustment Effects - Color grading and post-processing for mockups.

Implements standard color adjustments:
- Brightness/Contrast
- Saturation
- Lighting adjustment
- Color temperature (warm/cool)
- Sharpening
"""

import logging

import cv2
import numpy as np

from generators.effects.config import EffectConfig

logger = logging.getLogger(__name__)


class ColorAdjustment:
    """
    Applies color adjustments to the creative region only.

    All adjustments are masked so they only affect the billboard frame,
    not the surrounding photo.
    """

    def __init__(self, config: EffectConfig):
        """
        Initialize color adjustment.

        Args:
            config: EffectConfig with color parameters
        """
        self.config = config
        self.brightness = config.brightness / 100.0
        self.contrast = config.contrast / 100.0
        self.saturation = config.saturation / 100.0
        self.lighting = config.lighting_adjustment
        self.temperature = config.color_temperature

    def apply_brightness_contrast(
        self,
        image: np.ndarray,
        mask: np.ndarray,
    ) -> np.ndarray:
        """
        Apply brightness and contrast adjustment.

        Args:
            image: Image to modify (BGR, float32)
            mask: Float mask (0.0-1.0)

        Returns:
            Modified image
        """
        if self.brightness == 1.0 and self.contrast == 1.0:
            return image

        # Apply contrast and brightness to create adjusted version
        adjusted = image * self.contrast + (self.brightness - 1) * 100
        adjusted = np.clip(adjusted, 0, 255)

        # Blend using mask: only apply effect within masked region
        mask_3ch = np.stack([mask] * 3, axis=-1)
        result = image * (1 - mask_3ch) + adjusted * mask_3ch

        logger.debug(f"[COLOR] Applied brightness={self.brightness:.2f}, contrast={self.contrast:.2f}")
        return result

    def apply_saturation(
        self,
        image: np.ndarray,
        mask: np.ndarray,
    ) -> np.ndarray:
        """
        Apply saturation adjustment.

        Args:
            image: Image to modify (BGR, float32)
            mask: Float mask (0.0-1.0)

        Returns:
            Modified image
        """
        if self.saturation == 1.0:
            return image

        # Convert to HSV
        image_uint = image.astype(np.uint8)
        hsv = cv2.cvtColor(image_uint, cv2.COLOR_BGR2HSV).astype(np.float32)

        # Apply saturation only where mask exists
        hsv[:, :, 1] = hsv[:, :, 1] * self.saturation * mask + hsv[:, :, 1] * (1 - mask)
        hsv[:, :, 1] = np.clip(hsv[:, :, 1], 0, 255)

        result = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR).astype(np.float32)

        logger.debug(f"[COLOR] Applied saturation={self.saturation:.2f}")
        return result

    def apply_lighting(
        self,
        image: np.ndarray,
        mask: np.ndarray,
    ) -> np.ndarray:
        """
        Apply additive lighting adjustment.

        Args:
            image: Image to modify (BGR, float32)
            mask: Float mask (0.0-1.0)

        Returns:
            Modified image
        """
        if self.lighting == 0:
            return image

        mask_3ch = np.stack([mask] * 3, axis=-1)
        result = image + (self.lighting * 2 * mask_3ch)
        result = np.clip(result, 0, 255)

        logger.debug(f"[COLOR] Applied lighting adjustment={self.lighting}")
        return result

    def apply_temperature(
        self,
        image: np.ndarray,
        mask: np.ndarray,
    ) -> np.ndarray:
        """
        Apply color temperature shift.

        Positive = warmer (more yellow/red)
        Negative = cooler (more blue)

        Args:
            image: Image to modify (BGR, float32)
            mask: Float mask (0.0-1.0)

        Returns:
            Modified image
        """
        if self.temperature == 0:
            return image

        result = image.copy()

        if self.temperature > 0:
            # Warm: increase red and green (yellow)
            result[:, :, 2] += self.temperature * 2 * mask  # Red
            result[:, :, 1] += self.temperature * 1 * mask  # Green
        else:
            # Cool: increase blue
            result[:, :, 0] += abs(self.temperature) * 2 * mask  # Blue

        result = np.clip(result, 0, 255)

        logger.debug(f"[COLOR] Applied color temperature={self.temperature}")
        return result

    def apply_all(
        self,
        image: np.ndarray,
        mask: np.ndarray,
    ) -> np.ndarray:
        """
        Apply all color adjustments in the correct order.

        Args:
            image: Image to modify (BGR, float32)
            mask: Float mask (0.0-1.0)

        Returns:
            Modified image
        """
        result = image

        # Apply in order: brightness/contrast, saturation, lighting, temperature
        result = self.apply_brightness_contrast(result, mask)
        result = self.apply_saturation(result, mask)
        result = self.apply_lighting(result, mask)
        result = self.apply_temperature(result, mask)

        return result


class ImageBlur:
    """
    Applies Gaussian blur to the creative before warping.

    Useful for matching the blur level of the billboard photo.
    """

    def __init__(self, config: EffectConfig):
        """
        Initialize image blur.

        Args:
            config: EffectConfig with image_blur parameter
        """
        self.blur_strength = config.image_blur
        self.enabled = config.image_blur > 0

    def apply(self, image: np.ndarray) -> np.ndarray:
        """
        Apply Gaussian blur to image.

        Args:
            image: Image to blur (any format)

        Returns:
            Blurred image
        """
        if not self.enabled:
            return image

        # Use kernel size that scales with blur intensity
        kernel_size = int(self.blur_strength * 2 + 1)
        if kernel_size % 2 == 0:
            kernel_size += 1

        result = cv2.GaussianBlur(image, (kernel_size, kernel_size), 0)

        logger.info(f"[COLOR] Applied image blur (strength: {self.blur_strength}, kernel: {kernel_size})")
        return result


class Sharpening:
    """
    Applies unsharp mask sharpening to the final result.
    """

    def __init__(self, config: EffectConfig):
        """
        Initialize sharpening effect.

        Args:
            config: EffectConfig with sharpening parameter
        """
        self.strength_percent = config.sharpening
        self.enabled = config.sharpening > 0

        # Convert percentage to multiplier (0-100 -> 1.0-1.5x)
        self.strength = 1.0 + (self.strength_percent / 100.0) * 0.5

    def apply(
        self,
        image: np.ndarray,
        mask: np.ndarray,
    ) -> np.ndarray:
        """
        Apply unsharp mask sharpening.

        Args:
            image: Image to sharpen (BGR, uint8)
            mask: Float mask (0.0-1.0) to limit effect to creative region

        Returns:
            Sharpened image
        """
        if not self.enabled:
            return image

        # Apply unsharp mask
        gaussian_blur = cv2.GaussianBlur(image, (0, 0), 2.0)
        negative_weight = -(self.strength - 1.0)
        sharpened = cv2.addWeighted(image, self.strength, gaussian_blur, negative_weight, 0)

        # Apply only within frame region
        mask_3ch = np.stack([mask] * 3, axis=-1)
        result = (image.astype(np.float32) * (1 - mask_3ch) +
                  sharpened.astype(np.float32) * mask_3ch).astype(np.uint8)

        logger.info(f"[COLOR] Applied sharpening: {self.strength_percent}% (strength: {self.strength:.2f}x)")
        return result


class OverlayBlending:
    """
    Applies overlay blending to let billboard texture show through.
    """

    def __init__(self, config: EffectConfig):
        """
        Initialize overlay blending.

        Args:
            config: EffectConfig with overlay_opacity parameter
        """
        self.opacity = config.overlay_opacity / 100.0
        self.enabled = config.overlay_opacity > 0

        # Calculate creative opacity (higher overlay = more transparent creative)
        # Max 50% overlay = 75% creative opacity
        self.creative_opacity = 1.0 - (self.opacity * 0.5)

    def get_creative_opacity(self) -> float:
        """
        Get the opacity to use when compositing the creative.

        Returns:
            Float between 0.5 and 1.0
        """
        return self.creative_opacity
