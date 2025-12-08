"""
Unified Storage Client.

Provides a single interface to interact with any storage provider.
Follows the same pattern as integrations/auth/client.py (AuthClient).
"""

import logging
from pathlib import Path
from typing import Any, BinaryIO, Dict, List, Optional, Union

from integrations.storage.base import (
    StorageProvider,
    StorageFile,
    StorageType,
    UploadResult,
    DownloadResult,
    ListResult,
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
        metadata: Optional[Dict[str, Any]] = None,
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
        metadata: Optional[Dict[str, Any]] = None,
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

    async def list_buckets(self) -> List[str]:
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
