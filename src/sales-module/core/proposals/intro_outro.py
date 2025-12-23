"""
Intro/Outro Slide Handler.

Handles selection and extraction of intro/outro slides for proposals.
"""

from typing import Any

import config
from core.utils import match_location_key, get_location_metadata


class IntroOutroHandler:
    """
    Handles intro/outro slide selection for proposals.

    Responsibilities:
    - Find suitable location for intro/outro slides
    - Prefer "The Landmark Series" locations
    - Fall back to first location if no Landmark found
    """

    def __init__(self, available_locations: list[dict[str, Any]]):
        """
        Initialize handler with available locations.

        Args:
            available_locations: List of location dicts from AssetService
        """
        self.available_locations = available_locations
        self.logger = config.logger

    def get_intro_outro_location(
        self,
        validated_proposals: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """
        Find suitable location for intro/outro slides.

        Strategy:
        1. Search for "The Landmark Series" location
        2. Fall back to first location in proposals
        3. Return None if no suitable location found

        Args:
            validated_proposals: List of validated proposal dicts

        Returns:
            Dict with location info for intro/outro, or None if not found:
            {
                'key': str,
                'series': str,
                'template_path': str,
                'metadata': dict,
                'is_landmark': bool,  # True if Landmark Series
                'is_non_landmark': bool,  # True if fallback (for rest.pdf)
            }

        Example:
            >>> handler = IntroOutroHandler(available_locations)
            >>> info = handler.get_intro_outro_location(validated_proposals)
            >>> if info and info.get('is_landmark'):
            ...     use_landmark_intro_outro(info['template_path'])
        """
        self.logger.info(
            f"[INTRO_OUTRO] 🔍 Searching for suitable location from {len(validated_proposals)} proposals"
        )

        mapping = config.get_location_mapping()

        # First, look for locations with "The Landmark Series"
        for idx, proposal in enumerate(validated_proposals):
            location_key = proposal.get("location")
            self.logger.info(f"[INTRO_OUTRO] Checking proposal {idx+1}: location='{location_key}'")

            if not location_key:
                continue

            # Get location metadata
            location_meta = get_location_metadata(location_key, self.available_locations)
            if not location_meta:
                continue

            display_type = location_meta.get('display_type', 'Unknown')
            series = location_meta.get('series', '')
            display_name = location_meta.get('display_name', location_key)

            self.logger.info(f"[INTRO_OUTRO] Found location: '{display_name}' (key: {location_key})")
            self.logger.info(f"[INTRO_OUTRO]   - Display Type: {display_type}")
            self.logger.info(f"[INTRO_OUTRO]   - Series: '{series}'")

            if series == 'The Landmark Series':
                self.logger.info(
                    f"[INTRO_OUTRO] ✅ LANDMARK SERIES FOUND! Using '{display_name}' for intro/outro"
                )
                return {
                    'key': location_key,
                    'series': series,
                    'template_path': str(config.TEMPLATES_DIR / mapping.get(location_key, '')),
                    'metadata': location_meta,
                    'is_landmark': True
                }

        # If no Landmark Series found, use the first location from proposals
        self.logger.info("[INTRO_OUTRO] ❌ No Landmark Series location found in proposals")

        if validated_proposals:
            first_location_key = validated_proposals[0].get("location")
            self.logger.info(f"[INTRO_OUTRO] 📍 Falling back to first location: '{first_location_key}'")

            if first_location_key:
                location_meta = get_location_metadata(first_location_key, self.available_locations)
                if location_meta:
                    series = location_meta.get('series', '')
                    display_name = location_meta.get('display_name', first_location_key)
                    display_type = location_meta.get('display_type', 'Unknown')

                    self.logger.info(f"[INTRO_OUTRO] 🎯 Using first location: '{display_name}' (key: {first_location_key})")
                    self.logger.info(f"[INTRO_OUTRO]   - Display Type: {display_type}")
                    self.logger.info(f"[INTRO_OUTRO]   - Series: {series}")

                    # Mark as non-landmark for rest.pdf usage
                    return {
                        'key': first_location_key,
                        'series': series,
                        'template_path': str(config.TEMPLATES_DIR / mapping.get(first_location_key, '')),
                        'metadata': location_meta,
                        'is_non_landmark': True  # Flag to use rest.pdf
                    }

        self.logger.info("[INTRO_OUTRO] ⚠️ No suitable location found for intro/outro")
        return None
