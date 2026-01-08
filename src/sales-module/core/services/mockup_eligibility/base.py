"""
Base classes for mockup eligibility services.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EligibilityMode(Enum):
    """Modes for mockup eligibility checking."""
    SETUP = "setup"
    GENERATE_FORM = "generate_form"
    GENERATE_LLM = "generate_llm"


@dataclass
class EligibilityResult:
    """Result of an eligibility check."""
    eligible: bool
    reason: str | None = None


@dataclass
class LocationOption:
    """
    Frontend-friendly location/package option.

    Used for populating dropdowns in the UI.
    """
    key: str
    name: str
    type: str  # "network" or "package"
    has_frames: bool
    frame_count: int = 0
    company: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "key": self.key,
            "name": self.name,
            "type": self.type,
            "has_frames": self.has_frames,
            "frame_count": self.frame_count,
            "company": self.company,
        }


@dataclass
class TemplateOption:
    """
    Frontend-friendly template option.

    Represents a specific mockup template (photo + time_of_day + side combination).
    """
    template_id: str
    network_key: str
    network_name: str | None = None
    time_of_day: str = "day"
    side: str = "gold"
    photo_filename: str = ""
    environment: str = "outdoor"
    frame_count: int = 1
    company: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "template_id": self.template_id,
            "network_key": self.network_key,
            "network_name": self.network_name,
            "time_of_day": self.time_of_day,
            "side": self.side,
            "photo_filename": self.photo_filename,
            "environment": self.environment,
            "frame_count": self.frame_count,
            "company": self.company,
        }


class BaseEligibilityService(ABC):
    """
    Abstract base class for mockup eligibility services.

    Each mode (setup, generate_form, generate_llm) has different eligibility rules.
    Subclasses implement mode-specific logic.

    Provides shared helper methods for:
    - Finding packages by key
    - Checking if networks/packages have mockup frames
    - Getting location data from Asset-Management
    """

    def __init__(self, user_companies: list[str]):
        """
        Initialize eligibility service.

        Args:
            user_companies: List of company schemas the user has access to
        """
        if not user_companies:
            raise ValueError("At least one company must be provided")
        self.user_companies = user_companies
        self._logger = None
        self._frame_service = None
        self._asset_client = None

    @property
    def logger(self):
        """Lazy-load logger to avoid circular imports."""
        if self._logger is None:
            import config
            self._logger = config.get_logger("core.services.mockup_eligibility")
        return self._logger

    @property
    def frame_service(self):
        """Lazy-load MockupFrameService."""
        if self._frame_service is None:
            from core.services.mockup_frame_service import MockupFrameService
            self._frame_service = MockupFrameService(companies=self.user_companies)
        return self._frame_service

    @property
    def asset_client(self):
        """Lazy-load asset management client."""
        if self._asset_client is None:
            from integrations.asset_management import asset_mgmt_client
            self._asset_client = asset_mgmt_client
        return self._asset_client

    # =========================================================================
    # SHARED HELPER METHODS
    # =========================================================================

    async def _get_location_data(self, location_key: str) -> dict | None:
        """
        Get location/network data from Asset-Management.

        Args:
            location_key: The location key to look up

        Returns:
            Location dict if found, None otherwise
        """
        try:
            return await self.asset_client.get_location_by_key(
                location_key=location_key.lower().strip(),
                companies=self.user_companies
            )
        except Exception as e:
            self.logger.debug(f"[ELIGIBILITY] Error getting location data: {e}")
            return None

    async def _find_package(self, package_key: str) -> dict | None:
        """
        Find a package by key in user's companies.

        Args:
            package_key: Package key to search for

        Returns:
            Package dict with id, package_key, name, company if found, None otherwise
        """
        try:
            packages = await self.asset_client.get_packages(
                companies=self.user_companies,
                active_only=True
            )

            normalized_key = package_key.lower().strip()
            for package in packages:
                pkg_key = package.get("package_key", "").lower()
                if pkg_key == normalized_key:
                    return {
                        "id": package.get("id"),
                        "package_key": package.get("package_key"),
                        "name": package.get("name"),
                        "company": package.get("company_schema") or package.get("company"),
                    }

        except Exception as e:
            self.logger.debug(f"[ELIGIBILITY] Error finding package: {e}")

        return None

    async def _check_network_has_frames(
        self,
        network_key: str,
        company_hint: str | None = None
    ) -> bool:
        """
        Check if a network has mockup frames configured.

        Args:
            network_key: Network key to check
            company_hint: Optional company for faster lookup

        Returns:
            True if network has at least one frame, False otherwise
        """
        try:
            return await self.frame_service.has_mockup_frames(
                network_key,
                company_hint=company_hint
            )
        except Exception as e:
            self.logger.debug(f"[ELIGIBILITY] Error checking network frames: {e}")
            return False

    async def _check_package_has_frames(
        self,
        package_id: int,
        company: str
    ) -> bool:
        """
        Check if any network in a package has mockup frames.

        Args:
            package_id: Package ID to check
            company: Company schema

        Returns:
            True if at least one network in the package has frames, False otherwise
        """
        try:
            package_detail = await self.asset_client.get_package(
                company=company,
                package_id=package_id,
                include_items=True
            )

            if not package_detail or not package_detail.get("items"):
                return False

            for item in package_detail.get("items", []):
                network_key = item.get("network_key")
                if network_key:
                    has_frames = await self._check_network_has_frames(
                        network_key,
                        company_hint=company
                    )
                    if has_frames:
                        return True

            return False

        except Exception as e:
            self.logger.warning(f"[ELIGIBILITY] Error checking package frames: {e}")
            return False

    async def _get_package_detail(
        self,
        package_id: int,
        company: str
    ) -> dict | None:
        """
        Get package details with items.

        Args:
            package_id: Package ID
            company: Company schema

        Returns:
            Package dict with items, or None if not found
        """
        try:
            return await self.asset_client.get_package(
                company=company,
                package_id=package_id,
                include_items=True
            )
        except Exception as e:
            self.logger.debug(f"[ELIGIBILITY] Error getting package detail: {e}")
            return None

    # =========================================================================
    # ABSTRACT METHODS (must be implemented by subclasses)
    # =========================================================================

    @abstractmethod
    async def get_eligible_locations(self) -> list[LocationOption]:
        """
        Get all locations eligible for this mode.

        Returns:
            List of LocationOption objects suitable for frontend dropdowns
        """
        pass

    @abstractmethod
    async def check_eligibility(self, location_key: str) -> EligibilityResult:
        """
        Check if a specific location is eligible for this mode.

        Args:
            location_key: Location or package key to check

        Returns:
            EligibilityResult with eligible status and reason if not eligible
        """
        pass
