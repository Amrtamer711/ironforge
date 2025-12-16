"""
File utilities for hashing, validation, and management.

Provides:
- SHA256 hash calculation for file integrity/deduplication
- File size validation
- File extension extraction
"""

import hashlib
from pathlib import Path
from typing import BinaryIO


def calculate_file_hash(
    data: bytes | BinaryIO | str | Path,
    algorithm: str = "sha256",
    chunk_size: int = 8192,
) -> str:
    """
    Calculate hash of file contents.

    Supports bytes, file objects, and file paths.
    Uses streaming to handle large files efficiently.

    Args:
        data: File content as bytes, file object, or path
        algorithm: Hash algorithm ('sha256', 'md5', etc.)
        chunk_size: Chunk size for streaming reads

    Returns:
        Hex-encoded hash string

    Examples:
        # From bytes
        hash = calculate_file_hash(b"hello world")

        # From file path
        hash = calculate_file_hash("/path/to/file.pdf")

        # From file object
        with open("file.pdf", "rb") as f:
            hash = calculate_file_hash(f)
    """
    hasher = hashlib.new(algorithm)

    if isinstance(data, bytes):
        hasher.update(data)
    elif isinstance(data, str | Path):
        # File path - read in chunks
        path = Path(data)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        with open(path, "rb") as f:
            while chunk := f.read(chunk_size):
                hasher.update(chunk)
    else:
        # File-like object - read in chunks
        # Seek to start if possible
        if hasattr(data, "seek"):
            try:
                data.seek(0)
            except Exception:
                pass  # Some streams don't support seeking

        while chunk := data.read(chunk_size):
            hasher.update(chunk)

    return hasher.hexdigest()


def calculate_sha256(data: bytes | BinaryIO | str | Path) -> str:
    """
    Convenience function to calculate SHA256 hash.

    Args:
        data: File content as bytes, file object, or path

    Returns:
        SHA256 hex digest (64 characters)
    """
    return calculate_file_hash(data, algorithm="sha256")


def validate_file_size(
    size: int,
    max_size: int,
    min_size: int = 0,
) -> tuple[bool, str | None]:
    """
    Validate file size is within bounds.

    Args:
        size: File size in bytes
        max_size: Maximum allowed size in bytes
        min_size: Minimum allowed size in bytes (default 0)

    Returns:
        Tuple of (is_valid, error_message)

    Examples:
        valid, error = validate_file_size(file_size, max_size=200*1024*1024)
        if not valid:
            raise ValueError(error)
    """
    if size < min_size:
        if min_size == 1:
            return False, "Empty file not allowed"
        return False, f"File too small. Minimum size is {format_file_size(min_size)}"

    if size > max_size:
        return False, f"File too large. Maximum size is {format_file_size(max_size)}"

    return True, None


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human-readable format.

    Args:
        size_bytes: Size in bytes

    Returns:
        Formatted string (e.g., "10.5 MB")
    """
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def get_file_extension(filename: str) -> str:
    """
    Extract file extension from filename.

    Args:
        filename: Filename or path

    Returns:
        Lowercase extension with dot (e.g., '.pdf')
        Empty string if no extension
    """
    return Path(filename).suffix.lower()


def get_mime_type(filename: str) -> str:
    """
    Get MIME type based on file extension.

    Args:
        filename: Filename or path

    Returns:
        MIME type string (e.g., 'application/pdf')
    """
    import mimetypes

    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or "application/octet-stream"


# Common max file sizes
MAX_FILE_SIZE_DEFAULT = 200 * 1024 * 1024  # 200 MB
MAX_FILE_SIZE_IMAGE = 50 * 1024 * 1024     # 50 MB
MAX_FILE_SIZE_DOCUMENT = 100 * 1024 * 1024  # 100 MB
