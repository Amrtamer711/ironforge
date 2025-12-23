"""
Data models for Sales-Module.

Provides Pydantic models for type safety and validation across proposals, mockups, and locations.
"""

from core.models.location import Location, PricingInfo
from core.models.proposal import ProposalLocation, Proposal
from core.models.mockup import FrameCoordinates, MockupConfig

__all__ = [
    # Location models
    "Location",
    "PricingInfo",
    # Proposal models
    "ProposalLocation",
    "Proposal",
    # Mockup models
    "FrameCoordinates",
    "MockupConfig",
]
