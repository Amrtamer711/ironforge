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

    # Simplified, direct prompt that emphasizes the key constraint upfront
    return f"""Generate a FLAT 2D advertisement graphic file. Output ONLY the artwork itself.

CRITICAL CONSTRAINT: The generated image must be the raw artwork file - like a Photoshop export or print-ready PDF. Do NOT render it on a billboard, wall, screen, poster board, or any surface. Do NOT show the ad mounted, displayed, or placed anywhere. The artwork must fill 100% of the canvas edge-to-edge with NO environment visible.

FORMAT: {aspect}, flat rectangular canvas, no perspective, no 3D, no depth.

CORRECT: A flat graphic design that fills the entire image (like opening an ad file in Photoshop)
WRONG: A photo of an ad on a billboard, wall, display, or any surface

DESIGN REQUIREMENTS:
- Professional advertisement design, modern 2024+ aesthetic
- Edge-to-edge design filling the entire canvas
- Bold colors, high contrast, clear typography
- Complete composition with background, imagery, text, and branding
- No blank/white backgrounds unless specified
- No glows, halos, or effects around text/logos
- Print-ready quality

CREATIVE BRIEF:
{prompt_section}

Remember: Output the FLAT ARTWORK FILE ONLY. Do NOT show it displayed on anything."""


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
