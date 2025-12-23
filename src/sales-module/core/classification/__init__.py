"""
Request Classification Module.

Provides modular, testable request classification for routing
requests to appropriate workflows (proposals, mockups, BO parsing).

All file uploads go through LLM classification because:
- Images could be artwork OR screenshots of booking orders
- PDFs/Excel could be booking orders OR artwork files

Classification outputs:
- BOOKING_ORDER → BO_PARSING workflow
- ARTWORK → MOCKUP workflow
- OTHER → Inform main LLM (neither BO nor artwork)

Usage:
    from core.classification import get_classifier, ClassificationContext, RequestType

    classifier = get_classifier()
    result = await classifier.classify(
        context=ClassificationContext(
            text=user_input,
            files=uploaded_files,
            user_id=user_id,
        ),
        download_file_func=download_file,
    )

    if result.is_high_confidence:
        if result.request_type == RequestType.BO_PARSING:
            # Route to BO parsing
            ...
        elif result.request_type == RequestType.MOCKUP:
            # Route to mockup generation
            ...
        elif result.request_type == RequestType.OTHER:
            # Inform main LLM about the classification
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
