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
        aspect = "portrait (2:3 ratio, vertical)"
    else:
        aspect = "landscape (3:2 ratio, horizontal)"

    # Use placeholder or actual prompt
    prompt_section = user_prompt if user_prompt else "{USER_PROMPT}"

    return f"""A high-resolution, print-ready billboard advertisement artwork in {aspect} format. Generate ONLY the flat ad print file itself - the artwork that gets sent to the printer. No billboard structure, no mounting frame, no background environment - just the raw ad graphic filling the entire canvas edge-to-edge like a PNG export from Adobe Illustrator.

CRITICAL: The image must BE the advertisement - filling 100% of the canvas edge-to-edge.
- Do NOT render it on a billboard, wall, screen, or any surface
- Do NOT show the ad mounted, displayed, placed, or hanging anywhere
- Do NOT include any environment, background scene, or physical context
- The artwork fills the ENTIRE image with NO borders or frames

Think of it like exporting a design from Photoshop - just the flat artwork file, nothing else. The camera angle is perfectly perpendicular to the design surface, with zero perspective distortion.

FORMAT: {aspect}, flat rectangular canvas, studio-lit with even illumination, no perspective, no 3D effects, no depth.

DESIGN REQUIREMENTS:
- Professional advertisement, modern 2024+ aesthetic
- Edge-to-edge design filling the entire canvas
- Complete composition: background, imagery, text, and branding
- Large hero image or focal point (50-70% of design)
- Bold, high-contrast colors appropriate for outdoor viewing
- No blank/white backgrounds unless explicitly requested
- No glows, halos, lens flares, or effects around text/logos
- Clean, readable sans-serif typography (7-10 words max)
- Print-ready quality, sharp and crisp

COLOR RULES:
- Use EXACTLY the colors specified in the brief - do not substitute
- Background must be fully designed (color, pattern, or imagery)
- High contrast between text and background

WHAT TO CREATE:
- A flat graphic design file (like a Photoshop/Illustrator export)
- Professional agency-level advertisement
- Complete, polished, modern design

WHAT NOT TO CREATE:
- Photo of a billboard or sign
- Ad displayed on any surface (wall, screen, poster board)
- Mockup showing installation context
- Any 3D perspective or environmental scene

CREATIVE BRIEF:
{prompt_section}

Output the FLAT ARTWORK ONLY - the pure advertisement design filling the entire canvas, like a PNG export from a design program."""


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
