"""
Proposal Validation Module.

Validates proposal data before processing.
"""

import re
from datetime import datetime, timedelta
from typing import Any

import config
from core.services.asset_service import get_asset_service
from core.utils import match_location_key, get_location_metadata


def _calculate_end_date(start_date: str, duration_str: str | int) -> str:
    """
    Calculate end date from start date and duration.

    Args:
        start_date: Start date string (e.g., "1st December 2025" or "01/12/2025")
        duration_str: Duration string (e.g., "4 Weeks", "2 weeks") or int

    Returns:
        End date in same format as start_date
    """
    # Parse duration (extract weeks number)
    weeks = 4  # default
    if isinstance(duration_str, str):
        match = re.search(r'(\d+)', duration_str)
        if match:
            weeks = int(match.group(1))
    elif isinstance(duration_str, int):
        weeks = duration_str

    # Parse start date (try multiple formats)
    parsed_date = None
    formats = [
        "%d/%m/%Y",  # 01/12/2025
        "%d-%m-%Y",  # 01-12-2025
    ]

    for fmt in formats:
        try:
            parsed_date = datetime.strptime(start_date, fmt)
            break
        except ValueError:
            continue

    # Try natural language format (1st December 2025)
    if not parsed_date:
        try:
            # Remove ordinal suffixes
            cleaned = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', start_date)
            parsed_date = datetime.strptime(cleaned, "%d %B %Y")
        except ValueError:
            pass

    if not parsed_date:
        # Return a placeholder if parsing fails
        return f"{weeks} weeks from {start_date}"

    # Calculate end date
    end_date = parsed_date + timedelta(weeks=weeks)

    # Return in same format as input
    if "/" in start_date:
        return end_date.strftime("%d/%m/%Y")
    else:
        # Return natural language format
        day = end_date.day
        suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
        return f"{day}{suffix} {end_date.strftime('%B %Y')}"


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
            durations = proposal.get("durations", [])
            net_rates = proposal.get("net_rates", [])
            spots = proposal.get("spots", 1)

            # Handle start_dates array (separate proposals) or start_date string (combined)
            start_dates = proposal.get("start_dates")  # Array for separate proposals
            start_date = proposal.get("start_date")    # Single for combined proposals

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
            is_package = False

            package_data = None
            if not matched_key:
                # Check if it's a package (packages are valid for proposals)
                from core.services.mockup_service.package_expander import PackageExpander
                expander = PackageExpander(self.user_companies)
                package_data = await expander._find_package(location)
                if package_data:
                    # It's a package - processor will handle expansion
                    matched_key = location
                    is_package = True
                    self.logger.info(f"[VALIDATOR] '{location}' is a package, will be expanded by processor")
                else:
                    self.logger.error(f"[VALIDATOR] No match found for location '{location}'")
                    errors.append(
                        f"Proposal {idx + 1}: Location '{location}' not found in accessible companies"
                    )
                    continue

            self.logger.info(f"[VALIDATOR] Matched '{location}' to '{matched_key}'")

            # Get full location metadata using O(1) index lookup
            # Note: Asset-Management returns 'company' field, but internally we use 'company_schema'
            # For packages, get company from package data
            if is_package and package_data:
                location_metadata = {}
                company_schema = package_data.get("company")
            else:
                location_metadata = self.get_location_metadata_fast(matched_key) or {}
                company_schema = location_metadata.get("company_schema") or location_metadata.get("company")

            # Validate duration/rate alignment (for separate proposals)
            if net_rates and len(durations) != len(net_rates):
                errors.append(
                    f"Proposal {idx + 1}: Mismatched durations ({len(durations)}) "
                    f"and rates ({len(net_rates)}) for {matched_key}"
                )
                continue

            # Validate start_dates alignment (for separate proposals with start_dates array)
            if start_dates and len(start_dates) != len(durations):
                errors.append(
                    f"Proposal {idx + 1}: Mismatched start_dates ({len(start_dates)}) "
                    f"and durations ({len(durations)}) for {matched_key}"
                )
                continue

            # Get template filename - prefer location metadata (from workflow context), fall back to global cache
            template_path = location_metadata.get("template_path") or location_metadata.get("pptx_rel_path")
            if not template_path:
                # Fall back to global mapping cache (legacy)
                mapping = config.get_location_mapping()
                template_path = mapping.get(matched_key)
            if not template_path:
                # Default template path pattern: {location_key}/{location_key}.pptx
                template_path = f"{matched_key}/{matched_key}.pptx"
                self.logger.info(f"[VALIDATOR] Using default template path for {matched_key}: {template_path}")

            # Extract SOV value (handle "16.6%" string, decimal 0.13, or percentage 16.6)
            sov_raw = location_metadata.get("sov_percent") or location_metadata.get("sov") or 16.6
            if isinstance(sov_raw, str):
                sov_value = float(sov_raw.replace("%", "").strip())
            else:
                sov_value = float(sov_raw)

            # Convert decimal format (0.13) to percentage format (13) if needed
            # Database stores as decimal fraction, display expects percentage
            if sov_value < 1:
                sov_value = sov_value * 100

            # Build validated proposal with full location metadata for combined slides
            validated_proposal = {
                "location": matched_key,
                "location_input": location,  # Keep original for logging
                "durations": durations,
                "spots": int(spots),
                "filename": template_path,
                "company_schema": company_schema,  # For O(1) template lookup
                "is_package": is_package,  # Flag for processor to handle package expansion
                # Include full location metadata for combined slide generation
                "location_metadata": {
                    "display_name": location_metadata.get("display_name") or matched_key.replace("_", " ").title(),
                    "display_type": (location_metadata.get("display_type") or "digital").lower(),
                    "series": location_metadata.get("series") or "",
                    "sov": sov_value,
                    "spot_duration": int(location_metadata.get("spot_duration") or 16),
                    "loop_duration": int(location_metadata.get("loop_duration") or 96),
                    "number_of_faces": int(location_metadata.get("number_of_faces") or 1),
                    "upload_fee": int(float(location_metadata.get("upload_fee") or 3000)),
                    "height": location_metadata.get("height") or "",
                    "width": location_metadata.get("width") or "",
                },
            }

            # Handle start_dates/end_dates (arrays for separate) vs start_date/end_date (singles for combined)
            if start_dates:
                # Separate proposals: arrays of start_dates → calculate end_dates array
                validated_proposal["start_dates"] = start_dates
                end_dates = []
                for i, duration in enumerate(durations):
                    sd = start_dates[i] if i < len(start_dates) else start_dates[0]
                    end_dates.append(_calculate_end_date(sd, duration))
                validated_proposal["end_dates"] = end_dates
                # Also set start_date to first for backward compat
                validated_proposal["start_date"] = start_dates[0]
                validated_proposal["end_date"] = end_dates[0]
                self.logger.debug(
                    f"[VALIDATOR] Calculated end_dates for {matched_key}: {end_dates}"
                )
            else:
                # Combined proposals: single start_date → calculate single end_date
                validated_proposal["start_date"] = start_date or "1st December 2025"
                # For combined, duration is singular (first item or from 'duration' field)
                duration_for_calc = durations[0] if durations else proposal.get("duration", "4 Weeks")
                validated_proposal["end_date"] = _calculate_end_date(
                    validated_proposal["start_date"],
                    duration_for_calc
                )
                self.logger.debug(
                    f"[VALIDATOR] Calculated end_date for {matched_key}: {validated_proposal['end_date']}"
                )

            # Add optional fields
            if net_rates:
                validated_proposal["net_rates"] = net_rates

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
            # Check if the single item is a package (packages are allowed alone)
            from core.services.mockup_service.package_expander import PackageExpander
            expander = PackageExpander(self.user_companies)
            single_location = proposals_data[0].get("location", "").lower().strip()
            is_package = await expander._find_package(single_location) is not None

            if not is_package:
                errors.append("Combined requires at least 2 locations (or 1 package)")

        # Check for package + network-inside-package overlap
        # This would result in duplicate content which is not allowed for combined
        if validated and len(validated) >= 2:
            from core.services.mockup_service.package_expander import PackageExpander
            expander = PackageExpander(self.user_companies)

            # Collect packages with their network keys and display names
            # package_key -> {name: display_name, networks: {network_key: display_name}}
            package_info: dict[str, dict] = {}
            non_package_locations: dict[str, str] = {}  # location_key -> display_name

            for proposal in validated:
                location_key = proposal.get("location", "").lower().strip()
                if proposal.get("is_package"):
                    # Expand package to get its network keys and display names
                    package_data = await expander._find_package(location_key)
                    if package_data:
                        targets = await expander._expand_package(package_data)
                        package_info[location_key] = {
                            "name": package_data.get("name", location_key.replace("_", " ").title()),
                            "networks": {
                                t.network_key.lower(): t.network_name or t.network_key.replace("_", " ").title()
                                for t in targets
                            }
                        }
                else:
                    # Get display name from location metadata
                    display_name = proposal.get("location_metadata", {}).get("display_name")
                    if not display_name:
                        display_name = location_key.replace("_", " ").title()
                    non_package_locations[location_key] = display_name

            # Check for overlap: any non-package location that's inside a package
            for package_key, pkg_data in package_info.items():
                network_keys = set(pkg_data["networks"].keys())
                overlaps = set(non_package_locations.keys()).intersection(network_keys)
                if overlaps:
                    # Use display names for user-friendly error message
                    overlap_display_names = [non_package_locations[k] for k in overlaps]
                    overlap_str = ", ".join(overlap_display_names)
                    package_name = pkg_data["name"]
                    errors.append(
                        f"Cannot combine {package_name} package with networks inside it ({overlap_str}). "
                        f"Either use just the package, or select individual networks instead."
                    )

        return validated, errors
