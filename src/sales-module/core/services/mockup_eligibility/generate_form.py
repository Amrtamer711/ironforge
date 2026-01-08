"""
Generate Form Eligibility Service.

Form-based generate mode is used when generating mockups via the UI form.
Shows both networks AND packages, but only those that have mockup frames configured.
"""

from integrations.asset_management import asset_mgmt_client
from core.services.mockup_frame_service import MockupFrameService
from .base import BaseEligibilityService, EligibilityResult, LocationOption, TemplateOption


class GenerateFormEligibilityService(BaseEligibilityService):
    """
    Form-based generate mode eligibility service.

    Rules:
    - Shows networks that have at least one mockup frame configured
    - Shows packages where at least one network has frames configured
    - Can fetch templates for a location (expands packages to constituent networks)

    Usage:
        service = GenerateFormEligibilityService(user_companies=["backlite_dubai"])
        locations = await service.get_eligible_locations()
        templates = await service.get_templates_for_location("dubai_bundle")  # package
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
        Get networks and packages eligible for mockup generation.

        Returns locations that have mockup frames configured:
        - Networks with at least one frame
        - Packages where at least one constituent network has frames

        Returns:
            List of LocationOption for eligible networks and packages
        """
        self.logger.info(
            f"[GENERATE_ELIGIBILITY] Getting eligible locations for companies: {self.user_companies}"
        )

        locations = []
        networks_with_frames = set()  # Track for package eligibility check

        try:
            # 1. Get all networks from Asset-Management API
            networks = await asset_mgmt_client.get_networks(
                companies=self.user_companies,
                active_only=True
            )

            for network in networks:
                network_key = network.get("network_key")
                if not network_key:
                    continue

                company = network.get("company_schema") or network.get("company")

                # Check if this network has frames
                has_frames = await self.frame_service.has_mockup_frames(
                    network_key, company_hint=company
                )

                if has_frames:
                    networks_with_frames.add(network_key)
                    variations = await self.frame_service.list_variations(
                        network_key, company_hint=company
                    )
                    frame_count = sum(len(sides) for sides in variations.values())

                    locations.append(LocationOption(
                        key=network_key,
                        name=network.get("name") or network_key.replace("_", " ").title(),
                        type="network",
                        has_frames=True,
                        frame_count=frame_count,
                        company=company,
                    ))

        except Exception as e:
            self.logger.warning(f"[GENERATE_ELIGIBILITY] Error querying networks: {e}")

        try:
            # 2. Get all packages from Asset-Management API
            packages = await asset_mgmt_client.get_packages(
                companies=self.user_companies,
                active_only=True
            )

            for package in packages:
                package_id = package.get("id")
                package_key = package.get("package_key")
                company = package.get("company_schema") or package.get("company")

                if not package_id or not package_key:
                    continue

                try:
                    # Get package with items to find networks
                    package_detail = await asset_mgmt_client.get_package(
                        company=company,
                        package_id=package_id,
                        include_items=True
                    )

                    if not package_detail or not package_detail.get("items"):
                        continue

                    # Check if any network in the package has frames
                    package_networks_with_frames = 0
                    for item in package_detail.get("items", []):
                        network_key = item.get("network_key")
                        if network_key and network_key in networks_with_frames:
                            package_networks_with_frames += 1

                    if package_networks_with_frames > 0:
                        locations.append(LocationOption(
                            key=package_key,
                            name=package.get("name") or package_key.replace("_", " ").title(),
                            type="package",
                            has_frames=True,
                            frame_count=package_networks_with_frames,  # Number of networks with frames
                            company=company,
                        ))

                except Exception as e:
                    self.logger.debug(f"[GENERATE_ELIGIBILITY] Error getting package {package_key}: {e}")
                    continue

        except Exception as e:
            self.logger.warning(f"[GENERATE_ELIGIBILITY] Error querying packages: {e}")

        # Sort by name for consistent UI ordering
        locations.sort(key=lambda x: x.name.lower())

        self.logger.info(
            f"[GENERATE_ELIGIBILITY] Found {len(locations)} eligible locations "
            f"({len(networks_with_frames)} networks with frames)"
        )
        return locations

    async def check_eligibility(self, location_key: str) -> EligibilityResult:
        """
        Check if a location is eligible for mockup generation.

        A location is eligible if:
        1. It's a network with at least one mockup frame, OR
        2. It's a package with at least one network that has frames

        Args:
            location_key: Location or package key to check

        Returns:
            EligibilityResult with status and reason if not eligible
        """
        self.logger.info(f"[GENERATE_ELIGIBILITY] Checking eligibility for: {location_key}")

        normalized_key = location_key.lower().strip()

        try:
            # Check if it's a network/location
            location_data = await asset_mgmt_client.get_location_by_key(
                location_key=normalized_key,
                companies=self.user_companies
            )

            if location_data:
                company = location_data.get("company_schema") or location_data.get("company")
                # It's a network - check if it has frames
                has_frames = await self.frame_service.has_mockup_frames(
                    normalized_key, company_hint=company
                )

                if has_frames:
                    self.logger.info(f"[GENERATE_ELIGIBILITY] {location_key} is eligible (network with frames)")
                    return EligibilityResult(eligible=True)
                else:
                    return EligibilityResult(
                        eligible=False,
                        reason=f"'{location_data.get('display_name', location_key)}' doesn't have any mockup frames configured. Please set up mockup frames in the Setup tab first."
                    )

            # Check if it's a package
            packages = await asset_mgmt_client.get_packages(
                companies=self.user_companies,
                active_only=True
            )

            for package in packages:
                pkg_key = package.get("package_key", "").lower()
                if pkg_key != normalized_key:
                    continue

                package_id = package.get("id")
                package_name = package.get("name", location_key)
                company = package.get("company_schema") or package.get("company")

                # Get package details with items
                package_detail = await asset_mgmt_client.get_package(
                    company=company,
                    package_id=package_id,
                    include_items=True
                )

                if package_detail and package_detail.get("items"):
                    for item in package_detail.get("items", []):
                        network_key = item.get("network_key")
                        if network_key:
                            has_frames = await self.frame_service.has_mockup_frames(
                                network_key, company_hint=company
                            )
                            if has_frames:
                                self.logger.info(
                                    f"[GENERATE_ELIGIBILITY] {location_key} is eligible (package with frames)"
                                )
                                return EligibilityResult(eligible=True)

                # Package exists but no networks have frames
                return EligibilityResult(
                    eligible=False,
                    reason=f"Package '{package_name}' doesn't have any networks with mockup frames. Please set up mockup frames for networks in this package first."
                )

        except Exception as e:
            self.logger.warning(f"[GENERATE_ELIGIBILITY] Error checking eligibility: {e}")

        # Not found
        return EligibilityResult(
            eligible=False,
            reason=f"Location '{location_key}' not found in your accessible companies."
        )

    async def get_templates_for_location(self, location_key: str) -> list[TemplateOption]:
        """
        Get all available templates for a location.

        If location is a package, returns templates from ALL networks in the package.
        If location is a network, returns templates for that network only.

        Args:
            location_key: Location or package key

        Returns:
            List of TemplateOption for available templates
        """
        self.logger.info(f"[GENERATE_ELIGIBILITY] Getting templates for: {location_key}")

        normalized_key = location_key.lower().strip()
        templates = []

        try:
            # Check if it's a network first
            location_data = await asset_mgmt_client.get_location_by_key(
                location_key=normalized_key,
                companies=self.user_companies
            )

            if location_data:
                # It's a network - get templates for this network
                network_templates = await self._get_network_templates(
                    normalized_key,
                    location_data.get("display_name"),
                    location_data.get("company") or location_data.get("company_schema"),
                )
                templates.extend(network_templates)
            else:
                # Check if it's a package
                packages = await asset_mgmt_client.get_packages(
                    companies=self.user_companies,
                    active_only=True
                )

                for package in packages:
                    pkg_key = package.get("package_key", "").lower()
                    if pkg_key != normalized_key:
                        continue

                    package_id = package.get("id")
                    company = package.get("company_schema") or package.get("company")

                    package_templates = await self._get_package_templates(
                        package_id,
                        company,
                    )
                    templates.extend(package_templates)
                    break  # Found the package

        except Exception as e:
            self.logger.warning(f"[GENERATE_ELIGIBILITY] Error getting templates: {e}")

        self.logger.info(f"[GENERATE_ELIGIBILITY] Found {len(templates)} templates for {location_key}")
        return templates

    async def _get_network_templates(
        self,
        network_key: str,
        network_name: str | None,
        company: str | None,
    ) -> list[TemplateOption]:
        """Get all templates for a single network."""
        templates = []

        try:
            # Get all frames for this network
            frames, found_company = await self.frame_service.get_all_frames(
                network_key, company_hint=company
            )

            for frame in frames:
                photo_filename = frame.get("photo_filename")
                if not photo_filename:
                    continue

                time_of_day = frame.get("time_of_day", "day")
                side = frame.get("side", "gold")
                environment = frame.get("environment", "outdoor")
                frames_data = frame.get("frames_data", [])

                template_id = f"{network_key}:{time_of_day}:{side}:{photo_filename}"

                templates.append(TemplateOption(
                    template_id=template_id,
                    network_key=network_key,
                    network_name=network_name or network_key.replace("_", " ").title(),
                    time_of_day=time_of_day,
                    side=side,
                    photo_filename=photo_filename,
                    environment=environment,
                    frame_count=len(frames_data) if frames_data else 1,
                    company=found_company or company,
                ))

        except Exception as e:
            self.logger.warning(f"[GENERATE_ELIGIBILITY] Error getting templates for {network_key}: {e}")

        return templates

    async def _get_package_templates(
        self,
        package_id: int,
        company: str,
    ) -> list[TemplateOption]:
        """Get all templates from all networks in a package."""
        templates = []

        try:
            # Get package with items from Asset-Management API
            package_detail = await asset_mgmt_client.get_package(
                company=company,
                package_id=package_id,
                include_items=True
            )

            if not package_detail or not package_detail.get("items"):
                return templates

            for item in package_detail.get("items", []):
                network_key = item.get("network_key")
                network_name = item.get("network_name") or item.get("name")

                if network_key:
                    network_templates = await self._get_network_templates(
                        network_key, network_name, company
                    )
                    templates.extend(network_templates)

        except Exception as e:
            self.logger.warning(f"[GENERATE_ELIGIBILITY] Error getting package templates: {e}")

        return templates
