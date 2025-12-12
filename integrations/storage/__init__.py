"""
Storage Integration Layer.

Provides abstracted access to storage providers with a unified interface.
Follows the same pattern as integrations/auth/, integrations/llm/,
and integrations/channels/.

Supported Providers:
- Local (LocalStorageProvider): Local filesystem storage (development)
- Supabase (SupabaseStorageProvider): Supabase Storage (S3-compatible, production)
- S3 (planned): Direct AWS S3

Usage:
    from integrations.storage import get_storage_client, upload_file, download_file

    # Get the configured storage client
    storage = get_storage_client()

    # Upload a file
    result = await storage.upload("proposals", "2024/proposal.pdf", pdf_bytes)
    if result.success:
        print(f"Uploaded: {result.file.url}")

    # Download a file
    result = await storage.download("proposals", "2024/proposal.pdf")
    if result.success:
        pdf_data = result.data

    # Get signed URL for temporary access
    url = await storage.get_signed_url("proposals", "2024/proposal.pdf", expires_in=3600)

    # Or use convenience functions
    result = await upload_file("mockups", "image.png", image_bytes)
    result = await download_file("mockups", "image.png")
    url = await get_file_url("mockups", "image.png", signed=True)

Configuration:
    Set STORAGE_PROVIDER environment variable:
    - "local" (default): Use local filesystem
    - "supabase": Use Supabase Storage (recommended for production)
    - "s3": Use AWS S3 directly (planned)

Storage Types (predefined buckets):
    - proposals: Generated proposal PDFs
    - mockups: Generated mockup images
    - uploads: User uploaded files
    - templates: Template files
    - temp: Temporary files
"""

from integrations.storage.base import (
    StorageProvider,
    StorageFile,
    StorageType,
    UploadResult,
    DownloadResult,
    ListResult,
)

from integrations.storage.client import (
    StorageClient,
    get_storage_client,
    set_storage_client,
    reset_storage_client,
    # Convenience functions
    upload_file,
    download_file,
    get_file_url,
    delete_file,
    # DB-aware file operations
    TrackedFile,
    FILE_SIZE_LIMITS,
    store_bo_file,
    store_proposal_file,
    store_mockup_file,
    get_tracked_file,
    download_tracked_file,
    soft_delete_tracked_file,
    soft_delete_mockup_by_location,
)

from integrations.storage.providers import (
    LocalStorageProvider,
    SupabaseStorageProvider,
)

__all__ = [
    # Base types
    "StorageProvider",
    "StorageFile",
    "StorageType",
    "UploadResult",
    "DownloadResult",
    "ListResult",
    # Client
    "StorageClient",
    "get_storage_client",
    "set_storage_client",
    "reset_storage_client",
    # Convenience functions
    "upload_file",
    "download_file",
    "get_file_url",
    "delete_file",
    # DB-aware file operations
    "TrackedFile",
    "FILE_SIZE_LIMITS",
    "store_bo_file",
    "store_proposal_file",
    "store_mockup_file",
    "get_tracked_file",
    "download_tracked_file",
    "soft_delete_tracked_file",
    "soft_delete_mockup_by_location",
    # Providers
    "LocalStorageProvider",
    "SupabaseStorageProvider",
]
