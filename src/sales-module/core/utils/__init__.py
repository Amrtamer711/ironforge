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
]
