"""
Template Service - Manages templates from Asset-Management.

Fetches templates from Asset-Management Supabase Storage via the Asset-Management API.
Templates are stored in Asset-Management because they are location-specific assets.
"""

import asyncio
import os
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
    - Check template existence across multiple companies

    Usage:
        service = TemplateService(companies=["backlite_dubai", "backlite_uk"])

        # Check if template exists (searches all companies)
        if await service.exists("dubai_mall"):
            template_path = await service.download_to_temp("dubai_mall")
            # Use template_path...
    """

    def __init__(self, companies: list[str] | str):
        """
        Initialize TemplateService.

        Args:
            companies: Company schema(s) - can be a single string or list of companies.
                       Required - no defaults allowed.
        """
        # Normalize to list
        if isinstance(companies, str):
            self.companies = [companies]
        else:
            self.companies = list(companies)

        if not self.companies:
            raise ValueError("At least one company must be provided")

        self.logger = _get_logger()

        # Request-scoped cache for downloaded templates
        # Avoids re-downloading the same template within a single request
        # Maps: location_key -> temp file path
        self._downloaded_templates: dict[str, str] = {}

        # Request-scoped cache for downloaded intro/outro PDFs
        # Avoids re-downloading the same PDF within a single request
        # Maps: pdf_name -> temp file path
        self._downloaded_intro_outro: dict[str, str] = {}

    async def _discover_templates_for_company(self, company: str) -> dict[str, dict[str, Any]]:
        """
        Discover templates from Asset-Management API for a single company.

        Args:
            company: Company schema

        Returns:
            Dict mapping location_key to template info
        """
        self.logger.info(f"[TEMPLATE_SERVICE] Discovering templates for {company}")

        try:
            template_list = await asset_mgmt_client.list_templates(company)
            templates: dict[str, dict[str, Any]] = {}

            for t in template_list:
                location_key = t.get("location_key", "").lower().strip()
                if location_key:
                    templates[location_key] = {
                        "storage_key": t.get("storage_key"),
                        "company": company,
                        "location_key": t.get("location_key"),
                        "filename": t.get("filename"),
                    }

            self.logger.info(f"[TEMPLATE_SERVICE] Discovered {len(templates)} templates in {company}")
            return templates

        except Exception as e:
            self.logger.error(f"[TEMPLATE_SERVICE] Error discovering templates for {company}: {e}")
            return {}

    async def refresh_cache(self, company: str) -> None:
        """Force refresh the template cache for a company."""
        templates = await self._discover_templates_for_company(company)
        await _template_cache.refresh(company, templates)

    async def _ensure_cache(self, company: str) -> None:
        """Ensure cache is populated and fresh for a company."""
        if _template_cache.is_stale(company):
            await self.refresh_cache(company)

    async def get_templates(self) -> dict[str, dict[str, Any]]:
        """
        Get all discovered templates across all companies.

        Returns:
            Dict mapping location_key to template info
        """
        all_templates: dict[str, dict[str, Any]] = {}

        for company in self.companies:
            await self._ensure_cache(company)
            company_templates = _template_cache.get_templates(company)
            all_templates.update(company_templates)

        return all_templates

    async def exists(self, location_key: str) -> tuple[bool, str | None]:
        """
        Check if a template exists for the given location across all companies.

        Args:
            location_key: Location identifier (e.g., "dubai_mall")

        Returns:
            Tuple of (exists, company_that_has_it)
        """
        normalized = location_key.lower().strip()

        for company in self.companies:
            # First check cache
            await self._ensure_cache(company)
            if _template_cache.has_template(company, normalized):
                return True, company

            # Fallback: check via API
            try:
                if await asset_mgmt_client.template_exists(company, location_key):
                    return True, company
            except Exception:
                continue

        return False, None

    async def download(
        self,
        location_key: str,
        company_hint: str | None = None,
    ) -> tuple[bytes | None, str | None]:
        """
        Download template file contents from Asset-Management.

        If company_hint is provided, tries that company first for O(1) lookup.
        Falls back to searching all companies if hint fails.

        Args:
            location_key: Location identifier
            company_hint: Optional company to try first (from WorkflowContext)

        Returns:
            Tuple of (file_bytes, company_that_had_it) or (None, None) if not found
        """
        self.logger.info(f"[TEMPLATE_SERVICE] Downloading template: {location_key}")

        # Try company_hint first if provided (O(1) lookup from WorkflowContext)
        if company_hint and company_hint in self.companies:
            try:
                data = await asset_mgmt_client.get_template(company_hint, location_key)
                if data:
                    self.logger.info(f"[TEMPLATE_SERVICE] Downloaded template from {company_hint}: {location_key} (direct hit)")
                    return data, company_hint
            except Exception as e:
                self.logger.debug(f"[TEMPLATE_SERVICE] Template not in hinted company {company_hint}: {e}")

        # Fallback: search all companies (skip the hint if we already tried it)
        for company in self.companies:
            if company == company_hint:
                continue  # Already tried this one
            try:
                data = await asset_mgmt_client.get_template(company, location_key)
                if data:
                    self.logger.info(f"[TEMPLATE_SERVICE] Downloaded template from {company}: {location_key}")
                    return data, company
            except Exception as e:
                self.logger.debug(f"[TEMPLATE_SERVICE] Template not in {company}: {e}")
                continue

        self.logger.warning(f"[TEMPLATE_SERVICE] Template not found in any company: {location_key}")
        return None, None

    async def download_to_temp(
        self,
        location_key: str,
        suffix: str = ".pptx",
        company_hint: str | None = None,
    ) -> str | None:
        """
        Download template to a temporary file.

        Uses request-scoped cache to avoid re-downloading the same template
        multiple times within a single request (e.g., combined proposals).

        Args:
            location_key: Location identifier
            suffix: File extension for temp file
            company_hint: Optional company to try first (from WorkflowContext)

        Returns:
            Path to temp file or None if download failed
        """
        normalized_key = location_key.lower().strip()

        # Check request-scoped cache first
        if normalized_key in self._downloaded_templates:
            cached_path = self._downloaded_templates[normalized_key]
            # Verify file still exists (might have been deleted by parallel task)
            if os.path.exists(cached_path):
                self.logger.info(f"[TEMPLATE_SERVICE] Cache hit for template: {location_key} -> {cached_path}")
                return cached_path
            else:
                # File was deleted, remove from cache and re-download
                self.logger.debug(f"[TEMPLATE_SERVICE] Cached file deleted, re-downloading: {location_key}")
                del self._downloaded_templates[normalized_key]

        data, _ = await self.download(location_key, company_hint=company_hint)
        if not data:
            return None

        # Create temp file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        temp_file.write(data)
        temp_file.close()

        # Cache the path for subsequent requests within this instance
        self._downloaded_templates[normalized_key] = temp_file.name

        self.logger.info(f"[TEMPLATE_SERVICE] Template saved to: {temp_file.name}")
        return temp_file.name

    async def get_intro_outro_pdf(
        self,
        pdf_name: str,
        company_hint: str | None = None,
    ) -> tuple[bytes | None, str | None]:
        """
        Download an intro/outro PDF from Asset-Management storage.

        If company_hint is provided, tries that company first for O(1) lookup.
        Falls back to searching all companies if hint fails.

        Args:
            pdf_name: Name of PDF (e.g., "landmark_series", "rest", "digital_icons")
            company_hint: Optional company to try first (from WorkflowContext)

        Returns:
            Tuple of (pdf_bytes, company) or (None, None) if not found
        """
        # Try company_hint first if provided (O(1) lookup from WorkflowContext)
        if company_hint and company_hint in self.companies:
            try:
                data = await asset_mgmt_client.get_intro_outro_pdf(company_hint, pdf_name)
                if data:
                    self.logger.info(f"[TEMPLATE_SERVICE] Downloaded intro/outro PDF from {company_hint}: {pdf_name} (direct hit)")
                    return data, company_hint
            except Exception as e:
                self.logger.debug(f"[TEMPLATE_SERVICE] Intro/outro PDF not in hinted company {company_hint}: {e}")

        # Fallback: search all companies (skip the hint if we already tried it)
        for company in self.companies:
            if company == company_hint:
                continue  # Already tried this one
            try:
                data = await asset_mgmt_client.get_intro_outro_pdf(company, pdf_name)
                if data:
                    self.logger.info(f"[TEMPLATE_SERVICE] Downloaded intro/outro PDF from {company}: {pdf_name}")
                    return data, company
            except Exception:
                continue

        self.logger.debug(f"[TEMPLATE_SERVICE] Intro/outro PDF not found: {pdf_name}")
        return None, None

    async def download_intro_outro_to_temp(
        self,
        pdf_name: str,
        company_hint: str | None = None,
    ) -> str | None:
        """
        Download intro/outro PDF to a temporary file.

        Uses request-scoped cache to avoid re-downloading the same PDF
        multiple times within a single request (e.g., combined proposals).

        Args:
            pdf_name: Name of PDF (e.g., "landmark_series", "rest")
            company_hint: Optional company to try first (from WorkflowContext)

        Returns:
            Path to temp file or None if not found
        """
        # Check request-scoped cache first
        if pdf_name in self._downloaded_intro_outro:
            cached_path = self._downloaded_intro_outro[pdf_name]
            # Verify file still exists (might have been deleted by parallel task)
            if os.path.exists(cached_path):
                self.logger.info(f"[TEMPLATE_SERVICE] Cache hit for intro/outro PDF: {pdf_name} -> {cached_path}")
                return cached_path
            else:
                # File was deleted, remove from cache and re-download
                self.logger.debug(f"[TEMPLATE_SERVICE] Cached PDF deleted, re-downloading: {pdf_name}")
                del self._downloaded_intro_outro[pdf_name]

        data, _ = await self.get_intro_outro_pdf(pdf_name, company_hint=company_hint)
        if not data:
            return None

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        temp_file.write(data)
        temp_file.close()

        # Cache the path for subsequent requests within this instance
        self._downloaded_intro_outro[pdf_name] = temp_file.name

        self.logger.info(f"[TEMPLATE_SERVICE] Intro/outro PDF saved to: {temp_file.name}")
        return temp_file.name

    async def upload(
        self,
        location_key: str,
        file_data: bytes,
        company: str,
        filename: str | None = None,
    ) -> bool:
        """
        Upload template to Asset-Management storage.

        Args:
            location_key: Location identifier
            file_data: Template file bytes
            company: Target company to upload to (required for writes)
            filename: Optional custom filename

        Returns:
            True if upload succeeded
        """
        if company not in self.companies:
            self.logger.error(f"[TEMPLATE_SERVICE] Company {company} not in user's companies")
            return False

        self.logger.info(f"[TEMPLATE_SERVICE] Uploading template to {company}: {location_key}")
        result = await asset_mgmt_client.upload_template(
            company,
            location_key,
            file_data,
            filename,
        )
        if result and result.get("success"):
            # Invalidate cache for this company
            await self.refresh_cache(company)
            self.logger.info(f"[TEMPLATE_SERVICE] Template uploaded to {company}: {location_key}")
            return True
        self.logger.error(f"[TEMPLATE_SERVICE] Failed to upload template: {location_key}")
        return False

    async def upload_from_path(
        self,
        location_key: str,
        file_path: str | Path,
        company: str,
    ) -> bool:
        """
        Upload template from a file path.

        Args:
            location_key: Location identifier
            file_path: Path to the template file
            company: Target company to upload to

        Returns:
            True if upload succeeded
        """
        file_path = Path(file_path)
        if not file_path.exists():
            self.logger.error(f"[TEMPLATE_SERVICE] File not found: {file_path}")
            return False

        with open(file_path, "rb") as f:
            file_data = f.read()

        return await self.upload(location_key, file_data, company, file_path.name)

    async def delete(self, location_key: str, company: str) -> bool:
        """
        Delete template from Asset-Management storage.

        Args:
            location_key: Location identifier
            company: Company to delete from (required for writes)

        Returns:
            True if delete succeeded
        """
        if company not in self.companies:
            self.logger.error(f"[TEMPLATE_SERVICE] Company {company} not in user's companies")
            return False

        self.logger.info(f"[TEMPLATE_SERVICE] Deleting template from {company}: {location_key}")
        result = await asset_mgmt_client.delete_template(company, location_key)
        if result and result.get("success"):
            # Invalidate cache for this company
            await self.refresh_cache(company)
            self.logger.info(f"[TEMPLATE_SERVICE] Template deleted from {company}: {location_key}")
            return True
        self.logger.error(f"[TEMPLATE_SERVICE] Failed to delete template: {location_key}")
        return False
