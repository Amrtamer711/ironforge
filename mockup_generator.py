import os
import random
import cv2
import numpy as np
from pathlib import Path
from typing import Optional, Tuple, List
import logging
import gc

import config
import db

logger = logging.getLogger("proposal-bot")

# Mockups storage directory
if os.path.exists("/data/"):
    MOCKUPS_DIR = Path("/data/mockups")
    logger.info(f"[MOCKUP INIT] Using PRODUCTION mockups directory: {MOCKUPS_DIR}")
else:
    MOCKUPS_DIR = Path(__file__).parent / "data" / "mockups"
    logger.info(f"[MOCKUP INIT] Using DEVELOPMENT mockups directory: {MOCKUPS_DIR}")

MOCKUPS_DIR.mkdir(parents=True, exist_ok=True)
logger.info(f"[MOCKUP INIT] Mockups directory exists: {MOCKUPS_DIR.exists()}, writable: {os.access(MOCKUPS_DIR, os.W_OK)}")


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
        # Simple reflection for small extensions
        return cv2.copyMakeBorder(
            image,
            extend_pixels, extend_pixels, extend_pixels, extend_pixels,
            cv2.BORDER_REFLECT_101
        )
    else:
        # Inpainting for larger extensions
        h, w = image.shape[:2]

        # Create extended canvas
        extended = cv2.copyMakeBorder(
            image,
            extend_pixels, extend_pixels, extend_pixels, extend_pixels,
            cv2.BORDER_REPLICATE
        )

        # Create mask for inpainting (only outermost border)
        mask = np.zeros((h + 2*extend_pixels, w + 2*extend_pixels), dtype=np.uint8)
        border_inpaint = min(extend_pixels, 15)  # Limit inpainting region

        mask[0:border_inpaint, :] = 255
        mask[-border_inpaint:, :] = 255
        mask[:, 0:border_inpaint] = 255
        mask[:, -border_inpaint:] = 255

        # Inpaint with Telea algorithm (fast and good quality)
        inpaint_radius = min(10, extend_pixels // 2)
        result = cv2.inpaint(extended, mask, inpaint_radius, cv2.INPAINT_TELEA)

        logger.info(f"[MOCKUP] Extended borders by {extend_pixels}px using inpainting")
        return result


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
    config: Optional[dict] = None,
    time_of_day: str = "day"
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

    # Get edge blur setting to determine border extension strategy
    edge_blur = 1
    if config and 'edgeBlur' in config:
        edge_blur = max(1, min(21, config['edgeBlur']))

    # Intelligently extend borders for high edge blur to prevent artifacts
    if edge_blur > 10:
        extend_amount = int(edge_blur * 2.5)
        method = 'inpaint' if edge_blur > 14 else 'reflect'
        logger.info(f"[MOCKUP] Extending creative borders by {extend_amount}px (method: {method}) for edge blur {edge_blur}")
        creative_upscaled = extend_image_borders_smart(creative_upscaled, extend_amount, method)

    # Source points (corners of upscaled creative image)
    h, w = creative_upscaled.shape[:2]
    src_pts = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)

    # Use the user's drawn frame exactly as-is (no scaling/adjustment)
    adjusted_dst_pts = dst_pts.copy()

    # Get perspective transform matrix
    H = cv2.getPerspectiveTransform(src_pts, adjusted_dst_pts)

    # Choose interpolation based on blur level (CUBIC has fewer artifacts for high blur)
    interp_method = cv2.INTER_CUBIC if edge_blur > 15 else cv2.INTER_LANCZOS4

    # Warp upscaled creative to billboard perspective with high-quality interpolation
    # Use BORDER_REFLECT_101 for natural mirrored borders (better than BORDER_REPLICATE)
    warped = cv2.warpPerspective(
        creative_upscaled,
        H,
        (billboard_image.shape[1], billboard_image.shape[0]),
        flags=interp_method,
        borderMode=cv2.BORDER_REFLECT_101  # Mirror reflection without edge duplication
    )

    # Create high-quality anti-aliased mask using super-sampling
    # Edge Smoother controls super-sampling factor (1-20x) for smooth edges
    edge_smoother = 3  # Default
    if config and 'edgeSmoother' in config:
        edge_smoother = max(1, min(20, config['edgeSmoother']))

    supersample_factor = edge_smoother
    h_hires = billboard_image.shape[0] * supersample_factor
    w_hires = billboard_image.shape[1] * supersample_factor
    logger.info(f"[MOCKUP] Edge smoother set to {edge_smoother}x super-sampling")

    # Scale destination points to high-res space
    dst_pts_hires = adjusted_dst_pts * supersample_factor

    # Draw mask at high resolution with anti-aliased lines
    mask_hires = np.zeros((h_hires, w_hires), dtype=np.uint8)
    cv2.fillPoly(mask_hires, [dst_pts_hires.astype(np.int32)], 255, lineType=cv2.LINE_AA)

    # Apply additional Gaussian blur at high-res for extra smoothing based on edge smoother
    # Higher edge smoother values = more aggressive smoothing
    if edge_smoother > 3:
        blur_strength = int((edge_smoother - 3) * 2)  # 0 at 3x, up to 34 at 20x
        if blur_strength > 0:
            kernel_size = blur_strength * 2 + 1  # Ensure odd
            mask_hires = cv2.GaussianBlur(mask_hires, (kernel_size, kernel_size), sigmaX=blur_strength/2)
            logger.info(f"[MOCKUP] Applied additional mask blur: {blur_strength}px for smoother edges")

    # Downsample to original resolution with high-quality interpolation
    # INTER_AREA is best for downsampling - produces smooth anti-aliased edges
    mask = cv2.resize(mask_hires, (billboard_image.shape[1], billboard_image.shape[0]),
                     interpolation=cv2.INTER_AREA)

    # Apply edge blur for additional smoothing (user-configurable)
    # Use config edge blur if provided
    edge_blur = 1
    if config and 'edgeBlur' in config:
        edge_blur = max(1, min(21, config['edgeBlur']))
        if edge_blur % 2 == 0:
            edge_blur += 1  # Ensure odd number for GaussianBlur

    mask_float = mask.astype(np.float32) / 255.0

    # ========================================================================
    # PHOTOREALISTIC EDGE COMPOSITING - Hollywood VFX-Grade Techniques
    # ========================================================================
    # This implements multiple industry-standard techniques from professional
    # compositing software (Nuke, After Effects, Fusion) for invisible edges
    # that look like the creative was actually printed on the billboard.
    #
    # Key principles:
    # - No hard black bars or obvious cutouts
    # - Natural light interaction at edges
    # - Billboard color influence on creative edges
    # - Depth-based edge darkening (ambient occlusion)
    # - Chromatic aberration simulation for realism
    # ========================================================================

    # Store original billboard colors at edge for color bleed later
    billboard_edge_colors = billboard_image.astype(np.float32)

    if edge_blur > 3:
        # =====================================================================
        # TECHNIQUE 1: Soft Matte with Gamma-Correct Blurring
        # =====================================================================
        # Linear blur (what we normally do) looks unnatural because human
        # vision and light work in gamma space. We convert to linear, blur,
        # then convert back for perceptually-correct edge softness.

        # Convert to linear space (inverse gamma 2.2)
        mask_linear = np.power(mask_float, 2.2)

        # Multi-radius blur for natural organic falloff
        # Large blur for soft outer edge + small blur for core sharpness
        kernel_size = edge_blur if edge_blur % 2 == 1 else edge_blur + 1
        mask_large = cv2.GaussianBlur(mask_linear, (kernel_size, kernel_size), sigmaX=edge_blur/2.5)

        # Calculate small kernel size - must be odd and at least 3
        small_kernel = kernel_size // 2
        if small_kernel % 2 == 0:  # If even, make it odd
            small_kernel = small_kernel + 1
        small_kernel = max(3, small_kernel)  # Minimum size is 3
        mask_small = cv2.GaussianBlur(mask_linear, (small_kernel, small_kernel), sigmaX=edge_blur/6.0)

        # Blend: core sharp, edges soft (80% soft blur, 20% sharp)
        mask_linear = mask_large * 0.8 + mask_small * 0.2

        # Convert back to gamma space
        mask_float = np.power(np.clip(mask_linear, 0, 1), 1/2.2)

        # =====================================================================
        # TECHNIQUE 2: Distance-Based Feathering with Falloff Curve
        # =====================================================================
        # Creates natural alpha gradient that mimics how real materials
        # transition. Uses smooth falloff curve (not linear).

        if edge_blur >= 8:
            mask_binary = (mask_float > 0.5).astype(np.uint8)
            dist_transform = cv2.distanceTransform(mask_binary, cv2.DIST_L2, 5)

            # Adaptive feather distance based on edge blur strength
            feather_pixels = min(edge_blur * 2.0, 40)

            # Smooth falloff curve (ease-in-out) instead of linear
            # This creates more natural-looking edges
            feather_normalized = np.clip(dist_transform / feather_pixels, 0, 1)
            # Apply smoothstep function: 3t² - 2t³ (ease in-out curve)
            feather_smooth = feather_normalized * feather_normalized * (3 - 2 * feather_normalized)

            # Blend with original (50% feathering for strong effect)
            feather_strength = 0.5
            mask_float = mask_float * (1 - feather_strength) + feather_smooth * feather_strength

        # =====================================================================
        # TECHNIQUE 3: Light Wrap / Edge Color Bleeding
        # =====================================================================
        # Simulates how billboard colors "wrap" around the creative edges
        # This is critical for realism - edges should pick up surrounding colors

        if edge_blur >= 8:
            # Find edge region (transition zone between billboard and creative)
            edge_detect_kernel = np.ones((5, 5), np.float32)
            dilated_mask = cv2.dilate(mask_float, edge_detect_kernel, iterations=1)
            eroded_mask = cv2.erode(mask_float, edge_detect_kernel, iterations=1)
            edge_region = dilated_mask - eroded_mask
            edge_region = np.clip(edge_region, 0, 1)

            # Extract billboard colors at edges with wide blur for color spill
            billboard_colors_blur = cv2.GaussianBlur(billboard_edge_colors, (31, 31), sigmaX=10)

            # Create light wrap effect (billboard color bleeds into creative edge)
            # Intensity scales with edge_blur (more blur = more color spill)
            light_wrap_strength = min(edge_blur / 20.0, 0.25)  # Max 25% blend
            edge_region_3ch = np.stack([edge_region] * 3, axis=-1)
            light_wrap_contribution = billboard_colors_blur * edge_region_3ch * light_wrap_strength
        else:
            light_wrap_contribution = None

        # =====================================================================
        # TECHNIQUE 4: Contact Shadow / Ambient Occlusion
        # =====================================================================
        # Simulates how edges darken where creative "meets" billboard surface
        # Creates depth and prevents floating appearance

        if edge_blur >= 10:
            # Detect edge more aggressively for contact shadow
            eroded = cv2.erode(mask_float, np.ones((3, 3), np.float32), iterations=2)
            edge_contact = mask_float - eroded
            edge_contact = np.clip(edge_contact * 4.0, 0, 1)

            # Blur the contact shadow for soft falloff
            edge_contact = cv2.GaussianBlur(edge_contact, (7, 7), sigmaX=2.0)

            # Stronger contact shadow for higher edge blur
            # This creates realistic "anchoring" of the creative to billboard
            shadow_intensity = min(0.2, edge_blur / 50.0)  # Max 20% darkening
            edge_shadow = edge_contact * shadow_intensity
        else:
            edge_shadow = None

        # =====================================================================
        # TECHNIQUE 5: Choke and Spread for Edge Refinement
        # =====================================================================
        # Professional technique to eliminate micro-jaggies and stair-stepping
        # while maintaining crisp inner edge

        if edge_blur >= 6:
            # Choke: Slightly pull in the edge
            kernel_choke = np.ones((2, 2), np.float32) / 4
            mask_choked = cv2.erode(mask_float, kernel_choke, iterations=1)

            # Spread: Expand back with soft blur
            mask_spread = cv2.GaussianBlur(mask_choked, (5, 5), sigmaX=1.5)

            # Blend between choked and spread based on edge quality needs
            mask_float = mask_spread * 0.7 + mask_choked * 0.3

        # =====================================================================
        # TECHNIQUE 6: Edge Luminance Adaptation
        # =====================================================================
        # Adjust edge transparency based on brightness difference
        # Bright edges against dark backgrounds need less feathering

        if edge_blur >= 8:
            # Calculate luminance at edges
            billboard_gray = cv2.cvtColor(billboard_image, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
            warped_gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0

            # Find edges again for luminance comparison
            edge_mask_binary = (mask_float > 0.1) & (mask_float < 0.9)

            # Calculate contrast at edges
            billboard_lum_blur = cv2.GaussianBlur(billboard_gray, (15, 15), sigmaX=5)
            warped_lum_blur = cv2.GaussianBlur(warped_gray, (15, 15), sigmaX=5)

            # High contrast edges can be sharper, low contrast needs more feather
            lum_diff = np.abs(billboard_lum_blur - warped_lum_blur)
            lum_diff_clipped = np.clip(lum_diff, 0, 1)

            # Sharpen high-contrast edges, soften low-contrast edges
            edge_adaptive = np.where(edge_mask_binary,
                                    1.0 + (lum_diff_clipped * 0.3),  # Up to 30% sharper
                                    1.0)
            mask_float = np.clip(mask_float * edge_adaptive, 0, 1)

    else:
        edge_shadow = None
        light_wrap_contribution = None

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
        depth_multiplier = config.get('depthMultiplier', 15)  # 5-30, default 15 (neutral)

        # Extract only the frame region from warped creative
        warped_float = warped.astype(np.float32)

        # ========================================================================
        # 3D DEPTH PERCEPTION EFFECTS (Time-of-Day Aware)
        # ========================================================================
        # EASY REMOVAL: Set ENABLE_DEPTH_EFFECTS = False to disable completely
        ENABLE_DEPTH_EFFECTS = True

        if ENABLE_DEPTH_EFFECTS and depth_multiplier != 15:
            # Calculate intensity: 0 at depth=15 (neutral), increases as it moves away from 15
            depth_intensity = abs(depth_multiplier - 15) / 15.0  # 0.0 to 1.0

            # Apply different effects based on time of day
            if time_of_day == "night":
                # NIGHT: Directional spotlight effect (lit from top)
                # Simulates billboard illuminated by spotlights from above
                x, y, w, h = cv2.boundingRect(dst_pts.astype(int))
                y_coords, x_coords = np.ogrid[:billboard_image.shape[0], :billboard_image.shape[1]]

                # Vertical gradient: top (lit) to bottom (shadow)
                y_norm = np.clip((y_coords - y) / max(h, 1), 0, 1)
                lighting_gradient = 1.0 - (y_norm * depth_intensity * 0.35)  # Up to 35% darker at bottom

                # Apply only within mask
                lighting_gradient = lighting_gradient * mask_float + (1 - mask_float)
                lighting_gradient_3ch = np.stack([lighting_gradient] * 3, axis=-1)
                warped_float = warped_float * lighting_gradient_3ch
                warped_float = np.clip(warped_float, 0, 255)

                logger.info(f"[MOCKUP] Applied night spotlight depth (intensity: {depth_intensity:.2f})")

            else:  # "day" or default
                # DAY: Atmospheric perspective (aerial perspective effect)
                # Things appear hazier, less saturated, and lower contrast when further away

                # Convert to HSV for saturation adjustment
                warped_uint = warped_float.astype(np.uint8)
                hsv = cv2.cvtColor(warped_uint, cv2.COLOR_BGR2HSV).astype(np.float32)

                # Reduce saturation (up to 15% at max intensity)
                desaturation = 1.0 - (depth_intensity * 0.15)
                hsv[:, :, 1] = hsv[:, :, 1] * desaturation * mask_float + hsv[:, :, 1] * (1 - mask_float)
                hsv[:, :, 1] = np.clip(hsv[:, :, 1], 0, 255)

                warped_float = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR).astype(np.float32)

                # Reduce contrast (up to 12% at max intensity)
                mean = np.mean(warped_float[mask_float > 0.5])
                contrast_factor = 1.0 - (depth_intensity * 0.12)
                warped_float = mean + (warped_float - mean) * contrast_factor
                warped_float = np.clip(warped_float, 0, 255)

                # Slight blue shift (atmospheric scattering - up to +8 blue)
                blue_shift = depth_intensity * 8
                warped_float[:, :, 0] += blue_shift * mask_float  # Blue channel
                warped_float = np.clip(warped_float, 0, 255)

                logger.info(f"[MOCKUP] Applied daytime atmospheric depth (intensity: {depth_intensity:.2f})")
        # ========================================================================

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

    # Apply photorealistic edge effects (from advanced edge smoothing)
    warped_enhanced = warped.astype(np.float32)

    # Apply contact shadow for depth
    if edge_shadow is not None:
        edge_shadow_3ch = np.stack([edge_shadow] * 3, axis=-1)
        warped_enhanced = warped_enhanced * (1 - edge_shadow_3ch)
        logger.info(f"[MOCKUP] Applied contact shadow for edge depth (blur: {edge_blur})")

    # Apply light wrap (billboard color bleeding onto creative edges)
    if light_wrap_contribution is not None:
        warped_enhanced = warped_enhanced + light_wrap_contribution
        warped_enhanced = np.clip(warped_enhanced, 0, 255)
        logger.info(f"[MOCKUP] Applied light wrap for photorealistic color bleeding (blur: {edge_blur})")

    # Prevent green screen/background bleed-through at high edge blur
    # When mask is heavily blurred, fill billboard frame area with creative edge color
    # This prevents green screens or adjacent billboards from showing through
    if edge_blur > 12:
        # Find pixels that are part of the frame (mask > 0.05)
        frame_region = mask_3ch[:,:,0] > 0.05

        if np.sum(frame_region) > 0:
            # Calculate average color from creative edges within frame
            edge_region = (mask_3ch[:,:,0] > 0.05) & (mask_3ch[:,:,0] < 0.95)
            if np.sum(edge_region) > 100:  # Enough edge pixels
                edge_pixels = warped_enhanced[edge_region]
                fill_color = np.mean(edge_pixels, axis=0)
            else:
                # Fallback: use overall average of warped creative in frame
                fill_color = np.mean(warped_enhanced[frame_region], axis=0)

            # Create filled billboard (replace frame area with fill color)
            billboard_filled = billboard_image.copy().astype(np.float32)
            billboard_filled[frame_region] = fill_color

            logger.info(f"[MOCKUP] Pre-filled billboard frame to prevent background bleed (edge blur: {edge_blur})")
        else:
            billboard_filled = billboard_image.astype(np.float32)
    else:
        billboard_filled = billboard_image.astype(np.float32)

    # Blend with adjusted opacity to let billboard details enhance the creative
    result = (billboard_filled * (1 - mask_3ch * creative_opacity) +
              warped_enhanced * mask_3ch * creative_opacity).astype(np.uint8)

    # Apply optional sharpening (user-configurable, default off)
    sharpening = 0  # Default: no sharpening
    if config and 'sharpening' in config:
        sharpening = max(0, min(100, config['sharpening']))

    if sharpening > 0:
        # Convert sharpening percentage to strength (0-100 -> 1.0-1.5x)
        strength = 1.0 + (sharpening / 100.0) * 0.5

        # Apply unsharp mask with user-defined strength
        gaussian_blur = cv2.GaussianBlur(result, (0, 0), 2.0)
        negative_weight = -(strength - 1.0)
        unsharp_mask = cv2.addWeighted(result, strength, gaussian_blur, negative_weight, 0)

        # Apply only within frame region (using mask)
        result = (result.astype(np.float32) * (1 - mask_3ch) +
                  unsharp_mask.astype(np.float32) * mask_3ch).astype(np.uint8)

        logger.info(f"[MOCKUP] Applied sharpening: {sharpening}% (strength: {strength:.2f}x)")

        # Cleanup sharpening intermediate arrays
        del gaussian_blur, unsharp_mask
    else:
        logger.info(f"[MOCKUP] Sharpening disabled (0%)")

    # Cleanup ALL intermediate processing arrays to free memory immediately
    # After this point, only 'result' is needed for return
    # Each del wrapped individually so one missing variable doesn't skip others
    import gc

    for var in ['creative_upscaled', 'warped', 'billboard_image', 'creative_image',
                'mask_hires', 'mask', 'mask_3ch', 'billboard_filled', 'warped_enhanced',
                'mask_float', 'mask_linear', 'mask_large', 'mask_small', 'mask_spread', 'mask_choked',
                'mask_binary', 'dist_transform', 'edge_detect_kernel', 'dilated_mask', 'eroded_mask',
                'edge_region', 'edge_region_3ch', 'edge_contact', 'edge_shadow', 'edge_mask_binary',
                'edge_adaptive', 'billboard_edge_colors', 'billboard_colors_blur', 'billboard_gray',
                'billboard_lum_blur', 'warped_float', 'warped_gray', 'warped_lum_blur', 'warped_uint',
                'light_wrap_contribution', 'lighting_gradient', 'lighting_gradient_3ch',
                'feather_normalized', 'feather_smooth', 'lum_diff', 'lum_diff_clipped',
                'hsv', 'y_coords', 'x_coords', 'y_norm', 'gaussian_blur', 'unsharp_mask']:
        try:
            del locals()[var]
        except:
            pass

    # Force immediate garbage collection
    gc.collect()

    return result


def get_location_photos_dir(location_key: str, time_of_day: str = "day", finish: str = "gold") -> Path:
    """Get the directory for a location's mockup photos with time_of_day and finish."""
    return MOCKUPS_DIR / location_key / time_of_day / finish


def save_location_photo(location_key: str, photo_filename: str, photo_data: bytes, time_of_day: str = "day", finish: str = "gold") -> Path:
    """Save a location photo to disk with time_of_day and finish."""
    location_dir = get_location_photos_dir(location_key, time_of_day, finish)

    logger.info(f"[MOCKUP] Creating directory: {location_dir}")
    location_dir.mkdir(parents=True, exist_ok=True)

    photo_path = location_dir / photo_filename
    logger.info(f"[MOCKUP] Writing {len(photo_data)} bytes to: {photo_path}")

    try:
        photo_path.write_bytes(photo_data)

        # Verify the file was written correctly
        if photo_path.exists():
            actual_size = photo_path.stat().st_size
            logger.info(f"[MOCKUP] ✓ Photo saved successfully: {photo_path} ({actual_size} bytes)")

            # Verify we can read it back
            test_read = photo_path.read_bytes()
            if len(test_read) == len(photo_data):
                logger.info(f"[MOCKUP] ✓ Photo verified readable")
            else:
                logger.error(f"[MOCKUP] ✗ Photo size mismatch! Written: {len(photo_data)}, Read: {len(test_read)}")
        else:
            logger.error(f"[MOCKUP] ✗ Photo path does not exist after write: {photo_path}")
    except Exception as e:
        logger.error(f"[MOCKUP] ✗ Failed to save photo: {e}", exc_info=True)
        raise

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

    # Special handling for "all" - pick from filtered variations
    if time_of_day == "all" or finish == "all":
        # Get all variations available for this location
        variations = db.list_mockup_variations(location_key)
        if not variations:
            logger.warning(f"[MOCKUP] No variations found for location '{location_key}'")
            return None

        # Build list of all (time_of_day, finish, photo) tuples, filtered by specified dimension
        all_photos = []
        for tod in variations:
            # If user specified time_of_day, only use that one
            if time_of_day != "all" and tod != time_of_day:
                continue

            for fin in variations[tod]:
                # If user specified finish, only use that one
                if finish != "all" and fin != finish:
                    continue

                photos = db.list_mockup_photos(location_key, tod, fin)
                for photo in photos:
                    all_photos.append((photo, tod, fin))

        if not all_photos:
            filter_info = ""
            if time_of_day != "all":
                filter_info += f" time_of_day={time_of_day}"
            if finish != "all":
                filter_info += f" finish={finish}"
            logger.warning(f"[MOCKUP] No photos found for location '{location_key}'{filter_info}")
            return None

        # Pick random from filtered available photos
        photo_filename, selected_tod, selected_finish = random.choice(all_photos)
        photo_path = get_location_photos_dir(location_key, selected_tod, selected_finish) / photo_filename

        if not photo_path.exists():
            logger.error(f"[MOCKUP] Photo file not found: {photo_path}")
            return None

        filter_desc = []
        if time_of_day != "all":
            filter_desc.append(f"time={time_of_day}")
        if finish != "all":
            filter_desc.append(f"finish={finish}")
        filter_str = f" (filtered: {', '.join(filter_desc)})" if filter_desc else " (all variations)"
        logger.info(f"[MOCKUP] Selected random photo for '{location_key}'{filter_str}: {photo_filename} ({selected_tod}/{selected_finish})")
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


def is_portrait_location(location_key: str) -> bool:
    """Check if a location has portrait orientation based on actual frame dimensions from database.

    Args:
        location_key: Location identifier

    Returns:
        True if height > width (portrait), False otherwise (landscape or unknown)
    """
    # Get any frame from this location to check dimensions
    variations = db.list_mockup_variations(location_key)
    if not variations:
        logger.warning(f"[ORIENTATION] No mockup frames found for '{location_key}'")
        return False  # Default to landscape if no frames

    # Get first available variation
    for time_of_day, finishes in variations.items():
        if finishes:
            finish = finishes[0]
            # Get any photo for this location
            photos = db.list_mockup_photos(location_key, time_of_day, finish)
            if photos:
                # Get frames from first photo
                frames_data = db.get_mockup_frames(location_key, photos[0], time_of_day, finish)
                if frames_data and len(frames_data) > 0:
                    # Extract first frame points: [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]
                    points = frames_data[0]["points"]

                    # Calculate width and height from the 4 corner points
                    # Width = average of top edge and bottom edge
                    # Height = average of left edge and right edge
                    import math

                    # Top edge length (point 0 to point 1)
                    top_width = math.sqrt((points[1][0] - points[0][0])**2 + (points[1][1] - points[0][1])**2)
                    # Bottom edge length (point 3 to point 2)
                    bottom_width = math.sqrt((points[2][0] - points[3][0])**2 + (points[2][1] - points[3][1])**2)
                    # Left edge length (point 0 to point 3)
                    left_height = math.sqrt((points[3][0] - points[0][0])**2 + (points[3][1] - points[0][1])**2)
                    # Right edge length (point 1 to point 2)
                    right_height = math.sqrt((points[2][0] - points[1][0])**2 + (points[2][1] - points[1][1])**2)

                    avg_width = (top_width + bottom_width) / 2
                    avg_height = (left_height + right_height) / 2

                    is_portrait = avg_height > avg_width
                    logger.info(f"[ORIENTATION] Location '{location_key}': frame dimensions {avg_width:.0f}x{avg_height:.0f}px → {'PORTRAIT' if is_portrait else 'LANDSCAPE'}")
                    return is_portrait

    logger.warning(f"[ORIENTATION] Could not determine orientation for '{location_key}'")
    return False  # Default to landscape if can't determine


async def generate_ai_creative(prompt: str, size: str = "1536x1024", location_key: Optional[str] = None, user_id: Optional[str] = None) -> Optional[Path]:
    """Generate a creative using OpenAI gpt-image-1 API.

    Args:
        prompt: Text description for image generation
        size: Image size (default landscape "1536x1024")
        location_key: Optional location key to auto-detect portrait orientation
        user_id: Optional Slack user ID for cost tracking (None for website mockup)

    Returns:
        Path to generated image, or None if failed
    """
    import tempfile
    import base64
    from openai import AsyncOpenAI
    import cost_tracking

    # Auto-detect portrait orientation if location_key provided
    if location_key and is_portrait_location(location_key):
        size = "1024x1536"  # Portrait aspect ratio
        logger.info(f"[AI_CREATIVE] Auto-detected portrait orientation for '{location_key}', using size {size}")
    else:
        logger.info(f"[AI_CREATIVE] Using landscape orientation, size {size}")

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

        # Track cost for image generation
        # Images API doesn't return token usage, so we track with fixed cost
        # gpt-image-1 high quality: $0.080 per image
        cost_tracking.track_image_generation(
            model="gpt-image-1",
            size=size,
            quality="high",
            n=1,
            user_id=user_id if user_id else "website_mockup",
            context=f"AI creative generation: {location_key or 'unknown location'}",
            metadata={"prompt_length": len(prompt), "size": size, "location_key": location_key}
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

        # Apply subtle sharpening (weakened to avoid artifacts)
        # Old: 1.8x sharpening was too aggressive
        # New: 1.2x mild sharpening to slightly enhance AI image without degradation
        gaussian = cv2.GaussianBlur(img_array, (0, 0), 2.0)
        sharpened = cv2.addWeighted(img_array, 1.2, gaussian, -0.2, 0)

        # Apply very subtle contrast enhancement
        lab = cv2.cvtColor(sharpened, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8))
        l = clahe.apply(l)
        enhanced = cv2.merge([l, a, b])
        enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)

        logger.info("[AI_CREATIVE] Applied subtle sharpening (1.2x) and contrast enhancement to AI image")

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
    finish: str = "gold",
    config_override: Optional[dict] = None
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
        config_override: Optional config dict to override saved frame config

    Returns:
        Tuple of (Path to the generated mockup image, photo_filename used), or (None, None) if failed
    """
    logger.info(f"[MOCKUP] Generating mockup for location '{location_key}/{time_of_day}/{finish}' with {len(creative_images)} creative(s)")

    # Get billboard photo
    if specific_photo:
        photo_filename = specific_photo
        photo_path = get_location_photos_dir(location_key, time_of_day, finish) / photo_filename
        if not photo_path.exists():
            logger.error(f"[MOCKUP] Specific photo not found: {photo_path}")
            return None, None
    else:
        result = get_random_location_photo(location_key, time_of_day, finish)
        if not result:
            return None, None
        photo_filename, time_of_day, finish, photo_path = result

    # Get all frame coordinates (list of frames)
    frames_data = db.get_mockup_frames(location_key, photo_filename, time_of_day, finish)
    if not frames_data:
        logger.error(f"[MOCKUP] No frame coordinates found for '{location_key}/{time_of_day}/{finish}/{photo_filename}'")
        return None, None

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
        return None, None

    # Load billboard
    try:
        billboard = cv2.imread(str(photo_path))
        if billboard is None:
            logger.error(f"[MOCKUP] Failed to load billboard image: {photo_path}")
            return None, None
    except Exception as e:
        logger.error(f"[MOCKUP] Error loading billboard: {e}")
        return None, None

    # Start with the billboard as the result
    result = billboard.copy()

    # Apply each creative to each frame
    for i, frame_data in enumerate(frames_data):
        # New format: {"points": [...], "config": {brightness: 100, blurStrength: 8, ...}}
        frame_points = frame_data["points"]
        frame_config = frame_data.get("config", {})

        logger.info(f"[MOCKUP] Frame {i+1} raw config: {frame_config}")

        # Merge configs: photo_config < frame_config < config_override (highest priority)
        merged_config = photo_config.copy() if photo_config else {}
        merged_config.update(frame_config)
        if config_override:
            merged_config.update(config_override)
            logger.info(f"[MOCKUP] Frame {i+1} applying config override: {config_override}")

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
                return None, None
        except Exception as e:
            logger.error(f"[MOCKUP] Error loading creative {i}: {e}")
            return None, None

        # Warp creative onto this frame with merged config
        try:
            result = warp_creative_to_billboard(result, creative, frame_points, config=merged_config, time_of_day=time_of_day)
            edge_blur = merged_config.get('edgeBlur', 8)
            image_blur = merged_config.get('imageBlur', 0)
            logger.info(f"[MOCKUP] Applied creative {i+1}/{num_frames} to frame {i+1} (edge blur: {edge_blur}px, image blur: {image_blur})")
        except Exception as e:
            logger.error(f"[MOCKUP] Error warping creative {i}: {e}")
            # Cleanup on error
            del billboard, result, creative
            gc.collect()
            return None, None

        # Explicitly delete creative image to free memory after each frame
        del creative

    # Save result
    if not output_path:
        import tempfile
        output_path = Path(tempfile.mktemp(suffix=".jpg"))

    try:
        cv2.imwrite(str(output_path), result)
        logger.info(f"[MOCKUP] Generated mockup saved to: {output_path}")

        # Cleanup large numpy arrays to free memory immediately
        del billboard, result
        gc.collect()

        return output_path, photo_filename
    except Exception as e:
        logger.error(f"[MOCKUP] Error saving mockup: {e}")
        # Cleanup on error
        try:
            del billboard, result
        except:
            pass
        gc.collect()
        return None, None


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
