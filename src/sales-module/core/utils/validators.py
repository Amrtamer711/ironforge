"""
Validation utilities for Sales-Module.

Provides common validation functions for proposals, mockups, and other workflows.
"""

from typing import Any


def validate_frame_count(frame_count: int, min_frames: int = 1, max_frames: int = 10) -> tuple[bool, str | None]:
    """
    Validate mockup frame count is within acceptable range.

    Args:
        frame_count: Number of frames to validate
        min_frames: Minimum allowed frames (default: 1)
        max_frames: Maximum allowed frames (default: 10)

    Returns:
        Tuple of (is_valid, error_message)
        - If valid: (True, None)
        - If invalid: (False, error_message)

    Examples:
        >>> validate_frame_count(5)
        (True, None)
        >>> validate_frame_count(0)
        (False, 'Frame count must be at least 1')
        >>> validate_frame_count(15)
        (False, 'Frame count cannot exceed 10')
    """
    if not isinstance(frame_count, int):
        return False, f"Frame count must be an integer, got {type(frame_count).__name__}"

    if frame_count < min_frames:
        return False, f"Frame count must be at least {min_frames}"

    if frame_count > max_frames:
        return False, f"Frame count cannot exceed {max_frames}"

    return True, None


def validate_company_access(user_companies: list[str]) -> tuple[bool, str | None]:
    """
    Validate that user has access to at least one company.

    Args:
        user_companies: List of company schemas user can access

    Returns:
        Tuple of (has_access, error_message)
        - If valid: (True, None)
        - If invalid: (False, error_message)

    Examples:
        >>> validate_company_access(["backlite_dubai", "viola"])
        (True, None)
        >>> validate_company_access([])
        (False, "You don't have access to any company data. Please contact your administrator.")
        >>> validate_company_access(None)
        (False, "You don't have access to any company data. Please contact your administrator.")
    """
    if not user_companies:
        return False, (
            "You don't have access to any company data. "
            "Please contact your administrator to be assigned to a company."
        )

    return True, None


def validate_duration(duration_str: str) -> tuple[bool, str | None]:
    """
    Validate a duration string format.

    Expected formats: "2 Weeks", "4 Weeks", "1 Month", etc.

    Args:
        duration_str: Duration string to validate

    Returns:
        Tuple of (is_valid, error_message)

    Examples:
        >>> validate_duration("4 Weeks")
        (True, None)
        >>> validate_duration("invalid")
        (False, "Invalid duration format: 'invalid'. Expected format like '4 Weeks'")
    """
    if not duration_str:
        return False, "Duration cannot be empty"

    # Basic format check: should have number + unit
    parts = duration_str.strip().split()
    if len(parts) < 2:
        return False, f"Invalid duration format: '{duration_str}'. Expected format like '4 Weeks'"

    # First part should be numeric
    try:
        num = int(parts[0])
        if num <= 0:
            return False, f"Duration must be positive: '{duration_str}'"
    except ValueError:
        return False, f"Duration must start with a number: '{duration_str}'"

    # Second part should be a valid unit
    valid_units = {"week", "weeks", "month", "months", "day", "days"}
    unit = parts[1].lower()
    if unit not in valid_units:
        return False, f"Invalid duration unit '{parts[1]}'. Valid units: {valid_units}"

    return True, None


def validate_currency(currency: str | None) -> tuple[bool, str | None]:
    """
    Validate currency code format.

    Args:
        currency: Currency code to validate (e.g., 'AED', 'USD', 'EUR')
                 None is treated as valid (defaults to AED)

    Returns:
        Tuple of (is_valid, error_message)

    Examples:
        >>> validate_currency("AED")
        (True, None)
        >>> validate_currency(None)
        (True, None)
        >>> validate_currency("INVALID")
        (False, "Invalid currency code: 'INVALID'. Must be 3 uppercase letters.")
    """
    if currency is None:
        return True, None  # None is valid, will default to AED

    if not isinstance(currency, str):
        return False, f"Currency must be a string, got {type(currency).__name__}"

    # Currency codes are 3 uppercase letters (ISO 4217)
    if len(currency) != 3:
        return False, f"Invalid currency code: '{currency}'. Must be 3 letters."

    if not currency.isupper():
        return False, f"Invalid currency code: '{currency}'. Must be 3 uppercase letters."

    if not currency.isalpha():
        return False, f"Invalid currency code: '{currency}'. Must contain only letters."

    # Could add whitelist of valid currencies, but keeping flexible for now
    return True, None


def validate_rate(rate_str: str, allow_zero: bool = False) -> tuple[bool, str | None]:
    """
    Validate a rate/price string format.

    Expected formats: "AED 50,000", "USD 10,000", "5000"

    Args:
        rate_str: Rate string to validate
        allow_zero: Whether to allow zero rates (default: False)

    Returns:
        Tuple of (is_valid, error_message)

    Examples:
        >>> validate_rate("AED 50,000")
        (True, None)
        >>> validate_rate("0")
        (False, "Rate must be greater than zero")
        >>> validate_rate("0", allow_zero=True)
        (True, None)
        >>> validate_rate("invalid")
        (False, "Rate must contain numeric value: 'invalid'")
    """
    if not rate_str:
        return False, "Rate cannot be empty"

    # Remove currency prefix if present
    rate_cleaned = rate_str.strip()
    for currency in ["AED", "USD", "EUR", "GBP"]:
        if rate_cleaned.startswith(currency):
            rate_cleaned = rate_cleaned[len(currency):].strip()
            break

    # Remove commas and other formatting
    rate_cleaned = rate_cleaned.replace(",", "").replace(" ", "")

    # Try to parse as number
    try:
        value = float(rate_cleaned)
        if not allow_zero and value <= 0:
            return False, "Rate must be greater than zero"
        if value < 0:
            return False, "Rate cannot be negative"
    except ValueError:
        return False, f"Rate must contain numeric value: '{rate_str}'"

    return True, None


def validate_date_format(date_str: str) -> tuple[bool, str | None]:
    """
    Validate a date string is in acceptable format.

    Accepts flexible formats: "1st December 2025", "01/12/2025", "2025-12-01", etc.

    Args:
        date_str: Date string to validate

    Returns:
        Tuple of (is_valid, error_message)

    Examples:
        >>> validate_date_format("1st December 2025")
        (True, None)
        >>> validate_date_format("")
        (False, "Date cannot be empty")
    """
    if not date_str:
        return False, "Date cannot be empty"

    # Very basic validation - just check it's non-empty and reasonable length
    # Actual parsing will be done by dateutil.parser or similar
    if len(date_str) < 3:
        return False, f"Date string too short: '{date_str}'"

    if len(date_str) > 50:
        return False, f"Date string too long: '{date_str}'"

    return True, None


def validate_spots(spots: int | str, min_spots: int = 1, max_spots: int = 100) -> tuple[bool, str | None]:
    """
    Validate number of spots for a proposal.

    Args:
        spots: Number of spots (can be int or string)
        min_spots: Minimum allowed spots (default: 1)
        max_spots: Maximum allowed spots (default: 100)

    Returns:
        Tuple of (is_valid, error_message)

    Examples:
        >>> validate_spots(5)
        (True, None)
        >>> validate_spots("10")
        (True, None)
        >>> validate_spots(0)
        (False, 'Number of spots must be at least 1')
        >>> validate_spots(200)
        (False, 'Number of spots cannot exceed 100')
    """
    # Convert to int if string
    try:
        spots_int = int(spots)
    except (ValueError, TypeError):
        return False, f"Spots must be a number, got '{spots}'"

    if spots_int < min_spots:
        return False, f"Number of spots must be at least {min_spots}"

    if spots_int > max_spots:
        return False, f"Number of spots cannot exceed {max_spots}"

    return True, None


def validate_proposal_data(proposal: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Validate a complete proposal data structure.

    Checks all required fields and validates their formats.

    Args:
        proposal: Proposal dictionary to validate

    Returns:
        Tuple of (is_valid, list_of_errors)
        - If valid: (True, [])
        - If invalid: (False, ["error1", "error2", ...])

    Example:
        >>> proposal = {
        ...     "location": "dubai_gateway",
        ...     "start_date": "1st Dec 2025",
        ...     "durations": ["4 Weeks"],
        ...     "net_rates": ["AED 50,000"]
        ... }
        >>> validate_proposal_data(proposal)
        (True, [])
    """
    errors = []

    # Required fields
    required_fields = ["location", "start_date", "durations"]
    for field in required_fields:
        if field not in proposal or not proposal[field]:
            errors.append(f"Missing required field: '{field}'")

    # Validate location
    if "location" in proposal and not proposal["location"]:
        errors.append("Location cannot be empty")

    # Validate start_date
    if "start_date" in proposal:
        is_valid, error = validate_date_format(proposal["start_date"])
        if not is_valid:
            errors.append(f"Invalid start_date: {error}")

    # Validate durations
    if "durations" in proposal:
        durations = proposal["durations"]
        if not isinstance(durations, list) or not durations:
            errors.append("Durations must be a non-empty list")
        else:
            for duration in durations:
                is_valid, error = validate_duration(duration)
                if not is_valid:
                    errors.append(f"Invalid duration: {error}")

    # Validate net_rates if present
    if "net_rates" in proposal:
        rates = proposal["net_rates"]
        if isinstance(rates, list):
            for rate in rates:
                is_valid, error = validate_rate(rate)
                if not is_valid:
                    errors.append(f"Invalid rate: {error}")

    # Validate spots if present
    if "spots" in proposal:
        is_valid, error = validate_spots(proposal["spots"])
        if not is_valid:
            errors.append(f"Invalid spots: {error}")

    return len(errors) == 0, errors
