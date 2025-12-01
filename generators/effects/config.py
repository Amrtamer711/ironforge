"""
Effect Configuration - Centralized config for all image effects.

All effect parameters are defined here with defaults, ranges, and descriptions.
This makes it easy to:
1. See all available parameters in one place
2. Validate parameter ranges
3. Add new parameters without hunting through code
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EffectConfig:
    """
    Configuration for all image effects.

    All parameters have sensible defaults. Override only what you need.
    """

    # =========================================================================
    # EDGE COMPOSITING
    # =========================================================================

    # Edge blur: Gaussian blur applied to mask edges (1-21, odd numbers)
    # Higher = softer edges, lower = sharper edges
    edge_blur: int = 8

    # Edge smoother: Super-sampling factor for anti-aliased edges (1-20)
    # Higher = smoother edges but more processing time
    # 4x is standard MSAA level - good balance of quality and performance
    edge_smoother: int = 4

    # Image blur: Gaussian blur applied to creative before warping (0-20)
    # 0 = no blur, higher = more blur (useful for matching billboard photo blur)
    image_blur: int = 0

    # =========================================================================
    # COLOR ADJUSTMENTS
    # =========================================================================

    # Brightness: Multiplier for image brightness (0-200, 100 = no change)
    brightness: int = 100

    # Contrast: Multiplier for image contrast (0-200, 100 = no change)
    contrast: int = 100

    # Saturation: Multiplier for color saturation (0-200, 100 = no change)
    saturation: int = 100

    # Lighting adjustment: Additive brightness shift (-100 to 100, 0 = no change)
    lighting_adjustment: int = 0

    # Color temperature: Warm/cool shift (-100 to 100, 0 = neutral)
    # Positive = warmer (more yellow/red), negative = cooler (more blue)
    color_temperature: int = 0

    # =========================================================================
    # DEPTH & LIGHTING EFFECTS
    # =========================================================================

    # Depth multiplier: 3D depth perception intensity (5-30, 15 = neutral/disabled)
    # <15 = less depth effect, >15 = more depth effect
    # Night: Creates spotlight gradient (top lit, bottom darker)
    # Day: Creates atmospheric perspective (slight desaturation, contrast reduction)
    depth_multiplier: int = 15

    # Vignette strength: Edge darkening effect (0-100, 0 = disabled)
    vignette: int = 0

    # Shadow intensity: Edge shadow/darkening (0-100, 0 = disabled)
    shadow_intensity: int = 0

    # Overlay opacity: Billboard texture bleed-through (0-100, 0 = disabled)
    # Higher values let more of the billboard show through the creative
    overlay_opacity: int = 0

    # =========================================================================
    # POST-PROCESSING
    # =========================================================================

    # Sharpening: Unsharp mask strength (0-100, 0 = disabled)
    sharpening: int = 0

    # =========================================================================
    # ADVANCED EDGE EFFECTS (auto-enabled based on edge_blur)
    # =========================================================================

    # These are automatically applied when edge_blur is high enough.
    # Set to False to disable even when edge_blur would trigger them.

    # Enable gamma-correct edge blurring (requires edge_blur > 3)
    enable_gamma_blur: bool = True

    # Enable distance-based feathering (requires edge_blur >= 8)
    enable_feathering: bool = True

    # Enable contact shadow at edges (requires edge_blur >= 10)
    enable_contact_shadow: bool = True

    # Enable choke/spread edge refinement (requires edge_blur >= 6)
    enable_choke_spread: bool = True

    # Enable luminance-adaptive edges (requires edge_blur >= 8)
    enable_luminance_adaptation: bool = True

    # Enable background bleed prevention (requires edge_blur > 12)
    enable_bleed_prevention: bool = True

    def validate(self) -> "EffectConfig":
        """Validate and clamp all parameters to valid ranges."""
        self.edge_blur = self._clamp_odd(self.edge_blur, 1, 21)
        self.edge_smoother = self._clamp(self.edge_smoother, 1, 20)
        self.image_blur = self._clamp(self.image_blur, 0, 20)

        self.brightness = self._clamp(self.brightness, 0, 200)
        self.contrast = self._clamp(self.contrast, 0, 200)
        self.saturation = self._clamp(self.saturation, 0, 200)
        self.lighting_adjustment = self._clamp(self.lighting_adjustment, -100, 100)
        self.color_temperature = self._clamp(self.color_temperature, -100, 100)

        self.depth_multiplier = self._clamp(self.depth_multiplier, 5, 30)
        self.vignette = self._clamp(self.vignette, 0, 100)
        self.shadow_intensity = self._clamp(self.shadow_intensity, 0, 100)
        self.overlay_opacity = self._clamp(self.overlay_opacity, 0, 100)

        self.sharpening = self._clamp(self.sharpening, 0, 100)

        return self

    @staticmethod
    def _clamp(value: int, min_val: int, max_val: int) -> int:
        """Clamp value to range."""
        return max(min_val, min(max_val, value))

    @staticmethod
    def _clamp_odd(value: int, min_val: int, max_val: int) -> int:
        """Clamp value to range and ensure odd."""
        value = max(min_val, min(max_val, value))
        if value % 2 == 0:
            value += 1
        return min(value, max_val)

    @classmethod
    def from_dict(cls, config_dict: Optional[dict]) -> "EffectConfig":
        """
        Create EffectConfig from a dictionary (e.g., from database or API).

        Handles camelCase keys (from JavaScript frontend) and snake_case keys.
        """
        if not config_dict:
            return cls()

        # Map camelCase to snake_case
        key_mapping = {
            "edgeBlur": "edge_blur",
            "edgeSmoother": "edge_smoother",
            "imageBlur": "image_blur",
            "lightingAdjustment": "lighting_adjustment",
            "colorTemperature": "color_temperature",
            "depthMultiplier": "depth_multiplier",
            "shadowIntensity": "shadow_intensity",
            "overlayOpacity": "overlay_opacity",
        }

        # Convert camelCase keys to snake_case
        normalized = {}
        for key, value in config_dict.items():
            snake_key = key_mapping.get(key, key)
            normalized[snake_key] = value

        # Only pass known fields to avoid TypeError
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in normalized.items() if k in known_fields}

        return cls(**filtered).validate()

    def to_dict(self) -> dict:
        """Convert to dictionary with camelCase keys for JavaScript frontend."""
        return {
            "edgeBlur": self.edge_blur,
            "edgeSmoother": self.edge_smoother,
            "imageBlur": self.image_blur,
            "brightness": self.brightness,
            "contrast": self.contrast,
            "saturation": self.saturation,
            "lightingAdjustment": self.lighting_adjustment,
            "colorTemperature": self.color_temperature,
            "depthMultiplier": self.depth_multiplier,
            "vignette": self.vignette,
            "shadowIntensity": self.shadow_intensity,
            "overlayOpacity": self.overlay_opacity,
            "sharpening": self.sharpening,
        }


# Default configuration - use this as a starting point
DEFAULT_CONFIG = EffectConfig()
