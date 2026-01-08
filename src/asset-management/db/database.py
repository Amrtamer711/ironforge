"""
Database Router - Selects and exposes the appropriate database backend.

This module provides a unified interface to the database, automatically
selecting between SQLite and Supabase based on environment configuration.

Usage:
    from db.database import db

    # All methods are exposed directly:
    db.create_network(...)
    db.list_locations(...)
    db.check_location_eligibility(...)

Configuration:
    Set DB_BACKEND environment variable:
    - "sqlite" (default): Use local SQLite database
    - "supabase": Use Supabase cloud database

    For Supabase, also set:
    - SUPABASE_URL: Your Supabase project URL
    - SUPABASE_SERVICE_ROLE_KEY: Your Supabase service role key
"""

import logging
import os
from typing import Any

from db.backends.sqlite import SQLiteBackend
from db.base import DatabaseBackend
import config  # Import config to use service-specific env vars

logger = logging.getLogger("asset-management")

# Backend selection from environment
DB_BACKEND = os.getenv("DB_BACKEND", "sqlite").lower()


def _get_backend() -> DatabaseBackend:
    """
    Get the configured database backend.

    Returns:
        DatabaseBackend instance based on DB_BACKEND environment variable.

    Raises:
        RuntimeError: In production if Supabase credentials are missing
    """
    environment = os.getenv("ENVIRONMENT", "development")
    is_production = environment == "production"

    if DB_BACKEND == "supabase":
        # Use config values which derive from service-specific env vars
        supabase_url = config.SUPABASE_URL
        supabase_key = config.SUPABASE_SERVICE_KEY

        if not supabase_url or not supabase_key:
            if is_production:
                raise RuntimeError(
                    "[DB] FATAL: Supabase credentials missing in production. "
                    "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY, "
                    "or set DB_BACKEND=sqlite if SQLite is intended."
                )
            logger.warning("[DB] Supabase credentials not set, falling back to SQLite")
            return SQLiteBackend()

        try:
            from db.backends.supabase import SupabaseBackend
            logger.info("[DB] Using Supabase backend")
            return SupabaseBackend()
        except ImportError as e:
            if is_production:
                raise RuntimeError(f"[DB] FATAL: Supabase package not installed in production: {e}")
            logger.warning(f"[DB] Supabase package not installed ({e}), falling back to SQLite")
            return SQLiteBackend()
        except Exception as e:
            if is_production:
                raise RuntimeError(f"[DB] FATAL: Failed to initialize Supabase backend: {e}")
            logger.error(f"[DB] Failed to initialize Supabase backend: {e}")
            logger.info("[DB] Falling back to SQLite backend")
            return SQLiteBackend()
    else:
        logger.info("[DB] Using SQLite backend")
        return SQLiteBackend()


# Create the backend instance
_backend = _get_backend()

# Initialize the database
_backend.init_db()


class _DatabaseNamespace:
    """
    Namespace wrapper to expose backend methods as db.method() calls.

    This maintains a clean interface:
        from db.database import db
        db.list_networks(...)
    """

    def __init__(self, backend: DatabaseBackend):
        self._backend = backend

    @property
    def backend_name(self) -> str:
        """Get the name of the current backend."""
        return self._backend.name

    # =========================================================================
    # NETWORKS
    # =========================================================================

    def create_network(
        self,
        network_key: str,
        name: str,
        company_schema: str,
        description: str | None = None,
        created_by: str | None = None,
        # Unified architecture fields
        standalone: bool = False,
        display_type: str | None = None,
        series: str | None = None,
        height: str | None = None,
        width: str | None = None,
        number_of_faces: int | None = None,
        spot_duration: int | None = None,
        loop_duration: int | None = None,
        sov_percent: float | None = None,
        upload_fee: float | None = None,
        city: str | None = None,
        area: str | None = None,
        country: str | None = None,
        address: str | None = None,
        gps_lat: float | None = None,
        gps_lng: float | None = None,
        template_path: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any] | None:
        return self._backend.create_network(
            network_key=network_key,
            name=name,
            company_schema=company_schema,
            description=description,
            created_by=created_by,
            standalone=standalone,
            display_type=display_type,
            series=series,
            height=height,
            width=width,
            number_of_faces=number_of_faces,
            spot_duration=spot_duration,
            loop_duration=loop_duration,
            sov_percent=sov_percent,
            upload_fee=upload_fee,
            city=city,
            area=area,
            country=country,
            address=address,
            gps_lat=gps_lat,
            gps_lng=gps_lng,
            template_path=template_path,
            notes=notes,
        )

    def get_network(
        self,
        network_id: int,
        company_schemas: list[str],
    ) -> dict[str, Any] | None:
        return self._backend.get_network(network_id, company_schemas)

    def get_network_by_key(
        self,
        network_key: str,
        company_schemas: list[str],
    ) -> dict[str, Any] | None:
        return self._backend.get_network_by_key(network_key, company_schemas)

    def list_networks(
        self,
        company_schemas: list[str],
        include_inactive: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        return self._backend.list_networks(company_schemas, include_inactive, limit, offset)

    def update_network(
        self,
        network_id: int,
        company_schema: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        return self._backend.update_network(network_id, company_schema, updates)

    def delete_network(
        self,
        network_id: int,
        company_schema: str,
        hard_delete: bool = False,
    ) -> bool:
        return self._backend.delete_network(network_id, company_schema, hard_delete)

    # =========================================================================
    # ASSET TYPES
    # =========================================================================

    def create_asset_type(
        self,
        type_key: str,
        name: str,
        network_id: int,
        company_schema: str,
        description: str | None = None,
        specs: dict | None = None,
        created_by: str | None = None,
    ) -> dict[str, Any] | None:
        return self._backend.create_asset_type(
            type_key, name, network_id, company_schema, description, specs, created_by
        )

    def get_asset_type(
        self,
        type_id: int,
        company_schemas: list[str],
    ) -> dict[str, Any] | None:
        return self._backend.get_asset_type(type_id, company_schemas)

    def list_asset_types(
        self,
        company_schemas: list[str],
        network_id: int | None = None,
        include_inactive: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        return self._backend.list_asset_types(
            company_schemas, network_id, include_inactive, limit, offset
        )

    def update_asset_type(
        self,
        type_id: int,
        company_schema: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        return self._backend.update_asset_type(type_id, company_schema, updates)

    def delete_asset_type(
        self,
        type_id: int,
        company_schema: str,
        hard_delete: bool = False,
    ) -> bool:
        return self._backend.delete_asset_type(type_id, company_schema, hard_delete)

    # =========================================================================
    # LOCATIONS
    # =========================================================================

    def create_location(
        self,
        location_key: str,
        display_name: str,
        display_type: str,
        company_schema: str,
        network_id: int | None = None,
        type_id: int | None = None,
        created_by: str | None = None,
        **kwargs,
    ) -> dict[str, Any] | None:
        return self._backend.create_location(
            location_key, display_name, display_type, company_schema,
            network_id, type_id, created_by, **kwargs
        )

    def get_location(
        self,
        location_id: int,
        company_schemas: list[str],
    ) -> dict[str, Any] | None:
        return self._backend.get_location(location_id, company_schemas)

    def get_location_by_key(
        self,
        location_key: str,
        company_schemas: list[str],
    ) -> dict[str, Any] | None:
        return self._backend.get_location_by_key(location_key, company_schemas)

    def list_locations(
        self,
        company_schemas: list[str],
        network_id: int | None = None,
        type_id: int | None = None,
        include_inactive: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        return self._backend.list_locations(
            company_schemas, network_id, type_id, include_inactive, limit, offset
        )

    def update_location(
        self,
        location_id: int,
        company_schema: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        return self._backend.update_location(location_id, company_schema, updates)

    def delete_location(
        self,
        location_id: int,
        company_schema: str,
        hard_delete: bool = False,
    ) -> bool:
        return self._backend.delete_location(location_id, company_schema, hard_delete)

    # =========================================================================
    # PACKAGES
    # =========================================================================

    def create_package(
        self,
        package_key: str,
        name: str,
        company_schema: str,
        description: str | None = None,
        created_by: str | None = None,
    ) -> dict[str, Any] | None:
        return self._backend.create_package(
            package_key, name, company_schema, description, created_by
        )

    def get_package(
        self,
        package_id: int,
        company_schemas: list[str],
    ) -> dict[str, Any] | None:
        return self._backend.get_package(package_id, company_schemas)

    def list_packages(
        self,
        company_schemas: list[str],
        include_inactive: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        return self._backend.list_packages(company_schemas, include_inactive, limit, offset)

    def update_package(
        self,
        package_id: int,
        company_schema: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        return self._backend.update_package(package_id, company_schema, updates)

    def delete_package(
        self,
        package_id: int,
        company_schema: str,
        hard_delete: bool = False,
    ) -> bool:
        return self._backend.delete_package(package_id, company_schema, hard_delete)

    # =========================================================================
    # PACKAGE ITEMS
    # =========================================================================

    def add_package_item(
        self,
        package_id: int,
        company_schema: str,
        network_id: int,
    ) -> dict[str, Any] | None:
        """Add a network to a package. Unified architecture: only networks allowed."""
        return self._backend.add_package_item(
            package_id=package_id,
            company_schema=company_schema,
            network_id=network_id,
        )

    def remove_package_item(
        self,
        item_id: int,
        company_schema: str,
    ) -> bool:
        return self._backend.remove_package_item(item_id, company_schema)

    def get_package_items(
        self,
        package_id: int,
        company_schema: str,
    ) -> list[dict[str, Any]]:
        return self._backend.get_package_items(package_id, company_schema)

    def get_package_locations(
        self,
        package_id: int,
        company_schema: str,
    ) -> list[dict[str, Any]]:
        return self._backend.get_package_locations(package_id, company_schema)

    # =========================================================================
    # ELIGIBILITY
    # =========================================================================

    def check_location_eligibility(
        self,
        location_id: int,
        company_schemas: list[str],
    ) -> dict[str, Any]:
        return self._backend.check_location_eligibility(location_id, company_schemas)

    def check_network_eligibility(
        self,
        network_id: int,
        company_schemas: list[str],
    ) -> dict[str, Any]:
        return self._backend.check_network_eligibility(network_id, company_schemas)

    def get_eligible_locations(
        self,
        service: str,
        company_schemas: list[str],
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        return self._backend.get_eligible_locations(service, company_schemas, limit, offset)

    def get_eligible_networks(
        self,
        service: str,
        company_schemas: list[str],
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        return self._backend.get_eligible_networks(service, company_schemas, limit, offset)

    # =========================================================================
    # CROSS-SERVICE LOOKUPS
    # =========================================================================

    def has_mockup_frame(
        self,
        location_key: str,
        company_schema: str,
    ) -> bool:
        return self._backend.has_mockup_frame(location_key, company_schema)

    # =========================================================================
    # MOCKUP FRAMES
    # =========================================================================

    def list_mockup_frames(
        self,
        location_key: str,
        company_schema: str,
    ) -> list[dict[str, Any]]:
        """List all mockup frames for a location."""
        return self._backend.list_mockup_frames(location_key, company_schema)

    def save_mockup_frame(
        self,
        location_key: str,
        photo_filename: str,
        frames_data: list[dict],
        company_schema: str,
        environment: str = "outdoor",
        time_of_day: str = "day",
        side: str = "gold",
        created_by: str | None = None,
        config: dict | None = None,
    ) -> str:
        """Save mockup frame data. Returns auto-numbered filename."""
        return self._backend.save_mockup_frame(
            location_key, photo_filename, frames_data, company_schema,
            environment, time_of_day, side, created_by, config
        )

    def get_mockup_frame(
        self,
        location_key: str,
        company: str,
        environment: str = "outdoor",
        time_of_day: str = "day",
        side: str = "gold",
        photo_filename: str | None = None,
    ) -> dict[str, Any] | None:
        """Get specific mockup frame data."""
        return self._backend.get_mockup_frame(
            location_key, company, environment, time_of_day, side, photo_filename
        )

    def delete_mockup_frame(
        self,
        location_key: str,
        company: str,
        photo_filename: str,
        environment: str = "outdoor",
        time_of_day: str = "day",
        side: str = "gold",
    ) -> bool:
        """Delete a mockup frame."""
        return self._backend.delete_mockup_frame(
            location_key, company, photo_filename, environment, time_of_day, side
        )

    # =========================================================================
    # MOCKUP STORAGE INFO (Unified Architecture)
    # =========================================================================

    def get_mockup_storage_info(
        self,
        network_key: str,
        company_schemas: list[str],
    ) -> dict[str, Any] | None:
        """
        Get mockup storage info for a network.

        Resolves the correct storage key(s) based on whether the network is
        standalone or traditional.

        Returns:
            {
                "network_key": str,
                "company": str,
                "is_standalone": bool,
                "storage_keys": list[str],  # network_key for standalone, asset_keys for traditional
                "sample_assets": list[dict],  # For traditional: one per asset_type
            }
        """
        return self._backend.get_mockup_storage_info(network_key, company_schemas)


# Create the singleton database interface
db = _DatabaseNamespace(_backend)
