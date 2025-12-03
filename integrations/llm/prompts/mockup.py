# Mockup prompts - AI image generation for billboard artwork


def get_mockup_prompt(is_portrait: bool = False, user_prompt: str | None = None) -> str:
    """
    Generate the system prompt for AI billboard artwork generation.

    This unified function supports both Slack bot and Web API use cases.

    Args:
        is_portrait: True for portrait/vertical orientation, False for landscape/horizontal
        user_prompt: Optional user's creative brief. If provided, replaces {USER_PROMPT} placeholder.
                    If None, returns template with {USER_PROMPT} placeholder for later substitution.

    Returns:
        The complete prompt, either with placeholder or with user_prompt embedded
    """
    if is_portrait:
        orientation_text = """📐 FORMAT & DIMENSIONS:
- Aspect ratio: Tall portrait (roughly 2:3 ratio)
- Orientation: Vertical/portrait ONLY
- Canvas: Perfectly flat, rectangular, no warping or perspective
- Fill entire frame edge-to-edge with design
- No white borders, frames, or margins around the design"""
    else:
        orientation_text = """📐 FORMAT & DIMENSIONS:
- Aspect ratio: Wide landscape (roughly 3:2 ratio)
- Orientation: Horizontal/landscape ONLY
- Canvas: Perfectly flat, rectangular, no warping or perspective
- Fill entire frame edge-to-edge with design
- No white borders, frames, or margins around the design"""

    # Use placeholder or actual prompt
    prompt_section = user_prompt if user_prompt else "{USER_PROMPT}"

    return f"""🚨🚨🚨 MANDATORY OUTPUT FORMAT 🚨🚨🚨
The generated image must BE the advertisement itself - filling 100% of the canvas from edge to edge.
NEVER show the ad placed on, mounted on, or displayed on ANY surface (no walls, billboards, screens, displays, posters on surfaces, etc.)
The ad IS the entire image. Nothing else should be visible - no environment, no mounting surface, no frame.

Create a professional flat 2D artwork/creative design for outdoor advertising.

⚠️ CRITICAL RULES - READ FIRST:
1. THE AD MUST FILL THE ENTIRE IMAGE - the ad IS the image, not an ad placed inside an image
2. Generate CLEAN, FLAT graphics with SOLID elements
3. FILL THE ENTIRE CANVAS - create a COMPLETE, full advertisement design
4. NO blank/empty backgrounds unless explicitly requested
5. Use modern, contemporary design aesthetic (2024+ style)
6. ABSOLUTELY NO glowing effects, light flares, halos, sparkles, or radiating effects around ANY elements, especially text and logos
7. This should look like a PROFESSIONAL AD from a creative agency
8. DO NOT place the ad on a billboard, wall, screen, or any surface - just create the raw flat artwork
9. DO NOT show the ad as a poster/sign hanging or mounted anywhere - the ad fills the entire generated image

═══════════════════════════════════════════════════════════
🚨 CRITICAL: WHAT YOU ARE CREATING
═══════════════════════════════════════════════════════════

YOU ARE CREATING: **ARTWORK/CREATIVE CONTENT ONLY**
- This is the flat graphic design file (like a Photoshop/Illustrator artwork)
- This artwork will later be placed on a billboard template by our system
- Generate ONLY the creative content, NOT a billboard mockup or photo

✅ CORRECT OUTPUT (what we want):
- A flat, rectangular advertisement design filling the entire canvas
- The actual graphic artwork (like a poster, magazine ad, or digital banner)
- Perfectly flat with no perspective, no 3D elements, no depth
- Edge-to-edge design with no borders, frames, or margins
- Think: the content you'd see on a computer screen when designing an ad
- Like a print-ready advertisement file before it's mounted anywhere

❌ INCORRECT OUTPUT (what we DON'T want):
- ❌ DO NOT create a photo of a physical billboard
- ❌ DO NOT show billboard frames, poles, or support structures
- ❌ DO NOT include perspective, angles, or 3D rendering
- ❌ DO NOT show street scenes, buildings, sky, roads, or environment
- ❌ DO NOT create a mockup showing how the billboard looks when installed
- ❌ DO NOT add vanishing points or dimensional representation
- ❌ DO NOT place the ad ON a surface, wall, screen, or display
- ❌ DO NOT show the ad mounted, posted, or displayed on anything
- ❌ DO NOT render the ad as if it's hanging, projected, or attached to something

**REMEMBER:** You are creating the ARTWORK that will go ON the billboard,
not a picture OF a billboard. We have a separate template system for that.

═══════════════════════════════════════════════════════════
DETAILED DESIGN REQUIREMENTS:
═══════════════════════════════════════════════════════════

{orientation_text}

🎨 VISUAL DESIGN PRINCIPLES:
- MODERN 2024+ AESTHETIC: Contemporary, sleek, professional design style
- FILL THE CANVAS: Edge-to-edge design with rich visual content - NO blank/empty spaces
- High-impact composition that catches attention immediately
- Large hero image or visual focal point (50-70% of design)
- Strong colors appropriate for outdoor advertising
- Background should be FULLY designed - use colors, images, patterns, or textures (NOT blank white/empty)
- Clear separation between design elements for readability
- Simple but COMPLETE layout (viewer has 5-7 seconds max)
- Professional photo quality or clean vector graphics
- FLAT graphics only - no special effects, glows, or embellishments around elements

✍️ TYPOGRAPHY (if text is needed):
- LARGE, highly readable fonts with clean edges
- Sans-serif typefaces work best for outdoor viewing
- Maximum 7-10 words total (fewer is better)
- Strong text-to-background distinction for readability
- Text size: headlines should occupy 15-25% of vertical height
- Clear hierarchy: one main message, optional supporting text
- Avoid script fonts, thin fonts, or decorative typefaces
- Letter spacing optimized for distance reading
- Text should be solid and clean - NO glows, halos, shadows, or effects around letters

🎯 COMPOSITION STRATEGY:
- FULL CANVAS UTILIZATION: Every part of the design should be intentional and filled
- Rule of thirds or strong visual hierarchy
- One clear focal point (don't scatter attention)
- Strategic use of space - but NO large blank/empty areas
- Visual flow guides eye to key message/CTA
- Brand logo prominent but not dominating (10-15% of space)
- Clean, professional layout with purposeful design elements throughout
- Modern advertising style: bold, complete, visually rich compositions

💡 COLOR THEORY FOR OUTDOOR:
- CRITICAL: Use EXACTLY the colors specified in the creative brief - DO NOT substitute or change colors
- If user requests red background, use RED background - not blue or any other color
- If user requests specific brand colors, use those EXACT colors without modification
- NO BLANK WHITE BACKGROUNDS unless explicitly requested - use rich, designed backgrounds
- Strong colors appropriate to brand (avoid pastels or muted tones)
- Clear distinction between foreground and background elements
- Colors that work well in outdoor conditions
- Background should be fully designed with color, imagery, or patterns - NOT empty/blank
- Avoid repetitive color schemes - vary your palette based on the creative brief
- Solid, flat color application - NO gradients radiating from text or logos

🔍 QUALITY STANDARDS:
- Sharp, crisp graphics (no blur, pixelation, or artifacts)
- Professional commercial photography or illustration
- Even, balanced exposure across all design elements
- No watermarks, stock photo markers, or placeholder text
- Print-ready quality at large scale
- Polished, agency-level execution
- COMPLETE DESIGN: No unfinished areas, blank spaces, or missing elements
- Modern, contemporary look that matches current 2024+ advertising trends

═══════════════════════════════════════════════════════════
⚠️ CRITICAL - FINAL REMINDER - READ CAREFULLY:
═══════════════════════════════════════════════════════════

🚫 ABSOLUTELY DO NOT INCLUDE:
- NO billboards, signs, or advertising structures
- NO street scenes, highways, or roads
- NO people holding/viewing the ad
- NO frames, borders, or physical contexts
- NO 3D perspective or mockup views
- NO environmental surroundings whatsoever
- NO glowing effects, light flares, or dramatic lighting around text/logos
- NO lens flares, sparkles, or artificial light sources
- NO halos, glows, or radiating effects from any elements
- NO blank/empty white backgrounds (unless specifically requested)
- NO unfinished or incomplete designs
- NO dated or old-fashioned design styles - keep it modern
- NO surfaces the ad is placed on (walls, screens, displays, boards, panels)
- NO background showing the ad mounted or installed anywhere
- NO "ad within an image" - the ad IS the entire image, edge to edge

✅ YOU MUST CREATE:
- The FLAT ARTWORK FILE ONLY - the pure advertisement design
- A COMPLETE, FILLED, PROFESSIONAL advertisement (edge-to-edge)
- MODERN 2024+ design style - contemporary, sleek, polished
- A rectangular graphic that will be PLACED onto a billboard LATER
- Think: top-tier creative agency advertisement design
- The final output is a COMPLETE CREATIVE with NO blank areas

📐 DELIVERABLE:
Imagine you're delivering a print file to a billboard company.
They will take YOUR flat design and apply it to their billboard.
Your job: create a COMPLETE, PROFESSIONAL, MODERN advertisement.
Their job: put it on the billboard.

Example: If asked for a "Nike shoe ad," create a COMPLETE advertisement graphic with:
- Full background design (colored, textured, or image-based - NOT blank)
- Product imagery (shoe)
- Brand elements (swoosh logo)
- Text/slogan if needed
- Modern, contemporary design style
- FILLED canvas with intentional design throughout

DELIVER A COMPLETE, MODERN, PROFESSIONAL ADVERTISEMENT - FULLY DESIGNED, NO BLANK AREAS.

═══════════════════════════════════════════════════════════
🎯 YOUR CREATIVE BRIEF (FOLLOW THIS EXACTLY):
═══════════════════════════════════════════════════════════

{prompt_section}"""


# Backward compatibility aliases
def get_ai_mockup_prompt(is_portrait: bool = False) -> str:
    """
    Backward compatibility wrapper for get_mockup_prompt.

    Deprecated: Use get_mockup_prompt() instead.
    """
    return get_mockup_prompt(is_portrait=is_portrait, user_prompt=None)


def get_api_mockup_prompt(ai_prompt: str) -> str:
    """
    Backward compatibility wrapper for get_mockup_prompt.

    Deprecated: Use get_mockup_prompt() instead.
    """
    return get_mockup_prompt(is_portrait=False, user_prompt=ai_prompt)
