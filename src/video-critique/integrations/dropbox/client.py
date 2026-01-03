"""
Dropbox API Client for Video Critique.

Provides async-compatible Dropbox operations with automatic
token refresh and error handling.
"""

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import dropbox
import requests

from core.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class UploadResult:
    """Result of a file upload operation."""
    success: bool
    path: str = ""
    error: str = ""
    metadata: dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class SearchResult:
    """Result of a file search operation."""
    found: bool
    files: list[dict] = None
    error: str = ""

    def __post_init__(self):
        if self.files is None:
            self.files = []


@dataclass
class SharedLinkResult:
    """Result of a shared link operation."""
    success: bool
    url: str = ""
    error: str = ""


class DropboxClient:
    """
    Dropbox API client with automatic token refresh.

    Handles OAuth2 token refresh and provides clean async interface
    for Dropbox operations.
    """

    def __init__(
        self,
        refresh_token: str,
        app_key: str,
        app_secret: str,
        credentials_path: Path | None = None,
    ):
        """
        Initialize Dropbox client.

        Args:
            refresh_token: OAuth2 refresh token
            app_key: Dropbox app key (client ID)
            app_secret: Dropbox app secret (client secret)
            credentials_path: Optional path to store updated tokens
        """
        self._refresh_token = refresh_token
        self._app_key = app_key
        self._app_secret = app_secret
        self._credentials_path = credentials_path
        self._client: dropbox.Dropbox | None = None

    @classmethod
    def from_config(cls) -> "DropboxClient":
        """
        Create a DropboxClient from config.py settings.

        Falls back to credentials file if env vars not set.

        Returns:
            Configured DropboxClient instance
        """
        import config

        # Try environment variables first
        refresh_token = getattr(config, "DROPBOX_REFRESH_TOKEN", "")
        app_key = getattr(config, "DROPBOX_APP_KEY", "")
        app_secret = getattr(config, "DROPBOX_APP_SECRET", "")
        credentials_path = getattr(config, "DROPBOX_CREDENTIALS_PATH", None)

        # Fall back to credentials file
        if not all([refresh_token, app_key, app_secret]) and credentials_path:
            try:
                creds = cls._load_credentials(credentials_path)
                refresh_token = refresh_token or creds.get("refresh_token", "")
                app_key = app_key or creds.get("client_id", "")
                app_secret = app_secret or creds.get("client_secret", "")
            except Exception as e:
                logger.warning(f"[Dropbox] Failed to load credentials file: {e}")

        if not all([refresh_token, app_key, app_secret]):
            raise ValueError(
                "Dropbox credentials not configured. "
                "Set DROPBOX_REFRESH_TOKEN, DROPBOX_APP_KEY, DROPBOX_APP_SECRET"
            )

        return cls(
            refresh_token=refresh_token,
            app_key=app_key,
            app_secret=app_secret,
            credentials_path=credentials_path,
        )

    @staticmethod
    def _load_credentials(path: Path) -> dict:
        """Load credentials from JSON file."""
        with open(path) as f:
            return json.load(f)

    def _save_credentials(self, access_token: str) -> None:
        """Save updated access token to credentials file."""
        if not self._credentials_path:
            return

        try:
            creds = self._load_credentials(self._credentials_path)
            creds["access_token"] = access_token
            with open(self._credentials_path, "w") as f:
                json.dump(creds, f, indent=2)
            logger.debug("[Dropbox] Saved updated access token")
        except Exception as e:
            logger.warning(f"[Dropbox] Failed to save credentials: {e}")

    def _get_client(self) -> dropbox.Dropbox:
        """Get or create Dropbox client with automatic token refresh."""
        if self._client is not None:
            return self._client

        try:
            # Use SDK-managed token refresh
            self._client = dropbox.Dropbox(
                oauth2_access_token=None,
                oauth2_refresh_token=self._refresh_token,
                app_key=self._app_key,
                app_secret=self._app_secret,
            )
            # Verify connection
            self._client.users_get_current_account()
            logger.info("[Dropbox] Client initialized with SDK-managed refresh")
            return self._client

        except Exception as e:
            logger.warning(f"[Dropbox] SDK init failed ({e}), trying manual refresh")
            # Fall back to manual token refresh
            access_token = self._refresh_access_token()
            self._client = dropbox.Dropbox(access_token)
            return self._client

    def _refresh_access_token(self) -> str:
        """Manually refresh the access token."""
        response = requests.post(
            "https://api.dropbox.com/oauth2/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
                "client_id": self._app_key,
                "client_secret": self._app_secret,
            },
        )

        if response.status_code != 200:
            raise Exception(f"Token refresh failed: {response.text}")

        access_token = response.json()["access_token"]
        self._save_credentials(access_token)
        logger.info("[Dropbox] Access token refreshed manually")
        return access_token

    # ========================================================================
    # FILE OPERATIONS (async wrappers)
    # ========================================================================

    async def upload_file(
        self,
        local_path: Path | str,
        dropbox_path: str,
        overwrite: bool = False,
    ) -> UploadResult:
        """
        Upload a file to Dropbox.

        Args:
            local_path: Local file path
            dropbox_path: Destination path in Dropbox
            overwrite: Whether to overwrite existing file

        Returns:
            UploadResult with success status and metadata
        """
        local_path = Path(local_path)
        if not local_path.exists():
            return UploadResult(success=False, error=f"File not found: {local_path}")

        def _upload():
            client = self._get_client()
            mode = (
                dropbox.files.WriteMode.overwrite
                if overwrite
                else dropbox.files.WriteMode.add
            )

            with open(local_path, "rb") as f:
                # Use upload_session for large files (> 150 MB)
                file_size = local_path.stat().st_size
                if file_size > 150 * 1024 * 1024:
                    return self._upload_large_file(client, f, dropbox_path, mode)
                else:
                    metadata = client.files_upload(f.read(), dropbox_path, mode=mode)
                    return metadata

        try:
            loop = asyncio.get_event_loop()
            metadata = await loop.run_in_executor(None, _upload)
            return UploadResult(
                success=True,
                path=metadata.path_display,
                metadata={"id": metadata.id, "size": metadata.size},
            )
        except Exception as e:
            logger.error(f"[Dropbox] Upload failed: {e}")
            return UploadResult(success=False, error=str(e))

    def _upload_large_file(
        self,
        client: dropbox.Dropbox,
        file,
        dropbox_path: str,
        mode: dropbox.files.WriteMode,
    ):
        """Upload large file using chunked upload session."""
        CHUNK_SIZE = 4 * 1024 * 1024  # 4 MB chunks

        file_size = file.seek(0, 2)
        file.seek(0)

        session_start_result = client.files_upload_session_start(
            file.read(CHUNK_SIZE)
        )
        cursor = dropbox.files.UploadSessionCursor(
            session_id=session_start_result.session_id,
            offset=file.tell(),
        )
        commit = dropbox.files.CommitInfo(path=dropbox_path, mode=mode)

        while file.tell() < file_size:
            if (file_size - file.tell()) <= CHUNK_SIZE:
                # Final chunk
                return client.files_upload_session_finish(
                    file.read(CHUNK_SIZE),
                    cursor,
                    commit,
                )
            else:
                client.files_upload_session_append_v2(
                    file.read(CHUNK_SIZE),
                    cursor,
                )
                cursor.offset = file.tell()

    async def download_file(
        self,
        dropbox_path: str,
        local_path: Path | str,
    ) -> bool:
        """
        Download a file from Dropbox.

        Args:
            dropbox_path: Path in Dropbox
            local_path: Local destination path

        Returns:
            True if successful
        """
        local_path = Path(local_path)

        def _download():
            client = self._get_client()
            client.files_download_to_file(str(local_path), dropbox_path)
            return True

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _download)
            return True
        except Exception as e:
            logger.error(f"[Dropbox] Download failed: {e}")
            return False

    async def create_folder(self, path: str) -> bool:
        """
        Create a folder in Dropbox.

        Args:
            path: Folder path to create

        Returns:
            True if created or already exists
        """
        def _create():
            client = self._get_client()
            try:
                client.files_create_folder_v2(path)
                return True
            except dropbox.exceptions.ApiError as e:
                if hasattr(e.error, "is_path") and e.error.is_path():
                    # Folder already exists
                    return True
                raise

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _create)
            return True
        except Exception as e:
            logger.error(f"[Dropbox] Create folder failed: {e}")
            return False

    async def move_file(
        self,
        from_path: str,
        to_path: str,
    ) -> bool:
        """
        Move a file in Dropbox.

        Args:
            from_path: Source path
            to_path: Destination path

        Returns:
            True if successful
        """
        def _move():
            client = self._get_client()
            client.files_move_v2(from_path, to_path)
            return True

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _move)
            return True
        except Exception as e:
            logger.error(f"[Dropbox] Move failed: {e}")
            return False

    async def list_folder(
        self,
        path: str,
        recursive: bool = False,
    ) -> list[dict]:
        """
        List contents of a folder.

        Args:
            path: Folder path
            recursive: Whether to list recursively

        Returns:
            List of file/folder metadata dicts
        """
        def _list():
            client = self._get_client()
            entries = []
            result = client.files_list_folder(path, recursive=recursive)

            while True:
                for entry in result.entries:
                    entries.append({
                        "name": entry.name,
                        "path": entry.path_display,
                        "is_folder": isinstance(entry, dropbox.files.FolderMetadata),
                        "size": getattr(entry, "size", 0),
                        "modified": getattr(entry, "server_modified", None),
                    })

                if not result.has_more:
                    break
                result = client.files_list_folder_continue(result.cursor)

            return entries

        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _list)
        except Exception as e:
            logger.error(f"[Dropbox] List folder failed: {e}")
            return []

    async def search_files(
        self,
        query: str,
        path: str = "",
    ) -> SearchResult:
        """
        Search for files in Dropbox.

        Args:
            query: Search query (filename pattern)
            path: Path to search in (empty for all)

        Returns:
            SearchResult with matching files
        """
        def _search():
            client = self._get_client()
            results = []

            search_result = client.files_search_v2(query, options=dropbox.files.SearchOptions(
                path=path if path else None,
                max_results=100,
            ))

            for match in search_result.matches:
                if hasattr(match, "metadata") and hasattr(match.metadata, "metadata"):
                    entry = match.metadata.metadata
                    results.append({
                        "name": entry.name,
                        "path": entry.path_display,
                        "size": getattr(entry, "size", 0),
                        "modified": getattr(entry, "server_modified", None),
                    })

            return results

        try:
            loop = asyncio.get_event_loop()
            files = await loop.run_in_executor(None, _search)
            return SearchResult(found=len(files) > 0, files=files)
        except Exception as e:
            logger.error(f"[Dropbox] Search failed: {e}")
            return SearchResult(found=False, error=str(e))

    async def get_shared_link(
        self,
        path: str,
        direct: bool = True,
    ) -> SharedLinkResult:
        """
        Get or create a shared link for a file.

        Args:
            path: File path in Dropbox
            direct: Whether to return direct download link

        Returns:
            SharedLinkResult with URL
        """
        def _get_link():
            client = self._get_client()

            # Try to get existing link first
            try:
                existing = client.sharing_list_shared_links(path=path, direct_only=True)
                if existing.links:
                    url = existing.links[0].url
                    if direct:
                        url = url.replace("?dl=0", "?dl=1")
                    return url
            except Exception:
                pass

            # Create new link
            try:
                settings = dropbox.sharing.SharedLinkSettings(
                    requested_visibility=dropbox.sharing.RequestedVisibility.public
                )
                link = client.sharing_create_shared_link_with_settings(path, settings)
                url = link.url
                if direct:
                    url = url.replace("?dl=0", "?dl=1")
                return url
            except dropbox.exceptions.ApiError as e:
                if hasattr(e.error, "is_shared_link_already_exists"):
                    # Link exists, try to get it
                    existing = client.sharing_list_shared_links(path=path, direct_only=True)
                    if existing.links:
                        url = existing.links[0].url
                        if direct:
                            url = url.replace("?dl=0", "?dl=1")
                        return url
                raise

        try:
            loop = asyncio.get_event_loop()
            url = await loop.run_in_executor(None, _get_link)
            return SharedLinkResult(success=True, url=url)
        except Exception as e:
            logger.error(f"[Dropbox] Get shared link failed: {e}")
            return SharedLinkResult(success=False, error=str(e))

    async def file_exists(self, path: str) -> bool:
        """Check if a file exists at the given path."""
        def _check():
            client = self._get_client()
            try:
                client.files_get_metadata(path)
                return True
            except dropbox.exceptions.ApiError:
                return False

        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _check)
        except Exception:
            return False
