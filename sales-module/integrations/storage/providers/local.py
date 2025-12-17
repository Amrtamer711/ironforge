"""
Local filesystem storage provider.

Implements StorageProvider using local filesystem for storage.
Useful for development and self-hosted deployments.
"""

import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO

from integrations.storage.base import (
    DownloadResult,
    ListResult,
    StorageFile,
    StorageProvider,
    UploadResult,
)

logger = logging.getLogger("proposal-bot")


class LocalStorageProvider(StorageProvider):
    """
    Local filesystem storage provider.

    Stores files in a configurable base directory, organized by buckets (subdirectories).

    Usage:
        provider = LocalStorageProvider(base_path="/data/storage")

        # Upload a file
        result = await provider.upload("proposals", "2024/proposal.pdf", pdf_bytes)

        # Download a file
        result = await provider.download("proposals", "2024/proposal.pdf")

        # Get URL (returns local file:// URL or API route path)
        url = await provider.get_public_url("proposals", "2024/proposal.pdf")
    """

    def __init__(
        self,
        base_path: str | Path | None = None,
        url_prefix: str | None = None,
    ):
        """
        Initialize local storage provider.

        Args:
            base_path: Base directory for storage (defaults to DATA_DIR/storage)
            url_prefix: URL prefix for generating public URLs (e.g., "/api/files")
        """
        if base_path:
            self._base_path = Path(base_path)
        else:
            # Default to data_dir/storage from settings, or local data/storage
            try:
                from app_settings import settings
                if settings.data_dir:
                    self._base_path = Path(settings.data_dir) / "storage"
                elif os.path.exists("/data/"):
                    # Production environment
                    self._base_path = Path("/data/storage")
                else:
                    # Development: use local data/storage relative to project root
                    self._base_path = Path(__file__).parent.parent.parent.parent / "data" / "storage"
            except ImportError:
                # Settings not available, use sensible default
                if os.path.exists("/data/"):
                    self._base_path = Path("/data/storage")
                else:
                    self._base_path = Path(__file__).parent.parent.parent.parent / "data" / "storage"

        self._url_prefix = url_prefix or "/api/files"

        # Ensure base directory exists
        self._base_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"[STORAGE:LOCAL] Provider initialized at {self._base_path}")

    @property
    def name(self) -> str:
        return "local"

    def _get_full_path(self, bucket: str, key: str) -> Path:
        """Get full filesystem path for a bucket/key."""
        key = self.normalize_key(key)
        return self._base_path / bucket / key

    def _get_file_info(self, path: Path, bucket: str, key: str) -> StorageFile:
        """Create StorageFile from filesystem path."""
        stat = path.stat()
        return StorageFile(
            key=key,
            bucket=bucket,
            name=path.name,
            size=stat.st_size,
            content_type=self.get_content_type(path.name),
            created_at=datetime.fromtimestamp(stat.st_ctime),
            updated_at=datetime.fromtimestamp(stat.st_mtime),
            url=f"{self._url_prefix}/{bucket}/{key}",
        )

    # =========================================================================
    # UPLOAD OPERATIONS
    # =========================================================================

    async def upload(
        self,
        bucket: str,
        key: str,
        data: bytes | BinaryIO,
        content_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> UploadResult:
        """Upload data to local storage."""
        try:
            full_path = self._get_full_path(bucket, key)

            # Ensure parent directory exists
            full_path.parent.mkdir(parents=True, exist_ok=True)

            # Write data
            if isinstance(data, bytes):
                full_path.write_bytes(data)
            else:
                # File-like object
                with open(full_path, "wb") as f:
                    shutil.copyfileobj(data, f)

            file_info = self._get_file_info(full_path, bucket, self.normalize_key(key))

            logger.info(f"[STORAGE:LOCAL] Uploaded {bucket}/{key} ({file_info.size} bytes)")
            return UploadResult(success=True, file=file_info)

        except Exception as e:
            logger.error(f"[STORAGE:LOCAL] Upload failed {bucket}/{key}: {e}")
            return UploadResult(success=False, error=str(e))

    async def upload_from_path(
        self,
        bucket: str,
        key: str,
        local_path: str | Path,
        content_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> UploadResult:
        """Upload file from local path to storage."""
        try:
            source_path = Path(local_path)
            if not source_path.exists():
                return UploadResult(success=False, error=f"Source file not found: {local_path}")

            full_path = self._get_full_path(bucket, key)

            # Ensure parent directory exists
            full_path.parent.mkdir(parents=True, exist_ok=True)

            # Copy file
            shutil.copy2(source_path, full_path)

            file_info = self._get_file_info(full_path, bucket, self.normalize_key(key))

            logger.info(f"[STORAGE:LOCAL] Uploaded from path {bucket}/{key}")
            return UploadResult(success=True, file=file_info)

        except Exception as e:
            logger.error(f"[STORAGE:LOCAL] Upload from path failed {bucket}/{key}: {e}")
            return UploadResult(success=False, error=str(e))

    # =========================================================================
    # DOWNLOAD OPERATIONS
    # =========================================================================

    async def download(
        self,
        bucket: str,
        key: str,
    ) -> DownloadResult:
        """Download file contents from storage."""
        try:
            full_path = self._get_full_path(bucket, key)

            if not full_path.exists():
                return DownloadResult(success=False, error=f"File not found: {bucket}/{key}")

            data = full_path.read_bytes()
            file_info = self._get_file_info(full_path, bucket, self.normalize_key(key))

            logger.debug(f"[STORAGE:LOCAL] Downloaded {bucket}/{key}")
            return DownloadResult(success=True, data=data, file=file_info)

        except Exception as e:
            logger.error(f"[STORAGE:LOCAL] Download failed {bucket}/{key}: {e}")
            return DownloadResult(success=False, error=str(e))

    async def download_to_path(
        self,
        bucket: str,
        key: str,
        local_path: str | Path,
    ) -> DownloadResult:
        """Download file to local filesystem."""
        try:
            source_path = self._get_full_path(bucket, key)

            if not source_path.exists():
                return DownloadResult(success=False, error=f"File not found: {bucket}/{key}")

            dest_path = Path(local_path)

            # Ensure parent directory exists
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            # Copy file
            shutil.copy2(source_path, dest_path)

            file_info = self._get_file_info(source_path, bucket, self.normalize_key(key))

            logger.debug(f"[STORAGE:LOCAL] Downloaded {bucket}/{key} to {local_path}")
            return DownloadResult(success=True, file=file_info)

        except Exception as e:
            logger.error(f"[STORAGE:LOCAL] Download to path failed {bucket}/{key}: {e}")
            return DownloadResult(success=False, error=str(e))

    # =========================================================================
    # FILE OPERATIONS
    # =========================================================================

    async def delete(
        self,
        bucket: str,
        key: str,
    ) -> bool:
        """Delete a file from storage."""
        try:
            full_path = self._get_full_path(bucket, key)

            if not full_path.exists():
                logger.warning(f"[STORAGE:LOCAL] Delete: file not found {bucket}/{key}")
                return False

            full_path.unlink()
            logger.info(f"[STORAGE:LOCAL] Deleted {bucket}/{key}")
            return True

        except Exception as e:
            logger.error(f"[STORAGE:LOCAL] Delete failed {bucket}/{key}: {e}")
            return False

    async def exists(
        self,
        bucket: str,
        key: str,
    ) -> bool:
        """Check if a file exists."""
        full_path = self._get_full_path(bucket, key)
        return full_path.exists() and full_path.is_file()

    async def get_file_info(
        self,
        bucket: str,
        key: str,
    ) -> StorageFile | None:
        """Get file metadata without downloading."""
        try:
            full_path = self._get_full_path(bucket, key)

            if not full_path.exists():
                return None

            return self._get_file_info(full_path, bucket, self.normalize_key(key))

        except Exception as e:
            logger.error(f"[STORAGE:LOCAL] Get file info failed {bucket}/{key}: {e}")
            return None

    async def list_files(
        self,
        bucket: str,
        prefix: str | None = None,
        limit: int = 100,
        continuation_token: str | None = None,
    ) -> ListResult:
        """List files in a bucket with optional prefix filtering."""
        try:
            bucket_path = self._base_path / bucket

            if not bucket_path.exists():
                return ListResult(success=True, files=[], total=0)

            files = []
            search_path = bucket_path / prefix if prefix else bucket_path

            # Get all files recursively
            all_files = list(search_path.rglob("*") if search_path.exists() else [])
            all_files = [f for f in all_files if f.is_file()]

            # Sort by modification time (newest first)
            all_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

            total = len(all_files)

            # Handle pagination via continuation_token (simple offset-based)
            offset = int(continuation_token) if continuation_token else 0
            page_files = all_files[offset:offset + limit]

            for file_path in page_files:
                # Get key relative to bucket
                key = str(file_path.relative_to(bucket_path))
                files.append(self._get_file_info(file_path, bucket, key))

            # Next continuation token
            next_token = None
            if offset + limit < total:
                next_token = str(offset + limit)

            return ListResult(
                success=True,
                files=files,
                total=total,
                continuation_token=next_token,
            )

        except Exception as e:
            logger.error(f"[STORAGE:LOCAL] List files failed {bucket}: {e}")
            return ListResult(success=False, error=str(e))

    async def copy(
        self,
        source_bucket: str,
        source_key: str,
        dest_bucket: str,
        dest_key: str,
    ) -> UploadResult:
        """Copy a file within storage."""
        try:
            source_path = self._get_full_path(source_bucket, source_key)
            dest_path = self._get_full_path(dest_bucket, dest_key)

            if not source_path.exists():
                return UploadResult(success=False, error=f"Source not found: {source_bucket}/{source_key}")

            # Ensure parent directory exists
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            # Copy file
            shutil.copy2(source_path, dest_path)

            file_info = self._get_file_info(dest_path, dest_bucket, self.normalize_key(dest_key))

            logger.info(f"[STORAGE:LOCAL] Copied {source_bucket}/{source_key} to {dest_bucket}/{dest_key}")
            return UploadResult(success=True, file=file_info)

        except Exception as e:
            logger.error(f"[STORAGE:LOCAL] Copy failed: {e}")
            return UploadResult(success=False, error=str(e))

    async def move(
        self,
        source_bucket: str,
        source_key: str,
        dest_bucket: str,
        dest_key: str,
    ) -> UploadResult:
        """Move a file within storage."""
        try:
            source_path = self._get_full_path(source_bucket, source_key)
            dest_path = self._get_full_path(dest_bucket, dest_key)

            if not source_path.exists():
                return UploadResult(success=False, error=f"Source not found: {source_bucket}/{source_key}")

            # Ensure parent directory exists
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            # Move file
            shutil.move(str(source_path), str(dest_path))

            file_info = self._get_file_info(dest_path, dest_bucket, self.normalize_key(dest_key))

            logger.info(f"[STORAGE:LOCAL] Moved {source_bucket}/{source_key} to {dest_bucket}/{dest_key}")
            return UploadResult(success=True, file=file_info)

        except Exception as e:
            logger.error(f"[STORAGE:LOCAL] Move failed: {e}")
            return UploadResult(success=False, error=str(e))

    # =========================================================================
    # URL OPERATIONS
    # =========================================================================

    async def get_public_url(
        self,
        bucket: str,
        key: str,
    ) -> str | None:
        """Get URL for file access."""
        key = self.normalize_key(key)

        # Check file exists
        full_path = self._get_full_path(bucket, key)
        if not full_path.exists():
            return None

        # Return API route URL
        return f"{self._url_prefix}/{bucket}/{key}"

    async def get_signed_url(
        self,
        bucket: str,
        key: str,
        expires_in: int = 3600,
    ) -> str | None:
        """
        Get signed URL for file access.

        Note: Local storage doesn't support true signed URLs.
        Returns the same as get_public_url for compatibility.
        For production, use Supabase or S3 provider.
        """
        return await self.get_public_url(bucket, key)

    # =========================================================================
    # BUCKET OPERATIONS
    # =========================================================================

    async def ensure_bucket(
        self,
        bucket: str,
        public: bool = False,
    ) -> bool:
        """Ensure a bucket (directory) exists."""
        try:
            bucket_path = self._base_path / bucket
            bucket_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"[STORAGE:LOCAL] Ensured bucket: {bucket}")
            return True
        except Exception as e:
            logger.error(f"[STORAGE:LOCAL] Ensure bucket failed {bucket}: {e}")
            return False

    async def list_buckets(self) -> list[str]:
        """List all buckets (directories)."""
        try:
            buckets = []
            for item in self._base_path.iterdir():
                if item.is_dir():
                    buckets.append(item.name)
            return sorted(buckets)
        except Exception as e:
            logger.error(f"[STORAGE:LOCAL] List buckets failed: {e}")
            return []
