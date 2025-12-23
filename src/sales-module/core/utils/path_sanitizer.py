"""
Path sanitization utilities for Sales-Module.

Provides security-focused path handling to prevent path traversal attacks
and ensure safe file operations.
"""

import os
from pathlib import Path


def sanitize_path_component(component: str, allow_empty: bool = False) -> str:
    """
    Sanitize a single path component (filename or directory name).

    Removes dangerous characters and path traversal attempts.

    Args:
        component: The path component to sanitize (e.g., "my-file.pdf")
        allow_empty: Whether to allow empty strings (default: False)

    Returns:
        Sanitized path component safe for use in file operations

    Raises:
        ValueError: If component contains path traversal attempts or is invalid

    Examples:
        >>> sanitize_path_component("my-file.pdf")
        'my-file.pdf'
        >>> sanitize_path_component("../../etc/passwd")
        Traceback (most recent call last):
        ...
        ValueError: Path component contains path traversal attempt: '../../etc/passwd'
        >>> sanitize_path_component("file<>name.txt")
        Traceback (most recent call last):
        ...
        ValueError: Path component contains invalid characters: 'file<>name.txt'
    """
    if not component:
        if allow_empty:
            return ""
        raise ValueError("Path component cannot be empty")

    # Check for path traversal attempts
    if ".." in component:
        raise ValueError(f"Path component contains path traversal attempt: '{component}'")

    # Check for absolute path indicators
    if component.startswith("/") or component.startswith("\\"):
        raise ValueError(f"Path component cannot be absolute: '{component}'")

    # Check for drive letter (Windows)
    if len(component) >= 2 and component[1] == ":":
        raise ValueError(f"Path component cannot contain drive letter: '{component}'")

    # Check for null bytes
    if "\0" in component:
        raise ValueError(f"Path component contains null byte: '{component}'")

    # Check for dangerous characters (OS-specific)
    # Allow: alphanumeric, dash, underscore, dot, space
    dangerous_chars = set('<>:"|?*')
    if any(char in component for char in dangerous_chars):
        raise ValueError(f"Path component contains invalid characters: '{component}'")

    # Normalize the component (remove duplicate separators, normalize case on Windows)
    normalized = os.path.normpath(component)

    # Double-check no traversal happened during normalization
    if ".." in normalized or normalized != component.replace("\\", "/").replace("/", os.sep):
        raise ValueError(f"Path normalization resulted in traversal: '{component}' -> '{normalized}'")

    return component


def safe_path_join(base_path: Path, *components: str, must_exist: bool = False) -> Path:
    """
    Safely join path components, ensuring the result stays within base_path.

    Prevents path traversal attacks by validating that the final path
    is a child of base_path.

    Args:
        base_path: The base directory (all results must be within this)
        *components: Path components to join (each will be sanitized)
        must_exist: If True, raise error if final path doesn't exist (default: False)

    Returns:
        Safe resolved Path object within base_path

    Raises:
        ValueError: If path traversal detected or path is outside base_path
        FileNotFoundError: If must_exist=True and path doesn't exist

    Examples:
        >>> base = Path("/var/data")
        >>> safe_path_join(base, "user", "file.txt")
        PosixPath('/var/data/user/file.txt')
        >>> safe_path_join(base, "..", "etc", "passwd")
        Traceback (most recent call last):
        ...
        ValueError: Path component contains path traversal attempt: '..'
    """
    if not base_path:
        raise ValueError("Base path cannot be empty")

    # Ensure base_path is absolute
    base_path = Path(base_path).resolve()

    # Sanitize all components
    sanitized_components = []
    for comp in components:
        if not comp:
            continue
        sanitized = sanitize_path_component(comp, allow_empty=False)
        sanitized_components.append(sanitized)

    # Join the components
    if not sanitized_components:
        result_path = base_path
    else:
        result_path = base_path.joinpath(*sanitized_components)

    # Resolve to absolute path (follows symlinks)
    result_path = result_path.resolve()

    # CRITICAL: Verify the result is within base_path
    try:
        result_path.relative_to(base_path)
    except ValueError:
        raise ValueError(
            f"Path traversal detected: resulting path '{result_path}' "
            f"is outside base path '{base_path}'"
        )

    # Optional existence check
    if must_exist and not result_path.exists():
        raise FileNotFoundError(f"Path does not exist: '{result_path}'")

    return result_path


def validate_file_extension(
    filename: str,
    allowed_extensions: set[str],
    case_sensitive: bool = False,
) -> bool:
    """
    Validate that a filename has an allowed extension.

    Args:
        filename: The filename to validate (e.g., "document.pdf")
        allowed_extensions: Set of allowed extensions (e.g., {'.pdf', '.docx'})
                           Include the leading dot
        case_sensitive: Whether extension matching is case-sensitive (default: False)

    Returns:
        True if extension is allowed, False otherwise

    Examples:
        >>> validate_file_extension("report.pdf", {'.pdf', '.docx'})
        True
        >>> validate_file_extension("report.PDF", {'.pdf', '.docx'})
        True
        >>> validate_file_extension("report.exe", {'.pdf', '.docx'})
        False
    """
    if not filename or not allowed_extensions:
        return False

    # Get the extension
    _, ext = os.path.splitext(filename)

    if not case_sensitive:
        ext = ext.lower()
        allowed_extensions = {e.lower() for e in allowed_extensions}

    return ext in allowed_extensions


def sanitize_filename(filename: str, max_length: int = 255) -> str:
    """
    Sanitize a filename by removing dangerous characters and limiting length.

    Preserves the file extension but sanitizes the base name.

    Args:
        filename: The filename to sanitize
        max_length: Maximum allowed filename length (default: 255, common FS limit)

    Returns:
        Sanitized filename safe for filesystem operations

    Examples:
        >>> sanitize_filename("my report.pdf")
        'my report.pdf'
        >>> sanitize_filename("../../etc/passwd")
        'passwd'
        >>> sanitize_filename("file<>name.txt")
        'filename.txt'
    """
    if not filename:
        return "unnamed"

    # Split into base and extension
    base, ext = os.path.splitext(filename)

    # Remove path separators from base
    base = base.replace("/", "_").replace("\\", "_")

    # Remove dangerous characters
    dangerous_chars = '<>:"|?*\0'
    for char in dangerous_chars:
        base = base.replace(char, "")

    # Remove leading/trailing dots and spaces
    base = base.strip(". ")

    # If base is empty after sanitization, use default
    if not base:
        base = "unnamed"

    # Reconstruct filename
    sanitized = base + ext

    # Limit length (reserve some space for extension)
    if len(sanitized) > max_length:
        # Truncate base name while preserving extension
        max_base_length = max_length - len(ext)
        base = base[:max_base_length]
        sanitized = base + ext

    return sanitized
