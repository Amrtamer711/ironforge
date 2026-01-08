"""
Response Builder - Builds frontend-friendly grouped responses for mockup generation.

Aggregates mockup generation results into a structured response grouped by network.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MockupResult:
    """A single mockup generation result."""
    storage_key: str
    image_url: str
    template_used: dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "storage_key": self.storage_key,
            "image_url": self.image_url,
            "template_used": self.template_used,
            "success": self.success,
            "error": self.error,
        }


@dataclass
class NetworkResult:
    """Results for a single network."""
    network_key: str
    network_name: str
    is_standalone: bool
    mockups: list[MockupResult] = field(default_factory=list)
    company: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "network_key": self.network_key,
            "network_name": self.network_name,
            "is_standalone": self.is_standalone,
            "mockups": [m.to_dict() for m in self.mockups],
            "company": self.company,
        }


class MockupResponseBuilder:
    """
    Builds frontend-friendly grouped responses for mockup generation.

    Groups results by network for maximum frontend flexibility.
    Frontend can easily:
    - Display grouped by network
    - Flatten to single list
    - Filter/sort as needed

    Usage:
        builder = MockupResponseBuilder(location_key="dubai_bundle")

        # Add results for each network
        builder.add_network_result(network_result1)
        builder.add_network_result(network_result2)

        # Build final response
        response = builder.build()
    """

    def __init__(self, location_key: str):
        """
        Initialize response builder.

        Args:
            location_key: Original request location key (package or network)
        """
        self.location_key = location_key
        self.network_results: list[NetworkResult] = []

    def add_network_result(self, result: NetworkResult) -> None:
        """Add a network result to the response."""
        self.network_results.append(result)

    def add_mockup_to_network(
        self,
        network_key: str,
        mockup: MockupResult,
    ) -> None:
        """
        Add a mockup result to an existing network.

        If network doesn't exist, creates a new NetworkResult.
        """
        for result in self.network_results:
            if result.network_key == network_key:
                result.mockups.append(mockup)
                return

        # Network not found - this shouldn't happen if used correctly
        # but handle gracefully
        new_result = NetworkResult(
            network_key=network_key,
            network_name=network_key.replace("_", " ").title(),
            is_standalone=True,
            mockups=[mockup],
        )
        self.network_results.append(new_result)

    @property
    def total_mockups(self) -> int:
        """Get total number of mockups generated."""
        return sum(len(r.mockups) for r in self.network_results)

    @property
    def total_networks(self) -> int:
        """Get total number of networks."""
        return len(self.network_results)

    @property
    def successful_mockups(self) -> int:
        """Get number of successfully generated mockups."""
        return sum(
            1 for r in self.network_results
            for m in r.mockups
            if m.success
        )

    @property
    def failed_mockups(self) -> int:
        """Get number of failed mockup generations."""
        return sum(
            1 for r in self.network_results
            for m in r.mockups
            if not m.success
        )

    def build(self) -> dict[str, Any]:
        """
        Build the final response dictionary.

        Returns a frontend-friendly structure grouped by network.
        """
        return {
            "success": self.failed_mockups == 0 and self.total_mockups > 0,
            "location_key": self.location_key,
            "total_mockups": self.total_mockups,
            "total_networks": self.total_networks,
            "successful_mockups": self.successful_mockups,
            "failed_mockups": self.failed_mockups,
            "results": [r.to_dict() for r in self.network_results],
        }

    def build_summary(self) -> str:
        """
        Build a human-readable summary for chat responses.

        Returns a string suitable for LLM chat responses.
        """
        if self.total_mockups == 0:
            return "No mockups were generated."

        if self.total_networks == 1:
            network = self.network_results[0]
            if len(network.mockups) == 1:
                return f"Generated 1 mockup for {network.network_name}."
            else:
                return f"Generated {len(network.mockups)} mockups for {network.network_name}."

        # Multiple networks
        summary_parts = []
        for result in self.network_results:
            count = len(result.mockups)
            summary_parts.append(f"{result.network_name} ({count})")

        return (
            f"Generated {self.total_mockups} mockups across {self.total_networks} locations: "
            f"{', '.join(summary_parts)}."
        )
