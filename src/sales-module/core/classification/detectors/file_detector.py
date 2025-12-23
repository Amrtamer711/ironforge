"""
File Detector.

Fast file-type based classification.
Images → MOCKUP (high confidence, deterministic)
PDF/Excel → Needs LLM classification (returns None to continue)
"""

from core.classification.models import (
    ClassificationContext,
    ClassificationResult,
    Confidence,
    DetectedFile,
    FileType,
    RequestType,
)
from core.utils.constants import is_document_mimetype, is_image_mimetype

from .base import Detector


class FileDetector(Detector):
    """
    Detects request type based on uploaded files.

    Fast-path classification:
    - Image files → MOCKUP (deterministic, no LLM needed)
    - PDF/Excel → Returns None (needs LLM classification via bo_parser)
    """

    @property
    def name(self) -> str:
        return "FileDetector"

    @property
    def priority(self) -> int:
        return 10  # Run first

    async def detect(self, context: ClassificationContext) -> ClassificationResult | None:
        """
        Analyze files in context.

        Returns:
            ClassificationResult for images (deterministic MOCKUP)
            None for documents (needs LLM classification)
            None if no files
        """
        if not context.files:
            return None

        # Detect file types
        detected_files = self._detect_file_types(context.files)

        if not detected_files:
            return None

        # Check for images - deterministic MOCKUP
        image_files = [f for f in detected_files if f.is_image]
        if image_files and not any(f.is_pdf or f.is_excel for f in detected_files):
            return ClassificationResult(
                request_type=RequestType.MOCKUP,
                confidence=Confidence.HIGH,
                files=detected_files,
                reasoning=f"Image file(s) detected: {', '.join(f.filename for f in image_files)}",
                is_deterministic=True,
            )

        # Documents (PDF/Excel) need LLM classification
        # Return None to let the classifier use bo_parser.classify_document()
        return None

    def _detect_file_types(self, files: list[dict]) -> list[DetectedFile]:
        """Detect file types from file info dicts."""
        detected = []

        for f in files:
            filetype = f.get("filetype", "")
            mimetype = f.get("mimetype", "")
            filename = f.get("name", "").lower()

            # Determine file type
            file_type = FileType.UNKNOWN

            # Image detection
            if (filetype in ["jpg", "jpeg", "png", "gif", "bmp", "webp"] or
                is_image_mimetype(mimetype) or
                any(filename.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"])):
                file_type = FileType.IMAGE

            # PDF detection
            elif (filetype == "pdf" or
                  mimetype == "application/pdf" or
                  filename.endswith(".pdf")):
                file_type = FileType.PDF

            # Excel detection
            elif (filetype in ["xlsx", "xls"] or
                  mimetype in ["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               "application/vnd.ms-excel"] or
                  any(filename.endswith(ext) for ext in [".xlsx", ".xls"])):
                file_type = FileType.EXCEL

            # PowerPoint detection
            elif (filetype in ["pptx", "ppt"] or
                  mimetype in ["application/vnd.openxmlformats-officedocument.presentationml.presentation",
                               "application/vnd.ms-powerpoint"] or
                  any(filename.endswith(ext) for ext in [".pptx", ".ppt"])):
                file_type = FileType.POWERPOINT

            # Other documents
            elif (is_document_mimetype(mimetype) or
                  any(filename.endswith(ext) for ext in [".doc", ".docx", ".csv"])):
                file_type = FileType.DOCUMENT

            detected.append(DetectedFile(
                filename=f.get("name", "unknown"),
                mimetype=mimetype,
                file_type=file_type,
                size_bytes=f.get("size", 0),
                file_info=f,
            ))

        return detected

    def get_detected_files(self, context: ClassificationContext) -> list[DetectedFile]:
        """Public method to get detected files without classification."""
        return self._detect_file_types(context.files)
