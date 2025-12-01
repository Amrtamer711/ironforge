# Mockup prompts - AI image generation for billboard artwork


def get_ai_mockup_prompt(is_portrait: bool = False) -> str:
    """
    Generate the enhanced system prompt for AI billboard artwork generation.

    Args:
        is_portrait: True for portrait/vertical orientation, False for landscape/horizontal

    Returns:
        The complete prompt template with {USER_PROMPT} placeholder
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

    return f"""Create a professional flat 2D artwork/creative design for outdoor advertising.

⚠️ CRITICAL RULES - READ FIRST:
1. Generate CLEAN, FLAT graphics with SOLID elements
2. FILL THE ENTIRE CANVAS - create a COMPLETE, full advertisement design
3. NO blank/empty backgrounds unless explicitly requested
4. Use modern, contemporary design aesthetic (2024+ style)
5. ABSOLUTELY NO glowing effects, light flares, halos, sparkles, or radiating effects around ANY elements, especially text and logos
6. This should look like a PROFESSIONAL AD from a creative agency

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

{{USER_PROMPT}}"""





def get_api_mockup_prompt(ai_prompt: str) -> str:
    """
    Generate the enhanced system prompt for API billboard artwork generation.

    This is used by the web API endpoint for AI mockup generation.

    Args:
        ai_prompt: The user's creative brief/prompt describing what they want

    Returns:
        The complete prompt with the user's brief embedded
    """
    return f"""Create a professional outdoor advertising billboard creative - IMPORTANT: This is the FLAT 2D ARTWORK FILE that will be printed and placed ON a billboard, NOT a photograph of an existing billboard.

═══════════════════════════════════════════════════════════
CRITICAL DISTINCTIONS:
═══════════════════════════════════════════════════════════

✅ CORRECT OUTPUT (what we want):
- A flat, rectangular advertisement design (like a Photoshop/Illustrator file)
- The actual graphic design artwork that goes ON the billboard surface
- Think: magazine ad, poster design, digital banner creative
- Perfectly rectangular, no perspective, no angle, no depth
- Edge-to-edge design filling the entire rectangular canvas
- Like looking at a computer screen showing the ad design

❌ INCORRECT OUTPUT (what we DON'T want):
- A photograph of a physical billboard in a street scene
- 3D rendering showing billboard from an angle/perspective
- Image with billboard frame, poles, or support structure visible
- Photo showing buildings, sky, roads, or environment around billboard
- Any mockup showing how the billboard looks in real life
- Perspective view, vanishing points, or dimensional representation

═══════════════════════════════════════════════════════════
DETAILED DESIGN REQUIREMENTS:
═══════════════════════════════════════════════════════════

📐 FORMAT & DIMENSIONS:
- Aspect ratio: Wide landscape (roughly 3:2 ratio)
- Orientation: Horizontal/landscape ONLY
- Canvas: Perfectly flat, rectangular, no warping or perspective
- Fill entire frame edge-to-edge with design
- No white borders, frames, or margins around the design

🎨 VISUAL DESIGN PRINCIPLES:
- Bold, high-impact composition that catches attention immediately
- Large hero image or visual focal point (50-70% of design)
- Vibrant, saturated colors that pop in daylight
- High contrast between elements for maximum visibility
- Simple, uncluttered layout (viewer has 5-7 seconds max)
- Professional photo quality or clean vector graphics
- Modern, contemporary advertising aesthetic

✍️ TYPOGRAPHY (if text is needed):
- LARGE, bold, highly readable fonts
- Sans-serif typefaces work best for outdoor viewing
- Maximum 7-10 words total (fewer is better)
- High contrast text-to-background ratio
- Text size: headlines should occupy 15-25% of vertical height
- Clear hierarchy: one main message, optional supporting text
- Avoid script fonts, thin fonts, or decorative typefaces
- Letter spacing optimized for distance reading

🎯 COMPOSITION STRATEGY:
- Rule of thirds or strong visual hierarchy
- One clear focal point (don't scatter attention)
- Negative space used strategically
- Visual flow guides eye to key message/CTA
- Brand logo prominent but not dominating (10-15% of space)
- Clean, professional layout with breathing room

💡 COLOR THEORY FOR OUTDOOR:
- Vibrant, saturated colors (avoid pastels or muted tones)
- High contrast pairings: dark on light or light on dark
- Colors that work in bright sunlight and shadows
- Consistent brand color palette if applicable
- Background should enhance, not compete with message
- Consider: bright blues, bold reds, energetic oranges, fresh greens

🔍 QUALITY STANDARDS:
- Sharp, crisp graphics (no blur, pixelation, or artifacts)
- Professional commercial photography or illustration
- Consistent lighting across all design elements
- No watermarks, stock photo markers, or placeholder text
- Print-ready quality at large scale
- Polished, agency-level execution

═══════════════════════════════════════════════════════════
CREATIVE BRIEF:
═══════════════════════════════════════════════════════════

{ai_prompt}

═══════════════════════════════════════════════════════════
FINAL REMINDER:
═══════════════════════════════════════════════════════════

You are creating the ARTWORK FILE - the actual advertisement design.
Imagine you're a graphic designer creating this in Adobe Illustrator or Photoshop.
The output should be the flat design that will be PLACED onto a billboard structure later.
DO NOT show the billboard itself, the street, or any environmental context.
Just deliver the pure, flat, rectangular advertisement graphic.

Example analogy: If asked to create a "movie poster," you'd create the poster ARTWORK, not a photo of someone holding a poster in a cinema."""

