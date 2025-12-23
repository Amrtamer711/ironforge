"""
Classification Models.

Data models for request classification system.
Reuses existing classification from bo_parser.classify_document().
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RequestType(Enum):
    """Types of requests the system can handle."""

    PROPOSAL = "proposal"
    MOCKUP = "mockup"
    BO_PARSING = "bo_parsing"
    OTHER = "other"  # Confidently determined to be neither BO nor artwork
    CONVERSATION = "conversation"
    UNKNOWN = "unknown"


class FileType(Enum):
    """Detected file types."""

    PDF = "pdf"
    EXCEL = "excel"
    IMAGE = "image"
    POWERPOINT = "powerpoint"
    DOCUMENT = "document"
    UNKNOWN = "unknown"


class Confidence(Enum):
    """Confidence levels matching existing bo_parser schema."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class DetectedFile:
    """Information about a detected file."""

    filename: str
    mimetype: str
    file_type: FileType
    size_bytes: int = 0
    file_info: dict = field(default_factory=dict)  # Original file dict from channel

    @property
    def is_image(self) -> bool:
        return self.file_type == FileType.IMAGE

    @property
    def is_pdf(self) -> bool:
        return self.file_type == FileType.PDF

    @property
    def is_excel(self) -> bool:
        return self.file_type == FileType.EXCEL


@dataclass
class ClassificationResult:
    """
    Result of request classification.

    Unified result that can come from:
    - Fast file-type detection (deterministic)
    - LLM-based document classification (from bo_parser.classify_document)
    """

    request_type: RequestType
    confidence: Confidence

    # For BO_PARSING: which company (backlite/viola)
    company: str | None = None

    # Detected files
    files: list[DetectedFile] = field(default_factory=list)

    # Reasoning (from LLM or detector)
    reasoning: str = ""

    # Whether this was determined without LLM
    is_deterministic: bool = False

    # Raw classification result from bo_parser (if used)
    raw_classification: dict[str, Any] | None = None

    @property
    def has_files(self) -> bool:
        return len(self.files) > 0

    @property
    def has_images(self) -> bool:
        return any(f.is_image for f in self.files)

    @property
    def has_documents(self) -> bool:
        return any(f.is_pdf or f.is_excel for f in self.files)

    @property
    def is_high_confidence(self) -> bool:
        return self.confidence == Confidence.HIGH


@dataclass
class ClassificationContext:
    """Context for classification."""

    text: str
    files: list[dict[str, Any]] = field(default_factory=list)
    user_id: str | None = None
    user_companies: list[str] = field(default_factory=list)
    channel_type: str = "unknown"
