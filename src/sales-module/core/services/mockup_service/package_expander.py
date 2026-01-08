"""
Package Expander - Expands packages/networks to generation targets with storage info.

Handles the complexity of:
- Detecting if a key is a package or network
- Expanding packages to constituent networks
- Determining standalone vs traditional for each network
- Resolving storage keys (network-level for standalone, asset-level for traditional)

Note: Uses asset_mgmt_client for all data access (Asset-Management API).
The networks, packages, and assets tables are in Asset-Management's database.
"""

from dataclasses import dataclass, field
from typing import Any

from integrations.asset_management import asset_mgmt_client


# Lazy import logger to avoid circular dependency
_logger = None


def _get_logger():
    global _logger
    if _logger is None:
        import config
        _logger = config.get_logger("core.services.mockup_service.package_expander")
    return _logger


@dataclass
class GenerationTarget:
    """
    A single target for mockup generation.

    Represents a network with its storage keys resolved based on type:
    - Standalone networks: storage_keys = [network_key]
    - Traditional networks: storage_keys = [asset_key1, asset_key2, ...]
    """
    network_key: str
    network_name: str
    is_standalone: bool
    storage_keys: list[str] = field(default_factory=list)
    company: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "network_key": self.network_key,
            "network_name": self.network_name,
            "is_standalone": self.is_standalone,
            "storage_keys": self.storage_keys,
            "company": self.company,
        }


class PackageExpander:
    """
    Expands packages/networks to generation targets with storage info.

    This is the key service for handling the unified architecture where:
    - Standalone networks store mockups at network level
    - Traditional networks store mockups at asset level
    - Packages contain multiple networks (mixed types possible)

    Usage:
        expander = PackageExpander(user_companies=["backlite_dubai"])

        # Expand a single network
        targets = await expander.expand("dubai_gateway")

        # Expand a package to all its networks
        targets = await expander.expand("dubai_bundle")

        # Generate mockups for each target
        for target in targets:
            for storage_key in target.storage_keys:
                # Generate mockup using storage_key
                pass
    """

    def __init__(self, user_companies: list[str]):
        """
        Initialize PackageExpander.

        Args:
            user_companies: List of company schemas the user has access to
        """
        if not user_companies:
            raise ValueError("At least one company must be provided")

        self.user_companies = user_companies
        self.logger = _get_logger()

    async def expand(self, location_key: str) -> list[GenerationTarget]:
        """
        Expand a location key to a list of generation targets.

        If location_key is a package: returns targets for all networks in the package
        If location_key is a network: returns a single target for that network

        Each target includes:
        - network_key, network_name
        - is_standalone flag
        - storage_keys (where mockups are stored)
        - company

        Args:
            location_key: Package key or network key

        Returns:
            List of GenerationTarget objects
        """
        self.logger.info(f"[PACKAGE_EXPANDER] Expanding: {location_key}")

        normalized_key = location_key.lower().strip()

        # Check if it's a package first
        package_data = await self._find_package(normalized_key)

        if package_data:
            self.logger.info(f"[PACKAGE_EXPANDER] {location_key} is a package, expanding...")
            return await self._expand_package(package_data)

        # It's a network - get single target
        self.logger.info(f"[PACKAGE_EXPANDER] {location_key} is a network")
        target = await self._get_network_target(normalized_key)

        if target:
            return [target]
        else:
            self.logger.warning(f"[PACKAGE_EXPANDER] Network not found: {location_key}")
            return []

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
                    return {
                        "id": package.get("id"),
                        "package_key": package.get("package_key"),
                        "name": package.get("name"),
                        "company": package.get("company_schema") or package.get("company"),
                    }

        except Exception as e:
            self.logger.debug(f"[PACKAGE_EXPANDER] Error finding package: {e}")

        return None

    async def _expand_package(self, package_data: dict) -> list[GenerationTarget]:
        """Expand a package to all its network targets."""
        targets = []
        package_id = package_data.get("id")
        company = package_data.get("company")

        if not package_id or not company:
            return targets

        try:
            # Get package with items from Asset-Management API
            package_detail = await asset_mgmt_client.get_package(
                company=company,
                package_id=package_id,
                include_items=True
            )

            if not package_detail or not package_detail.get("items"):
                self.logger.warning(f"[PACKAGE_EXPANDER] Package {package_id} has no items")
                return targets

            for item in package_detail.get("items", []):
                network_key = item.get("network_key")
                if not network_key:
                    continue

                # Get storage info for this network
                target = await self._get_network_target(network_key)
                if target:
                    targets.append(target)

            self.logger.info(
                f"[PACKAGE_EXPANDER] Package expanded to {len(targets)} network targets"
            )

        except Exception as e:
            self.logger.error(f"[PACKAGE_EXPANDER] Error expanding package: {e}")

        return targets

    async def _get_network_target(self, network_key: str) -> GenerationTarget | None:
        """Get a single network target using Asset-Management API."""
        try:
            # Use get_mockup_storage_info which returns all the info we need
            storage_info = await asset_mgmt_client.get_mockup_storage_info(
                network_key=network_key,
                companies=self.user_companies
            )

            if not storage_info:
                self.logger.debug(f"[PACKAGE_EXPANDER] Network not found: {network_key}")
                return None

            return GenerationTarget(
                network_key=storage_info.get("network_key", network_key),
                network_name=storage_info.get("network_name") or network_key.replace("_", " ").title(),
                is_standalone=storage_info.get("is_standalone", False),
                storage_keys=storage_info.get("storage_keys", [network_key]),
                company=storage_info.get("company"),
            )

        except Exception as e:
            self.logger.debug(f"[PACKAGE_EXPANDER] Error getting network target: {e}")
            return None

    async def get_storage_info(self, location_key: str) -> dict | None:
        """
        Get detailed storage info for a single location.

        Convenience method that returns storage info for a single network.
        For packages, use expand() instead.

        Args:
            location_key: Network key

        Returns:
            Dict with network_key, is_standalone, storage_keys, company
        """
        target = await self._get_network_target(location_key.lower().strip())

        if target:
            return target.to_dict()

        return None
