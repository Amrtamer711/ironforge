"""
Mockup Channel Handler.

Handles mockup generation requests from chat channels (Slack, Web, etc.).
Bridges channel events to MockupCoordinator.
"""

import os
from collections.abc import Callable
from pathlib import Path

import config

from .coordinator import MockupCoordinator

logger = config.logger


def format_location_label(location_value: str) -> str:
    value = (location_value or "").strip()
    if not value:
        return ""

    location_key = value.lower().replace(" ", "_")
    if location_key in config.LOCATION_METADATA:
        display_name = config.LOCATION_METADATA[location_key].get("display_name") or value
        return f"{display_name}"

    key_from_display = config.get_location_key_from_display_name(value)
    if key_from_display:
        display_name = config.LOCATION_METADATA.get(key_from_display, {}).get("display_name") or value
        return f"{display_name}"

    return value


async def handle_mockup_generation(
    location_name: str,
    time_of_day: str,
    side: str,
    ai_prompts: list[str],
    user_id: str,
    channel: str,
    status_ts: str,
    user_companies: list[str],
    channel_event: dict = None,
    download_file_func: Callable = None,
    generate_mockup_queued_func: Callable = None,
    generate_ai_mockup_queued_func: Callable = None,
    company_hint: str | None = None,
    venue_type: str = "all",
    asset_type_key: str | None = None,
) -> bool:
    """
    Handle mockup generation request from chat channels.

    Channel-agnostic: Works with any channel adapter (Slack, Web, etc.)

    Supports three modes:
    1. Upload mode: User uploads image(s)
    2. AI mode: User provides AI prompt(s) for generation
    3. Follow-up mode: Reuse previous creatives for new location

    Args:
        location_name: Display name or key of the location
        time_of_day: Time of day filter (e.g., "day", "night", "all")
        side: Side type filter (e.g., "gold", "silver", "all")
        ai_prompts: List of AI prompts for generation
        user_id: User identifier
        channel: Channel/conversation ID
        status_ts: ID of status message to update
        user_companies: List of company schemas user can access
        channel_event: Original channel event dict (for file access)
        download_file_func: Function to download files (channel-agnostic)
        generate_mockup_queued_func: Function for queued mockup generation
        generate_ai_mockup_queued_func: Function for queued AI mockup generation
        company_hint: Optional company to try first for O(1) asset lookups
        venue_type: Venue type filter ("indoor", "outdoor", "all")
        asset_type_key: Optional asset type key for traditional networks

    Returns:
        True when handled (success or error)
    """

    logger.info(f"[MOCKUP] User requested mockup generation for {location_name}")

    # Normalize parameters
    time_of_day = (time_of_day or "all").strip().lower()
    side = (side or "all").strip().lower()
    venue_type = (venue_type or "all").strip().lower()

    # Clean and validate AI prompts
    if not isinstance(ai_prompts, list):
        ai_prompts = [ai_prompts] if ai_prompts else []
    ai_prompts = [str(p).strip() for p in ai_prompts if p]

    # Extract uploaded images
    uploaded_creatives = await _extract_uploaded_images(channel_event, download_file_func)

    # Use MockupCoordinator for business logic
    coordinator = MockupCoordinator(
        user_companies=user_companies,
        generate_mockup_func=generate_mockup_queued_func,
        generate_ai_mockup_func=generate_ai_mockup_queued_func,
        company_hint=company_hint,
    )

    # Generate mockup (coordinator handles all modes: upload/AI/followup)
    result_path, creative_paths, metadata, error = await coordinator.generate_mockup(
        location_name=location_name,
        time_of_day=time_of_day,
        side=side,
        user_id=user_id,
        uploaded_creatives=uploaded_creatives,
        ai_prompts=ai_prompts,
        venue_type=venue_type,
        asset_type_key=asset_type_key,
    )

    channel_adapter = config.get_channel_adapter()

    # Handle errors
    if error:
        await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
        await channel_adapter.send_message(channel_id=channel, content=f"❌ **Error:** {error}")
        return True

    # Handle success - upload the mockup
    if not result_path:
        await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
        await channel_adapter.send_message(
            channel_id=channel,
            content="❌ **Error:** Failed to generate mockup (no result)"
        )
        return True

    # Update status
    await channel_adapter.update_message(
        channel_id=channel,
        message_id=status_ts,
        content="📤 Uploading mockup..."
    )

    # Build upload message based on mode
    mode = metadata.get("mode", "unknown")
    location_display = format_location_label(location_name)
    num_frames = metadata.get("num_frames", 1)

    variation_info = ""
    if time_of_day != "all" or side != "all":
        variation_info = f" ({time_of_day}/{side})"

    frames_info = f" ({num_frames} frame(s))" if num_frames > 1 else ""

    if mode == "followup":
        previous_location = format_location_label(metadata.get("previous_location", "unknown"))
        comment = (
            f"🎨 **Billboard Mockup Generated** (Follow-up)\n\n"
            f"📍 New Location: {location_display}{variation_info}\n"
            f"🔄 Using creative(s) from: {previous_location}{frames_info}\n"
            f"✨ Your creative has been applied to this location."
        )
    elif mode == "ai_generated":
        comment = (
            f"🎨 **AI-Generated Billboard Mockup**\n\n"
            f"📍 Location: {location_display}{variation_info}{frames_info}\n"
        )
    else:  # uploaded
        comment = (
            f"🎨 **Billboard Mockup Generated**\n\n"
            f"📍 Location: {location_display}{variation_info}\n"
            f"🖼️ Creative(s): {len(creative_paths)} image(s)\n"
            f"✨ Your creative has been applied to a billboard photo."
        )

    # Upload the mockup
    await channel_adapter.upload_file(
        channel_id=channel,
        file_path=str(result_path),
        title=f"mockup_{metadata.get('location_key', location_name)}_{time_of_day}_{side}.jpg",
        comment=comment
    )

    # Delete status message
    try:
        await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
    except Exception as e:
        logger.debug(f"[MOCKUP] Failed to delete status message: {e}")

    # Cleanup result file
    try:
        os.unlink(result_path)
    except OSError as e:
        logger.debug(f"[MOCKUP] Failed to cleanup result file: {e}")

    logger.info(f"[MOCKUP] Mockup generated successfully for user {user_id}")
    return True


async def _extract_uploaded_images(
    channel_event: dict,
    download_file_func: Callable,
) -> list[Path]:
    """Extract uploaded image files from channel event."""
    uploaded_creatives = []

    if not channel_event:
        return uploaded_creatives

    if "files" not in channel_event and channel_event.get("subtype") != "file_share":
        return uploaded_creatives

    from core.utils.constants import is_image_mimetype

    files = channel_event.get("files", [])
    if not files and channel_event.get("subtype") == "file_share" and "file" in channel_event:
        files = [channel_event["file"]]

    for f in files:
        filetype = f.get("filetype", "")
        mimetype = f.get("mimetype", "")
        filename = f.get("name", "").lower()

        # Use exact MIME type matching for security (no .startswith())
        is_image = (
            filetype in ["jpg", "jpeg", "png", "gif", "bmp"]
            or is_image_mimetype(mimetype)
            or any(filename.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".bmp"])
        )

        if is_image:
            try:
                creative_file = await download_file_func(f)
                uploaded_creatives.append(creative_file)
                logger.info(f"[MOCKUP] Found uploaded image: {f.get('name')}")
            except Exception as e:
                logger.error(f"[MOCKUP] Failed to download image: {e}")

    return uploaded_creatives
