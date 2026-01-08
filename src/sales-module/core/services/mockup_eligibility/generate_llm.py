"""
Generate LLM Eligibility Service.

LLM-based generate mode is used when generating mockups via natural language (chat/Slack).
Cannot pre-filter because we don't know what the user will request until after parsing.
Provides post-parse validation with user-friendly feedback messages.
"""

from integrations.asset_management import asset_mgmt_client
from core.services.mockup_frame_service import MockupFrameService
from .base import BaseEligibilityService, EligibilityResult, LocationOption


class GenerateLLMEligibilityService(BaseEligibilityService):
    """
    LLM-based generate mode eligibility service.

    Rules:
    - Cannot pre-filter (user might say anything)
    - Checks eligibility AFTER parsing user's request
    - Returns user-friendly messages for chat responses

    Usage:
        service = GenerateLLMEligibilityService(user_companies=["backlite_dubai"])

        # After parsing user request to extract location
        result = await service.check_eligibility("dubai_gateway")
        if not result.eligible:
            return f"Sorry, {result.reason}"  # Send to user in chat
    """

    def __init__(self, user_companies: list[str]):
        super().__init__(user_companies)
        self._frame_service = None

    @property
    def frame_service(self) -> MockupFrameService:
        """Lazy-load frame service."""
        if self._frame_service is None:
            self._frame_service = MockupFrameService(companies=self.user_companies)
        return self._frame_service

    async def get_eligible_locations(self) -> list[LocationOption]:
        """
        LLM mode doesn't pre-filter locations.

        This method exists for interface compatibility but returns empty list.
        Use check_eligibility() after parsing the user's request.

        Returns:
            Empty list (LLM mode doesn't pre-filter)
        """
        self.logger.info(
            "[LLM_ELIGIBILITY] get_eligible_locations called - LLM mode doesn't pre-filter"
        )
        return []

    async def check_eligibility(self, location_key: str) -> EligibilityResult:
        """
        Check if a location is eligible for mockup generation.

        Called AFTER parsing the user's natural language request.
        Returns user-friendly messages suitable for chat responses.

        A location is eligible if:
        1. It's a network with at least one mockup frame, OR
        2. It's a package with at least one network that has frames

        Args:
            location_key: Location or package key parsed from user request

        Returns:
            EligibilityResult with status and user-friendly reason if not eligible
        """
        self.logger.info(f"[LLM_ELIGIBILITY] Checking eligibility for: {location_key}")

        normalized_key = location_key.lower().strip()

        try:
            # Check if it's a network/location
            location_data = await asset_mgmt_client.get_location_by_key(
                location_key=normalized_key,
                companies=self.user_companies
            )

            if location_data:
                display_name = location_data.get("display_name") or location_key.replace("_", " ").title()
                company = location_data.get("company") or location_data.get("company_schema")

                # Check if it has frames
                has_frames = await self.frame_service.has_mockup_frames(
                    normalized_key, company_hint=company
                )

                if has_frames:
                    self.logger.info(f"[LLM_ELIGIBILITY] {location_key} is eligible (network with frames)")
                    return EligibilityResult(eligible=True)
                else:
                    self.logger.info(f"[LLM_ELIGIBILITY] {location_key} has no frames")
                    return EligibilityResult(
                        eligible=False,
                        reason=(
                            f"'{display_name}' doesn't have mockup frames configured yet. "
                            "Please set up mockup frames in the Setup tab first, then try again."
                        )
                    )

            # Check if it's a package
            package_data = await self._find_package(normalized_key)

            if package_data:
                package_name = package_data.get("name", location_key)
                package_id = package_data.get("id")
                company = package_data.get("company")

                # Check if any network in package has frames
                has_network_with_frames = await self._package_has_frames(package_id, company)

                if has_network_with_frames:
                    self.logger.info(f"[LLM_ELIGIBILITY] {location_key} is eligible (package with frames)")
                    return EligibilityResult(eligible=True)
                else:
                    self.logger.info(f"[LLM_ELIGIBILITY] Package {location_key} has no networks with frames")
                    return EligibilityResult(
                        eligible=False,
                        reason=(
                            f"Package '{package_name}' doesn't have any networks with mockup frames configured. "
                            "Please set up mockup frames for the networks in this package first."
                        )
                    )

        except Exception as e:
            self.logger.warning(f"[LLM_ELIGIBILITY] Error checking eligibility: {e}")

        # Location not found at all - provide helpful message
        self.logger.warning(f"[LLM_ELIGIBILITY] {location_key} not found")
        return EligibilityResult(
            eligible=False,
            reason=(
                f"I couldn't find a location called '{location_key}'. "
                "Please check the name and try again, or use the form-based mockup tool to see available locations."
            )
        )

    async def _find_package(self, package_key: str) -> dict | None:
        """Find a package by key in user's companies."""
        try:
            packages = await asset_mgmt_client.get_packages(
                companies=self.user_companies,
                active_only=True
            )

            for package in packages:
                pkg_key = package.get("package_key", "").lower()
                if pkg_key == package_key.lower():
                    result = {
                        "id": package.get("id"),
                        "package_key": package.get("package_key"),
                        "name": package.get("name"),
                        "company": package.get("company_schema") or package.get("company"),
                    }
                    return result

        except Exception as e:
            self.logger.debug(f"[LLM_ELIGIBILITY] Error finding package: {e}")

        return None

    async def _package_has_frames(self, package_id: int, company: str) -> bool:
        """Check if any network in a package has mockup frames."""
        try:
            # Get package with items from Asset-Management API
            package_detail = await asset_mgmt_client.get_package(
                company=company,
                package_id=package_id,
                include_items=True
            )

            if not package_detail or not package_detail.get("items"):
                return False

            for item in package_detail.get("items", []):
                network_key = item.get("network_key")
                if network_key:
                    has_frames = await self.frame_service.has_mockup_frames(
                        network_key, company_hint=company
                    )
                    if has_frames:
                        return True

            return False

        except Exception as e:
            self.logger.warning(f"[LLM_ELIGIBILITY] Error checking package frames: {e}")
            return False

    async def get_ineligibility_message(self, location_key: str) -> str | None:
        """
        Get a user-friendly message explaining why a location is ineligible.

        Convenience method that returns just the reason string.

        Args:
            location_key: Location or package key

        Returns:
            Reason string if ineligible, None if eligible
        """
        result = await self.check_eligibility(location_key)
        return result.reason if not result.eligible else None
