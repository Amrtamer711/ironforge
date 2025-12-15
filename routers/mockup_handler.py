"""
Mockup Handler - Handles mockup generation requests.

Extracted from tool_router.py for better decoupling and maintainability.
"""

import os
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import config
from db.database import db
from db.cache import (
    mockup_history,
    get_mockup_history,
    get_location_frame_count,
    store_mockup_history,
)
from utils.memory import cleanup_memory

logger = config.logger


async def handle_mockup_generation(
    location_name: str,
    time_of_day: str,
    finish: str,
    ai_prompts: List[str],
    user_id: str,
    channel: str,
    status_ts: str,
    channel_event: dict = None,
    download_file_func: Callable = None,
    generate_mockup_queued_func: Callable = None,
    generate_ai_mockup_queued_func: Callable = None,
) -> bool:
    """
    Handle mockup generation request.

    Channel-agnostic: Works with any channel adapter (Slack, Web, etc.)

    Supports three modes:
    1. Upload mode: User uploads image(s)
    2. AI mode: User provides AI prompt(s) for generation
    3. Follow-up mode: Reuse previous creatives for new location

    Args:
        location_name: Display name or key of the location
        time_of_day: Time of day filter (e.g., "day", "night", "all")
        finish: Finish type filter (e.g., "matte", "gloss", "all")
        ai_prompts: List of AI prompts for generation
        user_id: User identifier
        channel: Channel/conversation ID
        status_ts: ID of status message to update
        channel_event: Original channel event dict (for file access)
        download_file_func: Function to download files (channel-agnostic)
        generate_mockup_queued_func: Function for queued mockup generation
        generate_ai_mockup_queued_func: Function for queued AI mockup generation

    Returns:
        True when handled (success or error)
    """
    from generators import mockup as mockup_generator

    logger.info(f"[MOCKUP] User requested mockup generation for {location_name}")

    # Normalize parameters
    time_of_day = (time_of_day or "all").strip().lower()
    finish = (finish or "all").strip().lower()

    # Clean and validate AI prompts
    if not isinstance(ai_prompts, list):
        ai_prompts = [ai_prompts] if ai_prompts else []
    ai_prompts = [str(p).strip() for p in ai_prompts if p]
    num_ai_frames = len(ai_prompts)

    if ai_prompts:
        logger.info(f"[MOCKUP] LLM extracted {num_ai_frames} AI prompt(s)")
    else:
        logger.info(f"[MOCKUP] No AI prompts provided")

    # Resolve location key
    location_key = config.get_location_key_from_display_name(location_name)
    if not location_key:
        location_key = location_name.lower().replace(" ", "_")

    channel_adapter = config.get_channel_adapter()

    # Validate location exists
    if location_key not in config.LOCATION_METADATA:
        await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
        await channel_adapter.send_message(
            channel_id=channel,
            content=f"❌ **Error:** Location '{location_name}' not found. Please choose from available locations."
        )
        return True

    # Check if location has any mockup photos configured
    variations = db.list_mockup_variations(location_key)
    if not variations:
        await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
        mockup_url = os.getenv("RENDER_EXTERNAL_URL", "http://localhost:3000") + "/mockup"
        await channel_adapter.send_message(
            channel_id=channel,
            content=(
                f"❌ **Error:** No billboard photos configured for *{location_name}* (location key: `{location_key}`).\n\n"
                f"Ask an admin to set up mockup frames at {mockup_url}"
            )
        )
        return True

    # Get frame count for this location
    new_location_frame_count = get_location_frame_count(location_key, time_of_day, finish)

    # Get user's mockup history if exists
    mockup_user_hist = get_mockup_history(user_id)

    # Check if user uploaded image(s) with the request
    uploaded_creatives = await _extract_uploaded_images(
        channel_event, download_file_func
    )
    has_images = len(uploaded_creatives) > 0

    # Determine mode and handle accordingly
    # Priority: 1) New upload 2) AI prompt 3) History reuse 4) Error

    # FOLLOW-UP MODE: Check if this is a follow-up request
    if not has_images and not ai_prompts and mockup_user_hist:
        return await _handle_followup_mode(
            mockup_user_hist=mockup_user_hist,
            location_key=location_key,
            location_name=location_name,
            time_of_day=time_of_day,
            finish=finish,
            new_location_frame_count=new_location_frame_count,
            user_id=user_id,
            channel=channel,
            status_ts=status_ts,
            generate_mockup_queued_func=generate_mockup_queued_func,
        )

    # UPLOAD MODE: User uploaded image(s)
    if has_images:
        return await _handle_upload_mode(
            uploaded_creatives=uploaded_creatives,
            location_key=location_key,
            location_name=location_name,
            time_of_day=time_of_day,
            finish=finish,
            new_location_frame_count=new_location_frame_count,
            user_id=user_id,
            channel=channel,
            status_ts=status_ts,
            generate_mockup_queued_func=generate_mockup_queued_func,
        )

    # AI MODE: User provided AI prompt(s)
    if ai_prompts:
        return await _handle_ai_mode(
            ai_prompts=ai_prompts,
            num_ai_frames=num_ai_frames,
            location_key=location_key,
            location_name=location_name,
            time_of_day=time_of_day,
            finish=finish,
            new_location_frame_count=new_location_frame_count,
            user_id=user_id,
            channel=channel,
            status_ts=status_ts,
            generate_ai_mockup_queued_func=generate_ai_mockup_queued_func,
        )

    # NO INPUT PROVIDED: Show help message
    await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
    await channel_adapter.send_message(
        channel_id=channel,
        content=(
            f"❌ **Sorry!** You need to provide a creative for the mockup.\n\n"
            f"**Three ways to generate mockups:**\n\n"
            f"1️⃣ **Upload Your Image:** Attach your creative when you send the request\n"
            f"   Example: [Upload creative.jpg] + \"mockup for {location_name}\"\n\n"
            f"2️⃣ **AI Generation (No upload needed):** Describe what you want\n"
            f"   Example: \"mockup for {location_name} with luxury watch ad, gold and elegant typography\"\n"
            f"   The AI will generate the creative for you!\n\n"
            f"3️⃣ **Follow-up Request:** If you recently generated a mockup (within 30 min), just ask!\n"
            f"   Example: \"show me this on {location_name}\" or \"apply to {location_name}\"\n"
            f"   I'll reuse your previous creative(s) automatically.\n\n"
            f"Please try again with an image attachment, creative description, or generate a mockup first!"
        )
    )
    return True


async def _extract_uploaded_images(
    channel_event: dict,
    download_file_func: Callable,
) -> List[Path]:
    """Extract uploaded image files from Slack event."""
    uploaded_creatives = []

    if not channel_event:
        return uploaded_creatives

    if "files" not in channel_event and channel_event.get("subtype") != "file_share":
        return uploaded_creatives

    from utils.constants import is_image_mimetype

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


async def _handle_followup_mode(
    mockup_user_hist: dict,
    location_key: str,
    location_name: str,
    time_of_day: str,
    finish: str,
    new_location_frame_count: int,
    user_id: str,
    channel: str,
    status_ts: str,
    generate_mockup_queued_func: Callable,
) -> bool:
    """Handle follow-up request to apply previous creatives to new location."""
    stored_frames = mockup_user_hist.get("metadata", {}).get("num_frames", 1)
    stored_creative_paths = mockup_user_hist.get("creative_paths", [])
    stored_location = mockup_user_hist.get("metadata", {}).get("location_name", "unknown")

    channel_adapter = config.get_channel_adapter()

    # Verify all creative files still exist
    missing_files = [str(p) for p in stored_creative_paths if not p.exists()]

    if missing_files:
        logger.error(f"[MOCKUP] Creative files missing from history: {missing_files}")
        await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
        await channel_adapter.send_message(
            channel_id=channel,
            content=(
                f"❌ **Error:** Your previous creative files are no longer available.\n\n"
                f"Please upload new images or use AI generation."
            )
        )
        # Clean up corrupted history
        del mockup_history[user_id]
        return True

    # Validate creative count: Allow if 1 creative (tile) OR matches frame count
    num_stored_creatives = len(stored_creative_paths)
    is_valid_count = (num_stored_creatives == 1) or (num_stored_creatives == new_location_frame_count)

    if not is_valid_count:
        await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
        await channel_adapter.send_message(
            channel_id=channel,
            content=(
                f"⚠️ **Creative Count Mismatch**\n\n"
                f"I have **{num_stored_creatives} creative(s)** from your previous mockup (**{stored_location}**), "
                f"but **{location_name}** requires **{new_location_frame_count} frame(s)**.\n\n"
                f"**Valid options:**\n"
                f"• Upload **1 image** (will be tiled across all frames)\n"
                f"• Upload **{new_location_frame_count} images** (one per frame)\n"
                f"• Use AI generation with a creative description"
            )
        )
        return True

    logger.info(f"[MOCKUP] Follow-up request - reusing {len(stored_creative_paths)} creative(s)")

    await channel_adapter.update_message(
        channel_id=channel,
        message_id=status_ts,
        content=f"⏳ _Applying your previous creative(s) to {location_name}..._"
    )

    result_path = None
    try:
        result_path, _ = await generate_mockup_queued_func(
            location_key,
            stored_creative_paths,
            time_of_day=time_of_day,
            finish=finish
        )

        if not result_path:
            raise Exception("Failed to generate mockup")

        await channel_adapter.update_message(
            channel_id=channel,
            message_id=status_ts,
            content="📤 Uploading mockup..."
        )

        variation_info = ""
        if time_of_day != "all" or finish != "all":
            variation_info = f" ({time_of_day}/{finish})"

        frames_info = f" ({stored_frames} frame(s))" if stored_frames > 1 else ""

        await channel_adapter.upload_file(
            channel_id=channel,
            file_path=str(result_path),
            title=f"mockup_{location_key}_{time_of_day}_{finish}.jpg",
            comment=(
                f"🎨 **Billboard Mockup Generated** (Follow-up)\n\n"
                f"📍 New Location: {location_name}{variation_info}\n"
                f"🔄 Using creative(s) from: {stored_location}{frames_info}\n"
                f"✨ Your creative has been applied to this location."
            )
        )

        try:
            await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
        except Exception as e:
            logger.debug(f"[MOCKUP] Failed to delete status message: {e}")

        # Update history with new location
        mockup_user_hist["metadata"]["location_key"] = location_key
        mockup_user_hist["metadata"]["location_name"] = location_name
        mockup_user_hist["metadata"]["time_of_day"] = time_of_day
        mockup_user_hist["metadata"]["finish"] = finish

        logger.info(f"[MOCKUP] Follow-up mockup generated successfully for user {user_id}")

    except Exception as e:
        logger.error(f"[MOCKUP] Error generating follow-up mockup: {e}", exc_info=True)
        await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
        await channel_adapter.send_message(
            channel_id=channel,
            content=f"❌ **Error:** Failed to generate follow-up mockup. {str(e)}"
        )
    finally:
        # Cleanup and memory management
        if result_path:
            try:
                os.unlink(result_path)
            except OSError as cleanup_err:
                logger.debug(f"[MOCKUP] Failed to cleanup result file: {cleanup_err}")
        cleanup_memory(context="mockup_followup", aggressive=False, log_stats=False)

    return True


async def _handle_upload_mode(
    uploaded_creatives: List[Path],
    location_key: str,
    location_name: str,
    time_of_day: str,
    finish: str,
    new_location_frame_count: int,
    user_id: str,
    channel: str,
    status_ts: str,
    generate_mockup_queued_func: Callable,
) -> bool:
    """Handle mockup generation from uploaded images."""
    logger.info(f"[MOCKUP] Processing {len(uploaded_creatives)} uploaded image(s)")

    channel_adapter = config.get_channel_adapter()

    # Validate creative count
    num_uploaded = len(uploaded_creatives)
    is_valid_count = (num_uploaded == 1) or (num_uploaded == new_location_frame_count)

    if not is_valid_count:
        await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
        await channel_adapter.send_message(
            channel_id=channel,
            content=(
                f"⚠️ **Creative Count Mismatch**\n\n"
                f"You uploaded **{num_uploaded} image(s)**, but **{location_name}** requires **{new_location_frame_count} frame(s)**.\n\n"
                f"**Valid options:**\n"
                f"• Upload **1 image** (will be tiled across all frames)\n"
                f"• Upload **{new_location_frame_count} images** (one per frame)"
            )
        )
        return True

    await channel_adapter.update_message(
        channel_id=channel,
        message_id=status_ts,
        content="⏳ _Generating mockup from uploaded image(s)..._"
    )

    result_path = None
    try:
        result_path, _ = await generate_mockup_queued_func(
            location_key,
            uploaded_creatives,
            time_of_day=time_of_day,
            finish=finish
        )

        if not result_path:
            raise Exception("Failed to generate mockup")

        await channel_adapter.update_message(
            channel_id=channel,
            message_id=status_ts,
            content="📤 Uploading mockup..."
        )

        variation_info = ""
        if time_of_day != "all" or finish != "all":
            variation_info = f" ({time_of_day}/{finish})"

        await channel_adapter.upload_file(
            channel_id=channel,
            file_path=str(result_path),
            title=f"mockup_{location_key}_{time_of_day}_{finish}.jpg",
            comment=(
                f"🎨 **Billboard Mockup Generated**\n\n"
                f"📍 Location: {location_name}{variation_info}\n"
                f"🖼️ Creative(s): {len(uploaded_creatives)} image(s)\n"
                f"✨ Your creative has been applied to a billboard photo."
            )
        )

        try:
            await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
        except Exception as e:
            logger.debug(f"[MOCKUP] Failed to delete status message: {e}")

        # Store in history for follow-ups
        location_frame_count = get_location_frame_count(location_key, time_of_day, finish)
        store_mockup_history(user_id, uploaded_creatives, {
            "location_key": location_key,
            "location_name": location_name,
            "time_of_day": time_of_day,
            "finish": finish,
            "mode": "uploaded",
            "num_frames": location_frame_count or 1
        })
        logger.info(f"[MOCKUP] Stored {len(uploaded_creatives)} uploaded creative(s) in history")

    except Exception as e:
        logger.error(f"[MOCKUP] Error generating mockup from upload: {e}", exc_info=True)
        await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
        await channel_adapter.send_message(
            channel_id=channel,
            content=f"❌ **Error:** Failed to generate mockup. {str(e)}"
        )
        # Cleanup uploaded files on error
        for creative_file in uploaded_creatives:
            try:
                os.unlink(creative_file)
            except OSError as cleanup_err:
                logger.debug(f"[MOCKUP] Failed to cleanup creative file: {cleanup_err}")
    finally:
        # Cleanup and memory management
        if result_path:
            try:
                os.unlink(result_path)
            except OSError as cleanup_err:
                logger.debug(f"[MOCKUP] Failed to cleanup result file: {cleanup_err}")
        cleanup_memory(context="mockup_upload", aggressive=False, log_stats=False)

    return True


async def _handle_ai_mode(
    ai_prompts: List[str],
    num_ai_frames: int,
    location_key: str,
    location_name: str,
    time_of_day: str,
    finish: str,
    new_location_frame_count: int,
    user_id: str,
    channel: str,
    status_ts: str,
    generate_ai_mockup_queued_func: Callable,
) -> bool:
    """Handle mockup generation with AI-generated creative."""
    from generators import mockup as mockup_generator

    channel_adapter = config.get_channel_adapter()

    # Validate frame count
    is_valid_count = (num_ai_frames == 1) or (num_ai_frames == new_location_frame_count)

    if not is_valid_count:
        await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
        await channel_adapter.send_message(
            channel_id=channel,
            content=(
                f"⚠️ **Frame Count Mismatch**\n\n"
                f"You provided **{num_ai_frames} AI prompt(s)**, but **{location_name}** has **{new_location_frame_count} frame(s)**.\n\n"
                f"**Valid options:**\n"
                f"• Provide **1 prompt** (will be tiled across all frames)\n"
                f"• Provide **{new_location_frame_count} prompts** (one per frame)"
            )
        )
        return True

    frames_text = f"{num_ai_frames} artworks and mockup" if num_ai_frames > 1 else "AI artwork and mockup"
    await channel_adapter.update_message(
        channel_id=channel,
        message_id=status_ts,
        content=f"⏳ _Generating {frames_text}..._"
    )

    result_path = None
    ai_creative_paths = []

    try:
        # generate_ai_creative applies the system prompt internally
        result_path, ai_creative_paths = await generate_ai_mockup_queued_func(
            ai_prompts=ai_prompts,
            location_key=location_key,
            time_of_day=time_of_day,
            finish=finish,
            user_id=user_id
        )

        if not result_path:
            raise Exception("Failed to generate mockup")

        await channel_adapter.update_message(
            channel_id=channel,
            message_id=status_ts,
            content="📤 Uploading mockup..."
        )

        variation_info = ""
        if time_of_day != "all" or finish != "all":
            variation_info = f" ({time_of_day}/{finish})"

        frames_info = f" ({num_ai_frames} frames)" if num_ai_frames > 1 else ""

        await channel_adapter.upload_file(
            channel_id=channel,
            file_path=str(result_path),
            title=f"ai_mockup_{location_key}_{time_of_day}_{finish}.jpg",
            comment=(
                f"🎨 **AI-Generated Billboard Mockup**\n\n"
                f"📍 Location: {location_name}{variation_info}{frames_info}\n"
            )
        )

        try:
            await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
        except Exception as e:
            logger.debug(f"[MOCKUP] Failed to delete status message: {e}")

        # Store in history for follow-ups
        store_mockup_history(user_id, ai_creative_paths, {
            "location_key": location_key,
            "location_name": location_name,
            "time_of_day": time_of_day,
            "finish": finish,
            "mode": "ai_generated",
            "num_frames": num_ai_frames
        })
        logger.info(f"[MOCKUP] Stored {len(ai_creative_paths)} AI creative(s) in history")

    except Exception as e:
        logger.error(f"[MOCKUP] Error generating AI mockup: {e}", exc_info=True)
        await channel_adapter.delete_message(channel_id=channel, message_id=status_ts)
        await channel_adapter.send_message(
            channel_id=channel,
            content=f"❌ **Error:** Failed to generate AI mockup. {str(e)}"
        )
        # Cleanup AI creatives on error
        for creative_path in ai_creative_paths:
            if creative_path and creative_path.exists():
                try:
                    os.unlink(creative_path)
                except OSError as cleanup_err:
                    logger.debug(f"[MOCKUP] Failed to cleanup AI creative: {cleanup_err}")
    finally:
        # Cleanup and memory management
        if result_path:
            try:
                os.unlink(result_path)
            except OSError as cleanup_err:
                logger.debug(f"[MOCKUP] Failed to cleanup result file: {cleanup_err}")
        cleanup_memory(context="mockup_ai", aggressive=False, log_stats=False)

    return True
