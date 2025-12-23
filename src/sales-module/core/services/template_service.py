"""
Template Service - Manages templates from Asset-Management.

Fetches templates from Asset-Management Supabase Storage via the Asset-Management API.
Templates are stored in Asset-Management because they are location-specific assets.
"""

import asyncio
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
        _logger = config.get_logger("core.services.template_service")
    return _logger


# Cache TTL in seconds (5 minutes)
CACHE_TTL = 300


class TemplateCache:
    """Thread-safe cache for template discovery results."""

    def __init__(self):
        self._templates: dict[str, dict[str, Any]] = {}  # {company: {location_key: info}}
        self._last_refresh: dict[str, float] = {}  # {company: timestamp}
        self._lock = asyncio.Lock()

    def is_stale(self, company: str) -> bool:
        """Check if cache needs refresh for company."""
        last = self._last_refresh.get(company, 0)
        return time.time() - last > CACHE_TTL

    async def refresh(self, company: str, templates: dict[str, dict[str, Any]]) -> None:
        """Update cache with new data for company."""
        async with self._lock:
            self._templates[company] = templates
            self._last_refresh[company] = time.time()

    def get_templates(self, company: str) -> dict[str, dict[str, Any]]:
        """Get cached templates for company."""
        return self._templates.get(company, {})

    def has_template(self, company: str, location_key: str) -> bool:
        """Check if template is in cache."""
        return location_key.lower() in self._templates.get(company, {})


# Global cache instance
_template_cache = TemplateCache()


class TemplateService:
    """
    Service for managing proposal templates from Asset-Management.

    Templates are stored in Asset-Management Supabase Storage and accessed
    via the Asset-Management API. This ensures templates are co-located
    with their location metadata.

    Responsibilities:
    - Discover templates from Asset-Management API
    - Cache template metadata with TTL
    - Download templates to temp files for processing
    - Check template existence

    Usage:
        service = TemplateService(company="backlite_dubai")

        # Check if template exists
        if await service.exists("dubai_mall"):
            template_path = await service.download_to_temp("dubai_mall")
            # Use template_path...
    """

    def __init__(self, company: str = "backlite_dubai"):
        """
        Initialize TemplateService.

        Args:
            company: Company schema (e.g., "backlite_dubai")
        """
        self.company = company
        self.logger = _get_logger()

    async def _discover_templates(self) -> dict[str, dict[str, Any]]:
        """
        Discover templates from Asset-Management API.

        Returns:
            Dict mapping location_key to template info
        """
        self.logger.info(f"[TEMPLATE_SERVICE] Discovering templates from Asset-Management for {self.company}")

        try:
            template_list = await asset_mgmt_client.list_templates(self.company)
            templates: dict[str, dict[str, Any]] = {}

            for t in template_list:
                location_key = t.get("location_key", "").lower().strip()
                if location_key:
                    templates[location_key] = {
                        "storage_key": t.get("storage_key"),
                        "company": self.company,
                        "location_key": t.get("location_key"),
                        "filename": t.get("filename"),
                    }

            self.logger.info(f"[TEMPLATE_SERVICE] Discovered {len(templates)} templates")
            return templates

        except Exception as e:
            self.logger.error(f"[TEMPLATE_SERVICE] Error discovering templates: {e}")
            return {}

    async def refresh_cache(self) -> None:
        """Force refresh the template cache."""
        templates = await self._discover_templates()
        await _template_cache.refresh(self.company, templates)
        self.logger.info(f"[TEMPLATE_SERVICE] Cache refreshed with {len(templates)} templates")

    async def _ensure_cache(self) -> None:
        """Ensure cache is populated and fresh."""
        if _template_cache.is_stale(self.company):
            await self.refresh_cache()

    async def get_templates(self) -> dict[str, dict[str, Any]]:
        """
        Get all discovered templates for company.

        Returns:
            Dict mapping location_key to template info
        """
        await self._ensure_cache()
        return _template_cache.get_templates(self.company)

    async def exists(self, location_key: str) -> bool:
        """
        Check if a template exists for the given location.

        Args:
            location_key: Location identifier (e.g., "dubai_mall")

        Returns:
            True if template exists
        """
        # First check cache
        await self._ensure_cache()
        normalized = location_key.lower().strip()
        if _template_cache.has_template(self.company, normalized):
            return True

        # Fallback: check via API
        try:
            return await asset_mgmt_client.template_exists(self.company, location_key)
        except Exception:
            return False

    async def download(self, location_key: str) -> bytes | None:
        """
        Download template file contents from Asset-Management.

        Args:
            location_key: Location identifier

        Returns:
            File bytes or None if not found
        """
        self.logger.info(f"[TEMPLATE_SERVICE] Downloading template: {location_key}")

        try:
            data = await asset_mgmt_client.get_template(self.company, location_key)
            if data:
                self.logger.info(f"[TEMPLATE_SERVICE] Downloaded template: {location_key}")
                return data
            self.logger.warning(f"[TEMPLATE_SERVICE] Template not found: {location_key}")
            return None
        except Exception as e:
            self.logger.error(f"[TEMPLATE_SERVICE] Failed to download {location_key}: {e}")
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
        Download an intro/outro PDF from Asset-Management storage.

        Args:
            pdf_name: Name of PDF (e.g., "landmark_series", "rest", "digital_icons")

        Returns:
            PDF bytes or None if not found
        """
        try:
            data = await asset_mgmt_client.get_intro_outro_pdf(self.company, pdf_name)
            if data:
                self.logger.info(f"[TEMPLATE_SERVICE] Downloaded intro/outro PDF: {pdf_name}")
                return data
            self.logger.debug(f"[TEMPLATE_SERVICE] Intro/outro PDF not found: {pdf_name}")
            return None
        except Exception as e:
            self.logger.debug(f"[TEMPLATE_SERVICE] Error getting intro/outro PDF: {e}")
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


async def get_template_service(company: str = "backlite_dubai") -> TemplateService:
    """Get a TemplateService instance."""
    return TemplateService(company=company)


async def template_exists(location_key: str, company: str = "backlite_dubai") -> bool:
    """Check if template exists for location."""
    service = TemplateService(company=company)
    return await service.exists(location_key)


async def download_template(location_key: str, company: str = "backlite_dubai") -> str | None:
    """Download template to temp file."""
    service = TemplateService(company=company)
    return await service.download_to_temp(location_key)


async def get_template_mapping(company: str = "backlite_dubai") -> dict[str, dict[str, Any]]:
    """Get all templates with their info."""
    service = TemplateService(company=company)
    return await service.get_templates()
