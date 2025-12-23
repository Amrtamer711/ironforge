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
    1. For single file uploads, use LLM classification (handles all file types)
    2. Falls through to main LLM for multi-file or no-file cases

    All file types go through LLM classification because:
    - Images could be artwork OR screenshots of booking orders
    - PDFs/Excel could be booking orders OR artwork files
    - The LLM can classify as BOOKING_ORDER, ARTWORK, or OTHER
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

        # For single file uploads, use LLM classification
        # This handles ALL file types (images, PDFs, Excel) since:
        # - Images could be BO screenshots
        # - PDFs could be artwork
        if len(context.files) == 1 and download_file_func:
            detected_files = self.file_detector.get_detected_files(context)

            if detected_files:
                result = await self._classify_file(
                    context=context,
                    detected_file=detected_files[0],
                    download_file_func=download_file_func,
                )
                if result:
                    return result

        # No classification possible - let main LLM handle
        detected_files = self.file_detector.get_detected_files(context)
        return ClassificationResult(
            request_type=RequestType.UNKNOWN,
            confidence=Confidence.LOW,
            files=detected_files,
            reasoning="No classification - requires main LLM",
            is_deterministic=False,
        )

    async def _classify_file(
        self,
        context: ClassificationContext,
        detected_file,
        download_file_func,
    ) -> ClassificationResult | None:
        """
        Classify a file using existing bo_parser.classify_document().

        This reuses the existing LLM-based classification logic.
        Works with all file types (images, PDFs, Excel).
        """
        tmp_file = None
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
            result = self._map_classification(classification, [detected_file])

            # Cleanup tmp file after classification
            # Note: _handle_booking_order_parse downloads the file again,
            # so we can safely clean up here for all cases
            if tmp_file:
                try:
                    Path(tmp_file).unlink(missing_ok=True)
                    logger.debug(f"[CLASSIFIER] Cleaned up tmp file: {tmp_file}")
                except Exception:
                    pass

            return result

        except Exception as e:
            logger.error(f"[CLASSIFIER] Document classification failed: {e}", exc_info=True)
            # Cleanup on error
            if tmp_file:
                try:
                    Path(tmp_file).unlink(missing_ok=True)
                except Exception:
                    pass
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
        elif classification == "OTHER":
            request_type = RequestType.OTHER
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
