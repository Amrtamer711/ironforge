"""
Setup Mode Eligibility Service.

Setup mode is used when configuring mockup frames for locations.
Only networks are allowed (no packages) because frames are configured at the network level.
"""

from integrations.asset_management import asset_mgmt_client
from .base import BaseEligibilityService, EligibilityResult, LocationOption


class SetupEligibilityService(BaseEligibilityService):
    """
    Setup mode eligibility service.

    Rules:
    - Only networks are eligible (no packages)
    - Packages cannot be used because mockup frames are configured per-network

    Usage:
        service = SetupEligibilityService(user_companies=["backlite_dubai", "backlite_uk"])
        locations = await service.get_eligible_locations()
        result = await service.check_eligibility("dubai_gateway")
    """

    async def get_eligible_locations(self) -> list[LocationOption]:
        """
        Get all networks eligible for mockup setup.

        Returns networks from the user's accessible companies.
        Packages are excluded because frames are configured at the network level.

        Returns:
            List of LocationOption for networks only
        """
        self.logger.info(
            f"[SETUP_ELIGIBILITY] Getting eligible locations for companies: {self.user_companies}"
        )

        locations = []

        try:
            # Get all networks from Asset-Management API (packages excluded)
            networks = await asset_mgmt_client.get_networks(
                companies=self.user_companies,
                active_only=True
            )

            for network in networks:
                locations.append(LocationOption(
                    key=network.get("network_key", ""),
                    name=network.get("name") or network.get("network_key", "").replace("_", " ").title(),
                    type="network",
                    has_frames=False,  # Not relevant for setup mode
                    frame_count=0,
                    company=network.get("company_schema") or network.get("company"),
                ))

        except Exception as e:
            self.logger.warning(f"[SETUP_ELIGIBILITY] Error querying networks: {e}")

        # Sort by name for consistent UI ordering
        locations.sort(key=lambda x: x.name.lower())

        self.logger.info(f"[SETUP_ELIGIBILITY] Found {len(locations)} eligible networks")
        return locations

    async def check_eligibility(self, location_key: str) -> EligibilityResult:
        """
        Check if a location is eligible for mockup setup.

        A location is eligible if:
        1. It exists as a network in the user's accessible companies
        2. It is NOT a package

        Args:
            location_key: Location key to check

        Returns:
            EligibilityResult with status and reason if not eligible
        """
        self.logger.info(f"[SETUP_ELIGIBILITY] Checking eligibility for: {location_key}")

        normalized_key = location_key.lower().strip()

        try:
            # Check if it's a network in user's companies
            location_data = await asset_mgmt_client.get_location_by_key(
                location_key=normalized_key,
                companies=self.user_companies
            )

            if location_data:
                self.logger.info(f"[SETUP_ELIGIBILITY] {location_key} is eligible (network)")
                return EligibilityResult(eligible=True)

            # Check if it's a package (to provide helpful error message)
            packages = await asset_mgmt_client.get_packages(
                companies=self.user_companies,
                active_only=True
            )

            for package in packages:
                pkg_key = package.get("package_key", "").lower()
                if pkg_key == normalized_key:
                    package_name = package.get("name", location_key)
                    self.logger.info(
                        f"[SETUP_ELIGIBILITY] {location_key} is a package, not eligible"
                    )
                    return EligibilityResult(
                        eligible=False,
                        reason=f"'{package_name}' is a package. Mockup frames must be configured for individual networks, not packages. Please select a specific network within the package."
                    )

        except Exception as e:
            self.logger.warning(f"[SETUP_ELIGIBILITY] Error checking eligibility: {e}")

        # Location not found at all
        self.logger.warning(f"[SETUP_ELIGIBILITY] {location_key} not found")
        return EligibilityResult(
            eligible=False,
            reason=f"Location '{location_key}' not found in your accessible companies."
        )
