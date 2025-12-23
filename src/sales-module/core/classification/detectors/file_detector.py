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

        All file types (images, PDFs, Excel) need LLM classification because:
        - Images could be artwork for mockups OR screenshots of booking orders
        - PDFs/Excel could be booking orders OR artwork files

        Returns:
            None - all files need LLM classification
        """
        # File detector no longer returns deterministic results
        # All files go through LLM classification to handle edge cases like:
        # - Booking orders sent as screenshots/images
        # - Artwork sent as PDFs
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
