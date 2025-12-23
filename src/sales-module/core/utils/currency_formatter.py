"""
Currency formatting utilities.

Provides consistent currency handling across Sales-Module.
"""

from decimal import Decimal, InvalidOperation
from typing import Any


# Supported currencies
SUPPORTED_CURRENCIES = {
    "AED": {"symbol": "AED", "decimals": 2},
    "USD": {"symbol": "$", "decimals": 2},
    "EUR": {"symbol": "€", "decimals": 2},
    "GBP": {"symbol": "£", "decimals": 2},
}

DEFAULT_CURRENCY = "AED"


def format_currency(
    amount: float | Decimal | str | int,
    currency: str = DEFAULT_CURRENCY,
    include_symbol: bool = True,
) -> str:
    """
    Format an amount as currency string.

    Args:
        amount: The amount to format (can be float, Decimal, str, or int)
        currency: Currency code (AED, USD, EUR, GBP)
        include_symbol: Whether to include currency symbol

    Returns:
        Formatted currency string (e.g., "AED 1,234.56" or "1,234.56")

    Examples:
        >>> format_currency(1234.56, "AED")
        "AED 1,234.56"
        >>> format_currency(1234.56, "USD")
        "$ 1,234.56"
        >>> format_currency(1234.56, "AED", include_symbol=False)
        "1,234.56"
        >>> format_currency("1234.56", "AED")
        "AED 1,234.56"
    """
    # Convert to Decimal for precision
    try:
        if isinstance(amount, str):
            # Remove commas and whitespace
            amount = amount.replace(",", "").strip()
        decimal_amount = Decimal(str(amount))
    except (InvalidOperation, ValueError):
        raise ValueError(f"Invalid amount: '{amount}'")

    # Validate currency
    currency = currency.upper()
    if currency not in SUPPORTED_CURRENCIES:
        raise ValueError(
            f"Unsupported currency: '{currency}'. "
            f"Supported currencies: {', '.join(SUPPORTED_CURRENCIES.keys())}"
        )

    # Get currency config
    currency_config = SUPPORTED_CURRENCIES[currency]
    decimals = currency_config["decimals"]
    symbol = currency_config["symbol"]

    # Format the number with commas and decimals
    formatted_number = f"{decimal_amount:,.{decimals}f}"

    # Add symbol if requested
    if include_symbol:
        return f"{symbol} {formatted_number}"
    return formatted_number


def parse_currency(
    currency_string: str,
    expected_currency: str | None = None,
) -> tuple[Decimal, str]:
    """
    Parse a currency string to extract amount and currency code.

    Args:
        currency_string: String like "AED 1,234.56" or "$1234.56" or "1234.56"
        expected_currency: Optional currency to validate against

    Returns:
        Tuple of (amount, currency_code)

    Raises:
        ValueError: If currency string is invalid

    Examples:
        >>> parse_currency("AED 1,234.56")
        (Decimal('1234.56'), 'AED')
        >>> parse_currency("$ 1,234.56")
        (Decimal('1234.56'), 'USD')
        >>> parse_currency("1234.56", expected_currency="AED")
        (Decimal('1234.56'), 'AED')
    """
    if not currency_string:
        raise ValueError("Currency string cannot be empty")

    currency_string = currency_string.strip()

    # Try to detect currency symbol
    detected_currency = None

    # Check for currency code prefix (e.g., "AED 1234.56")
    for code in SUPPORTED_CURRENCIES:
        if currency_string.upper().startswith(code):
            detected_currency = code
            # Remove currency code
            amount_str = currency_string[len(code):].strip()
            break

    # Check for currency symbol (e.g., "$1234.56")
    if not detected_currency:
        for code, config in SUPPORTED_CURRENCIES.items():
            symbol = config["symbol"]
            if currency_string.startswith(symbol):
                detected_currency = code
                # Remove symbol
                amount_str = currency_string[len(symbol):].strip()
                break

    # No currency detected - use expected or default
    if not detected_currency:
        amount_str = currency_string
        detected_currency = expected_currency or DEFAULT_CURRENCY

    # Remove commas from amount
    amount_str = amount_str.replace(",", "").strip()

    # Parse amount
    try:
        amount = Decimal(amount_str)
    except (InvalidOperation, ValueError):
        raise ValueError(f"Invalid currency amount: '{amount_str}'")

    # Validate expected currency if provided
    if expected_currency and detected_currency != expected_currency.upper():
        raise ValueError(
            f"Currency mismatch: expected {expected_currency}, "
            f"got {detected_currency}"
        )

    return amount, detected_currency


def validate_currency_code(currency: str) -> bool:
    """
    Validate a currency code.

    Args:
        currency: Currency code to validate

    Returns:
        True if valid, False otherwise

    Example:
        >>> validate_currency_code("AED")
        True
        >>> validate_currency_code("XXX")
        False
    """
    return currency.upper() in SUPPORTED_CURRENCIES


def get_currency_symbol(currency: str) -> str:
    """
    Get the symbol for a currency code.

    Args:
        currency: Currency code

    Returns:
        Currency symbol

    Raises:
        ValueError: If currency not supported

    Example:
        >>> get_currency_symbol("AED")
        "AED"
        >>> get_currency_symbol("USD")
        "$"
    """
    currency = currency.upper()
    if currency not in SUPPORTED_CURRENCIES:
        raise ValueError(f"Unsupported currency: '{currency}'")
    return SUPPORTED_CURRENCIES[currency]["symbol"]


def convert_to_decimal(
    amount: float | str | int | Decimal | Any,
    field_name: str = "amount",
) -> Decimal:
    """
    Safely convert various types to Decimal.

    Args:
        amount: Amount to convert
        field_name: Name of field (for error messages)

    Returns:
        Decimal value

    Raises:
        ValueError: If conversion fails

    Examples:
        >>> convert_to_decimal(1234.56)
        Decimal('1234.56')
        >>> convert_to_decimal("1234.56")
        Decimal('1234.56')
        >>> convert_to_decimal("AED 1,234.56")
        Decimal('1234.56')
    """
    if isinstance(amount, Decimal):
        return amount

    # Handle string amounts that might include currency
    if isinstance(amount, str):
        # Try parsing as currency string first
        try:
            decimal_amount, _ = parse_currency(amount)
            return decimal_amount
        except ValueError:
            # Not a currency string, try direct conversion
            try:
                clean_amount = amount.replace(",", "").strip()
                return Decimal(clean_amount)
            except (InvalidOperation, ValueError):
                raise ValueError(f"Invalid {field_name}: '{amount}'")

    # Handle numeric types
    try:
        return Decimal(str(amount))
    except (InvalidOperation, ValueError):
        raise ValueError(f"Invalid {field_name}: '{amount}'")
