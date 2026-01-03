"""
Proposal Validation Module.

Validates proposal data before processing.
"""

from typing import Any

import config
from core.services.asset_service import get_asset_service
from core.utils import match_location_key, get_location_metadata


class ProposalValidator:
    """
    Validates proposal data and resolves location keys.

    Responsibilities:
    - Validate proposal data structure
    - Resolve location names to canonical keys
    - Validate user has access to requested locations
    - Validate duration/rate alignment
    """

    def __init__(self, user_companies: list[str]):
        """
        Initialize validator with user's company access.

        Args:
            user_companies: List of company schemas user has access to
        """
        self.user_companies = user_companies
        self.asset_service = get_asset_service()  # Use singleton for shared cache
        self._available_locations: list[dict[str, Any]] | None = None
        # O(1) lookup index for location metadata: {location_key_lower: metadata}
        self._location_index: dict[str, dict[str, Any]] | None = None
        self.logger = config.logger

    async def _get_available_locations(self) -> list[dict[str, Any]]:
        """Lazy-load available locations and build O(1) lookup index (async)."""
        if self._available_locations is None:
            self._available_locations = await self.asset_service.get_locations_for_companies(
                self.user_companies
            )
            # Build O(1) lookup index by location_key
            self._location_index = {}
            for loc in self._available_locations:
                key = loc.get("location_key", "").lower().strip()
                if key:
                    self._location_index[key] = loc
                    # Also index by display_name for fuzzy matching
                    display_name = loc.get("display_name", "").lower().strip()
                    if display_name and display_name not in self._location_index:
                        self._location_index[display_name] = loc
            self.logger.debug(f"[VALIDATOR] Built location index with {len(self._location_index)} entries")
        return self._available_locations

    def get_location_metadata_fast(self, location_key: str) -> dict[str, Any] | None:
        """
        Get location metadata with O(1) lookup using pre-built index.

        Args:
            location_key: Location key or display name

        Returns:
            Location metadata dict or None if not found
        """
        if self._location_index is None:
            return None
        normalized = location_key.lower().strip()
        return self._location_index.get(normalized)

    async def validate_proposals(
        self,
        proposals_data: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """
        Validate proposal data and resolve location keys.

        Args:
            proposals_data: Raw proposal data from LLM/API

        Returns:
            Tuple of (validated_proposals, errors)
            - validated_proposals: List of validated proposal dicts with resolved location_key
            - errors: List of error messages (empty if all valid)

        Example:
            >>> validator = ProposalValidator(["backlite_dubai"])
            >>> validated, errors = await validator.validate_proposals(proposals_data)
            >>> if errors:
            ...     return {"success": False, "errors": errors}
        """
        validated = []
        errors = []

        if not proposals_data:
            errors.append("No proposals provided")
            return validated, errors

        # Fetch locations once (async)
        available_locations = await self._get_available_locations()

        for idx, proposal in enumerate(proposals_data):
            # Extract proposal data
            location = proposal.get("location", "").lower().strip()
            start_date = proposal.get("start_date")
            durations = proposal.get("durations", [])
            net_rates = proposal.get("net_rates", [])
            spots = proposal.get("spots", 1)

            self.logger.info(f"[VALIDATOR] Validating proposal {idx + 1}: location='{location}'")

            # Validate required fields
            if not location:
                errors.append(f"Proposal {idx + 1}: Missing location")
                continue

            if not durations:
                errors.append(f"Proposal {idx + 1}: Missing durations")
                continue

            # Match location to canonical key
            matched_key = match_location_key(location, available_locations)
            if not matched_key:
                self.logger.error(f"[VALIDATOR] No match found for location '{location}'")
                errors.append(
                    f"Proposal {idx + 1}: Location '{location}' not found in accessible companies"
                )
                continue

            self.logger.info(f"[VALIDATOR] Matched '{location}' to '{matched_key}'")

            # Get full location metadata using O(1) index lookup
            # Note: Asset-Management returns 'company' field, but internally we use 'company_schema'
            location_metadata = self.get_location_metadata_fast(matched_key) or {}
            company_schema = location_metadata.get("company_schema") or location_metadata.get("company")

            # Validate duration/rate alignment (for separate proposals)
            if net_rates and len(durations) != len(net_rates):
                errors.append(
                    f"Proposal {idx + 1}: Mismatched durations ({len(durations)}) "
                    f"and rates ({len(net_rates)}) for {matched_key}"
                )
                continue

            # Get template filename from mapping
            mapping = config.get_location_mapping()
            if matched_key not in mapping:
                errors.append(f"Proposal {idx + 1}: No template file for location '{matched_key}'")
                continue

            # Build validated proposal
            validated_proposal = {
                "location": matched_key,
                "location_input": location,  # Keep original for logging
                "start_date": start_date or "1st December 2025",
                "durations": durations,
                "spots": int(spots),
                "filename": mapping[matched_key],
                "company_schema": company_schema,  # For O(1) template lookup
            }

            # Add optional fields
            if net_rates:
                validated_proposal["net_rates"] = net_rates

            if "end_date" in proposal:
                validated_proposal["end_date"] = proposal["end_date"]

            if "production_fee" in proposal:
                validated_proposal["production_fee"] = proposal["production_fee"]

            if "payment_terms" in proposal:
                validated_proposal["payment_terms"] = proposal["payment_terms"]

            validated.append(validated_proposal)

        return validated, errors

    async def validate_combined_package(
        self,
        proposals_data: list[dict[str, Any]],
        combined_net_rate: str,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """
        Validate proposals for combined package.

        Args:
            proposals_data: Raw proposal data
            combined_net_rate: Combined rate for the package

        Returns:
            Tuple of (validated_proposals, errors)
        """
        if not combined_net_rate:
            return [], ["Combined package requires combined_net_rate"]

        # Use standard validation (async)
        validated, errors = await self.validate_proposals(proposals_data)

        # Additional validation for combined packages
        if validated and len(validated) < 2:
            errors.append("Combined package requires at least 2 locations")

        return validated, errors
