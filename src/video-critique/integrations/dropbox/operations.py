"""
Dropbox Helper Operations for Video Critique.

Provides utility functions for working with Dropbox folder structure
and file naming conventions used in the video workflow.
"""

import re
from datetime import datetime


# Dropbox folder structure for video workflow
DROPBOX_FOLDERS = {
    "raw": "/Site Videos/Raw",
    "pending": "/Site Videos/Pending",
    "critique": "/Site Videos/Critique",
    "rejected": "/Site Videos/Rejected",
    "editing": "/Site Videos/Editing",
    "submitted": "/Site Videos/Submitted to Sales",
    "returned": "/Site Videos/Returned",
    "accepted": "/Site Videos/Accepted",
}

# Status mapping from folder to task status
FOLDER_TO_STATUS = {
    "/Site Videos/Raw": "Raw",
    "/Site Videos/Pending": "Critique",
    "/Site Videos/Critique": "Critique",
    "/Site Videos/Rejected": "Editing",
    "/Site Videos/Editing": "Editing",
    "/Site Videos/Submitted to Sales": "Submitted to Sales",
    "/Site Videos/Returned": "Returned",
    "/Site Videos/Accepted": "Done",
}

# Reverse mapping: status to folder
STATUS_TO_FOLDER = {
    "Raw": DROPBOX_FOLDERS["raw"],
    "Critique": DROPBOX_FOLDERS["critique"],
    "Editing": DROPBOX_FOLDERS["editing"],
    "Submitted to Sales": DROPBOX_FOLDERS["submitted"],
    "Returned": DROPBOX_FOLDERS["returned"],
    "Done": DROPBOX_FOLDERS["accepted"],
}


def get_status_from_folder(folder: str) -> str:
    """
    Determine task status based on which Dropbox folder the file is in.

    Args:
        folder: Dropbox folder path

    Returns:
        Task status string
    """
    return FOLDER_TO_STATUS.get(folder, "Unknown")


def get_folder_for_status(status: str) -> str | None:
    """
    Get the Dropbox folder path for a given task status.

    Args:
        status: Task status

    Returns:
        Folder path or None if no mapping
    """
    return STATUS_TO_FOLDER.get(status)


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
        Full Dropbox path
    """
    # Sanitize components
    brand_clean = sanitize_filename(brand)
    ref_clean = sanitize_filename(reference_number)
    location_clean = sanitize_filename(location)

    # Build filename
    filename = f"{brand_clean}_{ref_clean}_{location_clean}_v{version}"

    # Get folder path
    folder_path = DROPBOX_FOLDERS.get(folder, DROPBOX_FOLDERS["pending"])

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
        Full Dropbox folder path
    """
    folder_path = DROPBOX_FOLDERS.get(folder, DROPBOX_FOLDERS["pending"])
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
