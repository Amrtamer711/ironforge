"""
Image Effects Module - Modular, configurable image processing effects.

This module provides reusable image effect classes for billboard mockup generation.
Each effect is isolated, testable, and has configurable parameters.

Usage:
    from generators.effects import BillboardCompositor, EffectConfig

    # Simple usage with defaults
    from generators.effects import warp_creative_to_billboard
    result = warp_creative_to_billboard(billboard, creative, points, config_dict)

    # Advanced usage with custom config
    config = EffectConfig(edge_blur=15, depth_multiplier=20)
    compositor = BillboardCompositor(config, time_of_day="night")
    result = compositor.composite(billboard, creative, points)
"""

from generators.effects.config import EffectConfig, DEFAULT_CONFIG
from generators.effects.edge import EdgeCompositor
from generators.effects.depth import DepthEffect, VignetteEffect, ShadowEffect
from generators.effects.color import ColorAdjustment, ImageBlur, Sharpening, OverlayBlending
from generators.effects.compositor import BillboardCompositor, warp_creative_to_billboard, order_points

__all__ = [
    # Main entry points
    "BillboardCompositor",
    "warp_creative_to_billboard",
    "order_points",
    # Configuration
    "EffectConfig",
    "DEFAULT_CONFIG",
    # Individual effects (for advanced usage)
    "EdgeCompositor",
    "DepthEffect",
    "VignetteEffect",
    "ShadowEffect",
    "ColorAdjustment",
    "ImageBlur",
    "Sharpening",
    "OverlayBlending",
]
