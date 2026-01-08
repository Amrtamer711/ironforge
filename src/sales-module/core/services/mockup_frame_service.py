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
    - List available mockup variations (time_of_day/side combos)
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

    async def get_all_frames(
        self,
        location_key: str,
        company_hint: str | None = None,
    ) -> tuple[list[dict], str | None]:
        """
        Get all mockup frames for a location across all companies.

        Uses global cache to avoid redundant API calls. Cache TTL is 5 minutes.
        If company_hint is provided, tries that company first for O(1) lookup.
        Falls back to searching all companies if hint fails.

        Args:
            location_key: Location identifier (e.g., "dubai_mall")
            company_hint: Optional company to try first (from WorkflowContext)

        Returns:
            Tuple of (list of frame dicts, company that had the frames)
        """
        normalized_key = location_key.lower().strip()

        # Check cache first - prioritize company_hint
        companies_to_check = []
        if company_hint and company_hint in self.companies:
            companies_to_check.append(company_hint)
        companies_to_check.extend([c for c in self.companies if c != company_hint])

        for company in companies_to_check:
            if not _frame_cache.is_stale(company):
                cached = _frame_cache.get_frames(company, normalized_key)
                if cached is not None:
                    self.logger.info(
                        f"[MOCKUP_FRAME_SERVICE] Cache hit: {len(cached)} frames for {location_key} in {company}"
                    )
                    return cached, company

        self.logger.info(f"[MOCKUP_FRAME_SERVICE] Cache miss, fetching frames for {location_key}")

        # Try company_hint first if provided (O(1) lookup from WorkflowContext)
        if company_hint and company_hint in self.companies:
            try:
                frames = await asset_mgmt_client.get_mockup_frames(company_hint, location_key)
                if frames:
                    # Cache the result
                    await _frame_cache.refresh(company_hint, normalized_key, frames)
                    self.logger.info(
                        f"[MOCKUP_FRAME_SERVICE] Found {len(frames)} frames in {company_hint} (direct hit, cached)"
                    )
                    return frames, company_hint
            except Exception as e:
                self.logger.debug(f"[MOCKUP_FRAME_SERVICE] No frames in hinted company {company_hint}: {e}")

        # Fallback: search all companies (skip hint if already tried)
        for company in self.companies:
            if company == company_hint:
                continue  # Already tried this one
            try:
                frames = await asset_mgmt_client.get_mockup_frames(company, location_key)
                if frames:
                    # Cache the result
                    await _frame_cache.refresh(company, normalized_key, frames)
                    self.logger.info(
                        f"[MOCKUP_FRAME_SERVICE] Found {len(frames)} frames in {company} (cached)"
                    )
                    return frames, company
            except Exception as e:
                self.logger.debug(f"[MOCKUP_FRAME_SERVICE] No frames in {company}: {e}")
                continue

        self.logger.info(f"[MOCKUP_FRAME_SERVICE] No frames found for {location_key}")
        return [], None

    async def list_variations(
        self,
        location_key: str,
        company_hint: str | None = None,
    ) -> dict[str, list[str]]:
        """
        List available mockup variations for a location.

        Args:
            location_key: Location identifier
            company_hint: Optional company to try first (from WorkflowContext)

        Returns:
            Dict mapping time_of_day to list of sides, e.g.:
            {"day": ["gold", "silver"], "night": ["gold"]}
        """
        self.logger.info(f"[MOCKUP_FRAME_SERVICE] Listing variations for {location_key}")

        try:
            frames, _ = await self.get_all_frames(location_key, company_hint=company_hint)
            variations: dict[str, list[str]] = {}

            for frame in frames:
                tod = frame.get("time_of_day", "day")
                side = frame.get("side", "gold")

                if tod not in variations:
                    variations[tod] = []
                if side not in variations[tod]:
                    variations[tod].append(side)

            self.logger.info(f"[MOCKUP_FRAME_SERVICE] Variations for {location_key}: {variations}")
            return variations
        except Exception as e:
            self.logger.error(f"[MOCKUP_FRAME_SERVICE] Error listing variations: {e}")
            return {}

    async def list_photos(
        self,
        location_key: str,
        time_of_day: str = "day",
        side: str = "gold",
        company_hint: str | None = None,
    ) -> list[str]:
        """
        List available photos for a location/time/side combination.

        Args:
            location_key: Location identifier
            time_of_day: "day" or "night"
            side: "gold", "silver", or "single_side"
            company_hint: Optional company to try first (from WorkflowContext)

        Returns:
            List of photo filenames
        """
        try:
            frames, _ = await self.get_all_frames(location_key, company_hint=company_hint)
            photos = []

            for frame in frames:
                if frame.get("time_of_day") == time_of_day and frame.get("side") == side:
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
        side: str = "gold",
        photo_filename: str | None = None,
        environment: str = "outdoor",
        company_hint: str | None = None,
    ) -> list[dict] | None:
        """
        Get frame data for a specific location/photo combination.

        If company_hint is provided, tries that company first for O(1) lookup.

        Args:
            location_key: Location identifier
            time_of_day: "day" or "night" (ignored for indoor)
            side: "gold", "silver", or "single_side" (ignored for indoor)
            photo_filename: Specific photo (optional, returns first match if None)
            environment: "indoor" or "outdoor"
            company_hint: Optional company to try first (from WorkflowContext)

        Returns:
            List of frame dicts with "points" and optional "config", or None if not found
        """
        self.logger.info(
            f"[MOCKUP_FRAME_SERVICE] Getting frames for {location_key}/{environment}/{time_of_day}/{side}"
            + (f"/{photo_filename}" if photo_filename else "")
        )

        # Try company_hint first if provided (O(1) lookup from WorkflowContext)
        if company_hint and company_hint in self.companies:
            try:
                frame_data = await asset_mgmt_client.get_mockup_frame(
                    company_hint,
                    location_key,
                    environment,
                    time_of_day,
                    side,
                    photo_filename,
                )
                if frame_data and "frames_data" in frame_data:
                    self.logger.debug(f"[MOCKUP_FRAME_SERVICE] Frame found in {company_hint} (direct hit)")
                    return frame_data["frames_data"]
            except Exception as e:
                self.logger.debug(f"[MOCKUP_FRAME_SERVICE] No frame in hinted company {company_hint}: {e}")

        # Fallback: search all companies
        for company in self.companies:
            if company == company_hint:
                continue
            try:
                frame_data = await asset_mgmt_client.get_mockup_frame(
                    company,
                    location_key,
                    environment,
                    time_of_day,
                    side,
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
        side: str = "gold",
        photo_filename: str | None = None,
        environment: str = "outdoor",
        company_hint: str | None = None,
    ) -> dict | None:
        """
        Get mockup config for a specific location/photo.

        Args:
            location_key: Location identifier
            time_of_day: "day" or "night" (ignored for indoor)
            side: "gold", "silver", or "single_side" (ignored for indoor)
            photo_filename: Specific photo (optional)
            environment: "indoor" or "outdoor"
            company_hint: Optional company to try first (from WorkflowContext)

        Returns:
            Config dict or None
        """
        # Try company_hint first if provided
        if company_hint and company_hint in self.companies:
            try:
                frame_data = await asset_mgmt_client.get_mockup_frame(
                    company_hint,
                    location_key,
                    environment,
                    time_of_day,
                    side,
                    photo_filename,
                )
                if frame_data and frame_data.get("config"):
                    return frame_data["config"]
            except Exception as e:
                self.logger.debug(f"[MOCKUP_FRAME_SERVICE] No config in hinted company {company_hint}: {e}")

        # Fallback: search all companies
        for company in self.companies:
            if company == company_hint:
                continue
            try:
                frame_data = await asset_mgmt_client.get_mockup_frame(
                    company,
                    location_key,
                    environment,
                    time_of_day,
                    side,
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
        side: str,
        photo_filename: str,
        environment: str = "outdoor",
        company_hint: str | None = None,
    ) -> Path | None:
        """
        Download mockup background photo to a temporary file.

        If company_hint is provided, tries that company first for O(1) lookup.

        Args:
            location_key: Location identifier
            time_of_day: "day" or "night" (ignored for indoor)
            side: "gold", "silver", or "single_side" (ignored for indoor)
            photo_filename: Photo filename
            environment: "indoor" or "outdoor"
            company_hint: Optional company to try first (from WorkflowContext)

        Returns:
            Path to temp file or None if download failed
        """
        self.logger.info(
            f"[MOCKUP_FRAME_SERVICE] Downloading photo: {location_key}/{environment}/{time_of_day}/{side}/{photo_filename}"
        )

        # Try company_hint first if provided (O(1) lookup from WorkflowContext)
        if company_hint and company_hint in self.companies:
            try:
                data = await asset_mgmt_client.get_mockup_photo(
                    company_hint,
                    location_key,
                    time_of_day,
                    side,
                    photo_filename,
                    environment,
                )

                if data:
                    suffix = Path(photo_filename).suffix or ".jpg"
                    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                    temp_file.write(data)
                    temp_file.close()

                    self.logger.info(f"[MOCKUP_FRAME_SERVICE] Photo saved to: {temp_file.name} (direct hit)")
                    return Path(temp_file.name)
            except Exception as e:
                self.logger.debug(f"[MOCKUP_FRAME_SERVICE] No photo in hinted company {company_hint}: {e}")

        # Fallback: search all companies
        for company in self.companies:
            if company == company_hint:
                continue
            try:
                data = await asset_mgmt_client.get_mockup_photo(
                    company,
                    location_key,
                    time_of_day,
                    side,
                    photo_filename,
                    environment,
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
        side: str = "all",
        environment: str = "all",
        company_hint: str | None = None,
    ) -> tuple[str, str, str, str, Path, str] | None:
        """
        Get a random photo for a location that has frame data.

        Handles both standalone and traditional networks:
        - Standalone: Fetches frames directly under network_key
        - Traditional: Resolves storage keys first, aggregates frames from all assets

        Args:
            location_key: Location identifier (network_key)
            time_of_day: "day", "night", or "all" for random (ignored for indoor)
            side: "gold", "silver", "single_side", or "all" for random (ignored for indoor)
            environment: "indoor", "outdoor", or "all" for random
            company_hint: Optional company to try first (from WorkflowContext)

        Returns:
            Tuple of (photo_filename, time_of_day, side, environment, photo_path, storage_key) or None
            The storage_key is the actual key where frames are stored (may differ from location_key
            for traditional networks).
        """
        self.logger.info(
            f"[MOCKUP_FRAME_SERVICE] Getting random photo for {location_key} "
            f"(env={environment}, time={time_of_day}, side={side})"
        )

        try:
            # First, resolve storage keys for traditional networks
            storage_info = await self.get_storage_info(location_key, include_all_assets=True)
            company = company_hint

            if storage_info:
                storage_keys = storage_info.get("storage_keys", [])
                company = storage_info.get("company") or company_hint
            else:
                # Fallback: use location_key directly
                storage_keys = [location_key]

            # Collect matching frames from all storage keys
            # matching is list of (storage_key, photo, tod, side, env)
            matching = []

            for storage_key in storage_keys:
                frames, found_company = await self.get_all_frames(storage_key, company_hint=company)
                if not frames:
                    continue

                # Update company hint if we found frames
                if found_company:
                    company = found_company

                for frame in frames:
                    env = frame.get("environment", "outdoor")
                    tod = frame.get("time_of_day", "day")
                    frame_side = frame.get("side", "gold")
                    photo = frame.get("photo_filename")

                    if not photo:
                        continue

                    if environment != "all" and env != environment:
                        continue

                    # For outdoor, apply time_of_day and side filters
                    if env == "outdoor":
                        if time_of_day != "all" and tod != time_of_day:
                            continue
                        if side != "all" and frame_side != side:
                            continue

                    matching.append((storage_key, photo, tod, frame_side, env))

            if not matching:
                self.logger.warning(
                    f"[MOCKUP_FRAME_SERVICE] No matching photos for {location_key} "
                    f"with env={environment}, time={time_of_day}, side={side}"
                )
                return None

            # Pick random
            selected_storage_key, photo_filename, selected_tod, selected_side, selected_env = random.choice(matching)

            self.logger.info(
                f"[MOCKUP_FRAME_SERVICE] Selected: {photo_filename} from {selected_storage_key} "
                f"({selected_env}/{selected_tod}/{selected_side})"
            )

            # Download the photo using the actual storage_key (not the original location_key)
            photo_path = await self.download_photo(
                selected_storage_key, selected_tod, selected_side, photo_filename,
                environment=selected_env,
                company_hint=company,
            )

            if not photo_path:
                return None

            return photo_filename, selected_tod, selected_side, selected_env, photo_path, selected_storage_key

        except Exception as e:
            self.logger.error(f"[MOCKUP_FRAME_SERVICE] Error getting random photo: {e}")
            return None

    async def has_mockup_frames(
        self,
        location_key: str,
        company_hint: str | None = None,
    ) -> bool:
        """
        Check if a location has any mockup frames available.

        Handles both standalone and traditional networks:
        - Standalone: Checks frames directly under network_key
        - Traditional: Gets storage keys first, then checks each asset path

        Args:
            location_key: Location identifier (network_key)
            company_hint: Optional company to try first (from WorkflowContext)

        Returns:
            True if at least one mockup frame exists
        """
        # First, try to get storage info to resolve traditional network paths
        storage_info = await self.get_storage_info(location_key, include_all_assets=True)

        if storage_info:
            storage_keys = storage_info.get("storage_keys", [])
            company = storage_info.get("company")

            # Check each storage key for frames
            for storage_key in storage_keys:
                frames, _ = await self.get_all_frames(storage_key, company_hint=company)
                if frames:
                    self.logger.info(
                        f"[MOCKUP_FRAME_SERVICE] Found frames for {location_key} at storage_key={storage_key}"
                    )
                    return True

            self.logger.info(f"[MOCKUP_FRAME_SERVICE] No frames found in any storage key for {location_key}")
            return False

        # Fallback: try direct lookup (backward compatibility)
        frames, _ = await self.get_all_frames(location_key, company_hint=company_hint)
        return len(frames) > 0

    async def is_portrait(
        self,
        location_key: str,
        company_hint: str | None = None,
    ) -> bool:
        """
        Check if a location has portrait orientation based on frame dimensions.

        Args:
            location_key: Location identifier
            company_hint: Optional company to try first (from WorkflowContext)

        Returns:
            True if height > width (portrait), False otherwise
        """
        import math

        try:
            frames, _ = await self.get_all_frames(location_key, company_hint=company_hint)
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

    async def get_storage_info(
        self,
        location_key: str,
        include_all_assets: bool = False,
    ) -> dict | None:
        """
        Get mockup storage info for a location.

        This is the key method for working with the unified architecture.
        Returns storage keys based on network type:
        - Standalone networks: returns network_key (mockups at network level)
        - Traditional networks: returns asset storage paths (mockups at asset level)

        Args:
            location_key: Location/network key
            include_all_assets: If True, returns ALL assets for traditional networks.
                               If False, returns only one sample per asset type.

        Returns:
            Dict with:
            - network_key: str
            - company: str
            - is_standalone: bool
            - storage_keys: list[str]
                - Standalone: [network_key]
                - Traditional: ["{network_key}/{type_key}/{asset_key}", ...]
            - assets: list[dict] - For traditional: asset details with storage_key
        """
        self.logger.info(f"[MOCKUP_FRAME_SERVICE] Getting storage info for {location_key} (include_all_assets={include_all_assets})")

        try:
            result = await asset_mgmt_client.get_mockup_storage_info(
                network_key=location_key,
                companies=self.companies,
                include_all_assets=include_all_assets,
            )

            if result:
                self.logger.info(
                    f"[MOCKUP_FRAME_SERVICE] Storage info for {location_key}: "
                    f"is_standalone={result.get('is_standalone')}, "
                    f"storage_keys={result.get('storage_keys', [])}"
                )
            return result

        except Exception as e:
            self.logger.error(f"[MOCKUP_FRAME_SERVICE] Error getting storage info: {e}")
            return None

    async def get_mockup_storage_keys(
        self,
        location_key: str,
    ) -> list[str]:
        """
        Get the storage keys for mockup operations.

        Convenience method that returns just the storage keys list.
        For standalone networks: returns [network_key]
        For traditional networks: returns [asset_key1, asset_key2, ...]

        Args:
            location_key: Location/network key

        Returns:
            List of storage keys for mockup operations
        """
        info = await self.get_storage_info(location_key)
        if info:
            return info.get("storage_keys", [])
        return []


# Convenience functions for module-level access


async def get_mockup_frame_service(
    companies: list[str] | str = "backlite_dubai"
) -> MockupFrameService:
    """Get a MockupFrameService instance."""
    return MockupFrameService(companies=companies)


async def has_mockup_frames(
    location_key: str,
    companies: list[str] | str = "backlite_dubai",
    company_hint: str | None = None,
) -> bool:
    """Check if location has mockup frames."""
    service = MockupFrameService(companies=companies)
    return await service.has_mockup_frames(location_key, company_hint=company_hint)


async def is_portrait_location(
    location_key: str,
    companies: list[str] | str = "backlite_dubai",
    company_hint: str | None = None,
) -> bool:
    """Check if location has portrait orientation."""
    service = MockupFrameService(companies=companies)
    return await service.is_portrait(location_key, company_hint=company_hint)
