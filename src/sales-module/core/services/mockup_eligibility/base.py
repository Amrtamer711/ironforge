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

    @property
    def logger(self):
        """Lazy-load logger to avoid circular imports."""
        if self._logger is None:
            import config
            self._logger = config.get_logger("core.services.mockup_eligibility")
        return self._logger

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
