"""
Abu Dhabi Location Configuration & Helper Functions

This module provides utilities for working with Abu Dhabi locations and scheduling configuration.
It reads from the videographer_config.json file and provides convenient access functions.
"""

import json
import os
from typing import Optional, List, Dict, Any
from config import VIDEOGRAPHER_CONFIG_PATH
from logger import logger


def _load_config() -> Dict[str, Any]:
    """Load configuration from videographer_config.json"""
    try:
        with open(VIDEOGRAPHER_CONFIG_PATH, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading videographer config: {e}")
        return {}


def get_abu_dhabi_locations() -> Dict[str, List[str]]:
    """
    Get Abu Dhabi location mappings.

    Returns:
        Dict with keys 'GALLERIA_MALL' and 'AL_QANA', values are lists of location names
    """
    config = _load_config()
    return config.get('abu_dhabi_locations', {
        'GALLERIA_MALL': [],
        'AL_QANA': []
    })


def get_scheduling_config() -> Dict[str, Any]:
    """
    Get Abu Dhabi scheduling configuration.

    Returns:
        Dict with scheduling parameters (allowed_weekdays, max_shoots_per_week, etc.)
    """
    config = _load_config()
    return config.get('abu_dhabi_scheduling', {
        'allowed_weekdays': [1, 3, 4],  # Tue, Thu, Fri
        'preferred_weekdays': [1, 4, 3],
        'avoided_weekdays': [0],  # Monday
        'max_shoots_per_week': 2,
        'min_gap_between_shoots_days': 1,
        'planning_horizon_weeks': 4,
        'freeze_threshold_hours': 24,
        'min_campaigns_per_shoot': 2,
        'allow_single_campaign_exceptions': True,
        'time_blocks': ['day', 'night', 'both']
    })


def is_abu_dhabi_location(location: str) -> bool:
    """
    Check if a location is in Abu Dhabi.

    Args:
        location: Location name string

    Returns:
        True if location is in Abu Dhabi, False otherwise
    """
    if not location:
        return False

    locations = get_abu_dhabi_locations()
    all_locations = []
    for area_locations in locations.values():
        all_locations.extend(area_locations)

    # Exact match
    if location in all_locations:
        return True

    # Partial match (for Promo Stand with description)
    location_lower = location.lower()
    for loc in all_locations:
        if loc.lower() in location_lower:
            return True

    return False


def get_abu_dhabi_area(location: str) -> Optional[str]:
    """
    Get the area (GALLERIA_MALL or AL_QANA) for an Abu Dhabi location.

    Args:
        location: Location name string

    Returns:
        'GALLERIA_MALL', 'AL_QANA', or None if not an Abu Dhabi location
    """
    if not location:
        return None

    locations = get_abu_dhabi_locations()

    # Check each area
    for area, area_locations in locations.items():
        # Exact match
        if location in area_locations:
            return area

        # Partial match (for Promo Stand with description)
        location_lower = location.lower()
        for loc in area_locations:
            if loc.lower() in location_lower:
                return area

    return None


def get_area_display_name(area: str) -> str:
    """
    Get human-readable area name.

    Args:
        area: Area code ('GALLERIA_MALL' or 'AL_QANA')

    Returns:
        Display name for the area
    """
    area_names = {
        'GALLERIA_MALL': 'Galleria Mall',
        'AL_QANA': 'Al Qana'
    }
    return area_names.get(area, area)


def get_config_value(key: str, default=None):
    """
    Get a scheduling configuration value.

    Args:
        key: Configuration key
        default: Default value if key not found

    Returns:
        Configuration value
    """
    config = get_scheduling_config()
    return config.get(key, default)


# Convenience constants
ALLOWED_WEEKDAYS = None  # Lazy loaded
MAX_SHOOTS_PER_WEEK = None
MIN_GAP_DAYS = None
FREEZE_THRESHOLD_HOURS = None


def _init_constants():
    """Initialize convenience constants"""
    global ALLOWED_WEEKDAYS, MAX_SHOOTS_PER_WEEK, MIN_GAP_DAYS, FREEZE_THRESHOLD_HOURS
    config = get_scheduling_config()
    ALLOWED_WEEKDAYS = config['allowed_weekdays']
    MAX_SHOOTS_PER_WEEK = config['max_shoots_per_week']
    MIN_GAP_DAYS = config['min_gap_between_shoots_days']
    FREEZE_THRESHOLD_HOURS = config['freeze_threshold_hours']


# Initialize on module load
_init_constants()
