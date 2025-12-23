"""
Request Classifier.

Main orchestrator for request classification.
Combines fast file detection with LLM-based document classification.
"""

import logging
from pathlib import Path

import config

from core.classification.detectors import FileDetector
from core.classification.models import (
    ClassificationContext,
    ClassificationResult,
    Confidence,
    RequestType,
)

logger = logging.getLogger(__name__)


class RequestClassifier:
    """
    Classifies incoming requests to determine the appropriate workflow.

    Classification strategy:
    1. Fast file detection (deterministic for images)
    2. LLM document classification for PDFs/Excel (uses existing bo_parser)
    3. Falls through to LLM for complex/ambiguous cases
    """

    def __init__(self):
        self.file_detector = FileDetector()

    async def classify(
        self,
        context: ClassificationContext,
        download_file_func=None,
    ) -> ClassificationResult:
        """
        Classify a request based on text and files.

        Args:
            context: Classification context with text, files, user info
            download_file_func: Function to download files (for LLM classification)

        Returns:
            ClassificationResult with request type and confidence
        """
        logger.info(f"[CLASSIFIER] Classifying request: text='{context.text[:50]}...', files={len(context.files)}")

        # Step 1: Fast file detection
        file_result = await self.file_detector.detect(context)

        if file_result and file_result.is_deterministic:
            logger.info(f"[CLASSIFIER] Fast-path: {file_result.request_type.value} ({file_result.reasoning})")
            return file_result

        # Step 2: For single documents, use LLM classification
        if len(context.files) == 1 and download_file_func:
            detected_files = self.file_detector.get_detected_files(context)
            doc_files = [f for f in detected_files if f.is_pdf or f.is_excel]

            if doc_files:
                result = await self._classify_document(
                    context=context,
                    detected_file=doc_files[0],
                    download_file_func=download_file_func,
                )
                if result:
                    return result

        # Step 3: No deterministic classification - let LLM handle
        detected_files = self.file_detector.get_detected_files(context)
        return ClassificationResult(
            request_type=RequestType.UNKNOWN,
            confidence=Confidence.LOW,
            files=detected_files,
            reasoning="No deterministic classification - requires LLM",
            is_deterministic=False,
        )

    async def _classify_document(
        self,
        context: ClassificationContext,
        detected_file,
        download_file_func,
    ) -> ClassificationResult | None:
        """
        Classify a document using existing bo_parser.classify_document().

        This reuses the existing LLM-based classification logic.
        """
        try:
            logger.info(f"[CLASSIFIER] Running LLM classification on: {detected_file.filename}")

            # Download the file
            tmp_file = await download_file_func(detected_file.file_info)
            logger.info(f"[CLASSIFIER] Downloaded: {tmp_file}")

            # Use existing bo_parser classifier
            from core.bo_messaging import get_user_real_name
            from workflows.bo_parser import BookingOrderParser

            user_name = await get_user_real_name(context.user_id) if context.user_id else None
            parser = BookingOrderParser(company="backlite")

            classification = await parser.classify_document(
                file_path=Path(tmp_file),
                user_message=context.text,
                user_id=user_name,
            )

            logger.info(f"[CLASSIFIER] LLM classification: {classification}")

            # Map to ClassificationResult
            return self._map_classification(classification, [detected_file])

        except Exception as e:
            logger.error(f"[CLASSIFIER] Document classification failed: {e}", exc_info=True)
            return None

    def _map_classification(
        self,
        raw_classification: dict,
        detected_files: list,
    ) -> ClassificationResult:
        """Map bo_parser classification result to ClassificationResult."""
        classification = raw_classification.get("classification", "UNKNOWN")
        confidence_str = raw_classification.get("confidence", "low")
        company = raw_classification.get("company")
        reasoning = raw_classification.get("reasoning", "")

        # Map classification to RequestType
        if classification == "BOOKING_ORDER":
            request_type = RequestType.BO_PARSING
        elif classification == "ARTWORK":
            request_type = RequestType.MOCKUP
        else:
            request_type = RequestType.UNKNOWN

        # Map confidence
        confidence_map = {
            "high": Confidence.HIGH,
            "medium": Confidence.MEDIUM,
            "low": Confidence.LOW,
        }
        confidence = confidence_map.get(confidence_str, Confidence.LOW)

        return ClassificationResult(
            request_type=request_type,
            confidence=confidence,
            company=company,
            files=detected_files,
            reasoning=reasoning,
            is_deterministic=False,
            raw_classification=raw_classification,
        )


# Singleton instance
_classifier: RequestClassifier | None = None


def get_classifier() -> RequestClassifier:
    """Get the singleton classifier instance."""
    global _classifier
    if _classifier is None:
        _classifier = RequestClassifier()
    return _classifier
