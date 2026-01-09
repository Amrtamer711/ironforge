"""
Generate Form Eligibility Service.

Form-based generate mode is used when generating mockups via the UI form.
Shows both networks AND packages, but only those that have mockup frames configured.
"""

import asyncio

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
            # 1. BULK: Get all locations with frames in a single query
            locations_with_frames = await self.frame_service.get_all_locations_with_frames()
            networks_with_frames = set(locations_with_frames.keys())

            self.logger.info(
                f"[GENERATE_ELIGIBILITY] Bulk query found {len(networks_with_frames)} locations with frames"
            )

            # 2. Get all networks from Asset-Management API
            networks = await self.asset_client.get_networks(
                companies=self.user_companies,
                active_only=True
            )

            # 3. Filter networks that have frames (O(1) lookup)
            for network in networks:
                network_key = network.get("network_key")
                if not network_key:
                    continue

                company = network.get("company_schema") or network.get("company")

                # O(1) lookup instead of N API calls
                if network_key in locations_with_frames:
                    frame_info = locations_with_frames[network_key]
                    locations.append(LocationOption(
                        key=network_key,
                        name=network.get("name") or network_key.replace("_", " ").title(),
                        type="network",
                        has_frames=True,
                        frame_count=frame_info.get("frame_count", 1),
                        company=frame_info.get("company") or company,
                    ))

        except Exception as e:
            self.logger.warning(f"[GENERATE_ELIGIBILITY] Error querying networks: {e}")

        try:
            # 2. Get all packages from Asset-Management API
            packages = await self.asset_client.get_packages(
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
                    # Get package with items to find networks (using shared method)
                    package_detail = await self._get_package_detail(package_id, company)

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
            # Check if it's a network/location (using shared method)
            location_data = await self._get_location_data(normalized_key)

            if location_data:
                company = location_data.get("company_schema") or location_data.get("company")
                display_name = location_data.get("display_name", location_key)

                # Check if it has frames (using shared method)
                has_frames = await self._check_network_has_frames(normalized_key, company_hint=company)

                if has_frames:
                    self.logger.info(f"[GENERATE_ELIGIBILITY] {location_key} is eligible (network with frames)")
                    return EligibilityResult(eligible=True)
                else:
                    return EligibilityResult(
                        eligible=False,
                        reason=f"'{display_name}' doesn't have any mockup frames configured. Please set up mockup frames in the Setup tab first."
                    )

            # Check if it's a package (using shared method)
            package_data = await self._find_package(normalized_key)

            if package_data:
                package_id = package_data.get("id")
                package_name = package_data.get("name", location_key)
                company = package_data.get("company")

                # Get bulk data for O(1) lookups
                locations_with_frames = await self.frame_service.get_all_locations_with_frames()

                # Check if any network in package has frames (using shared method with bulk data)
                has_frames = await self._check_package_has_frames(
                    package_id, company, locations_with_frames=locations_with_frames
                )

                if has_frames:
                    self.logger.info(f"[GENERATE_ELIGIBILITY] {location_key} is eligible (package with frames)")
                    return EligibilityResult(eligible=True)
                else:
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
            # Check if it's a network first (using shared method)
            location_data = await self._get_location_data(normalized_key)

            if location_data:
                # It's a network - get templates for this network
                network_templates = await self._get_network_templates(
                    normalized_key,
                    location_data.get("display_name"),
                    location_data.get("company") or location_data.get("company_schema"),
                )
                templates.extend(network_templates)
            else:
                # Check if it's a package (using shared method)
                package_data = await self._find_package(normalized_key)

                if package_data:
                    package_id = package_data.get("id")
                    company = package_data.get("company")

                    package_templates = await self._get_package_templates(package_id, company)
                    templates.extend(package_templates)

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
        """Get all templates from all networks in a package.

        Uses asyncio.gather for parallel fetching instead of sequential N API calls.
        """
        templates = []

        try:
            # Get package with items (using shared method)
            package_detail = await self._get_package_detail(package_id, company)

            if not package_detail or not package_detail.get("items"):
                return templates

            # Build list of tasks for parallel execution
            tasks = []
            for item in package_detail.get("items", []):
                network_key = item.get("network_key")
                network_name = item.get("network_name") or item.get("name")

                if network_key:
                    tasks.append(
                        self._get_network_templates(network_key, network_name, company)
                    )

            # Execute all network template fetches in parallel
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for result in results:
                    if isinstance(result, Exception):
                        self.logger.debug(f"[GENERATE_ELIGIBILITY] Error in parallel fetch: {result}")
                    elif result:
                        templates.extend(result)

        except Exception as e:
            self.logger.warning(f"[GENERATE_ELIGIBILITY] Error getting package templates: {e}")

        return templates

    def get_available_configs_from_templates(
        self,
        templates: list[TemplateOption],
        location_key: str = "",
    ) -> dict:
        """
        Build available config combinations from pre-fetched templates.

        This is the efficient version - use when you already have templates.

        Args:
            templates: List of TemplateOption objects
            location_key: Optional location key for logging

        Returns:
            Hierarchical structure for frontend filtering
        """
        if not templates:
            return {
                "has_frames": False,
                "available_venue_types": [],
                "available_time_of_days": {},
                "available_sides": {},
            }

        # Extract unique configs from templates
        venue_types = set()
        time_of_days_by_venue: dict[str, set[str]] = {}
        sides_by_venue_tod: dict[str, dict[str, set[str]]] = {}

        for template in templates:
            env = template.environment  # "outdoor" or "indoor"
            tod = template.time_of_day  # "day" or "night"
            side = template.side  # "gold", "silver", etc.

            # Track venue types
            venue_types.add(env)

            # Track time_of_days per venue type
            if env not in time_of_days_by_venue:
                time_of_days_by_venue[env] = set()
            # Only track time_of_day for outdoor (indoor ignores it)
            if env == "outdoor":
                time_of_days_by_venue[env].add(tod)

            # Track sides per venue_type + time_of_day
            if env not in sides_by_venue_tod:
                sides_by_venue_tod[env] = {}
            # Only track side for outdoor (indoor ignores it)
            if env == "outdoor":
                if tod not in sides_by_venue_tod[env]:
                    sides_by_venue_tod[env][tod] = set()
                sides_by_venue_tod[env][tod].add(side)

        # Convert sets to sorted lists for JSON serialization
        result = {
            "has_frames": True,
            "available_venue_types": sorted(venue_types),
            "available_time_of_days": {
                env: sorted(tods) for env, tods in time_of_days_by_venue.items()
            },
            "available_sides": {
                env: {
                    tod: sorted(sides) for tod, sides in tods.items()
                }
                for env, tods in sides_by_venue_tod.items()
            },
        }

        if location_key:
            self.logger.info(
                f"[GENERATE_ELIGIBILITY] Available configs for {location_key}: "
                f"venue_types={result['available_venue_types']}, "
                f"time_of_days={result['available_time_of_days']}"
            )

        return result

    async def get_available_configs_for_location(self, location_key: str) -> dict:
        """
        Get available config combinations for a location.

        Builds a hierarchical structure from templates for frontend filtering:
        - Which venue types (environments) are available
        - Which time_of_days are available for each venue type
        - Which sides are available for each venue_type + time_of_day combination

        Note: If you already have templates, use get_available_configs_from_templates()
        directly to avoid duplicate API calls.

        Args:
            location_key: Network key or package key

        Returns:
            {
                "has_frames": bool,
                "available_venue_types": ["outdoor", "indoor"],
                "available_time_of_days": {
                    "outdoor": ["day", "night"],
                    "indoor": []  # indoor ignores time_of_day
                },
                "available_sides": {
                    "outdoor": {
                        "day": ["gold", "silver"],
                        "night": ["gold"]
                    },
                    "indoor": {}  # indoor ignores side
                }
            }
        """
        self.logger.info(f"[GENERATE_ELIGIBILITY] Getting available configs for: {location_key}")

        # Fetch templates and delegate to sync method
        templates = await self.get_templates_for_location(location_key)
        return self.get_available_configs_from_templates(templates, location_key)
