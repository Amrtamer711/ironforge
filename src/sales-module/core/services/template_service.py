"""
Template Service - Manages templates in Supabase Storage.

Handles template discovery, caching, and downloads from Supabase Storage.
Replaces the filesystem-based template discovery in config.py.
"""

import asyncio
import tempfile
import time
from pathlib import Path
from typing import Any

from integrations.storage import get_storage_client

# Lazy import to avoid circular dependency
_logger = None


def _get_logger():
    global _logger
    if _logger is None:
        import config
        _logger = config.get_logger("core.services.template_service")
    return _logger


# Cache TTL in seconds (5 minutes)
CACHE_TTL = 300


class TemplateCache:
    """Thread-safe cache for template discovery results."""

    def __init__(self):
        self._templates: dict[str, dict[str, Any]] = {}
        self._mapping: dict[str, str] = {}  # location_key -> storage_key
        self._last_refresh: float = 0
        self._lock = asyncio.Lock()

    def is_stale(self) -> bool:
        """Check if cache needs refresh."""
        return time.time() - self._last_refresh > CACHE_TTL

    async def refresh(self, templates: dict[str, dict[str, Any]], mapping: dict[str, str]) -> None:
        """Update cache with new data."""
        async with self._lock:
            self._templates = templates
            self._mapping = mapping
            self._last_refresh = time.time()

    def get_templates(self) -> dict[str, dict[str, Any]]:
        """Get cached templates."""
        return self._templates

    def get_mapping(self) -> dict[str, str]:
        """Get cached location_key -> storage_key mapping."""
        return self._mapping


# Global cache instance
_template_cache = TemplateCache()


class TemplateService:
    """
    Service for managing proposal templates in Supabase Storage.

    Responsibilities:
    - Discover templates from Supabase Storage bucket
    - Cache template metadata with TTL
    - Download templates to temp files for processing
    - Check template existence

    Usage:
        service = TemplateService()

        # Check if template exists
        if await service.exists("dubai_mall"):
            template_path = await service.download_to_temp("dubai_mall")
            # Use template_path...
    """

    BUCKET = "templates"

    def __init__(self):
        self.logger = _get_logger()

    async def _discover_templates(self) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
        """
        Discover templates from Supabase Storage.

        Scans the templates bucket and builds a mapping of location keys
        to their storage paths and metadata.

        Returns:
            Tuple of (templates dict, mapping dict)
            - templates: {location_key: {storage_key, company, filename, ...}}
            - mapping: {location_key: storage_key}
        """
        storage = get_storage_client()
        templates: dict[str, dict[str, Any]] = {}
        mapping: dict[str, str] = {}

        self.logger.info("[TEMPLATE_SERVICE] Starting template discovery from Supabase Storage")

        try:
            # List all files in templates bucket
            result = await storage.list_files(self.BUCKET, limit=1000)

            if not result.success:
                self.logger.error(f"[TEMPLATE_SERVICE] Failed to list templates: {result.error}")
                return templates, mapping

            for file in result.files:
                # Expected structure: {company}/{location_key}/{location_key}.pptx
                # or: {company}/{location_key}/metadata.txt
                key = file.key
                if not key.endswith(".pptx"):
                    continue

                # Parse the path
                parts = key.split("/")
                if len(parts) < 3:
                    self.logger.warning(f"[TEMPLATE_SERVICE] Skipping malformed path: {key}")
                    continue

                company = parts[0]
                location_key = parts[1]
                filename = parts[-1]

                # Normalize location key
                normalized_key = location_key.lower().strip()

                templates[normalized_key] = {
                    "storage_key": key,
                    "company": company,
                    "location_key": location_key,
                    "filename": filename,
                    "size": file.size,
                }
                mapping[normalized_key] = key

                self.logger.debug(f"[TEMPLATE_SERVICE] Found template: {normalized_key} -> {key}")

            self.logger.info(f"[TEMPLATE_SERVICE] Discovered {len(templates)} templates")
            return templates, mapping

        except Exception as e:
            self.logger.error(f"[TEMPLATE_SERVICE] Error discovering templates: {e}")
            return templates, mapping

    async def refresh_cache(self) -> None:
        """Force refresh the template cache."""
        templates, mapping = await self._discover_templates()
        await _template_cache.refresh(templates, mapping)
        self.logger.info(f"[TEMPLATE_SERVICE] Cache refreshed with {len(templates)} templates")

    async def _ensure_cache(self) -> None:
        """Ensure cache is populated and fresh."""
        if _template_cache.is_stale():
            await self.refresh_cache()

    async def get_templates(self) -> dict[str, dict[str, Any]]:
        """
        Get all discovered templates.

        Returns:
            Dict mapping location_key to template info
        """
        await self._ensure_cache()
        return _template_cache.get_templates()

    async def get_mapping(self) -> dict[str, str]:
        """
        Get location_key -> storage_key mapping.

        Returns:
            Dict mapping location_key to storage path
        """
        await self._ensure_cache()
        return _template_cache.get_mapping()

    async def exists(self, location_key: str) -> bool:
        """
        Check if a template exists for the given location.

        Args:
            location_key: Location identifier (e.g., "dubai_mall")

        Returns:
            True if template exists in storage
        """
        await self._ensure_cache()
        normalized = location_key.lower().strip()
        return normalized in _template_cache.get_mapping()

    async def get_storage_key(self, location_key: str) -> str | None:
        """
        Get the storage key for a location's template.

        Args:
            location_key: Location identifier

        Returns:
            Storage key (path in bucket) or None if not found
        """
        await self._ensure_cache()
        normalized = location_key.lower().strip()
        return _template_cache.get_mapping().get(normalized)

    async def download(self, location_key: str) -> bytes | None:
        """
        Download template file contents.

        Args:
            location_key: Location identifier

        Returns:
            File bytes or None if not found
        """
        storage_key = await self.get_storage_key(location_key)
        if not storage_key:
            self.logger.warning(f"[TEMPLATE_SERVICE] Template not found: {location_key}")
            return None

        storage = get_storage_client()
        result = await storage.download(self.BUCKET, storage_key)

        if result.success:
            self.logger.info(f"[TEMPLATE_SERVICE] Downloaded template: {storage_key}")
            return result.data

        self.logger.error(f"[TEMPLATE_SERVICE] Failed to download {storage_key}: {result.error}")
        return None

    async def download_to_temp(self, location_key: str, suffix: str = ".pptx") -> str | None:
        """
        Download template to a temporary file.

        Args:
            location_key: Location identifier
            suffix: File extension for temp file

        Returns:
            Path to temp file or None if download failed
        """
        data = await self.download(location_key)
        if not data:
            return None

        # Create temp file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        temp_file.write(data)
        temp_file.close()

        self.logger.info(f"[TEMPLATE_SERVICE] Template saved to: {temp_file.name}")
        return temp_file.name

    async def get_intro_outro_pdf(self, pdf_name: str) -> bytes | None:
        """
        Download an intro/outro PDF from storage.

        Args:
            pdf_name: Name of PDF (e.g., "landmark_series", "rest", "digital_icons")

        Returns:
            PDF bytes or None if not found
        """
        storage = get_storage_client()
        storage_key = f"intro_outro/{pdf_name}.pdf"

        result = await storage.download(self.BUCKET, storage_key)
        if result.success:
            self.logger.info(f"[TEMPLATE_SERVICE] Downloaded intro/outro PDF: {pdf_name}")
            return result.data

        self.logger.debug(f"[TEMPLATE_SERVICE] Intro/outro PDF not found: {storage_key}")
        return None

    async def download_intro_outro_to_temp(self, pdf_name: str) -> str | None:
        """
        Download intro/outro PDF to a temporary file.

        Args:
            pdf_name: Name of PDF (e.g., "landmark_series", "rest")

        Returns:
            Path to temp file or None if not found
        """
        data = await self.get_intro_outro_pdf(pdf_name)
        if not data:
            return None

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        temp_file.write(data)
        temp_file.close()

        return temp_file.name


# Convenience functions for module-level access


async def get_template_service() -> TemplateService:
    """Get a TemplateService instance."""
    return TemplateService()


async def template_exists(location_key: str) -> bool:
    """Check if template exists for location."""
    service = TemplateService()
    return await service.exists(location_key)


async def download_template(location_key: str) -> str | None:
    """Download template to temp file."""
    service = TemplateService()
    return await service.download_to_temp(location_key)


async def get_template_mapping() -> dict[str, str]:
    """Get location_key -> storage_key mapping."""
    service = TemplateService()
    return await service.get_mapping()
