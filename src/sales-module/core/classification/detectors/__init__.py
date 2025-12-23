"""Classification detectors."""

from .base import Detector
from .file_detector import FileDetector

__all__ = [
    "Detector",
    "FileDetector",
]
