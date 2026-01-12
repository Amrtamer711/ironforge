"""
Intro/Outro Slide Handler.

Handles selection and extraction of intro/outro slides for proposals.
"""

from typing import Any

import config
from core.utils import get_location_metadata


class IntroOutroHandler:
    """
    Handles intro/outro slide selection for proposals.

    Responsibilities:
    - Find suitable location for intro/outro slides
    - Prefer "The Landmark Series" locations
    - Fall back to first location if no Landmark found
    """

    def __init__(
        self,
        available_locations: list[dict[str, Any]],
        location_index: dict[str, dict[str, Any]] | None = None,
    ):
        """
        Initialize handler with available locations.

        Args:
            available_locations: List of location dicts from AssetService
            location_index: Optional pre-built index for O(1) lookups.
                           If not provided, will be built from available_locations.
        """
        self.available_locations = available_locations
        self.logger = config.logger

        # OPTIMIZED: Build or use location index for O(1) lookups
        if location_index is not None:
            self._location_index = location_index
        else:
            # Build index from list
            self._location_index = {}
            for loc in available_locations:
                key = loc.get("location_key") or loc.get("key")
                if key:
                    self._location_index[key.lower()] = loc

    def _get_location_fast(self, location_key: str) -> dict[str, Any] | None:
        """O(1) location lookup using pre-built index."""
        return self._location_index.get(location_key.lower())

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
                'metadata': dict,
                'is_landmark': bool,  # True if Landmark Series
                'is_non_landmark': bool,  # True if fallback (for rest.pdf)
            }

        Example:
            >>> handler = IntroOutroHandler(available_locations)
            >>> info = handler.get_intro_outro_location(validated_proposals)
            >>> if info and info.get('is_landmark'):
            ...     # Use landmark series intro/outro
            ...     pass
        """
        self.logger.info(
            f"[INTRO_OUTRO] Searching for suitable location from {len(validated_proposals)} proposals"
        )

        # First, look for locations with "The Landmark Series"
        for idx, proposal in enumerate(validated_proposals):
            location_key = proposal.get("location")
            self.logger.info(f"[INTRO_OUTRO] Checking proposal {idx+1}: location='{location_key}'")

            if not location_key:
                continue

            # Prefer metadata from validated proposal (set by validator with fresh Asset Service data)
            # Fall back to handler's index if proposal doesn't have metadata
            proposal_meta = proposal.get("location_metadata", {})
            index_meta = self._get_location_fast(location_key) or {}

            # Merge: proposal metadata takes precedence
            location_meta = {**index_meta, **proposal_meta} if proposal_meta else index_meta

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
                    f"[INTRO_OUTRO] LANDMARK SERIES FOUND! Using '{display_name}' for intro/outro"
                )
                return {
                    'key': location_key,
                    'series': series,
                    'metadata': location_meta,
                    'is_landmark': True
                }

        # If no Landmark Series found, use the first location from proposals
        self.logger.info("[INTRO_OUTRO] No Landmark Series location found in proposals")

        if validated_proposals:
            first_proposal = validated_proposals[0]
            first_location_key = first_proposal.get("location")
            self.logger.info(f"[INTRO_OUTRO] Falling back to first location: '{first_location_key}'")

            if first_location_key:
                # Prefer metadata from validated proposal (set by validator with fresh Asset Service data)
                proposal_meta = first_proposal.get("location_metadata", {})
                index_meta = self._get_location_fast(first_location_key) or {}

                # Merge: proposal metadata takes precedence
                location_meta = {**index_meta, **proposal_meta} if proposal_meta else index_meta

                if location_meta:
                    series = location_meta.get('series', '')
                    display_name = location_meta.get('display_name', first_location_key)
                    display_type = location_meta.get('display_type', 'Unknown')

                    self.logger.info(f"[INTRO_OUTRO] Using first location: '{display_name}' (key: {first_location_key})")
                    self.logger.info(f"[INTRO_OUTRO]   - Display Type: {display_type}")
                    self.logger.info(f"[INTRO_OUTRO]   - Series: {series}")

                    # Mark as non-landmark for rest.pdf usage
                    return {
                        'key': first_location_key,
                        'series': series,
                        'metadata': location_meta,
                        'is_non_landmark': True  # Flag to use rest.pdf
                    }

        self.logger.info("[INTRO_OUTRO] No suitable location found for intro/outro")
        return None
