"""
Dropbox Integration for Video Critique.

This module provides a clean API client for Dropbox operations
required by the video critique workflow:
- Video file uploads
- Folder management
- File search and versioning
- Shared link generation

Usage:
    from integrations.dropbox import DropboxClient

    # Initialize client
    client = DropboxClient.from_config()

    # Upload a video
    result = await client.upload_file(local_path, dropbox_path)

    # Get shared link
    link = await client.get_shared_link(dropbox_path)
"""

from integrations.dropbox.client import DropboxClient
from integrations.dropbox.operations import (
    get_status_from_folder,
    parse_version_from_filename,
    build_submission_path,
)

__all__ = [
    "DropboxClient",
    "get_status_from_folder",
    "parse_version_from_filename",
    "build_submission_path",
]
