"""
Proposal Validation Module.

Validates proposal data before processing.
"""

from typing import Any

import config
from core.services import AssetService
from core.utils import match_location_key


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
        self.asset_service = AssetService()
        self.available_locations = self.asset_service.get_locations_for_companies(user_companies)
        self.logger = config.logger

    def validate_proposals(
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
            >>> validated, errors = validator.validate_proposals(proposals_data)
            >>> if errors:
            ...     return {"success": False, "errors": errors}
        """
        validated = []
        errors = []

        if not proposals_data:
            errors.append("No proposals provided")
            return validated, errors

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
            matched_key = match_location_key(location, self.available_locations)
            if not matched_key:
                self.logger.error(f"[VALIDATOR] No match found for location '{location}'")
                errors.append(
                    f"Proposal {idx + 1}: Location '{location}' not found in accessible companies"
                )
                continue

            self.logger.info(f"[VALIDATOR] Matched '{location}' to '{matched_key}'")

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

    def validate_combined_package(
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

        # Use standard validation
        validated, errors = self.validate_proposals(proposals_data)

        # Additional validation for combined packages
        if validated and len(validated) < 2:
            errors.append("Combined package requires at least 2 locations")

        return validated, errors
