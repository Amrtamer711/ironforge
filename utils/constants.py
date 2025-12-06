"""
Shared constants for the Sales Proposals Bot.

This module centralizes constants used across multiple modules to:
- Reduce duplication
- Ensure consistency
- Make configuration easier to find and modify

Note: Environment-specific configuration should go in config/settings.py (Pydantic settings).
This module is for true constants that don't change between environments.
"""

from pathlib import Path

# =============================================================================
# PATH CONSTANTS
# =============================================================================

# Base directory of the project
BASE_DIR = Path(__file__).parent.parent


# =============================================================================
# API CONSTANTS
# =============================================================================

# Debounce window for Slack message processing (seconds)
SLACK_DEBOUNCE_WINDOW = 3

# Default pagination limits
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


# =============================================================================
# BUSINESS CONSTANTS
# =============================================================================

# Default currency
DEFAULT_CURRENCY = "AED"

# Default upload fee for locations (AED)
DEFAULT_UPLOAD_FEE = 3000

# Default SOV (Share of Voice) percentage
DEFAULT_SOV_PERCENT = 16.6

# Default spot/loop durations (seconds)
DEFAULT_SPOT_DURATION = 16
DEFAULT_LOOP_DURATION = 96


# =============================================================================
# FILE TYPE CONSTANTS
# =============================================================================

# Supported image formats
SUPPORTED_IMAGE_FORMATS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}

# Supported document formats
SUPPORTED_DOCUMENT_FORMATS = {".pdf", ".pptx", ".xlsx", ".docx"}

# Temporary file extensions for cleanup
TEMP_FILE_EXTENSIONS = {".pptx", ".pdf", ".bin", ".tmp"}


# =============================================================================
# HTTP STATUS MESSAGES
# =============================================================================

HTTP_STATUS_MESSAGES = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    422: "Validation Error",
    429: "Too Many Requests",
    500: "Internal Server Error",
    502: "Bad Gateway",
    503: "Service Unavailable",
}
