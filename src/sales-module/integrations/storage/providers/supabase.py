"""
Supabase Storage provider.

Implements StorageProvider using Supabase Storage (S3-compatible).
Recommended for production deployments already using Supabase.
"""

import base64
import contextlib
import json
import logging
import time
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


class SupabaseStorageProvider(StorageProvider):
    """
    Supabase Storage provider.

    Uses Supabase Storage API for file storage. Supabase Storage is S3-compatible
    and provides built-in support for presigned URLs, public buckets, and RLS policies.

    Usage:
        provider = SupabaseStorageProvider(
            supabase_url="https://xxx.supabase.co",
            supabase_key="service_role_key",
        )

        # Upload a file
        result = await provider.upload("proposals", "2024/proposal.pdf", pdf_bytes)

        # Get signed URL
        url = await provider.get_signed_url("proposals", "2024/proposal.pdf", expires_in=3600)

    Requirements:
        - pip install supabase
        - Buckets created in Supabase dashboard
    """

    def __init__(
        self,
        supabase_url: str | None = None,
        supabase_key: str | None = None,
    ):
        """
        Initialize Supabase storage provider.

        Args:
            supabase_url: Supabase project URL
            supabase_key: Supabase service role key (recommended) or anon key
        """
        self._url = supabase_url
        self._key = supabase_key
        self._client = None

        # Load from settings if not provided
        if not self._url or not self._key:
            self._load_from_settings()

        if not self._url or not self._key:
            raise ValueError("Supabase URL and key are required for SupabaseStorageProvider")

        logger.info(f"[STORAGE:SUPABASE] Provider initialized for {self._url}")

    def _load_from_settings(self):
        """Load configuration from app settings."""
        try:
            from app_settings import settings

            # Try environment-specific config first
            if settings.environment == "production":
                self._url = self._url or settings.salesbot_prod_supabase_url
                self._key = self._key or settings.salesbot_prod_supabase_service_role_key
            else:
                self._url = self._url or settings.salesbot_dev_supabase_url
                self._key = self._key or settings.salesbot_dev_supabase_service_role_key

            # Fall back to legacy config
            self._url = self._url or settings.supabase_url
            self._key = self._key or settings.supabase_service_key

        except Exception as e:
            logger.warning(f"[STORAGE:SUPABASE] Failed to load settings: {e}")

    def _get_client(self):
        """Get or create Supabase client."""
        if self._client is None:
            try:
                from supabase import create_client
                from supabase.lib.client_options import ClientOptions

                # Use longer timeouts (seconds) to handle slow network conditions
                options = ClientOptions(
                    postgrest_client_timeout=30,
                    storage_client_timeout=60,  # Storage operations can be slower
                )
                self._client = create_client(self._url, self._key, options=options)
            except ImportError:
                raise ImportError(
                    "supabase package is required for SupabaseStorageProvider. "
                    "Install with: pip install supabase"
                )
        return self._client

    @property
    def name(self) -> str:
        return "supabase"

    def _storage_file_from_response(
        self,
        bucket: str,
        key: str,
        data: dict[str, Any] | None = None,
    ) -> StorageFile:
        """Create StorageFile from Supabase response."""
        name = Path(key).name

        # Parse metadata from response if available
        size = data.get("metadata", {}).get("size", 0) if data else 0
        content_type = data.get("metadata", {}).get("mimetype", self.get_content_type(name)) if data else self.get_content_type(name)
        created_at = None
        updated_at = None

        if data:
            if "created_at" in data:
                with contextlib.suppress(ValueError, TypeError):
                    created_at = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
            if "updated_at" in data:
                with contextlib.suppress(ValueError, TypeError):
                    updated_at = datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00"))

        # Build public URL
        public_url = f"{self._url}/storage/v1/object/public/{bucket}/{key}"

        return StorageFile(
            key=key,
            bucket=bucket,
            name=name,
            size=size,
            content_type=content_type,
            created_at=created_at,
            updated_at=updated_at,
            url=public_url,
            metadata=data.get("metadata", {}) if data else {},
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
        """Upload data to Supabase Storage."""
        try:
            client = self._get_client()
            key = self.normalize_key(key)

            # Determine content type
            if not content_type:
                content_type = self.get_content_type(key)

            # Get bytes from file-like object if needed
            if hasattr(data, "read"):
                data = data.read()

            # Upload to Supabase Storage
            client.storage.from_(bucket).upload(
                path=key,
                file=data,
                file_options={
                    "content-type": content_type,
                    "upsert": "true",  # Overwrite if exists
                },
            )

            # Create file info
            file_info = self._storage_file_from_response(bucket, key)
            file_info.size = len(data) if isinstance(data, bytes) else 0
            file_info.content_type = content_type

            logger.info(f"[STORAGE:SUPABASE] Uploaded {bucket}/{key} ({file_info.size} bytes)")
            return UploadResult(success=True, file=file_info)

        except Exception as e:
            logger.error(f"[STORAGE:SUPABASE] Upload failed {bucket}/{key}: {e}")
            return UploadResult(success=False, error=str(e))

    async def upload_from_path(
        self,
        bucket: str,
        key: str,
        local_path: str | Path,
        content_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> UploadResult:
        """Upload file from local path to Supabase Storage."""
        try:
            local_path = Path(local_path)
            if not local_path.exists():
                return UploadResult(success=False, error=f"Source file not found: {local_path}")

            data = local_path.read_bytes()

            if not content_type:
                content_type = self.get_content_type(local_path.name)

            return await self.upload(bucket, key, data, content_type, metadata)

        except Exception as e:
            logger.error(f"[STORAGE:SUPABASE] Upload from path failed {bucket}/{key}: {e}")
            return UploadResult(success=False, error=str(e))

    # =========================================================================
    # DOWNLOAD OPERATIONS
    # =========================================================================

    async def download(
        self,
        bucket: str,
        key: str,
    ) -> DownloadResult:
        """Download file contents from Supabase Storage."""
        try:
            client = self._get_client()
            key = self.normalize_key(key)

            # Download from Supabase Storage
            response = client.storage.from_(bucket).download(key)

            file_info = self._storage_file_from_response(bucket, key)
            file_info.size = len(response)

            logger.debug(f"[STORAGE:SUPABASE] Downloaded {bucket}/{key}")
            return DownloadResult(success=True, data=response, file=file_info)

        except Exception as e:
            logger.error(f"[STORAGE:SUPABASE] Download failed {bucket}/{key}: {e}")
            return DownloadResult(success=False, error=str(e))

    async def download_to_path(
        self,
        bucket: str,
        key: str,
        local_path: str | Path,
    ) -> DownloadResult:
        """Download file to local filesystem."""
        try:
            result = await self.download(bucket, key)

            if not result.success:
                return result

            dest_path = Path(local_path)
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(result.data)

            logger.debug(f"[STORAGE:SUPABASE] Downloaded {bucket}/{key} to {local_path}")
            return DownloadResult(success=True, file=result.file)

        except Exception as e:
            logger.error(f"[STORAGE:SUPABASE] Download to path failed {bucket}/{key}: {e}")
            return DownloadResult(success=False, error=str(e))

    # =========================================================================
    # FILE OPERATIONS
    # =========================================================================

    async def delete(
        self,
        bucket: str,
        key: str,
    ) -> bool:
        """Delete a file from Supabase Storage."""
        try:
            client = self._get_client()
            key = self.normalize_key(key)

            client.storage.from_(bucket).remove([key])

            logger.info(f"[STORAGE:SUPABASE] Deleted {bucket}/{key}")
            return True

        except Exception as e:
            logger.error(f"[STORAGE:SUPABASE] Delete failed {bucket}/{key}: {e}")
            return False

    async def exists(
        self,
        bucket: str,
        key: str,
    ) -> bool:
        """Check if a file exists in Supabase Storage."""
        try:
            client = self._get_client()
            key = self.normalize_key(key)

            # Try to get file info via list with exact path
            # Supabase doesn't have a direct "exists" endpoint
            parent_path = str(Path(key).parent)
            if parent_path == ".":
                parent_path = ""

            response = client.storage.from_(bucket).list(parent_path)

            filename = Path(key).name
            return any(item.get("name") == filename for item in response)

        except Exception as e:
            logger.error(f"[STORAGE:SUPABASE] Exists check failed {bucket}/{key}: {e}")
            return False

    async def get_file_info(
        self,
        bucket: str,
        key: str,
    ) -> StorageFile | None:
        """Get file metadata from Supabase Storage."""
        try:
            client = self._get_client()
            key = self.normalize_key(key)

            # Get file info via list
            parent_path = str(Path(key).parent)
            if parent_path == ".":
                parent_path = ""

            response = client.storage.from_(bucket).list(parent_path)

            filename = Path(key).name
            for item in response:
                if item.get("name") == filename:
                    return self._storage_file_from_response(bucket, key, item)

            return None

        except Exception as e:
            logger.error(f"[STORAGE:SUPABASE] Get file info failed {bucket}/{key}: {e}")
            return None

    async def list_files(
        self,
        bucket: str,
        prefix: str | None = None,
        limit: int = 100,
        continuation_token: str | None = None,
    ) -> ListResult:
        """List files in a Supabase Storage bucket."""
        try:
            client = self._get_client()

            # Supabase list options
            options = {
                "limit": limit,
            }

            if continuation_token:
                options["offset"] = int(continuation_token)

            path = self.normalize_key(prefix) if prefix else ""
            response = client.storage.from_(bucket).list(path, options)

            files = []
            for item in response:
                if item.get("id"):  # It's a file, not a folder
                    file_key = f"{path}/{item['name']}" if path else item["name"]
                    files.append(self._storage_file_from_response(bucket, file_key, item))

            # Calculate next token
            offset = int(continuation_token) if continuation_token else 0
            next_token = str(offset + limit) if len(response) == limit else None

            return ListResult(
                success=True,
                files=files,
                total=len(files),  # Supabase doesn't return total count
                continuation_token=next_token,
            )

        except Exception as e:
            logger.error(f"[STORAGE:SUPABASE] List files failed {bucket}: {e}")
            return ListResult(success=False, error=str(e))

    async def copy(
        self,
        source_bucket: str,
        source_key: str,
        dest_bucket: str,
        dest_key: str,
    ) -> UploadResult:
        """Copy a file within Supabase Storage."""
        try:
            self._get_client()
            source_key = self.normalize_key(source_key)
            dest_key = self.normalize_key(dest_key)

            # Supabase doesn't have native copy - download and reupload
            result = await self.download(source_bucket, source_key)
            if not result.success:
                return UploadResult(success=False, error=f"Source not found: {source_bucket}/{source_key}")

            return await self.upload(
                dest_bucket,
                dest_key,
                result.data,
                result.file.content_type if result.file else None,
            )

        except Exception as e:
            logger.error(f"[STORAGE:SUPABASE] Copy failed: {e}")
            return UploadResult(success=False, error=str(e))

    async def move(
        self,
        source_bucket: str,
        source_key: str,
        dest_bucket: str,
        dest_key: str,
    ) -> UploadResult:
        """Move a file within Supabase Storage."""
        try:
            client = self._get_client()
            source_key = self.normalize_key(source_key)
            dest_key = self.normalize_key(dest_key)

            if source_bucket == dest_bucket:
                # Same bucket - use move
                client.storage.from_(source_bucket).move(source_key, dest_key)
                file_info = self._storage_file_from_response(dest_bucket, dest_key)
                logger.info(f"[STORAGE:SUPABASE] Moved {source_bucket}/{source_key} to {dest_key}")
                return UploadResult(success=True, file=file_info)
            else:
                # Different buckets - copy then delete
                result = await self.copy(source_bucket, source_key, dest_bucket, dest_key)
                if result.success:
                    await self.delete(source_bucket, source_key)
                return result

        except Exception as e:
            logger.error(f"[STORAGE:SUPABASE] Move failed: {e}")
            return UploadResult(success=False, error=str(e))

    # =========================================================================
    # URL OPERATIONS
    # =========================================================================

    async def get_public_url(
        self,
        bucket: str,
        key: str,
    ) -> str | None:
        """Get public URL for a file (if bucket is public)."""
        try:
            client = self._get_client()
            key = self.normalize_key(key)

            response = client.storage.from_(bucket).get_public_url(key)
            return response

        except Exception as e:
            logger.error(f"[STORAGE:SUPABASE] Get public URL failed {bucket}/{key}: {e}")
            return None

    def _decode_jwt_claims(self, token: str) -> dict | None:
        """Decode JWT claims without verification (for debugging)."""
        try:
            # JWT format: header.payload.signature
            parts = token.split(".")
            if len(parts) != 3:
                return None
            # Decode payload (add padding if needed)
            payload = parts[1]
            padding = 4 - len(payload) % 4
            if padding != 4:
                payload += "=" * padding
            decoded = base64.urlsafe_b64decode(payload)
            return json.loads(decoded)
        except Exception:
            return None

    async def get_signed_url(
        self,
        bucket: str,
        key: str,
        expires_in: int = 3600,
    ) -> str | None:
        """Get signed URL for temporary access."""
        try:
            import datetime

            # STEP 1: Log system time BEFORE API call
            time_before_call = time.time()
            dt_before = datetime.datetime.fromtimestamp(time_before_call, tz=datetime.timezone.utc)
            logger.info(f"[STORAGE:SUPABASE] ========== SIGNED URL REQUEST START ==========")
            logger.info(f"[STORAGE:SUPABASE] System time BEFORE call: {time_before_call} ({dt_before.isoformat()})")
            logger.info(f"[STORAGE:SUPABASE] Bucket: {bucket}, Key: {key}")
            logger.info(f"[STORAGE:SUPABASE] Requested expires_in: {expires_in}s ({expires_in/3600:.1f} hours)")
            logger.info(f"[STORAGE:SUPABASE] Supabase URL: {self._url}")
            logger.info(f"[STORAGE:SUPABASE] Service key prefix: {self._key[:20]}...")

            client = self._get_client()
            key = self.normalize_key(key)

            # STEP 2: Make API call and measure time
            logger.info(f"[STORAGE:SUPABASE] Calling Supabase create_signed_url API...")
            response = client.storage.from_(bucket).create_signed_url(key, expires_in)

            time_after_call = time.time()
            dt_after = datetime.datetime.fromtimestamp(time_after_call, tz=datetime.timezone.utc)
            api_duration = time_after_call - time_before_call
            logger.info(f"[STORAGE:SUPABASE] System time AFTER call: {time_after_call} ({dt_after.isoformat()})")
            logger.info(f"[STORAGE:SUPABASE] API call took: {api_duration:.3f}s")
            logger.info(f"[STORAGE:SUPABASE] Raw response: {response}")

            signed_url = None
            if response and "signedURL" in response:
                signed_url = response["signedURL"]
            elif response and "signedUrl" in response:
                signed_url = response["signedUrl"]

            if signed_url:
                logger.info(f"[STORAGE:SUPABASE] Signed URL generated (length: {len(signed_url)})")

                # STEP 3: Decode and analyze JWT token
                if "token=" in signed_url:
                    token = signed_url.split("token=")[1].split("&")[0]
                    logger.info(f"[STORAGE:SUPABASE] Extracted JWT token (length: {len(token)})")

                    claims = self._decode_jwt_claims(token)
                    if claims:
                        logger.info(f"[STORAGE:SUPABASE] ===== JWT TOKEN ANALYSIS =====")
                        logger.info(f"[STORAGE:SUPABASE] Full JWT claims: {json.dumps(claims, indent=2)}")

                        now = int(time.time())
                        exp = claims.get("exp", 0)
                        iat = claims.get("iat", 0)  # issued at time

                        time_until_exp = exp - now
                        time_since_issued = now - iat if iat else None
                        expected_exp = int(time_before_call) + expires_in
                        exp_drift = exp - expected_exp

                        dt_exp = datetime.datetime.fromtimestamp(exp, tz=datetime.timezone.utc)
                        dt_iat = datetime.datetime.fromtimestamp(iat, tz=datetime.timezone.utc) if iat else None

                        logger.info(f"[STORAGE:SUPABASE] Current server time: {now} ({datetime.datetime.fromtimestamp(now, tz=datetime.timezone.utc).isoformat()})")
                        logger.info(f"[STORAGE:SUPABASE] Token issued at (iat): {iat} ({dt_iat.isoformat() if dt_iat else 'N/A'})")
                        logger.info(f"[STORAGE:SUPABASE] Token expires at (exp): {exp} ({dt_exp.isoformat()})")
                        logger.info(f"[STORAGE:SUPABASE] Time until expiry: {time_until_exp}s ({time_until_exp/3600:.2f} hours)")

                        if time_since_issued is not None:
                            logger.info(f"[STORAGE:SUPABASE] Time since token issued: {time_since_issued}s")

                        logger.info(f"[STORAGE:SUPABASE] Expected exp (server_time + {expires_in}): {expected_exp}")
                        logger.info(f"[STORAGE:SUPABASE] Actual exp drift from expected: {exp_drift}s")

                        if time_until_exp < 0:
                            logger.error(f"[STORAGE:SUPABASE] ❌ TOKEN ALREADY EXPIRED!")
                            logger.error(f"[STORAGE:SUPABASE] Token expired {abs(time_until_exp)}s ago")
                            logger.error(f"[STORAGE:SUPABASE] This suggests CLOCK SKEW between your server and Supabase")
                        elif time_until_exp < 60:
                            logger.warning(f"[STORAGE:SUPABASE] ⚠️ Token expires in less than 60s!")
                        elif abs(exp_drift) > 300:  # More than 5 min drift
                            logger.warning(f"[STORAGE:SUPABASE] ⚠️ Large drift ({exp_drift}s) between expected and actual expiry")
                        else:
                            logger.info(f"[STORAGE:SUPABASE] ✅ Token appears valid and will expire in {time_until_exp/3600:.2f} hours")
                    else:
                        logger.warning(f"[STORAGE:SUPABASE] Failed to decode JWT claims")
                else:
                    logger.warning(f"[STORAGE:SUPABASE] No token parameter found in signed URL")

                logger.info(f"[STORAGE:SUPABASE] ========== SIGNED URL REQUEST END ==========")
                return signed_url

            if response and "error" in response:
                logger.error(f"[STORAGE:SUPABASE] Error from Supabase: {response.get('error')}")

            logger.warning(f"[STORAGE:SUPABASE] Unexpected response format: {response}")
            logger.info(f"[STORAGE:SUPABASE] ========== SIGNED URL REQUEST END (FAILED) ==========")
            return None

        except Exception as e:
            logger.error(f"[STORAGE:SUPABASE] Get signed URL failed {bucket}/{key}: {e}", exc_info=True)
            logger.info(f"[STORAGE:SUPABASE] ========== SIGNED URL REQUEST END (EXCEPTION) ==========")
            return None

    # =========================================================================
    # BUCKET OPERATIONS
    # =========================================================================

    async def ensure_bucket(
        self,
        bucket: str,
        public: bool = False,
    ) -> bool:
        """Ensure a bucket exists in Supabase Storage."""
        try:
            client = self._get_client()

            # Try to create bucket (will fail if exists, which is fine)
            try:
                client.storage.create_bucket(
                    bucket,
                    options={
                        "public": public,
                    }
                )
                logger.info(f"[STORAGE:SUPABASE] Created bucket: {bucket}")
            except Exception as e:
                # Bucket likely already exists
                if "already exists" not in str(e).lower():
                    logger.debug(f"[STORAGE:SUPABASE] Bucket exists or error: {bucket} - {e}")

            return True

        except Exception as e:
            logger.error(f"[STORAGE:SUPABASE] Ensure bucket failed {bucket}: {e}")
            return False

    async def list_buckets(self) -> list[str]:
        """List all buckets in Supabase Storage."""
        try:
            client = self._get_client()
            response = client.storage.list_buckets()

            return [b.name for b in response] if response else []

        except Exception as e:
            logger.error(f"[STORAGE:SUPABASE] List buckets failed: {e}")
            return []
