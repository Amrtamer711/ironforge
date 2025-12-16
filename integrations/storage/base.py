"""
Abstract base class for storage providers.

Each provider implements their own storage-specific operations.
Follows the same pattern as integrations/auth/base.py and integrations/llm/base.py.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, BinaryIO, Optional, Union


class StorageType(str, Enum):
    """Storage bucket types."""
    PROPOSALS = "proposals"
    MOCKUPS = "mockups"
    UPLOADS = "uploads"
    TEMPLATES = "templates"
    TEMP = "temp"


@dataclass
class StorageFile:
    """
    Platform-agnostic stored file representation.

    Similar to other platform-agnostic dataclasses in the integrations layer.
    """
    key: str  # Full path/key in storage
    bucket: str  # Bucket/container name
    name: str  # File name only
    size: int  # Size in bytes
    content_type: str  # MIME type
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    # URLs
    url: Optional[str] = None  # Public URL if available
    signed_url: Optional[str] = None  # Presigned URL for temporary access

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "key": self.key,
            "bucket": self.bucket,
            "name": self.name,
            "size": self.size,
            "content_type": self.content_type,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "metadata": self.metadata,
            "url": self.url,
            "signed_url": self.signed_url,
        }


@dataclass
class UploadResult:
    """Result from upload operations."""
    success: bool
    file: Optional[StorageFile] = None
    error: Optional[str] = None


@dataclass
class DownloadResult:
    """Result from download operations."""
    success: bool
    data: Optional[bytes] = None
    file: Optional[StorageFile] = None
    error: Optional[str] = None


@dataclass
class ListResult:
    """Result from list operations."""
    success: bool
    files: list[StorageFile] = field(default_factory=list)
    total: int = 0
    continuation_token: Optional[str] = None  # For pagination
    error: Optional[str] = None


class StorageProvider(ABC):
    """
    Abstract base class for storage providers.

    Each provider (Local, Supabase Storage, S3, etc.) implements this interface
    with their own storage-specific operations.

    Pattern follows:
    - integrations/auth/base.py (AuthProvider)
    - integrations/llm/base.py (LLMProvider)
    - integrations/channels/base.py (ChannelAdapter)
    - db/base.py (DatabaseBackend)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'local', 'supabase', 's3')."""
        pass

    # =========================================================================
    # UPLOAD OPERATIONS
    # =========================================================================

    @abstractmethod
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
        pass

    @abstractmethod
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
        pass

    # =========================================================================
    # DOWNLOAD OPERATIONS
    # =========================================================================

    @abstractmethod
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
        pass

    @abstractmethod
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
        pass

    # =========================================================================
    # FILE OPERATIONS
    # =========================================================================

    @abstractmethod
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
        pass

    @abstractmethod
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
        pass

    @abstractmethod
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
        pass

    @abstractmethod
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
        pass

    @abstractmethod
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
        pass

    @abstractmethod
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
        pass

    # =========================================================================
    # URL OPERATIONS
    # =========================================================================

    @abstractmethod
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
        pass

    @abstractmethod
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
            expires_in: URL expiration time in seconds

        Returns:
            Presigned URL or None if failed
        """
        pass

    # =========================================================================
    # BUCKET OPERATIONS
    # =========================================================================

    @abstractmethod
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
        pass

    @abstractmethod
    async def list_buckets(self) -> list[str]:
        """
        List all available buckets.

        Returns:
            List of bucket names
        """
        pass

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def get_content_type(self, filename: str) -> str:
        """
        Determine MIME type from filename.

        Args:
            filename: File name with extension

        Returns:
            MIME type string
        """
        import mimetypes
        content_type, _ = mimetypes.guess_type(filename)
        return content_type or "application/octet-stream"

    def normalize_key(self, key: str) -> str:
        """
        Normalize a storage key to consistent format.

        Removes leading slashes, converts backslashes.

        Args:
            key: File key/path

        Returns:
            Normalized key
        """
        # Convert backslashes to forward slashes
        key = key.replace("\\", "/")
        # Remove leading slashes
        key = key.lstrip("/")
        return key
