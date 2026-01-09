"""
Cache - In-memory caches for user sessions and mockup history.

All caches have TTL-based cleanup to prevent unbounded memory growth.
"""

import os
import time
from datetime import datetime, timedelta
from typing import Any

import config
from core.utils.memory import cleanup_memory

# Cache TTL settings (in seconds)
USER_HISTORY_TTL = 3600  # 1 hour
PENDING_LOCATION_TTL = 1800  # 30 minutes
PENDING_BOOKING_ORDER_TTL = 3600  # 1 hour
MAX_CACHE_SIZE = 1000  # Max entries per cache to prevent memory exhaustion

# Global for user conversation history
# Structure: {user_id: {"history": list, "timestamp": float}}
user_history: dict[str, dict[str, Any]] = {}

# Global for pending location additions (waiting for PPT upload)
# Structure: {user_id: {"data": dict, "timestamp": float}}
pending_location_additions: dict[str, dict[str, Any]] = {}

# Global for mockup history (30-minute memory per user)
# Structure: {user_id: {"creative_paths": List[Path], "metadata": dict, "timestamp": datetime}}
# Stores individual creative files (1-N files) so they can be reused on different locations with matching frame count
mockup_history: dict[str, dict[str, Any]] = {}

# Global for booking order draft review sessions (active until approved/cancelled)
# Structure: {user_id: {"data": dict, "warnings": List[str], "missing_required": List[str],
#                        "original_file_path": Path, "company": str, "file_type": str, "timestamp": float}}
pending_booking_orders: dict[str, dict[str, Any]] = {}


def cleanup_stale_caches():
    """
    Clean up all stale cache entries.

    OPTIMIZED: Prevents unbounded memory growth by removing expired entries.
    Called periodically or when cache size exceeds MAX_CACHE_SIZE.
    """
    now = time.time()
    cleaned_count = 0

    # Clean user_history
    stale_keys = [
        k for k, v in user_history.items()
        if now - v.get("timestamp", 0) > USER_HISTORY_TTL
    ]
    for k in stale_keys:
        del user_history[k]
        cleaned_count += 1

    # Clean pending_location_additions
    stale_keys = [
        k for k, v in pending_location_additions.items()
        if now - v.get("timestamp", 0) > PENDING_LOCATION_TTL
    ]
    for k in stale_keys:
        del pending_location_additions[k]
        cleaned_count += 1

    # Clean pending_booking_orders
    stale_keys = [
        k for k, v in pending_booking_orders.items()
        if now - v.get("timestamp", 0) > PENDING_BOOKING_ORDER_TTL
    ]
    for k in stale_keys:
        del pending_booking_orders[k]
        cleaned_count += 1

    if cleaned_count > 0:
        config.logger.info(f"[CACHE] Cleaned up {cleaned_count} stale cache entries")

    return cleaned_count


def _ensure_cache_size():
    """Ensure caches don't exceed MAX_CACHE_SIZE by removing oldest entries."""
    # Check user_history
    if len(user_history) > MAX_CACHE_SIZE:
        # Sort by timestamp, remove oldest
        sorted_keys = sorted(user_history.keys(), key=lambda k: user_history[k].get("timestamp", 0))
        for k in sorted_keys[:len(user_history) - MAX_CACHE_SIZE]:
            del user_history[k]
        config.logger.warning(f"[CACHE] Evicted {len(sorted_keys[:len(user_history) - MAX_CACHE_SIZE])} oldest user_history entries")

    # Similar for other caches
    if len(pending_location_additions) > MAX_CACHE_SIZE:
        sorted_keys = sorted(pending_location_additions.keys(), key=lambda k: pending_location_additions[k].get("timestamp", 0))
        for k in sorted_keys[:len(pending_location_additions) - MAX_CACHE_SIZE]:
            del pending_location_additions[k]

    if len(pending_booking_orders) > MAX_CACHE_SIZE:
        sorted_keys = sorted(pending_booking_orders.keys(), key=lambda k: pending_booking_orders[k].get("timestamp", 0))
        for k in sorted_keys[:len(pending_booking_orders) - MAX_CACHE_SIZE]:
            del pending_booking_orders[k]


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


