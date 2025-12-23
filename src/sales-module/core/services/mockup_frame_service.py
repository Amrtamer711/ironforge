"""
Mockup Frame Service - Manages mockup frames and photos from Asset-Management.

Fetches mockup frame data and background photos from Asset-Management Supabase Storage
via the Asset-Management API. Mockup frames are stored in Asset-Management because they
are location-specific assets.
"""

import asyncio
import io
import random
import tempfile
import time
from pathlib import Path
from typing import Any

from integrations.asset_management import asset_mgmt_client

# Lazy import to avoid circular dependency
_logger = None


def _get_logger():
    global _logger
    if _logger is None:
        import config
        _logger = config.get_logger("core.services.mockup_frame_service")
    return _logger


# Cache TTL in seconds (5 minutes)
CACHE_TTL = 300


class MockupFrameCache:
    """Thread-safe cache for mockup frame discovery results."""

    def __init__(self):
        self._frames: dict[str, dict[str, Any]] = {}  # {company: {location_key: [frames]}}
        self._last_refresh: dict[str, float] = {}  # {company: timestamp}
        self._lock = asyncio.Lock()

    def is_stale(self, company: str) -> bool:
        """Check if cache needs refresh for company."""
        last = self._last_refresh.get(company, 0)
        return time.time() - last > CACHE_TTL

    async def refresh(self, company: str, location_key: str, frames: list[dict]) -> None:
        """Update cache with new data for location."""
        async with self._lock:
            if company not in self._frames:
                self._frames[company] = {}
            self._frames[company][location_key] = frames
            self._last_refresh[company] = time.time()

    def get_frames(self, company: str, location_key: str) -> list[dict] | None:
        """Get cached frames for location."""
        return self._frames.get(company, {}).get(location_key)


# Global cache instance
_frame_cache = MockupFrameCache()


class MockupFrameService:
    """
    Service for managing mockup frames and photos from Asset-Management.

    Mockup frames and photos are stored in Asset-Management Supabase Storage
    and accessed via the Asset-Management API. This ensures mockup assets are
    co-located with location metadata.

    Responsibilities:
    - Get mockup frames for a location/photo combination
    - List available mockup variations (time_of_day/finish combos)
    - Download mockup photos to temp files for processing
    - Check mockup availability

    Usage:
        service = MockupFrameService(companies=["backlite_dubai", "backlite_ksa"])

        # Get available variations (searches all companies)
        variations = await service.list_variations("dubai_mall")
        # Returns: {"day": ["gold", "silver"], "night": ["gold"]}

        # Get frame data for specific photo
        frames = await service.get_frames("dubai_mall", "day", "gold", "photo1.jpg")

        # Download photo for processing
        photo_path = await service.download_photo("dubai_mall", "day", "gold", "photo1.jpg")
    """

    def __init__(self, companies: list[str] | str = "backlite_dubai"):
        """
        Initialize MockupFrameService.

        Args:
            companies: Company schema(s) - can be a single string or list of companies
        """
        # Normalize to list
        if isinstance(companies, str):
            self.companies = [companies]
        else:
            self.companies = companies
        self.logger = _get_logger()

    async def get_all_frames(self, location_key: str) -> tuple[list[dict], str | None]:
        """
        Get all mockup frames for a location across all companies.

        Args:
            location_key: Location identifier (e.g., "dubai_mall")

        Returns:
            Tuple of (list of frame dicts, company that had the frames)
        """
        self.logger.info(f"[MOCKUP_FRAME_SERVICE] Getting all frames for {location_key}")

        for company in self.companies:
            try:
                frames = await asset_mgmt_client.get_mockup_frames(company, location_key)
                if frames:
                    self.logger.info(
                        f"[MOCKUP_FRAME_SERVICE] Found {len(frames)} frames in {company}"
                    )
                    return frames, company
            except Exception as e:
                self.logger.debug(f"[MOCKUP_FRAME_SERVICE] No frames in {company}: {e}")
                continue

        self.logger.info(f"[MOCKUP_FRAME_SERVICE] No frames found for {location_key}")
        return [], None

    async def list_variations(self, location_key: str) -> dict[str, list[str]]:
        """
        List available mockup variations for a location.

        Args:
            location_key: Location identifier

        Returns:
            Dict mapping time_of_day to list of finishes, e.g.:
            {"day": ["gold", "silver"], "night": ["gold"]}
        """
        self.logger.info(f"[MOCKUP_FRAME_SERVICE] Listing variations for {location_key}")

        try:
            frames, _ = await self.get_all_frames(location_key)
            variations: dict[str, list[str]] = {}

            for frame in frames:
                tod = frame.get("time_of_day", "day")
                finish = frame.get("finish", "gold")

                if tod not in variations:
                    variations[tod] = []
                if finish not in variations[tod]:
                    variations[tod].append(finish)

            self.logger.info(f"[MOCKUP_FRAME_SERVICE] Variations for {location_key}: {variations}")
            return variations
        except Exception as e:
            self.logger.error(f"[MOCKUP_FRAME_SERVICE] Error listing variations: {e}")
            return {}

    async def list_photos(
        self,
        location_key: str,
        time_of_day: str = "day",
        finish: str = "gold",
    ) -> list[str]:
        """
        List available photos for a location/time/finish combination.

        Args:
            location_key: Location identifier
            time_of_day: "day" or "night"
            finish: "gold", "silver", or "black"

        Returns:
            List of photo filenames
        """
        try:
            frames, _ = await self.get_all_frames(location_key)
            photos = []

            for frame in frames:
                if frame.get("time_of_day") == time_of_day and frame.get("finish") == finish:
                    photo = frame.get("photo_filename")
                    if photo and photo not in photos:
                        photos.append(photo)

            return photos
        except Exception as e:
            self.logger.error(f"[MOCKUP_FRAME_SERVICE] Error listing photos: {e}")
            return []

    async def get_frames(
        self,
        location_key: str,
        time_of_day: str = "day",
        finish: str = "gold",
        photo_filename: str | None = None,
    ) -> list[dict] | None:
        """
        Get frame data for a specific location/photo combination.

        Args:
            location_key: Location identifier
            time_of_day: "day" or "night"
            finish: "gold", "silver", or "black"
            photo_filename: Specific photo (optional, returns first match if None)

        Returns:
            List of frame dicts with "points" and optional "config", or None if not found
        """
        self.logger.info(
            f"[MOCKUP_FRAME_SERVICE] Getting frames for {location_key}/{time_of_day}/{finish}"
            + (f"/{photo_filename}" if photo_filename else "")
        )

        for company in self.companies:
            try:
                frame_data = await asset_mgmt_client.get_mockup_frame(
                    company,
                    location_key,
                    time_of_day,
                    finish,
                    photo_filename,
                )

                if frame_data and "frames_data" in frame_data:
                    return frame_data["frames_data"]
            except Exception as e:
                self.logger.debug(f"[MOCKUP_FRAME_SERVICE] No frame in {company}: {e}")
                continue

        return None

    async def get_config(
        self,
        location_key: str,
        time_of_day: str = "day",
        finish: str = "gold",
        photo_filename: str | None = None,
    ) -> dict | None:
        """
        Get mockup config for a specific location/photo.

        Args:
            location_key: Location identifier
            time_of_day: "day" or "night"
            finish: "gold", "silver", or "black"
            photo_filename: Specific photo (optional)

        Returns:
            Config dict or None
        """
        for company in self.companies:
            try:
                frame_data = await asset_mgmt_client.get_mockup_frame(
                    company,
                    location_key,
                    time_of_day,
                    finish,
                    photo_filename,
                )

                if frame_data and frame_data.get("config"):
                    return frame_data["config"]
            except Exception as e:
                self.logger.debug(f"[MOCKUP_FRAME_SERVICE] No config in {company}: {e}")
                continue

        return None

    async def download_photo(
        self,
        location_key: str,
        time_of_day: str,
        finish: str,
        photo_filename: str,
    ) -> Path | None:
        """
        Download mockup background photo to a temporary file.

        Args:
            location_key: Location identifier
            time_of_day: "day" or "night"
            finish: "gold", "silver", or "black"
            photo_filename: Photo filename

        Returns:
            Path to temp file or None if download failed
        """
        self.logger.info(
            f"[MOCKUP_FRAME_SERVICE] Downloading photo: {location_key}/{time_of_day}/{finish}/{photo_filename}"
        )

        for company in self.companies:
            try:
                data = await asset_mgmt_client.get_mockup_photo(
                    company,
                    location_key,
                    time_of_day,
                    finish,
                    photo_filename,
                )

                if data:
                    # Determine suffix from filename
                    suffix = Path(photo_filename).suffix or ".jpg"

                    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                    temp_file.write(data)
                    temp_file.close()

                    self.logger.info(f"[MOCKUP_FRAME_SERVICE] Photo saved to: {temp_file.name}")
                    return Path(temp_file.name)
            except Exception as e:
                self.logger.debug(f"[MOCKUP_FRAME_SERVICE] No photo in {company}: {e}")
                continue

        self.logger.warning(f"[MOCKUP_FRAME_SERVICE] Photo not found in any company")
        return None

    async def get_random_photo(
        self,
        location_key: str,
        time_of_day: str = "all",
        finish: str = "all",
    ) -> tuple[str, str, str, Path] | None:
        """
        Get a random photo for a location that has frame data.

        Args:
            location_key: Location identifier
            time_of_day: "day", "night", or "all" for random
            finish: "gold", "silver", "black", or "all" for random

        Returns:
            Tuple of (photo_filename, time_of_day, finish, photo_path) or None
        """
        self.logger.info(
            f"[MOCKUP_FRAME_SERVICE] Getting random photo for {location_key} "
            f"(time={time_of_day}, finish={finish})"
        )

        try:
            frames, _ = await self.get_all_frames(location_key)
            if not frames:
                self.logger.warning(f"[MOCKUP_FRAME_SERVICE] No frames found for {location_key}")
                return None

            # Filter frames based on criteria
            matching = []
            for frame in frames:
                tod = frame.get("time_of_day", "day")
                fin = frame.get("finish", "gold")
                photo = frame.get("photo_filename")

                if not photo:
                    continue

                if time_of_day != "all" and tod != time_of_day:
                    continue
                if finish != "all" and fin != finish:
                    continue

                matching.append((photo, tod, fin))

            if not matching:
                self.logger.warning(
                    f"[MOCKUP_FRAME_SERVICE] No matching photos for {location_key} "
                    f"with time={time_of_day}, finish={finish}"
                )
                return None

            # Pick random
            photo_filename, selected_tod, selected_finish = random.choice(matching)

            # Download the photo
            photo_path = await self.download_photo(
                location_key, selected_tod, selected_finish, photo_filename
            )

            if not photo_path:
                return None

            self.logger.info(
                f"[MOCKUP_FRAME_SERVICE] Selected: {photo_filename} ({selected_tod}/{selected_finish})"
            )
            return photo_filename, selected_tod, selected_finish, photo_path

        except Exception as e:
            self.logger.error(f"[MOCKUP_FRAME_SERVICE] Error getting random photo: {e}")
            return None

    async def has_mockup_frames(self, location_key: str) -> bool:
        """
        Check if a location has any mockup frames available.

        Args:
            location_key: Location identifier

        Returns:
            True if at least one mockup frame exists
        """
        frames, _ = await self.get_all_frames(location_key)
        return len(frames) > 0

    async def is_portrait(self, location_key: str) -> bool:
        """
        Check if a location has portrait orientation based on frame dimensions.

        Args:
            location_key: Location identifier

        Returns:
            True if height > width (portrait), False otherwise
        """
        import math

        try:
            frames, _ = await self.get_all_frames(location_key)
            if not frames:
                return False

            # Get first frame with data
            for frame in frames:
                frames_data = frame.get("frames_data", [])
                if frames_data and len(frames_data) > 0:
                    points = frames_data[0].get("points", [])
                    if len(points) >= 4:
                        # Calculate dimensions from corner points
                        top_width = math.sqrt(
                            (points[1][0] - points[0][0])**2 +
                            (points[1][1] - points[0][1])**2
                        )
                        bottom_width = math.sqrt(
                            (points[2][0] - points[3][0])**2 +
                            (points[2][1] - points[3][1])**2
                        )
                        left_height = math.sqrt(
                            (points[3][0] - points[0][0])**2 +
                            (points[3][1] - points[0][1])**2
                        )
                        right_height = math.sqrt(
                            (points[2][0] - points[1][0])**2 +
                            (points[2][1] - points[1][1])**2
                        )

                        avg_width = (top_width + bottom_width) / 2
                        avg_height = (left_height + right_height) / 2

                        is_portrait = avg_height > avg_width
                        self.logger.info(
                            f"[MOCKUP_FRAME_SERVICE] {location_key}: "
                            f"{avg_width:.0f}x{avg_height:.0f}px → "
                            f"{'PORTRAIT' if is_portrait else 'LANDSCAPE'}"
                        )
                        return is_portrait

            return False
        except Exception as e:
            self.logger.error(f"[MOCKUP_FRAME_SERVICE] Error checking orientation: {e}")
            return False


# Convenience functions for module-level access


async def get_mockup_frame_service(
    companies: list[str] | str = "backlite_dubai"
) -> MockupFrameService:
    """Get a MockupFrameService instance."""
    return MockupFrameService(companies=companies)


async def has_mockup_frames(
    location_key: str, companies: list[str] | str = "backlite_dubai"
) -> bool:
    """Check if location has mockup frames."""
    service = MockupFrameService(companies=companies)
    return await service.has_mockup_frames(location_key)


async def is_portrait_location(
    location_key: str, companies: list[str] | str = "backlite_dubai"
) -> bool:
    """Check if location has portrait orientation."""
    service = MockupFrameService(companies=companies)
    return await service.is_portrait(location_key)
