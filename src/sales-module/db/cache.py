"""
Cache - In-memory caches for user sessions and mockup history.
"""

import os
from datetime import datetime, timedelta
from typing import Any

import config
from db.database import db
from utils.memory import cleanup_memory

# Global for user conversation history
user_history: dict[str, list] = {}

# Global for pending location additions (waiting for PPT upload)
pending_location_additions: dict[str, dict[str, Any]] = {}

# Global for mockup history (30-minute memory per user)
# Structure: {user_id: {"creative_paths": List[Path], "metadata": dict, "timestamp": datetime}}
# Stores individual creative files (1-N files) so they can be reused on different locations with matching frame count
mockup_history: dict[str, dict[str, Any]] = {}

# Global for booking order draft review sessions (active until approved/cancelled)
# Structure: {user_id: {"data": dict, "warnings": List[str], "missing_required": List[str],
#                        "original_file_path": Path, "company": str, "file_type": str}}
pending_booking_orders: dict[str, dict[str, Any]] = {}


def cleanup_expired_mockups():
    """Remove creative files that have expired (older than 30 minutes)"""
    now = datetime.now()
    expired_users = []

    for user_id, data in mockup_history.items():
        timestamp = data.get("timestamp")
        if timestamp and (now - timestamp) > timedelta(minutes=30):
            # Delete all creative files for this user
            creative_paths = data.get("creative_paths", [])
            deleted_count = 0
            for creative_path in creative_paths:
                if creative_path and creative_path.exists():
                    try:
                        os.unlink(creative_path)
                        deleted_count += 1
                    except Exception as e:
                        config.logger.error(f"[MOCKUP HISTORY] Failed to delete {creative_path}: {e}")

            if deleted_count > 0:
                config.logger.info(f"[MOCKUP HISTORY] Cleaned up {deleted_count} expired creative file(s) for user {user_id}")
            expired_users.append(user_id)

    # Remove from memory
    for user_id in expired_users:
        del mockup_history[user_id]
        config.logger.info(f"[MOCKUP HISTORY] Removed user {user_id} from mockup history")

    # Force garbage collection if we cleaned up any files
    if expired_users:
        cleanup_memory(context="mockup_history_cleanup", aggressive=False, log_stats=False)


def store_mockup_history(user_id: str, creative_paths: list, metadata: dict):
    """Store creative files in user's history with 30-minute expiry

    Args:
        user_id: Slack user ID
        creative_paths: List of Path objects to creative files (1-N files)
        metadata: Dict with location_key, location_name, num_frames, etc.
    """
    # Clean up old creative files for this user if exists
    if user_id in mockup_history:
        old_data = mockup_history[user_id]
        old_creative_paths = old_data.get("creative_paths", [])
        deleted_count = 0
        for old_path in old_creative_paths:
            if old_path and old_path.exists():
                try:
                    os.unlink(old_path)
                    deleted_count += 1
                except Exception as e:
                    config.logger.error(f"[MOCKUP HISTORY] Failed to delete old creative: {e}")
        if deleted_count > 0:
            config.logger.info(f"[MOCKUP HISTORY] Replaced {deleted_count} old creative file(s) for user {user_id}")
            # Force garbage collection when replacing files
            cleanup_memory(context="mockup_history_replace", aggressive=False, log_stats=False)

    # Store new creative files
    mockup_history[user_id] = {
        "creative_paths": creative_paths,
        "metadata": metadata,
        "timestamp": datetime.now()
    }
    config.logger.info(f"[MOCKUP HISTORY] Stored {len(creative_paths)} creative file(s) for user {user_id}")

    # Run cleanup to remove expired creatives from other users
    cleanup_expired_mockups()


def get_mockup_history(user_id: str) -> dict[str, Any] | None:
    """Get user's creative files from history if still valid (within 30 minutes)

    Returns:
        Dict with creative_paths (List[Path]), metadata, timestamp, or None if expired/not found
    """
    if user_id not in mockup_history:
        return None

    data = mockup_history[user_id]
    timestamp = data.get("timestamp")

    # Check if expired
    if timestamp and (datetime.now() - timestamp) > timedelta(minutes=30):
        # Expired - clean up all creative files
        creative_paths = data.get("creative_paths", [])
        deleted_count = 0
        for creative_path in creative_paths:
            if creative_path and creative_path.exists():
                try:
                    os.unlink(creative_path)
                    deleted_count += 1
                except OSError:
                    pass  # File in use or permission denied
        del mockup_history[user_id]

        # Force garbage collection if we deleted files
        if deleted_count > 0:
            cleanup_memory(context="mockup_history_auto_cleanup", aggressive=False, log_stats=False)
            config.logger.info(f"[MOCKUP HISTORY] Auto-cleaned {deleted_count} expired file(s) for user {user_id}")

        return None

    return data


def get_location_frame_count(
    location_key: str,
    company_schemas: list[str],
    time_of_day: str = "all",
    finish: str = "all",
) -> int | None:
    """Get the number of frames for a specific location configuration.

    Args:
        location_key: The location key to look up
        company_schemas: List of company schemas user can access
        time_of_day: Filter by time of day ("day", "night", "all")
        finish: Filter by finish type ("gold", "matte", "all")

    Returns:
        Number of frames, or None if location not found or no mockups configured
    """

    # Get available variations for the location (searches all user's schemas)
    variations = db.list_mockup_variations(location_key, company_schemas)
    if not variations:
        return None

    # Get the first available variation that matches time_of_day/finish
    # variations structure: {'day': ['gold', 'silver'], 'night': ['gold']}
    for tod, finish_list in variations.items():
        if time_of_day != "all" and tod != time_of_day:
            continue

        for fin in finish_list:
            if finish != "all" and fin != finish:
                continue

            # Get all photos for this time_of_day/finish combination
            photos = db.list_mockup_photos(location_key, company_schemas, tod, fin)
            if photos:
                # Search each schema to find which has the frames for this photo
                for schema in company_schemas:
                    frames_data = db.get_mockup_frames(location_key, photos[0], schema, tod, fin)
                    if frames_data:
                        return len(frames_data)

    return None
