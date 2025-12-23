"""
Request Classification Module.

Provides modular, testable request classification for routing
requests to appropriate workflows (proposals, mockups, BO parsing).

Fast-path classification:
- Image uploads → MOCKUP (deterministic, no LLM)
- PDF/Excel → Uses LLM classification (reuses bo_parser.classify_document)

Usage:
    from core.classification import get_classifier, ClassificationContext

    classifier = get_classifier()
    result = await classifier.classify(
        context=ClassificationContext(
            text=user_input,
            files=uploaded_files,
            user_id=user_id,
        ),
        download_file_func=download_file,
    )

    if result.request_type == RequestType.MOCKUP and result.is_high_confidence:
        # Fast-path to mockup generation
        ...
    elif result.request_type == RequestType.BO_PARSING and result.is_high_confidence:
        # Fast-path to BO parsing
        ...
    else:
        # Let LLM handle
        ...
"""

from core.classification.classifier import RequestClassifier, get_classifier
from core.classification.models import (
    ClassificationContext,
    ClassificationResult,
    Confidence,
    DetectedFile,
    FileType,
    RequestType,
)

__all__ = [
    # Main classifier
    "RequestClassifier",
    "get_classifier",
    # Models
    "ClassificationContext",
    "ClassificationResult",
    "Confidence",
    "DetectedFile",
    "FileType",
    "RequestType",
]
