"""
Generate LLM Eligibility Service.

LLM-based generate mode is used when generating mockups via natural language (chat/Slack).
Cannot pre-filter because we don't know what the user will request until after parsing.
Provides post-parse validation with user-friendly feedback messages.
"""

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
            # Check if it's a network/location (using shared method)
            location_data = await self._get_location_data(normalized_key)

            if location_data:
                display_name = location_data.get("display_name") or location_key.replace("_", " ").title()
                company = location_data.get("company") or location_data.get("company_schema")

                # Check if it has frames (using shared method)
                has_frames = await self._check_network_has_frames(normalized_key, company_hint=company)

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

            # Check if it's a package (using shared method)
            package_data = await self._find_package(normalized_key)

            if package_data:
                package_name = package_data.get("name", location_key)
                package_id = package_data.get("id")
                company = package_data.get("company")

                # Check if any network in package has frames (using shared method)
                has_network_with_frames = await self._check_package_has_frames(package_id, company)

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
