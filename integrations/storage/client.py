"""
Unified Storage Client.

Provides a single interface to interact with any storage provider.
Follows the same pattern as integrations/auth/client.py (AuthClient).

Extended with DB-aware operations that track files in the database
for the sales module (documents, mockup_files, proposal_files).
"""

import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Optional, Union

from integrations.storage.base import (
    DownloadResult,
    ListResult,
    StorageFile,
    StorageProvider,
    StorageType,
    UploadResult,
)

logger = logging.getLogger("proposal-bot")

# Global storage client instance
_storage_client: Optional["StorageClient"] = None


class StorageClient:
    """
    Unified storage client that abstracts provider-specific implementations.

    Similar to AuthClient, this provides a single interface for storage operations
    regardless of the underlying provider (Local, Supabase, S3, etc.).

    Usage:
        from integrations.storage import get_storage_client

        # Get the configured client
        storage = get_storage_client()

        # Upload a file
        result = await storage.upload("proposals", "2024/proposal.pdf", pdf_bytes)
        if result.success:
            print(f"Uploaded: {result.file.url}")

        # Download a file
        result = await storage.download("proposals", "2024/proposal.pdf")
        if result.success:
            pdf_data = result.data

        # Get a signed URL
        url = await storage.get_signed_url("proposals", "2024/proposal.pdf")
    """

    def __init__(self, provider: StorageProvider):
        """
        Initialize the storage client with a provider.

        Args:
            provider: The storage provider implementation to use
        """
        self._provider = provider
        logger.info(f"[STORAGE] Client initialized with provider: {provider.name}")

    @classmethod
    def from_config(cls, provider_name: Optional[str] = None) -> "StorageClient":
        """
        Create a StorageClient using configuration from environment.

        Args:
            provider_name: Which provider to use ("local", "supabase", "s3").
                          If None, uses STORAGE_PROVIDER env var or defaults to "local".

        Returns:
            Configured StorageClient instance
        """
        # Get provider name from settings if not provided
        if not provider_name:
            try:
                from app_settings import settings
                provider_name = settings.storage_provider
            except Exception:
                provider_name = "local"

        if provider_name == "supabase":
            from integrations.storage.providers.supabase import SupabaseStorageProvider
            provider = SupabaseStorageProvider()
        elif provider_name == "s3":
            # S3 provider would go here when implemented
            raise NotImplementedError(
                "S3 provider not yet implemented. Use 'supabase' for S3-compatible storage."
            )
        else:
            from integrations.storage.providers.local import LocalStorageProvider
            provider = LocalStorageProvider()

        return cls(provider)

    @property
    def provider(self) -> StorageProvider:
        """Access the underlying provider."""
        return self._provider

    @property
    def provider_name(self) -> str:
        """Get the name of the current provider."""
        return self._provider.name

    # =========================================================================
    # UPLOAD OPERATIONS
    # =========================================================================

    async def upload(
        self,
        bucket: str,
        key: str,
        data: Union[bytes, BinaryIO],
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> UploadResult:
        """
        Upload a file to storage.

        Args:
            bucket: Target bucket/container name
            key: File key/path within the bucket
            data: File contents as bytes or file-like object
            content_type: MIME type (auto-detected if not provided)
            metadata: Additional file metadata

        Returns:
            UploadResult with file info if successful
        """
        return await self._provider.upload(bucket, key, data, content_type, metadata)

    async def upload_from_path(
        self,
        bucket: str,
        key: str,
        local_path: Union[str, Path],
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> UploadResult:
        """
        Upload a file from local filesystem.

        Args:
            bucket: Target bucket/container name
            key: File key/path within the bucket
            local_path: Path to local file
            content_type: MIME type (auto-detected if not provided)
            metadata: Additional file metadata

        Returns:
            UploadResult with file info if successful
        """
        return await self._provider.upload_from_path(bucket, key, local_path, content_type, metadata)

    # =========================================================================
    # DOWNLOAD OPERATIONS
    # =========================================================================

    async def download(
        self,
        bucket: str,
        key: str,
    ) -> DownloadResult:
        """
        Download a file from storage.

        Args:
            bucket: Source bucket/container name
            key: File key/path within the bucket

        Returns:
            DownloadResult with file contents if successful
        """
        return await self._provider.download(bucket, key)

    async def download_to_path(
        self,
        bucket: str,
        key: str,
        local_path: Union[str, Path],
    ) -> DownloadResult:
        """
        Download a file to local filesystem.

        Args:
            bucket: Source bucket/container name
            key: File key/path within the bucket
            local_path: Path to save file locally

        Returns:
            DownloadResult with file info if successful
        """
        return await self._provider.download_to_path(bucket, key, local_path)

    # =========================================================================
    # FILE OPERATIONS
    # =========================================================================

    async def delete(
        self,
        bucket: str,
        key: str,
    ) -> bool:
        """
        Delete a file from storage.

        Args:
            bucket: Bucket/container name
            key: File key/path to delete

        Returns:
            True if deleted successfully
        """
        return await self._provider.delete(bucket, key)

    async def exists(
        self,
        bucket: str,
        key: str,
    ) -> bool:
        """
        Check if a file exists.

        Args:
            bucket: Bucket/container name
            key: File key/path to check

        Returns:
            True if file exists
        """
        return await self._provider.exists(bucket, key)

    async def get_file_info(
        self,
        bucket: str,
        key: str,
    ) -> Optional[StorageFile]:
        """
        Get file metadata without downloading contents.

        Args:
            bucket: Bucket/container name
            key: File key/path

        Returns:
            StorageFile with metadata or None if not found
        """
        return await self._provider.get_file_info(bucket, key)

    async def list_files(
        self,
        bucket: str,
        prefix: Optional[str] = None,
        limit: int = 100,
        continuation_token: Optional[str] = None,
    ) -> ListResult:
        """
        List files in a bucket with optional prefix filtering.

        Args:
            bucket: Bucket/container name
            prefix: Filter by key prefix (folder path)
            limit: Maximum number of files to return
            continuation_token: Token for pagination

        Returns:
            ListResult with list of files
        """
        return await self._provider.list_files(bucket, prefix, limit, continuation_token)

    async def copy(
        self,
        source_bucket: str,
        source_key: str,
        dest_bucket: str,
        dest_key: str,
    ) -> UploadResult:
        """
        Copy a file within storage.

        Args:
            source_bucket: Source bucket name
            source_key: Source file key
            dest_bucket: Destination bucket name
            dest_key: Destination file key

        Returns:
            UploadResult with new file info if successful
        """
        return await self._provider.copy(source_bucket, source_key, dest_bucket, dest_key)

    async def move(
        self,
        source_bucket: str,
        source_key: str,
        dest_bucket: str,
        dest_key: str,
    ) -> UploadResult:
        """
        Move a file within storage.

        Args:
            source_bucket: Source bucket name
            source_key: Source file key
            dest_bucket: Destination bucket name
            dest_key: Destination file key

        Returns:
            UploadResult with new file info if successful
        """
        return await self._provider.move(source_bucket, source_key, dest_bucket, dest_key)

    # =========================================================================
    # URL OPERATIONS
    # =========================================================================

    async def get_public_url(
        self,
        bucket: str,
        key: str,
    ) -> Optional[str]:
        """
        Get a public URL for a file (if bucket is public).

        Args:
            bucket: Bucket/container name
            key: File key/path

        Returns:
            Public URL or None if not available
        """
        return await self._provider.get_public_url(bucket, key)

    async def get_signed_url(
        self,
        bucket: str,
        key: str,
        expires_in: int = 3600,
    ) -> Optional[str]:
        """
        Get a presigned URL for temporary access.

        Args:
            bucket: Bucket/container name
            key: File key/path
            expires_in: URL expiration time in seconds (default 1 hour)

        Returns:
            Presigned URL or None if failed
        """
        return await self._provider.get_signed_url(bucket, key, expires_in)

    # =========================================================================
    # BUCKET OPERATIONS
    # =========================================================================

    async def ensure_bucket(
        self,
        bucket: str,
        public: bool = False,
    ) -> bool:
        """
        Ensure a bucket exists, create if it doesn't.

        Args:
            bucket: Bucket name
            public: Whether bucket should be publicly accessible

        Returns:
            True if bucket exists or was created
        """
        return await self._provider.ensure_bucket(bucket, public)

    async def list_buckets(self) -> list[str]:
        """
        List all available buckets.

        Returns:
            List of bucket names
        """
        return await self._provider.list_buckets()

    # =========================================================================
    # CONVENIENCE METHODS
    # =========================================================================

    async def ensure_default_buckets(self) -> None:
        """
        Ensure all default storage buckets exist.

        Creates buckets for: proposals, mockups, uploads, templates, temp
        """
        for bucket_type in StorageType:
            await self.ensure_bucket(bucket_type.value)
        logger.info("[STORAGE] Default buckets ensured")


# =============================================================================
# MODULE-LEVEL FUNCTIONS (like integrations/auth/client.py)
# =============================================================================


def get_storage_client() -> StorageClient:
    """
    Get the global storage client instance.

    Creates one if it doesn't exist.
    """
    global _storage_client
    if _storage_client is None:
        _storage_client = StorageClient.from_config()
    return _storage_client


def set_storage_client(client: StorageClient) -> None:
    """
    Set the global storage client instance.

    Args:
        client: StorageClient to use globally
    """
    global _storage_client
    _storage_client = client
    logger.info(f"[STORAGE] Global client set to: {client.provider_name}")


def reset_storage_client() -> None:
    """Reset the global storage client (mainly for testing)."""
    global _storage_client
    _storage_client = None


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


async def upload_file(
    bucket: str,
    key: str,
    data: Union[bytes, BinaryIO],
    content_type: Optional[str] = None,
) -> UploadResult:
    """
    Convenience function to upload a file using the global client.

    Args:
        bucket: Target bucket
        key: File key/path
        data: File contents
        content_type: MIME type

    Returns:
        UploadResult
    """
    return await get_storage_client().upload(bucket, key, data, content_type)


async def download_file(bucket: str, key: str) -> DownloadResult:
    """
    Convenience function to download a file using the global client.

    Args:
        bucket: Source bucket
        key: File key/path

    Returns:
        DownloadResult
    """
    return await get_storage_client().download(bucket, key)


async def get_file_url(
    bucket: str,
    key: str,
    signed: bool = False,
    expires_in: int = 3600,
) -> Optional[str]:
    """
    Convenience function to get a file URL.

    Args:
        bucket: Bucket name
        key: File key/path
        signed: If True, return a presigned URL
        expires_in: Expiration time for signed URLs

    Returns:
        URL string or None
    """
    client = get_storage_client()
    if signed:
        return await client.get_signed_url(bucket, key, expires_in)
    return await client.get_public_url(bucket, key)


async def delete_file(bucket: str, key: str) -> bool:
    """
    Convenience function to delete a file using the global client.

    Args:
        bucket: Bucket name
        key: File key/path

    Returns:
        True if deleted
    """
    return await get_storage_client().delete(bucket, key)


# =============================================================================
# DB-AWARE FILE OPERATIONS
# =============================================================================
# These functions combine storage operations with database tracking.
# They store file metadata in the appropriate table (documents, mockup_files,
# proposal_files) and handle file hashing for integrity.


@dataclass
class TrackedFile:
    """Result from DB-aware file operations."""
    file_id: str
    storage_provider: str
    storage_bucket: str
    storage_key: str
    original_filename: str
    file_size: int
    file_type: str
    file_hash: Optional[str] = None
    url: Optional[str] = None
    success: bool = True
    error: Optional[str] = None
    is_duplicate: bool = False  # True if file already existed (same hash)


# File size limits for different file types
FILE_SIZE_LIMITS = {
    "bo_document": 100 * 1024 * 1024,      # 100 MB for BO documents
    "original_bo": 100 * 1024 * 1024,      # 100 MB
    "combined_bo_pdf": 150 * 1024 * 1024,  # 150 MB for combined PDFs
    "proposal_pptx": 200 * 1024 * 1024,    # 200 MB for proposals
    "proposal_pdf": 200 * 1024 * 1024,     # 200 MB
    "mockup_image": 50 * 1024 * 1024,      # 50 MB for mockups
    "location_photo": 50 * 1024 * 1024,    # 50 MB
    "default": 100 * 1024 * 1024,          # 100 MB default
}


def _validate_file_size(file_size: int, file_type: str) -> Optional[str]:
    """
    Validate file size against limits.

    Returns error message if invalid, None if valid.
    """
    from utils.files import format_file_size

    max_size = FILE_SIZE_LIMITS.get(file_type, FILE_SIZE_LIMITS["default"])

    if file_size <= 0:
        return "File is empty"

    if file_size > max_size:
        return f"File too large ({format_file_size(file_size)}). Maximum size is {format_file_size(max_size)}"

    return None


async def _check_duplicate_by_hash(
    file_hash: str,
    table: str = "documents",
) -> Optional[TrackedFile]:
    """
    Check if a file with the same hash already exists.

    Returns existing TrackedFile if duplicate found, None otherwise.
    """
    from db.database import db

    try:
        client = db._get_client()
        response = client.table(table).select("*").eq(
            "file_hash", file_hash
        ).eq(
            "is_deleted", False
        ).limit(1).execute()

        if response.data:
            record = response.data[0]
            storage = get_storage_client()

            # Get fresh signed URL
            url = await storage.get_signed_url(
                record.get("storage_bucket"),
                record.get("storage_key"),
            )

            return TrackedFile(
                file_id=record.get("file_id"),
                storage_provider=record.get("storage_provider"),
                storage_bucket=record.get("storage_bucket"),
                storage_key=record.get("storage_key"),
                original_filename=record.get("original_filename"),
                file_size=record.get("file_size", 0),
                file_type=record.get("file_type", ""),
                file_hash=record.get("file_hash"),
                url=url,
                success=True,
                is_duplicate=True,
            )

        return None

    except Exception as e:
        logger.debug(f"[STORAGE] Duplicate check failed (non-critical): {e}")
        return None


async def store_bo_file(
    data: Union[bytes, BinaryIO, Path],
    filename: str,
    bo_id: int,
    user_id: Optional[str] = None,
    file_type: str = "bo_document",
    content_type: Optional[str] = None,
    skip_duplicate_check: bool = False,
) -> TrackedFile:
    """
    Store a file associated with a BO and track it in the database.

    This is the primary method for storing BO-related files (uploaded documents,
    generated PDFs, etc.). It:
    1. Validates file size
    2. Calculates file hash for integrity
    3. Checks for duplicates (returns existing file if found)
    4. Uploads to storage provider
    5. Records metadata in documents table

    Args:
        data: File contents (bytes, file-like object, or Path to local file)
        filename: Original filename
        bo_id: Associated BO ID
        user_id: User who uploaded (optional)
        file_type: Type of document (e.g., "bo_document", "supporting_doc")
        content_type: MIME type (auto-detected if not provided)
        skip_duplicate_check: If True, skip duplicate detection (for regenerated files)

    Returns:
        TrackedFile with storage info and file_id
    """
    from db.database import db
    from utils.files import calculate_sha256, get_mime_type

    storage = get_storage_client()
    file_id = str(uuid.uuid4())

    # Handle different input types
    if isinstance(data, Path):
        file_bytes = data.read_bytes()
        if not filename:
            filename = data.name
    elif isinstance(data, (bytes, bytearray)):
        file_bytes = bytes(data)
    else:
        # File-like object
        file_bytes = data.read()
        if hasattr(data, 'seek'):
            data.seek(0)

    file_size = len(file_bytes)

    # Validate file size
    size_error = _validate_file_size(file_size, file_type)
    if size_error:
        return TrackedFile(
            file_id=file_id,
            storage_provider=storage.provider_name,
            storage_bucket="",
            storage_key="",
            original_filename=filename,
            file_size=file_size,
            file_type=file_type,
            success=False,
            error=size_error,
        )

    file_hash = calculate_sha256(file_bytes)

    # Check for duplicate (same content already uploaded)
    if not skip_duplicate_check:
        existing = await _check_duplicate_by_hash(file_hash, "documents")
        if existing:
            logger.info(f"[STORAGE] Duplicate BO file detected: {filename} -> existing {existing.file_id}")
            return existing

    if not content_type:
        content_type = get_mime_type(filename)

    # Generate storage key: bo_files/{bo_id}/{file_id}_{filename}
    safe_filename = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)
    storage_key = f"bo_files/{bo_id}/{file_id}_{safe_filename}"
    bucket = StorageType.UPLOADS.value

    try:
        # Upload to storage
        result = await storage.upload(bucket, storage_key, file_bytes, content_type)

        if not result.success:
            return TrackedFile(
                file_id=file_id,
                storage_provider=storage.provider_name,
                storage_bucket=bucket,
                storage_key=storage_key,
                original_filename=filename,
                file_size=file_size,
                file_type=file_type,
                file_hash=file_hash,
                success=False,
                error=result.error or "Upload failed",
            )

        # Track in database
        db.create_document(
            file_id=file_id,
            user_id=user_id,
            original_filename=filename,
            file_type=file_type,
            storage_provider=storage.provider_name,
            storage_bucket=bucket,
            storage_key=storage_key,
            file_size=file_size,
            mime_type=content_type,
            file_hash=file_hash,
            bo_id=bo_id,
        )

        # Get URL
        url = result.file.url if result.file else None
        if not url:
            url = await storage.get_signed_url(bucket, storage_key)

        logger.info(f"[STORAGE] Stored BO file: {filename} -> {storage_key}")

        return TrackedFile(
            file_id=file_id,
            storage_provider=storage.provider_name,
            storage_bucket=bucket,
            storage_key=storage_key,
            original_filename=filename,
            file_size=file_size,
            file_type=file_type,
            file_hash=file_hash,
            url=url,
            success=True,
        )

    except Exception as e:
        logger.error(f"[STORAGE] Failed to store BO file {filename}: {e}")
        return TrackedFile(
            file_id=file_id,
            storage_provider=storage.provider_name,
            storage_bucket=bucket,
            storage_key=storage_key,
            original_filename=filename,
            file_size=file_size,
            file_type=file_type,
            file_hash=file_hash,
            success=False,
            error=str(e),
        )


async def store_proposal_file(
    data: Union[bytes, BinaryIO, Path],
    filename: str,
    user_id: str,
    proposal_id: Optional[int] = None,
    client_name: Optional[str] = None,
    locations_count: Optional[int] = None,
    file_type: str = "proposal_pptx",
    content_type: Optional[str] = None,
    skip_duplicate_check: bool = False,
) -> TrackedFile:
    """
    Store a generated proposal file and track it in the database.

    Args:
        data: File contents
        filename: Filename for the proposal
        user_id: User who generated the proposal (required)
        proposal_id: Associated proposal ID from proposals_log (optional)
        client_name: Client name for the proposal (optional)
        locations_count: Number of locations in proposal (optional)
        file_type: Type (e.g., "proposal_pptx", "proposal_pdf")
        content_type: MIME type
        skip_duplicate_check: If True, skip duplicate detection

    Returns:
        TrackedFile with storage info
    """
    from datetime import datetime

    from db.database import db
    from utils.files import calculate_sha256, get_mime_type

    storage = get_storage_client()
    file_id = str(uuid.uuid4())

    # Handle different input types
    if isinstance(data, Path):
        file_bytes = data.read_bytes()
        if not filename:
            filename = data.name
    elif isinstance(data, (bytes, bytearray)):
        file_bytes = bytes(data)
    else:
        file_bytes = data.read()
        if hasattr(data, 'seek'):
            data.seek(0)

    file_size = len(file_bytes)

    # Validate file size
    size_error = _validate_file_size(file_size, file_type)
    if size_error:
        return TrackedFile(
            file_id=file_id,
            storage_provider=storage.provider_name,
            storage_bucket="",
            storage_key="",
            original_filename=filename,
            file_size=file_size,
            file_type=file_type,
            success=False,
            error=size_error,
        )

    file_hash = calculate_sha256(file_bytes)

    # Check for duplicate
    if not skip_duplicate_check:
        existing = await _check_duplicate_by_hash(file_hash, "proposal_files")
        if existing:
            logger.info(f"[STORAGE] Duplicate proposal file detected: {filename} -> existing {existing.file_id}")
            return existing

    if not content_type:
        content_type = get_mime_type(filename)

    # Generate storage key: proposals/{user_id}/{date}/{file_id}_{filename}
    safe_filename = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)
    date_prefix = datetime.utcnow().strftime("%Y/%m/%d")
    storage_key = f"proposals/{user_id}/{date_prefix}/{file_id}_{safe_filename}"
    bucket = StorageType.PROPOSALS.value

    try:
        result = await storage.upload(bucket, storage_key, file_bytes, content_type)

        if not result.success:
            return TrackedFile(
                file_id=file_id,
                storage_provider=storage.provider_name,
                storage_bucket=bucket,
                storage_key=storage_key,
                original_filename=filename,
                file_size=file_size,
                file_type=file_type,
                file_hash=file_hash,
                success=False,
                error=result.error or "Upload failed",
            )

        # Track in proposal_files table (matches schema)
        client = db._get_client()
        insert_data = {
            "file_id": file_id,
            "user_id": user_id,
            "original_filename": filename,
            "storage_provider": storage.provider_name,
            "storage_bucket": bucket,
            "storage_key": storage_key,
            "file_size": file_size,
            "file_hash": file_hash,
        }
        if proposal_id:
            insert_data["proposal_id"] = proposal_id
        if client_name:
            insert_data["client_name"] = client_name
        if locations_count:
            insert_data["locations_count"] = locations_count

        client.table("proposal_files").insert(insert_data).execute()

        url = result.file.url if result.file else None
        if not url:
            url = await storage.get_signed_url(bucket, storage_key)

        logger.info(f"[STORAGE] Stored proposal file: {filename} -> {storage_key}")

        return TrackedFile(
            file_id=file_id,
            storage_provider=storage.provider_name,
            storage_bucket=bucket,
            storage_key=storage_key,
            original_filename=filename,
            file_size=file_size,
            file_type=file_type,
            file_hash=file_hash,
            url=url,
            success=True,
        )

    except Exception as e:
        logger.error(f"[STORAGE] Failed to store proposal file {filename}: {e}")
        return TrackedFile(
            file_id=file_id,
            storage_provider=storage.provider_name,
            storage_bucket=bucket,
            storage_key=storage_key,
            original_filename=filename,
            file_size=file_size,
            file_type=file_type,
            file_hash=file_hash,
            success=False,
            error=str(e),
        )


async def store_mockup_file(
    data: Union[bytes, BinaryIO, Path],
    filename: str,
    location_key: str,
    time_of_day: str = "day",
    finish: str = "gold",
    file_type: str = "mockup_image",
    content_type: Optional[str] = None,
    user_id: Optional[str] = None,
    mockup_usage_id: Optional[int] = None,
    skip_duplicate_check: bool = False,
) -> TrackedFile:
    """
    Store a generated mockup file and track it in the database.

    Args:
        data: File contents (image bytes)
        filename: Filename for the mockup
        location_key: Location identifier (e.g., "DUBAI_MALL_01")
        time_of_day: "day" or "night"
        finish: Billboard finish (e.g., "gold", "silver")
        file_type: Type (e.g., "mockup_image", "location_photo")
        content_type: MIME type
        user_id: User who created the mockup (optional)
        mockup_usage_id: Reference to mockup_usage table (optional)
        skip_duplicate_check: If True, skip duplicate detection

    Returns:
        TrackedFile with storage info
    """
    from db.database import db
    from utils.files import calculate_sha256, get_mime_type

    storage = get_storage_client()
    file_id = str(uuid.uuid4())

    # Handle different input types
    if isinstance(data, Path):
        file_bytes = data.read_bytes()
        if not filename:
            filename = data.name
    elif isinstance(data, (bytes, bytearray)):
        file_bytes = bytes(data)
    else:
        file_bytes = data.read()
        if hasattr(data, 'seek'):
            data.seek(0)

    file_size = len(file_bytes)

    # Validate file size
    size_error = _validate_file_size(file_size, file_type)
    if size_error:
        return TrackedFile(
            file_id=file_id,
            storage_provider=storage.provider_name,
            storage_bucket="",
            storage_key="",
            original_filename=filename,
            file_size=file_size,
            file_type=file_type,
            success=False,
            error=size_error,
        )

    file_hash = calculate_sha256(file_bytes)

    # Check for duplicate (mockup images with same content)
    if not skip_duplicate_check:
        existing = await _check_duplicate_by_hash(file_hash, "mockup_files")
        if existing:
            logger.info(f"[STORAGE] Duplicate mockup file detected: {filename} -> existing {existing.file_id}")
            return existing

    if not content_type:
        content_type = get_mime_type(filename)

    # Generate storage key: mockups/{location_key}/{time_of_day}/{finish}/{file_id}_{filename}
    safe_filename = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)
    storage_key = f"mockups/{location_key}/{time_of_day}/{finish}/{file_id}_{safe_filename}"
    bucket = StorageType.MOCKUPS.value

    try:
        result = await storage.upload(bucket, storage_key, file_bytes, content_type)

        if not result.success:
            return TrackedFile(
                file_id=file_id,
                storage_provider=storage.provider_name,
                storage_bucket=bucket,
                storage_key=storage_key,
                original_filename=filename,
                file_size=file_size,
                file_type=file_type,
                file_hash=file_hash,
                success=False,
                error=result.error or "Upload failed",
            )

        # Track in mockup_files table (matches schema)
        client = db._get_client()
        insert_data = {
            "file_id": file_id,
            "location_key": location_key,
            "time_of_day": time_of_day,
            "finish": finish,
            "photo_filename": filename,
            "original_filename": filename,
            "storage_provider": storage.provider_name,
            "storage_bucket": bucket,
            "storage_key": storage_key,
            "file_size": file_size,
            "file_hash": file_hash,
        }
        if user_id:
            insert_data["user_id"] = user_id
        if mockup_usage_id:
            insert_data["mockup_usage_id"] = mockup_usage_id

        client.table("mockup_files").insert(insert_data).execute()

        url = result.file.url if result.file else None
        if not url:
            url = await storage.get_signed_url(bucket, storage_key)

        logger.info(f"[STORAGE] Stored mockup file: {filename} -> {storage_key}")

        return TrackedFile(
            file_id=file_id,
            storage_provider=storage.provider_name,
            storage_bucket=bucket,
            storage_key=storage_key,
            original_filename=filename,
            file_size=file_size,
            file_type=file_type,
            file_hash=file_hash,
            url=url,
            success=True,
        )

    except Exception as e:
        logger.error(f"[STORAGE] Failed to store mockup file {filename}: {e}")
        return TrackedFile(
            file_id=file_id,
            storage_provider=storage.provider_name,
            storage_bucket=bucket,
            storage_key=storage_key,
            original_filename=filename,
            file_size=file_size,
            file_type=file_type,
            file_hash=file_hash,
            success=False,
            error=str(e),
        )


async def get_tracked_file(
    file_id: str,
    table: str = "documents",
) -> Optional[TrackedFile]:
    """
    Get a tracked file's info from database.

    Args:
        file_id: The file's UUID
        table: Which table to look in (documents, mockup_files, proposal_files)

    Returns:
        TrackedFile with info or None if not found
    """
    from db.database import db

    try:
        client = db._get_client()
        response = client.table(table).select("*").eq("file_id", file_id).execute()

        if not response.data:
            return None

        record = response.data[0]
        storage = get_storage_client()

        # Get URL
        url = await storage.get_signed_url(
            record.get("storage_bucket"),
            record.get("storage_key"),
        )

        return TrackedFile(
            file_id=record.get("file_id"),
            storage_provider=record.get("storage_provider"),
            storage_bucket=record.get("storage_bucket"),
            storage_key=record.get("storage_key"),
            original_filename=record.get("original_filename"),
            file_size=record.get("file_size", 0),
            file_type=record.get("file_type"),
            file_hash=record.get("file_hash"),
            url=url,
            success=True,
        )

    except Exception as e:
        logger.error(f"[STORAGE] Failed to get tracked file {file_id}: {e}")
        return None


async def download_tracked_file(
    file_id: str,
    table: str = "documents",
) -> Optional[bytes]:
    """
    Download a tracked file's contents.

    Args:
        file_id: The file's UUID
        table: Which table to look in

    Returns:
        File bytes or None if not found
    """
    tracked = await get_tracked_file(file_id, table)
    if not tracked:
        return None

    storage = get_storage_client()
    result = await storage.download(tracked.storage_bucket, tracked.storage_key)

    if result.success:
        return result.data
    return None


async def soft_delete_tracked_file(
    file_id: str,
    table: str = "documents",
) -> bool:
    """
    Soft-delete a tracked file (mark as deleted, keep in storage).

    Args:
        file_id: The file's UUID
        table: Which table to update

    Returns:
        True if deleted
    """
    from datetime import datetime

    from db.database import db

    try:
        client = db._get_client()
        client.table(table).update({
            "is_deleted": True,
            "deleted_at": datetime.utcnow().isoformat(),
        }).eq("file_id", file_id).execute()

        logger.info(f"[STORAGE] Soft-deleted file {file_id} from {table}")
        return True

    except Exception as e:
        logger.error(f"[STORAGE] Failed to soft-delete {file_id}: {e}")
        return False


async def soft_delete_mockup_by_location(
    location_key: str,
    photo_filename: str,
    time_of_day: str = "day",
    finish: str = "gold",
) -> bool:
    """
    Soft-delete a mockup file by location info (for delete_location_photo).

    Args:
        location_key: Location identifier
        photo_filename: Original photo filename
        time_of_day: "day" or "night"
        finish: Billboard finish

    Returns:
        True if deleted
    """
    from datetime import datetime

    from db.database import db

    try:
        client = db._get_client()
        # Find the file by location info
        response = client.table("mockup_files").select("file_id").eq(
            "location_key", location_key
        ).eq(
            "photo_filename", photo_filename
        ).eq(
            "time_of_day", time_of_day
        ).eq(
            "finish", finish
        ).eq(
            "is_deleted", False
        ).execute()

        if not response.data:
            logger.debug(f"[STORAGE] No mockup file found for {location_key}/{photo_filename}")
            return False

        # Soft-delete all matching records (usually just one)
        for record in response.data:
            file_id = record.get("file_id")
            client.table("mockup_files").update({
                "is_deleted": True,
                "deleted_at": datetime.utcnow().isoformat(),
            }).eq("file_id", file_id).execute()
            logger.info(f"[STORAGE] Soft-deleted mockup file {file_id}")

        return True

    except Exception as e:
        logger.error(f"[STORAGE] Failed to soft-delete mockup by location: {e}")
        return False
