"""
Dropbox Helper Operations for Video Critique.

Provides utility functions for working with Dropbox folder structure
and file naming conventions used in the video workflow.

NOTE: Folder paths are prefixed based on environment:
- Production: /Site Videos/...
- Development: /test/Site Videos/...

This prevents dev testing from touching production folders.
"""

import re
from datetime import datetime


def _get_folder_prefix() -> str:
    """Get the Dropbox folder prefix from config (lazy import to avoid circular deps)."""
    try:
        import config
        return getattr(config, "DROPBOX_FOLDER_PREFIX", "")
    except ImportError:
        return ""


def get_dropbox_folders() -> dict[str, str]:
    """
    Get Dropbox folder paths with environment-specific prefix.

    Returns:
        Dict mapping folder keys to full Dropbox paths
    """
    prefix = _get_folder_prefix()
    return {
        "raw": f"{prefix}/Site Videos/Raw",
        "pending": f"{prefix}/Site Videos/Pending",
        "critique": f"{prefix}/Site Videos/Critique",
        "rejected": f"{prefix}/Site Videos/Rejected",
        "editing": f"{prefix}/Site Videos/Editing",
        "submitted": f"{prefix}/Site Videos/Submitted to Sales",
        "returned": f"{prefix}/Site Videos/Returned",
        "accepted": f"{prefix}/Site Videos/Accepted",
    }


def get_folder_to_status_mapping() -> dict[str, str]:
    """
    Get folder-to-status mapping with environment-specific prefixes.

    Returns:
        Dict mapping folder paths to task statuses
    """
    prefix = _get_folder_prefix()
    return {
        f"{prefix}/Site Videos/Raw": "Raw",
        f"{prefix}/Site Videos/Pending": "Critique",
        f"{prefix}/Site Videos/Critique": "Critique",
        f"{prefix}/Site Videos/Rejected": "Editing",
        f"{prefix}/Site Videos/Editing": "Editing",
        f"{prefix}/Site Videos/Submitted to Sales": "Submitted to Sales",
        f"{prefix}/Site Videos/Returned": "Returned",
        f"{prefix}/Site Videos/Accepted": "Done",
    }


def get_status_to_folder_mapping() -> dict[str, str]:
    """
    Get status-to-folder mapping with environment-specific prefixes.

    Returns:
        Dict mapping task statuses to folder paths
    """
    folders = get_dropbox_folders()
    return {
        "Raw": folders["raw"],
        "Critique": folders["critique"],
        "Editing": folders["editing"],
        "Submitted to Sales": folders["submitted"],
        "Returned": folders["returned"],
        "Done": folders["accepted"],
    }


# Legacy static mappings (for backward compatibility - use functions above for new code)
# These are evaluated at import time, so they won't pick up config changes
DROPBOX_FOLDERS = get_dropbox_folders()
FOLDER_TO_STATUS = get_folder_to_status_mapping()
STATUS_TO_FOLDER = get_status_to_folder_mapping()


def get_status_from_folder(folder: str) -> str:
    """
    Determine task status based on which Dropbox folder the file is in.

    Args:
        folder: Dropbox folder path

    Returns:
        Task status string
    """
    # Use dynamic mapping to support dev/prod prefix
    mapping = get_folder_to_status_mapping()
    return mapping.get(folder, "Unknown")


def get_folder_for_status(status: str) -> str | None:
    """
    Get the Dropbox folder path for a given task status.

    Args:
        status: Task status

    Returns:
        Folder path or None if no mapping
    """
    # Use dynamic mapping to support dev/prod prefix
    mapping = get_status_to_folder_mapping()
    return mapping.get(status)


def parse_version_from_filename(filename: str) -> int:
    """
    Extract version number from a filename.

    Expected format: Brand_RefNumber_LocationKey_v1.mp4

    Args:
        filename: File name to parse

    Returns:
        Version number (1 if not found)
    """
    # Try pattern: _v1, _v2, etc.
    match = re.search(r'_v(\d+)(?:\.[^.]+)?$', filename, re.IGNORECASE)
    if match:
        return int(match.group(1))

    # Try pattern: _1, _2, etc. at end before extension
    match = re.search(r'_(\d+)(?:\.[^.]+)?$', filename)
    if match:
        return int(match.group(1))

    return 1


def get_latest_version_file(files: list[dict]) -> dict | None:
    """
    Find the file with the highest version number from a list.

    Args:
        files: List of file info dicts with 'name' and 'path' keys

    Returns:
        File info dict for highest version, or None if empty
    """
    if not files:
        return None

    latest_file = None
    latest_version = 0

    for file_info in files:
        version = parse_version_from_filename(file_info.get("name", ""))
        if version > latest_version:
            latest_version = version
            latest_file = file_info

    return latest_file if latest_file else files[0]


def build_submission_path(
    task_number: int,
    brand: str,
    reference_number: str,
    location: str,
    version: int = 1,
    folder: str = "pending",
) -> str:
    """
    Build a standard Dropbox path for a video submission.

    Args:
        task_number: Task number
        brand: Brand name
        reference_number: Reference number
        location: Location key
        version: Version number
        folder: Target folder key (default: pending)

    Returns:
        Full Dropbox path (with dev/prod prefix applied)
    """
    # Sanitize components
    brand_clean = sanitize_filename(brand)
    ref_clean = sanitize_filename(reference_number)
    location_clean = sanitize_filename(location)

    # Build filename
    filename = f"{brand_clean}_{ref_clean}_{location_clean}_v{version}"

    # Get folder path (dynamic to support dev/prod prefix)
    folders = get_dropbox_folders()
    folder_path = folders.get(folder, folders["pending"])

    # Build task folder
    task_folder = f"Task_{task_number}"

    return f"{folder_path}/{task_folder}/{filename}"


def build_submission_folder_path(
    task_number: int,
    folder: str = "pending",
) -> str:
    """
    Build the submission folder path for a task.

    Args:
        task_number: Task number
        folder: Target folder key

    Returns:
        Full Dropbox folder path (with dev/prod prefix applied)
    """
    # Get folder path (dynamic to support dev/prod prefix)
    folders = get_dropbox_folders()
    folder_path = folders.get(folder, folders["pending"])
    return f"{folder_path}/Task_{task_number}"


def sanitize_filename(name: str) -> str:
    """
    Sanitize a string for use in filenames.

    Removes or replaces characters that are not safe for filenames.

    Args:
        name: String to sanitize

    Returns:
        Sanitized string
    """
    if not name:
        return ""

    # Replace spaces with underscores
    result = name.replace(" ", "_")

    # Remove or replace unsafe characters
    unsafe_chars = '<>:"/\\|?*'
    for char in unsafe_chars:
        result = result.replace(char, "")

    # Remove leading/trailing dots and spaces
    result = result.strip(". ")

    return result


def build_folder_name(
    task_number: int,
    brand: str,
    reference_number: str,
    campaign_date: str,
) -> str:
    """
    Build a standard folder name for a task submission.

    Args:
        task_number: Task number
        brand: Brand name
        reference_number: Reference number
        campaign_date: Campaign date (DD-MM-YYYY format)

    Returns:
        Folder name
    """
    # Parse date if in DD-MM-YYYY format
    try:
        dt = datetime.strptime(campaign_date, "%d-%m-%Y")
        date_str = dt.strftime("%Y%m%d")
    except ValueError:
        date_str = campaign_date.replace("-", "").replace("/", "")

    brand_clean = sanitize_filename(brand)[:20]  # Limit length
    ref_clean = sanitize_filename(reference_number)

    return f"Task_{task_number}_{brand_clean}_{ref_clean}_{date_str}"
