"""
Centralized time utilities for UAE timezone.

This module provides a single source of truth for timezone handling
across the entire application.

Usage:
    from core.utils.time import UAE_TZ, get_uae_time, format_uae_datetime
"""

from datetime import datetime, timedelta, timezone

# UAE timezone (GMT+4)
UAE_TZ = timezone(timedelta(hours=4))


def get_uae_time() -> datetime:
    """
    Get current time in UAE timezone (GMT+4).

    Returns:
        datetime: Current time with UAE timezone info
    """
    return datetime.now(UAE_TZ)


def get_uae_time_iso() -> str:
    """
    Get current UAE time as ISO format string.

    Returns:
        str: ISO formatted datetime string
    """
    return get_uae_time().isoformat()


def format_uae_datetime(dt: datetime, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    Format a datetime in UAE timezone.

    Args:
        dt: datetime object (can be naive or aware)
        fmt: strftime format string

    Returns:
        str: Formatted datetime string
    """
    if dt.tzinfo is None:
        # Assume naive datetime is in UAE timezone
        dt = dt.replace(tzinfo=UAE_TZ)
    else:
        # Convert to UAE timezone
        dt = dt.astimezone(UAE_TZ)
    return dt.strftime(fmt)


def to_uae_timezone(dt: datetime) -> datetime:
    """
    Convert a datetime to UAE timezone.

    Args:
        dt: datetime object (can be naive or aware)

    Returns:
        datetime: Datetime in UAE timezone
    """
    if dt.tzinfo is None:
        # Assume naive datetime is UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(UAE_TZ)


def parse_datetime(dt_string: str) -> datetime:
    """
    Parse an ISO format datetime string and convert to UAE timezone.

    Args:
        dt_string: ISO format datetime string

    Returns:
        datetime: Parsed datetime in UAE timezone
    """
    dt = datetime.fromisoformat(dt_string)
    return to_uae_timezone(dt)
