"""
Base Detector Interface.

Abstract base class for all classification detectors.
"""

from abc import ABC, abstractmethod

from core.classification.models import ClassificationContext, ClassificationResult


class Detector(ABC):
    """
    Abstract base class for request classifiers.

    Each detector analyzes a specific aspect of the request
    (files, text intent, context, etc.) and returns a classification.
    """

    @abstractmethod
    async def detect(self, context: ClassificationContext) -> ClassificationResult | None:
        """
        Analyze the context and return a classification.

        Args:
            context: The classification context with text, files, etc.

        Returns:
            ClassificationResult if detection is confident, None otherwise.
            Returning None allows other detectors to try.
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Detector name for logging."""
        pass

    @property
    def priority(self) -> int:
        """
        Detector priority (lower = runs first).

        Default is 100. File detection should be lower (e.g., 10)
        to run before text analysis.
        """
        return 100
