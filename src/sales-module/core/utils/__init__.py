"""
Shared utilities for Sales-Module.

This package contains common functions used across proposals, mockups, and other workflows
to eliminate code duplication and ensure consistency.
"""

from core.utils.location_matcher import (
    match_location_key,
    validate_location_exists,
    get_location_display_name,
    match_and_validate,
    get_location_metadata,
)
from core.utils.path_sanitizer import (
    sanitize_path_component,
    safe_path_join,
    validate_file_extension,
    sanitize_filename,
)
from core.utils.validators import (
    validate_frame_count,
    validate_company_access,
    validate_duration,
    validate_currency,
    validate_rate,
    validate_date_format,
    validate_spots,
    validate_proposal_data,
)
from core.utils.currency_formatter import (
    format_currency,
    parse_currency,
    validate_currency_code,
    get_currency_symbol,
    convert_to_decimal,
    SUPPORTED_CURRENCIES,
    DEFAULT_CURRENCY,
)
from core.utils.file_utils import (
    download_file,
    _validate_pdf_file,
    _validate_powerpoint_file,
    _convert_pdf_to_pptx,
)
from core.utils.memory import (
    cleanup_memory,
    get_memory_usage,
    check_memory_threshold,
)
from core.utils.logging import (
    get_logger,
    setup_logging,
    get_request_id,
    logging_middleware_helper,
)
from core.utils.time import (
    UAE_TZ,
    get_uae_time,
    format_uae_datetime,
)
from core.utils.task_queue import (
    MockupTaskQueue,
    mockup_queue,
)
from core.utils.audit import (
    AuditAction,
    AuditEvent,
    AuditLogger,
    audit_action,
    audit_logger,
)
from core.utils.files import (
    MAX_FILE_SIZE_DEFAULT,
    MAX_FILE_SIZE_DOCUMENT,
    MAX_FILE_SIZE_IMAGE,
    calculate_file_hash,
    calculate_sha256,
    format_file_size,
    get_file_extension,
    get_mime_type,
    validate_file_size,
)
from core.utils.constants import (
    is_image_mimetype,
    is_document_mimetype,
)

__all__ = [
    # Location utilities
    "match_location_key",
    "validate_location_exists",
    "get_location_display_name",
    "match_and_validate",
    "get_location_metadata",
    # Path security
    "sanitize_path_component",
    "safe_path_join",
    "validate_file_extension",
    "sanitize_filename",
    # Validators
    "validate_frame_count",
    "validate_company_access",
    "validate_duration",
    "validate_currency",
    "validate_rate",
    "validate_date_format",
    "validate_spots",
    "validate_proposal_data",
    # Currency formatting
    "format_currency",
    "parse_currency",
    "validate_currency_code",
    "get_currency_symbol",
    "convert_to_decimal",
    "SUPPORTED_CURRENCIES",
    "DEFAULT_CURRENCY",
    # File utilities
    "download_file",
    "_validate_pdf_file",
    "_validate_powerpoint_file",
    "_convert_pdf_to_pptx",
    # Memory utilities
    "cleanup_memory",
    "get_memory_usage",
    "check_memory_threshold",
    # Logging utilities
    "get_logger",
    "setup_logging",
    "get_request_id",
    "logging_middleware_helper",
    # Time utilities
    "UAE_TZ",
    "get_uae_time",
    "format_uae_datetime",
    # Task queue
    "MockupTaskQueue",
    "mockup_queue",
    # Audit utilities
    "AuditAction",
    "AuditEvent",
    "AuditLogger",
    "audit_action",
    "audit_logger",
    # File utilities (extended)
    "MAX_FILE_SIZE_DEFAULT",
    "MAX_FILE_SIZE_DOCUMENT",
    "MAX_FILE_SIZE_IMAGE",
    "calculate_file_hash",
    "calculate_sha256",
    "format_file_size",
    "get_file_extension",
    "get_mime_type",
    "validate_file_size",
    # Constants
    "is_image_mimetype",
    "is_document_mimetype",
]
