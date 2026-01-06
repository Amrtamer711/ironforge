"""
Video Service for Video Critique.

Handles video file operations including:
- Video/ZIP upload processing
- File extraction and organization
- Version management
- Dropbox folder operations
"""

import asyncio
import re
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.utils.logging import get_logger
from core.utils.time import get_uae_time
from db.database import db
from integrations.dropbox.operations import get_dropbox_folders

if TYPE_CHECKING:
    from integrations.dropbox import DropboxClient

logger = get_logger(__name__)


def _get_folders() -> dict[str, str]:
    """Get Dropbox folders with dev/prod prefix applied."""
    return get_dropbox_folders()


# Legacy alias for backward compatibility (use _get_folders() for dynamic access)
DROPBOX_FOLDERS = _get_folders()


@dataclass
class UploadedFile:
    """Information about an uploaded file."""
    original_name: str
    dropbox_name: str
    dropbox_path: str
    size: int
    file_type: str


@dataclass
class UploadResult:
    """Result of a video upload operation."""
    success: bool
    task_number: int | None = None
    version: int = 1
    folder_name: str = ""
    folder_path: str = ""
    uploaded_files: list[UploadedFile] | None = None
    error: str = ""

    def __post_init__(self):
        if self.uploaded_files is None:
            self.uploaded_files = []


class VideoService:
    """
    Service for managing video files in the production workflow.

    Handles uploads, extractions, and movement of video files
    through the various stages of the approval process.
    """

    # Supported video formats
    VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
    # Supported archive formats
    ARCHIVE_EXTENSIONS = {".zip"}

    def __init__(self, dropbox_client: "DropboxClient | None" = None):
        """
        Initialize video service.

        Args:
            dropbox_client: Optional DropboxClient instance
        """
        self._dropbox = dropbox_client
        self._db = db
        # Concurrency control
        self._upload_semaphore = asyncio.Semaphore(10)  # Max concurrent uploads
        self._task_locks: dict[int, asyncio.Lock] = {}
        self._locks_lock = asyncio.Lock()

    async def _get_dropbox(self) -> "DropboxClient":
        """Get or create Dropbox client."""
        if self._dropbox is None:
            from integrations.dropbox import DropboxClient
            self._dropbox = DropboxClient.from_config()
        return self._dropbox

    async def _get_task_lock(self, task_number: int) -> asyncio.Lock:
        """Get or create a lock for a specific task to prevent race conditions."""
        async with self._locks_lock:
            if task_number not in self._task_locks:
                self._task_locks[task_number] = asyncio.Lock()
            return self._task_locks[task_number]

    # ========================================================================
    # UPLOAD OPERATIONS
    # ========================================================================

    async def process_upload(
        self,
        task_number: int,
        files: list[dict[str, Any]],
        uploader_id: str,
        uploader_name: str,
    ) -> UploadResult:
        """
        Process uploaded files for a task.

        Handles both direct video files and ZIP archives.
        Creates appropriate folder structure in Dropbox.

        Args:
            task_number: Task number
            files: List of file info dicts with 'content', 'name', 'size' keys
            uploader_id: Uploader's user ID
            uploader_name: Uploader's display name

        Returns:
            UploadResult with upload status and file info
        """
        # Acquire upload slot for concurrency control
        async with self._upload_semaphore:
            # Get task-specific lock to prevent concurrent uploads for same task
            task_lock = await self._get_task_lock(task_number)
            async with task_lock:
                return await self._do_upload(
                    task_number, files, uploader_id, uploader_name
                )

    async def _do_upload(
        self,
        task_number: int,
        files: list[dict[str, Any]],
        uploader_id: str,
        uploader_name: str,
    ) -> UploadResult:
        """Internal upload implementation."""
        try:
            dropbox = await self._get_dropbox()

            # Get task data
            task = await self._db.get_task(task_number)
            if not task:
                return UploadResult(
                    success=False,
                    error=f"Task #{task_number} not found",
                )

            # Determine next version number
            current_version = await self.get_latest_version(task_number)
            new_version = current_version + 1

            # Generate folder name
            folder_name = f"Task{task_number}_V{new_version}"
            folder_path = f"{DROPBOX_FOLDERS['pending']}/{folder_name}"

            # Create folder in Dropbox
            await dropbox.create_folder(folder_path)

            # Process each file
            uploaded_files = []
            file_index = 1

            for file_info in files:
                file_name = file_info.get("name", "")
                file_content = file_info.get("content", b"")
                file_ext = Path(file_name).suffix.lower()

                if file_ext in self.ARCHIVE_EXTENSIONS:
                    # Extract ZIP and upload contents
                    extracted = await self._extract_and_upload_zip(
                        dropbox,
                        file_content,
                        folder_path,
                        task_number,
                        new_version,
                        file_index,
                    )
                    uploaded_files.extend(extracted)
                    file_index += len(extracted)

                elif file_ext in self.VIDEO_EXTENSIONS:
                    # Upload video directly
                    uploaded = await self._upload_single_file(
                        dropbox,
                        file_content,
                        file_name,
                        folder_path,
                        task_number,
                        new_version,
                        file_index,
                    )
                    if uploaded:
                        uploaded_files.append(uploaded)
                        file_index += 1

                else:
                    logger.warning(f"[VideoService] Unsupported file type: {file_ext}")

            if not uploaded_files:
                return UploadResult(
                    success=False,
                    error="No valid video files found",
                )

            # Update task with submission folder
            await self._db.update_task(task_number, {
                "submission_folder": folder_name,
                "current_version": new_version,
                "updated_at": get_uae_time(),
            })

            logger.info(
                f"[VideoService] Uploaded {len(uploaded_files)} files for task #{task_number} v{new_version}"
            )

            return UploadResult(
                success=True,
                task_number=task_number,
                version=new_version,
                folder_name=folder_name,
                folder_path=folder_path,
                uploaded_files=uploaded_files,
            )

        except Exception as e:
            logger.error(f"[VideoService] Upload error for task #{task_number}: {e}")
            return UploadResult(
                success=False,
                task_number=task_number,
                error=str(e),
            )

    async def _upload_single_file(
        self,
        dropbox: "DropboxClient",
        content: bytes,
        original_name: str,
        folder_path: str,
        task_number: int,
        version: int,
        file_index: int,
    ) -> UploadedFile | None:
        """Upload a single video file to Dropbox."""
        try:
            file_ext = Path(original_name).suffix.lower()
            if not file_ext:
                file_ext = ".mp4"

            # Generate standardized filename
            dropbox_name = f"Task{task_number}_V{version}_{file_index}{file_ext}"
            dropbox_path = f"{folder_path}/{dropbox_name}"

            # Write to temp file and upload
            with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
                tmp.write(content)
                tmp_path = tmp.name

            try:
                result = await dropbox.upload_file(tmp_path, dropbox_path, overwrite=True)
                if result.success:
                    return UploadedFile(
                        original_name=original_name,
                        dropbox_name=dropbox_name,
                        dropbox_path=dropbox_path,
                        size=len(content),
                        file_type=file_ext.lstrip("."),
                    )
            finally:
                # Clean up temp file
                try:
                    Path(tmp_path).unlink()
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"[VideoService] Error uploading {original_name}: {e}")

        return None

    async def _extract_and_upload_zip(
        self,
        dropbox: "DropboxClient",
        zip_content: bytes,
        folder_path: str,
        task_number: int,
        version: int,
        start_index: int,
    ) -> list[UploadedFile]:
        """Extract ZIP archive and upload video files."""
        uploaded_files = []

        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp_zip:
            tmp_zip.write(zip_content)
            tmp_zip_path = tmp_zip.name

        try:
            with zipfile.ZipFile(tmp_zip_path, "r") as zf:
                file_index = start_index

                for name in zf.namelist():
                    # Skip directories and hidden files
                    if name.endswith("/") or name.startswith("__MACOSX"):
                        continue

                    file_ext = Path(name).suffix.lower()
                    if file_ext not in self.VIDEO_EXTENSIONS:
                        continue

                    # Extract to temp location
                    with tempfile.NamedTemporaryFile(
                        delete=False, suffix=file_ext
                    ) as tmp_video:
                        tmp_video.write(zf.read(name))
                        tmp_video_path = tmp_video.name

                    try:
                        # Generate standardized filename
                        dropbox_name = f"Task{task_number}_V{version}_{file_index}{file_ext}"
                        dropbox_path = f"{folder_path}/{dropbox_name}"

                        result = await dropbox.upload_file(
                            tmp_video_path, dropbox_path, overwrite=True
                        )

                        if result.success:
                            uploaded_files.append(
                                UploadedFile(
                                    original_name=Path(name).name,
                                    dropbox_name=dropbox_name,
                                    dropbox_path=dropbox_path,
                                    size=Path(tmp_video_path).stat().st_size,
                                    file_type=file_ext.lstrip("."),
                                )
                            )
                            file_index += 1

                    finally:
                        try:
                            Path(tmp_video_path).unlink()
                        except Exception:
                            pass

        finally:
            try:
                Path(tmp_zip_path).unlink()
            except Exception:
                pass

        return uploaded_files

    # ========================================================================
    # VERSION MANAGEMENT
    # ========================================================================

    async def get_latest_version(
        self,
        task_number: int,
        exclude_accepted: bool = True,
    ) -> int:
        """
        Get the latest version number for a task.

        Scans Dropbox folders for Task{N}_V{X} folders.

        Args:
            task_number: Task number
            exclude_accepted: Whether to exclude accepted folder

        Returns:
            Highest version number found (0 if none)
        """
        latest_version = 0

        try:
            dropbox = await self._get_dropbox()

            folders_to_check = dict(DROPBOX_FOLDERS)
            if exclude_accepted:
                folders_to_check.pop("accepted", None)

            for folder_key, folder_path in folders_to_check.items():
                try:
                    entries = await dropbox.list_folder(folder_path)

                    for entry in entries:
                        if entry.get("is_folder"):
                            folder_name = entry.get("name", "")
                            # Check for TaskN_VX pattern
                            if folder_name.startswith(f"Task{task_number}_V"):
                                try:
                                    parts = folder_name.split("_V")
                                    if len(parts) == 2 and parts[1].isdigit():
                                        version = int(parts[1])
                                        latest_version = max(latest_version, version)
                                except (ValueError, IndexError):
                                    continue

                except Exception as e:
                    logger.debug(f"[VideoService] Error checking {folder_path}: {e}")

        except Exception as e:
            logger.error(f"[VideoService] Error getting latest version: {e}")

        return latest_version

    # ========================================================================
    # FILE MOVEMENT OPERATIONS
    # ========================================================================

    async def move_to_folder(
        self,
        task_number: int,
        source_folder: str,
        destination_folder: str,
    ) -> bool:
        """
        Move a task's submission folder to a different folder.

        Args:
            task_number: Task number
            source_folder: Source folder key (pending, rejected, etc.)
            destination_folder: Destination folder key

        Returns:
            True if successful
        """
        try:
            dropbox = await self._get_dropbox()

            # Get task to find folder name
            task = await self._db.get_task(task_number)
            if not task or not task.submission_folder:
                logger.error(f"[VideoService] Task #{task_number} has no submission folder")
                return False

            folder_name = task.submission_folder
            source_path = f"{DROPBOX_FOLDERS[source_folder]}/{folder_name}"
            dest_path = f"{DROPBOX_FOLDERS[destination_folder]}/{folder_name}"

            success = await dropbox.move_file(source_path, dest_path)

            if success:
                logger.info(
                    f"[VideoService] Moved {folder_name} from {source_folder} to {destination_folder}"
                )

            return success

        except Exception as e:
            logger.error(f"[VideoService] Error moving folder: {e}")
            return False

    async def move_pending_to_submitted(self, task_number: int) -> bool:
        """Move task folder from pending to submitted."""
        return await self.move_to_folder(task_number, "pending", "submitted")

    async def move_pending_to_rejected(self, task_number: int) -> bool:
        """Move task folder from pending to rejected."""
        return await self.move_to_folder(task_number, "pending", "rejected")

    async def move_submitted_to_accepted(self, task_number: int) -> bool:
        """Move task folder from submitted to accepted."""
        return await self.move_to_folder(task_number, "submitted", "accepted")

    async def move_submitted_to_returned(self, task_number: int) -> bool:
        """Move task folder from submitted to returned."""
        return await self.move_to_folder(task_number, "submitted", "returned")

    # ========================================================================
    # SHARED LINK OPERATIONS
    # ========================================================================

    async def get_shared_link(self, dropbox_path: str) -> str:
        """
        Get a shareable link for a file or folder in Dropbox.

        Args:
            dropbox_path: Path to file or folder

        Returns:
            Shareable URL
        """
        try:
            dropbox = await self._get_dropbox()
            result = await dropbox.get_shared_link(dropbox_path)
            return result.url if result.success else ""
        except Exception as e:
            logger.error(f"[VideoService] Error getting shared link: {e}")
            return ""

    async def get_folder_shared_link(
        self,
        task_number: int,
        folder: str = "pending",
    ) -> str:
        """
        Get a shareable link for a task's submission folder.

        Args:
            task_number: Task number
            folder: Folder key

        Returns:
            Shareable URL
        """
        task = await self._db.get_task(task_number)
        if not task or not task.submission_folder:
            return ""

        folder_path = f"{DROPBOX_FOLDERS[folder]}/{task.submission_folder}"
        return await self.get_shared_link(folder_path)

    # ========================================================================
    # FILE LISTING
    # ========================================================================

    async def list_task_files(
        self,
        task_number: int,
        folder: str = "pending",
    ) -> list[dict[str, Any]]:
        """
        List all files in a task's submission folder.

        Args:
            task_number: Task number
            folder: Folder key

        Returns:
            List of file info dicts
        """
        try:
            dropbox = await self._get_dropbox()

            task = await self._db.get_task(task_number)
            if not task or not task.submission_folder:
                return []

            folder_path = f"{DROPBOX_FOLDERS[folder]}/{task.submission_folder}"
            entries = await dropbox.list_folder(folder_path)

            return [
                entry for entry in entries
                if not entry.get("is_folder")
            ]

        except Exception as e:
            logger.error(f"[VideoService] Error listing files: {e}")
            return []
