"""
Supabase database backend implementation for Asset Management.

This backend uses Supabase for cloud-hosted PostgreSQL storage with
multi-schema support for company isolation.
"""

import asyncio
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

from config import COMPANY_SCHEMAS, SUPABASE_URL, SUPABASE_SERVICE_KEY
from db.base import DatabaseBackend

logger = logging.getLogger("asset-management")

# Cache TTLs (in seconds)
NETWORK_CACHE_TTL = 1800  # 30 minutes for networks (rarely change)
LOCATION_CACHE_TTL = 600  # 10 minutes for locations
ASSET_TYPE_CACHE_TTL = 1800  # 30 minutes for asset types
PACKAGE_CACHE_TTL = 900  # 15 minutes for packages
FRAME_CACHE_TTL = 600  # 10 minutes for frames
NETWORK_ASSET_CACHE_TTL = 600  # 10 minutes for network assets


def _run_async(coro):
    """Run async code from sync context."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    else:
        return asyncio.run(coro)


class SupabaseOperationError(Exception):
    """Custom exception for Supabase operation failures."""
    pass


class SupabaseBackend(DatabaseBackend):
    """
    Supabase database backend implementation.

    Uses Supabase's PostgreSQL database with multi-schema support
    for company data isolation.
    """

    def __init__(self):
        """Initialize Supabase backend using config values."""
        self._client = None
        self._cache = None
        self._cache_initialized = False

        # Use config values which derive from service-specific env vars
        self._url = SUPABASE_URL
        self._key = SUPABASE_SERVICE_KEY

        if not self._url or not self._key:
            logger.warning(
                "[SUPABASE] Credentials not configured. "
                "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables."
            )

    # ========== CACHE METHODS ==========

    def _get_cache(self):
        """Get the cache backend (lazy initialization)."""
        if self._cache is not None:
            return self._cache

        if self._cache_initialized:
            return None

        self._cache_initialized = True

        try:
            from crm_cache import get_cache
            self._cache = get_cache()
            logger.info("[CACHE] Cache backend initialized for asset-management")
            return self._cache
        except ImportError:
            logger.warning("[CACHE] crm_cache not installed, caching disabled")
            return None
        except Exception as e:
            logger.warning(f"[CACHE] Failed to initialize cache: {e}")
            return None

    async def _cache_get(self, key: str) -> Any | None:
        """Get value from cache."""
        cache = self._get_cache()
        if not cache:
            return None
        try:
            return await cache.get(key)
        except Exception as e:
            logger.debug(f"[CACHE] Get error: {e}")
            return None

    async def _cache_set(self, key: str, value: Any, ttl: int = 300) -> None:
        """Set value in cache."""
        cache = self._get_cache()
        if not cache:
            return
        try:
            await cache.set(key, value, ttl=ttl)
        except Exception as e:
            logger.debug(f"[CACHE] Set error: {e}")

    async def _cache_delete(self, key: str) -> None:
        """Delete a specific cache key."""
        cache = self._get_cache()
        if not cache:
            return
        try:
            await cache.delete(key)
        except Exception as e:
            logger.debug(f"[CACHE] Delete error: {e}")

    async def _cache_delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern."""
        cache = self._get_cache()
        if not cache:
            return 0
        try:
            return await cache.delete_pattern(pattern)
        except Exception as e:
            logger.debug(f"[CACHE] Delete pattern error: {e}")
            return 0

    def invalidate_asset_caches(self, schemas: list[str] | None = None) -> None:
        """Invalidate all asset-related caches."""
        _run_async(self._cache_delete_pattern("networks:*"))
        _run_async(self._cache_delete_pattern("network:*"))
        _run_async(self._cache_delete_pattern("network_key:*"))
        _run_async(self._cache_delete_pattern("locations:*"))
        _run_async(self._cache_delete_pattern("location:*"))
        _run_async(self._cache_delete_pattern("location_id:*"))
        _run_async(self._cache_delete_pattern("asset_types:*"))
        _run_async(self._cache_delete_pattern("asset_type:*"))
        _run_async(self._cache_delete_pattern("packages:*"))
        _run_async(self._cache_delete_pattern("frames:*"))
        logger.info("[CACHE] Invalidated asset caches")

    def invalidate_frames_cache(self, location_key: str, company_schema: str) -> None:
        """Invalidate frames cache for a specific location."""
        cache_key = f"frames:{location_key.lower()}:{company_schema}"
        _run_async(self._cache_delete_pattern(cache_key))
        logger.debug(f"[CACHE] Invalidated frames cache for {location_key}")

    @property
    def name(self) -> str:
        return "supabase"

    def _get_client(self):
        """Get or create Supabase client (lazy initialization)."""
        if self._client is not None:
            return self._client

        if not self._url or not self._key:
            raise RuntimeError("Supabase credentials not configured")

        try:
            from supabase import create_client
            from supabase.lib.client_options import ClientOptions

            # Use longer timeouts (seconds) to handle slow network conditions
            options = ClientOptions(
                postgrest_client_timeout=30,
                storage_client_timeout=60,
            )
            self._client = create_client(self._url, self._key, options=options)
            logger.info("[SUPABASE] Client initialized successfully")
            return self._client
        except ImportError:
            raise RuntimeError("supabase package not installed. Run: pip install supabase")
        except Exception as e:
            logger.error(f"[SUPABASE] Failed to initialize client: {e}")
            raise

    def init_db(self) -> None:
        """
        Initialize Supabase connection.

        Note: Schema is managed through SQL migrations, not here.
        This method only verifies connectivity.
        """
        try:
            self._get_client()
            logger.info("[SUPABASE] Database connection verified")
            logger.info("[SUPABASE] Expected tables: networks, asset_types, locations, packages, package_items")
        except Exception as e:
            logger.error(f"[SUPABASE] Failed to initialize: {e}")
            raise

    def _now(self) -> str:
        """Get current timestamp in ISO format."""
        return datetime.utcnow().isoformat()

    # =========================================================================
    # MULTI-SCHEMA HELPERS
    # =========================================================================

    def _find_in_schemas(
        self,
        table: str,
        filters: dict[str, Any],
        user_companies: list[str],
        select: str = "*",
    ) -> tuple[dict | None, str | None, str]:
        """
        Search for a record across all company schemas IN PARALLEL with access control.

        Args:
            table: Table name to query
            filters: Dict of column->value filters (applied with .eq())
            user_companies: List of schemas the user can access
            select: Columns to select (default "*")

        Returns:
            Tuple of (data, found_schema, status) where:
            - data: The record if found and accessible, None otherwise
            - found_schema: Schema where record was found, None if not found
            - status: "found", "not_found", or "access_denied"
        """
        client = self._get_client()

        def search_schema(schema: str) -> tuple[str, Any]:
            """Search a single schema, return (schema, data) tuple."""
            try:
                query = client.schema(schema).table(table).select(select)
                for col, val in filters.items():
                    query = query.eq(col, val)
                response = query.execute()
                if response.data:
                    return (schema, response.data[0] if len(response.data) == 1 else response.data)
                return (schema, None)
            except Exception as e:
                logger.debug(f"[SUPABASE] Error searching {schema}.{table}: {e}")
                return (schema, None)

        # Search all schemas in parallel
        with ThreadPoolExecutor(max_workers=len(COMPANY_SCHEMAS)) as executor:
            results = list(executor.map(search_schema, COMPANY_SCHEMAS))

        # Find first match and check access
        for schema, data in results:
            if data:
                if schema in user_companies:
                    # Add company_schema to the result
                    if isinstance(data, dict):
                        data["company_schema"] = schema
                    elif isinstance(data, list):
                        for item in data:
                            item["company_schema"] = schema
                    return (data, schema, "found")
                else:
                    # Found but user can't access
                    return (None, schema, "access_denied")

        return (None, None, "not_found")

    def _query_schemas(
        self,
        table: str,
        company_schemas: list[str],
        select: str = "*",
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Query a table across multiple company schemas IN PARALLEL and aggregate results.

        Args:
            table: Table name to query
            company_schemas: List of schemas to query
            select: Columns to select
            filters: Optional dict of column->value filters
            order_by: Optional column to order by
            limit: Optional limit per schema
            offset: Optional offset per schema

        Returns:
            List of records from all schemas, each with 'company_schema' field
        """
        client = self._get_client()

        def query_single_schema(schema: str) -> list[dict[str, Any]]:
            """Query a single schema, return list of records with company_schema added."""
            try:
                query = client.schema(schema).table(table).select(select)

                if filters:
                    for col, val in filters.items():
                        if val is None:
                            query = query.is_(col, "null")
                        else:
                            query = query.eq(col, val)

                if order_by:
                    query = query.order(order_by)
                if limit:
                    query = query.limit(limit)
                if offset:
                    query = query.offset(offset)

                response = query.execute()

                if response.data:
                    for record in response.data:
                        record["company_schema"] = schema
                    return response.data
                return []
            except Exception as e:
                logger.error(f"[SUPABASE] Error querying {schema}.{table}: {e}")
                return []

        # Query all schemas in parallel
        with ThreadPoolExecutor(max_workers=len(company_schemas)) as executor:
            results = list(executor.map(query_single_schema, company_schemas))

        # Flatten results
        return [record for schema_results in results for record in schema_results]

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
        # New fields for unified architecture
        standalone: bool = False,
        series: str | None = None,
        sov_percent: float | None = None,
        upload_fee: float | None = None,
        spot_duration: int | None = None,
        loop_duration: int | None = None,
        number_of_faces: int | None = None,
        template_path: str | None = None,
        # Location fields (for standalone networks)
        display_type: str | None = None,
        height: str | None = None,
        width: str | None = None,
        city: str | None = None,
        area: str | None = None,
        address: str | None = None,
        gps_lat: float | None = None,
        gps_lng: float | None = None,
        notes: str | None = None,
    ) -> dict[str, Any] | None:
        client = self._get_client()
        try:
            now = self._now()
            data = {
                "network_key": network_key,
                "name": name,
                "description": description,
                "is_active": True,
                "created_at": now,
                "updated_at": now,
                "created_by": created_by,
                # New fields
                "standalone": standalone,
            }
            # Add optional fields if provided
            optional_fields = {
                "series": series,
                "sov_percent": sov_percent,
                "upload_fee": upload_fee,
                "spot_duration": spot_duration,
                "loop_duration": loop_duration,
                "number_of_faces": number_of_faces,
                "template_path": template_path,
                "display_type": display_type,
                "height": height,
                "width": width,
                "city": city,
                "area": area,
                "address": address,
                "gps_lat": gps_lat,
                "gps_lng": gps_lng,
                "notes": notes,
            }
            for field, value in optional_fields.items():
                if value is not None:
                    data[field] = value

            response = client.schema(company_schema).table("networks").insert(data).execute()

            if response.data:
                result = response.data[0]
                result["company_schema"] = company_schema

                # Invalidate networks cache
                _run_async(self._cache_delete_pattern(f"networks:*{company_schema}*"))

                return result
            return None
        except Exception as e:
            logger.error(f"[SUPABASE] Failed to create network: {e}")
            return None

    def get_network(
        self,
        network_id: int,
        company_schemas: list[str],
    ) -> dict[str, Any] | None:
        """Get a network by ID (cached)."""
        cache_key = f"network:{network_id}:{','.join(sorted(company_schemas))}"

        # Try cache first
        cached = _run_async(self._cache_get(cache_key))
        if cached is not None:
            logger.debug(f"[CACHE] Network cache hit: {network_id}")
            return cached

        result, _, status = self._find_in_schemas(
            "networks",
            {"id": network_id, "is_active": True},
            company_schemas,
        )

        if status == "found" and result:
            _run_async(self._cache_set(cache_key, result, ttl=NETWORK_CACHE_TTL))

        return result if status == "found" else None

    def get_network_by_key(
        self,
        network_key: str,
        company_schemas: list[str],
    ) -> dict[str, Any] | None:
        """Get a network by key (cached)."""
        cache_key = f"network_key:{network_key}:{','.join(sorted(company_schemas))}"

        # Try cache first
        cached = _run_async(self._cache_get(cache_key))
        if cached is not None:
            logger.debug(f"[CACHE] Network by key cache hit: {network_key}")
            return cached

        result, _, status = self._find_in_schemas(
            "networks",
            {"network_key": network_key, "is_active": True},
            company_schemas,
        )

        if status == "found" and result:
            _run_async(self._cache_set(cache_key, result, ttl=NETWORK_CACHE_TTL))

        return result if status == "found" else None

    def list_networks(
        self,
        company_schemas: list[str],
        include_inactive: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        # Create cache key
        cache_key = f"networks:{','.join(sorted(company_schemas))}:active={not include_inactive}"

        # Try cache first (only for default pagination)
        if offset == 0 and limit >= 100:
            cached = _run_async(self._cache_get(cache_key))
            if cached is not None:
                logger.debug(f"[CACHE] Networks cache hit ({len(cached)} networks)")
                return cached

        filters = {} if include_inactive else {"is_active": True}
        results = self._query_schemas(
            "networks",
            company_schemas,
            filters=filters,
            order_by="name",
            limit=limit,
            offset=offset,
        )

        # Cache the result (only for default pagination)
        if offset == 0 and limit >= 100:
            _run_async(self._cache_set(cache_key, results, ttl=NETWORK_CACHE_TTL))
            logger.debug(f"[CACHE] Cached {len(results)} networks")

        return results

    def update_network(
        self,
        network_id: int,
        company_schema: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not updates:
            return self.get_network(network_id, [company_schema])

        client = self._get_client()
        try:
            updates["updated_at"] = self._now()
            response = (
                client.schema(company_schema)
                .table("networks")
                .update(updates)
                .eq("id", network_id)
                .execute()
            )
            if response.data:
                result = response.data[0]
                result["company_schema"] = company_schema

                # Invalidate network caches
                _run_async(self._cache_delete_pattern(f"network:{network_id}:*"))
                _run_async(self._cache_delete_pattern(f"network_key:*"))
                _run_async(self._cache_delete_pattern(f"networks:*{company_schema}*"))

                return result
            return None
        except Exception as e:
            logger.error(f"[SUPABASE] Failed to update network: {e}")
            return None

    def delete_network(
        self,
        network_id: int,
        company_schema: str,
        hard_delete: bool = False,
    ) -> bool:
        client = self._get_client()
        try:
            if hard_delete:
                response = (
                    client.schema(company_schema)
                    .table("networks")
                    .delete()
                    .eq("id", network_id)
                    .execute()
                )
            else:
                response = (
                    client.schema(company_schema)
                    .table("networks")
                    .update({"is_active": False, "updated_at": self._now()})
                    .eq("id", network_id)
                    .execute()
                )

            success = len(response.data) > 0 if response.data else False

            if success:
                # Invalidate network caches
                _run_async(self._cache_delete_pattern(f"network:{network_id}:*"))
                _run_async(self._cache_delete_pattern(f"network_key:*"))
                _run_async(self._cache_delete_pattern(f"networks:*{company_schema}*"))

            return success
        except Exception as e:
            logger.error(f"[SUPABASE] Failed to delete network: {e}")
            return False

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
        client = self._get_client()
        try:
            now = self._now()
            data = {
                "type_key": type_key,
                "name": name,
                "network_id": network_id,
                "description": description,
                "specs": specs or {},
                "is_active": True,
                "created_at": now,
                "updated_at": now,
                "created_by": created_by,
            }
            response = client.schema(company_schema).table("asset_types").insert(data).execute()

            if response.data:
                result = response.data[0]
                result["company_schema"] = company_schema

                # Invalidate asset types cache
                _run_async(self._cache_delete_pattern(f"asset_types:*{company_schema}*"))

                return result
            return None
        except Exception as e:
            logger.error(f"[SUPABASE] Failed to create asset type: {e}")
            return None

    def get_asset_type(
        self,
        type_id: int,
        company_schemas: list[str],
    ) -> dict[str, Any] | None:
        """Get an asset type by ID (cached)."""
        cache_key = f"asset_type:{type_id}:{','.join(sorted(company_schemas))}"

        # Try cache first
        cached = _run_async(self._cache_get(cache_key))
        if cached is not None:
            logger.debug(f"[CACHE] Asset type cache hit: {type_id}")
            return cached

        result, schema, status = self._find_in_schemas(
            "asset_types",
            {"id": type_id, "is_active": True},
            company_schemas,
        )
        if status == "found" and result:
            # Fetch network name (also cached)
            network = self.get_network(result.get("network_id"), [schema])
            if network:
                result["network_name"] = network.get("name")
            # Cache the enriched result
            _run_async(self._cache_set(cache_key, result, ttl=ASSET_TYPE_CACHE_TTL))

        return result if status == "found" else None

    def list_asset_types(
        self,
        company_schemas: list[str],
        network_id: int | None = None,
        include_inactive: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        # Create cache key
        network_filter = f":network={network_id}" if network_id else ""
        cache_key = f"asset_types:{','.join(sorted(company_schemas))}:active={not include_inactive}{network_filter}"

        # Try cache first (only for default pagination)
        if offset == 0 and limit >= 100:
            cached = _run_async(self._cache_get(cache_key))
            if cached is not None:
                logger.debug(f"[CACHE] Asset types cache hit ({len(cached)} types)")
                return cached

        filters = {} if include_inactive else {"is_active": True}
        if network_id is not None:
            filters["network_id"] = network_id

        results = self._query_schemas(
            "asset_types",
            company_schemas,
            filters=filters,
            order_by="name",
            limit=limit,
            offset=offset,
        )

        # Enrich with network names - optimized with pre-fetched networks
        # Pre-fetch all networks to avoid N+1 queries
        networks_by_schema = {}
        for r in results:
            schema = r.get("company_schema")
            if schema not in networks_by_schema:
                networks_by_schema[schema] = {
                    n.get("id"): n for n in self.list_networks([schema])
                }
            network = networks_by_schema[schema].get(r.get("network_id"))
            if network:
                r["network_name"] = network.get("name")

        # Cache the result (only for default pagination)
        if offset == 0 and limit >= 100:
            _run_async(self._cache_set(cache_key, results, ttl=ASSET_TYPE_CACHE_TTL))
            logger.debug(f"[CACHE] Cached {len(results)} asset types")

        return results

    def update_asset_type(
        self,
        type_id: int,
        company_schema: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not updates:
            return self.get_asset_type(type_id, [company_schema])

        client = self._get_client()
        try:
            updates["updated_at"] = self._now()
            response = (
                client.schema(company_schema)
                .table("asset_types")
                .update(updates)
                .eq("id", type_id)
                .execute()
            )
            if response.data:
                result = response.data[0]
                result["company_schema"] = company_schema

                # Invalidate asset type caches
                _run_async(self._cache_delete_pattern(f"asset_type:{type_id}:*"))
                _run_async(self._cache_delete_pattern(f"asset_types:*{company_schema}*"))

                return result
            return None
        except Exception as e:
            logger.error(f"[SUPABASE] Failed to update asset type: {e}")
            return None

    def delete_asset_type(
        self,
        type_id: int,
        company_schema: str,
        hard_delete: bool = False,
    ) -> bool:
        client = self._get_client()
        try:
            if hard_delete:
                response = (
                    client.schema(company_schema)
                    .table("asset_types")
                    .delete()
                    .eq("id", type_id)
                    .execute()
                )
            else:
                response = (
                    client.schema(company_schema)
                    .table("asset_types")
                    .update({"is_active": False, "updated_at": self._now()})
                    .eq("id", type_id)
                    .execute()
                )

            success = len(response.data) > 0 if response.data else False

            if success:
                # Invalidate asset type caches
                _run_async(self._cache_delete_pattern(f"asset_type:{type_id}:*"))
                _run_async(self._cache_delete_pattern(f"asset_types:*{company_schema}*"))

            return success
        except Exception as e:
            logger.error(f"[SUPABASE] Failed to delete asset type: {e}")
            return False

    # =========================================================================
    # NETWORK ASSETS
    # =========================================================================

    def create_network_asset(
        self,
        asset_key: str,
        display_name: str,
        display_type: str,
        network_id: int,
        type_id: int,
        company_schema: str,
        created_by: str | None = None,
        **kwargs,
    ) -> dict[str, Any] | None:
        client = self._get_client()
        try:
            now = self._now()
            data = {
                "asset_key": asset_key,
                "display_name": display_name,
                "display_type": display_type,
                "network_id": network_id,
                "type_id": type_id,
                "is_active": True,
                "created_at": now,
                "updated_at": now,
                "created_by": created_by,
            }

            # Add optional fields
            optional_fields = [
                "series", "height", "width", "number_of_faces", "spot_duration",
                "loop_duration", "sov_percent", "upload_fee", "city", "area",
                "address", "gps_lat", "gps_lng", "template_path", "notes"
            ]
            for field in optional_fields:
                if field in kwargs and kwargs[field] is not None:
                    data[field] = kwargs[field]

            response = client.schema(company_schema).table("network_assets").insert(data).execute()

            if response.data:
                result = response.data[0]
                result["company_schema"] = company_schema

                # Invalidate network assets cache
                _run_async(self._cache_delete_pattern(f"network_assets:*{company_schema}*"))

                return result
            return None
        except Exception as e:
            logger.error(f"[SUPABASE] Failed to create network asset: {e}")
            return None

    def get_network_asset(
        self,
        asset_id: int,
        company_schemas: list[str],
    ) -> dict[str, Any] | None:
        """Get a network asset by ID (cached)."""
        schemas_key = ",".join(sorted(company_schemas))
        cache_key = f"network_asset:{asset_id}:{schemas_key}"

        # Try cache first
        cached = _run_async(self._cache_get(cache_key))
        if cached is not None:
            logger.debug(f"[CACHE] Network asset cache hit: {asset_id}")
            return cached

        result, schema, status = self._find_in_schemas(
            "network_assets",
            {"id": asset_id, "is_active": True},
            company_schemas,
        )
        if status == "found" and result:
            # Enrich with network and type names
            if result.get("network_id"):
                network = self.get_network(result["network_id"], [schema])
                if network:
                    result["network_name"] = network.get("name")
            if result.get("type_id"):
                asset_type = self.get_asset_type(result["type_id"], [schema])
                if asset_type:
                    result["type_name"] = asset_type.get("name")

            # Cache the result
            _run_async(self._cache_set(cache_key, result, ttl=NETWORK_ASSET_CACHE_TTL))

        return result if status == "found" else None

    def get_network_asset_by_key(
        self,
        asset_key: str,
        company_schemas: list[str],
    ) -> dict[str, Any] | None:
        result, schema, status = self._find_in_schemas(
            "network_assets",
            {"asset_key": asset_key, "is_active": True},
            company_schemas,
        )
        if status == "found" and result:
            if result.get("network_id"):
                network = self.get_network(result["network_id"], [schema])
                if network:
                    result["network_name"] = network.get("name")
            if result.get("type_id"):
                asset_type = self.get_asset_type(result["type_id"], [schema])
                if asset_type:
                    result["type_name"] = asset_type.get("name")
        return result if status == "found" else None

    def list_network_assets(
        self,
        company_schemas: list[str],
        network_id: int | None = None,
        type_id: int | None = None,
        include_inactive: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        filters = {} if include_inactive else {"is_active": True}
        if network_id is not None:
            filters["network_id"] = network_id
        if type_id is not None:
            filters["type_id"] = type_id

        results = self._query_schemas(
            "network_assets",
            company_schemas,
            filters=filters,
            order_by="display_name",
            limit=limit,
            offset=offset,
        )

        # Enrich with network and type names
        for r in results:
            schema = r.get("company_schema")
            if r.get("network_id"):
                network = self.get_network(r["network_id"], [schema])
                if network:
                    r["network_name"] = network.get("name")
            if r.get("type_id"):
                asset_type = self.get_asset_type(r["type_id"], [schema])
                if asset_type:
                    r["type_name"] = asset_type.get("name")

        return results

    def update_network_asset(
        self,
        asset_id: int,
        company_schema: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not updates:
            return self.get_network_asset(asset_id, [company_schema])

        client = self._get_client()
        try:
            updates["updated_at"] = self._now()
            response = (
                client.schema(company_schema)
                .table("network_assets")
                .update(updates)
                .eq("id", asset_id)
                .execute()
            )
            if response.data:
                result = response.data[0]
                result["company_schema"] = company_schema

                # Invalidate network asset caches
                _run_async(self._cache_delete_pattern(f"network_asset:{asset_id}:*"))
                _run_async(self._cache_delete_pattern(f"network_assets:*{company_schema}*"))

                return result
            return None
        except Exception as e:
            logger.error(f"[SUPABASE] Failed to update network asset: {e}")
            return None

    def delete_network_asset(
        self,
        asset_id: int,
        company_schema: str,
        hard_delete: bool = False,
    ) -> bool:
        client = self._get_client()
        try:
            if hard_delete:
                response = (
                    client.schema(company_schema)
                    .table("network_assets")
                    .delete()
                    .eq("id", asset_id)
                    .execute()
                )
            else:
                response = (
                    client.schema(company_schema)
                    .table("network_assets")
                    .update({"is_active": False, "updated_at": self._now()})
                    .eq("id", asset_id)
                    .execute()
                )

            success = len(response.data) > 0 if response.data else False

            if success:
                # Invalidate network asset caches
                _run_async(self._cache_delete_pattern(f"network_asset:{asset_id}:*"))
                _run_async(self._cache_delete_pattern(f"network_assets:*{company_schema}*"))

            return success
        except Exception as e:
            logger.error(f"[SUPABASE] Failed to delete network asset: {e}")
            return False

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
        client = self._get_client()
        try:
            now = self._now()
            data = {
                "location_key": location_key,
                "display_name": display_name,
                "display_type": display_type,
                "network_id": network_id,
                "type_id": type_id,
                "is_active": True,
                "created_at": now,
                "updated_at": now,
                "created_by": created_by,
            }

            # Add optional fields
            optional_fields = [
                "series", "height", "width", "number_of_faces", "spot_duration",
                "loop_duration", "sov_percent", "upload_fee", "address", "city",
                "country", "gps_lat", "gps_lng", "template_path", "notes"
            ]
            for field in optional_fields:
                if field in kwargs and kwargs[field] is not None:
                    data[field] = kwargs[field]

            response = client.schema(company_schema).table("locations").insert(data).execute()

            if response.data:
                result = response.data[0]
                result["company_schema"] = company_schema

                # Invalidate locations cache
                _run_async(self._cache_delete_pattern(f"locations:*{company_schema}*"))

                return result
            return None
        except Exception as e:
            logger.error(f"[SUPABASE] Failed to create location: {e}")
            return None

    def get_location(
        self,
        location_id: int,
        company_schemas: list[str],
    ) -> dict[str, Any] | None:
        """Get a location by ID (cached)."""
        cache_key = f"location_id:{location_id}:{','.join(sorted(company_schemas))}"

        # Try cache first
        cached = _run_async(self._cache_get(cache_key))
        if cached is not None:
            logger.debug(f"[CACHE] Location by ID cache hit: {location_id}")
            return cached

        result, schema, status = self._find_in_schemas(
            "locations",
            {"id": location_id, "is_active": True},
            company_schemas,
        )
        if status == "found" and result:
            # Enrich with network and type names (also cached now)
            if result.get("network_id"):
                network = self.get_network(result["network_id"], [schema])
                if network:
                    result["network_name"] = network.get("name")
            if result.get("type_id"):
                asset_type = self.get_asset_type(result["type_id"], [schema])
                if asset_type:
                    result["type_name"] = asset_type.get("name")
            # Cache the enriched result
            _run_async(self._cache_set(cache_key, result, ttl=LOCATION_CACHE_TTL))

        return result if status == "found" else None

    def get_location_by_key(
        self,
        location_key: str,
        company_schemas: list[str],
    ) -> dict[str, Any] | None:
        """Get a location by key (cached)."""
        normalized_key = location_key.lower().strip()
        cache_key = f"location:{normalized_key}:{','.join(sorted(company_schemas))}"

        # Try cache first
        cached = _run_async(self._cache_get(cache_key))
        if cached is not None:
            logger.debug(f"[CACHE] Location cache hit: {location_key}")
            return cached

        result, schema, status = self._find_in_schemas(
            "locations",
            {"location_key": location_key, "is_active": True},
            company_schemas,
        )
        if status == "found" and result:
            if result.get("network_id"):
                network = self.get_network(result["network_id"], [schema])
                if network:
                    result["network_name"] = network.get("name")
            if result.get("type_id"):
                asset_type = self.get_asset_type(result["type_id"], [schema])
                if asset_type:
                    result["type_name"] = asset_type.get("name")
            # Cache the enriched result
            _run_async(self._cache_set(cache_key, result, ttl=LOCATION_CACHE_TTL))

        return result if status == "found" else None

    def list_locations(
        self,
        company_schemas: list[str],
        network_id: int | None = None,
        type_id: int | None = None,
        include_inactive: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        # Create cache key
        filters_str = f":network={network_id}" if network_id else ""
        filters_str += f":type={type_id}" if type_id else ""
        cache_key = f"locations:{','.join(sorted(company_schemas))}:active={not include_inactive}{filters_str}"

        # Try cache first (only for default pagination)
        if offset == 0 and limit >= 100:
            cached = _run_async(self._cache_get(cache_key))
            if cached is not None:
                logger.debug(f"[CACHE] Locations cache hit ({len(cached)} locations)")
                return cached

        filters = {} if include_inactive else {"is_active": True}
        if network_id is not None:
            filters["network_id"] = network_id
        if type_id is not None:
            filters["type_id"] = type_id

        results = self._query_schemas(
            "locations",
            company_schemas,
            filters=filters,
            order_by="display_name",
            limit=limit,
            offset=offset,
        )

        # Enrich with network and type names - optimized with pre-fetched data
        # Pre-fetch networks and types per schema to avoid N+1 queries
        networks_by_schema = {}
        types_by_schema = {}

        for r in results:
            schema = r.get("company_schema")

            # Lazy-load networks for this schema
            if schema not in networks_by_schema:
                networks_by_schema[schema] = {
                    n.get("id"): n for n in self.list_networks([schema])
                }

            # Lazy-load asset types for this schema
            if schema not in types_by_schema:
                types_by_schema[schema] = {
                    t.get("id"): t for t in self.list_asset_types([schema])
                }

            if r.get("network_id"):
                network = networks_by_schema[schema].get(r["network_id"])
                if network:
                    r["network_name"] = network.get("name")
            if r.get("type_id"):
                asset_type = types_by_schema[schema].get(r["type_id"])
                if asset_type:
                    r["type_name"] = asset_type.get("name")

        # Cache the result (only for default pagination)
        if offset == 0 and limit >= 100:
            _run_async(self._cache_set(cache_key, results, ttl=LOCATION_CACHE_TTL))
            logger.debug(f"[CACHE] Cached {len(results)} locations")

        return results

    def update_location(
        self,
        location_id: int,
        company_schema: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not updates:
            return self.get_location(location_id, [company_schema])

        client = self._get_client()
        try:
            updates["updated_at"] = self._now()
            response = (
                client.schema(company_schema)
                .table("locations")
                .update(updates)
                .eq("id", location_id)
                .execute()
            )
            if response.data:
                result = response.data[0]
                result["company_schema"] = company_schema

                # Invalidate location caches
                location_key = result.get("location_key", "")
                _run_async(self._cache_delete_pattern(f"location_id:{location_id}:*"))
                if location_key:
                    _run_async(self._cache_delete_pattern(f"location:{location_key.lower()}:*"))
                _run_async(self._cache_delete_pattern(f"locations:*{company_schema}*"))

                return result
            return None
        except Exception as e:
            logger.error(f"[SUPABASE] Failed to update location: {e}")
            return None

    def delete_location(
        self,
        location_id: int,
        company_schema: str,
        hard_delete: bool = False,
    ) -> bool:
        client = self._get_client()
        try:
            # Get location_key before delete for cache invalidation
            existing = (
                client.schema(company_schema)
                .table("locations")
                .select("location_key")
                .eq("id", location_id)
                .single()
                .execute()
            )
            location_key = existing.data.get("location_key", "") if existing.data else ""

            if hard_delete:
                response = (
                    client.schema(company_schema)
                    .table("locations")
                    .delete()
                    .eq("id", location_id)
                    .execute()
                )
            else:
                response = (
                    client.schema(company_schema)
                    .table("locations")
                    .update({"is_active": False, "updated_at": self._now()})
                    .eq("id", location_id)
                    .execute()
                )

            success = len(response.data) > 0 if response.data else False

            if success:
                # Invalidate location caches
                _run_async(self._cache_delete_pattern(f"location_id:{location_id}:*"))
                if location_key:
                    _run_async(self._cache_delete_pattern(f"location:{location_key.lower()}:*"))
                _run_async(self._cache_delete_pattern(f"locations:*{company_schema}*"))

            return success
        except Exception as e:
            logger.error(f"[SUPABASE] Failed to delete location: {e}")
            return False

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
        client = self._get_client()
        try:
            now = self._now()
            data = {
                "package_key": package_key,
                "name": name,
                "description": description,
                "is_active": True,
                "created_at": now,
                "updated_at": now,
                "created_by": created_by,
            }
            response = client.schema(company_schema).table("packages").insert(data).execute()

            if response.data:
                result = response.data[0]
                result["company_schema"] = company_schema
                result["items"] = []
                return result
            return None
        except Exception as e:
            logger.error(f"[SUPABASE] Failed to create package: {e}")
            return None

    def get_package(
        self,
        package_id: int,
        company_schemas: list[str],
    ) -> dict[str, Any] | None:
        """Get a package by ID (cached)."""
        schemas_key = ",".join(sorted(company_schemas))
        cache_key = f"package:{package_id}:{schemas_key}"

        # Try cache first
        cached = _run_async(self._cache_get(cache_key))
        if cached is not None:
            logger.debug(f"[CACHE] Package cache hit: {package_id}")
            return cached

        result, schema, status = self._find_in_schemas(
            "packages",
            {"id": package_id, "is_active": True},
            company_schemas,
        )
        if status == "found" and result:
            result["items"] = self.get_package_items(package_id, schema)

            # Cache the result
            _run_async(self._cache_set(cache_key, result, ttl=PACKAGE_CACHE_TTL))

        return result if status == "found" else None

    def list_packages(
        self,
        company_schemas: list[str],
        include_inactive: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List all packages (cached for default pagination)."""
        schemas_key = ",".join(sorted(company_schemas))
        cache_key = f"packages:{schemas_key}:inactive={include_inactive}"

        # Only cache for default pagination
        if offset == 0 and limit >= 100:
            cached = _run_async(self._cache_get(cache_key))
            if cached is not None:
                logger.debug(f"[CACHE] Packages list cache hit")
                return cached

        filters = {} if include_inactive else {"is_active": True}
        results = self._query_schemas(
            "packages",
            company_schemas,
            filters=filters,
            order_by="name",
            limit=limit,
            offset=offset,
        )

        # Cache for default pagination
        if offset == 0 and limit >= 100:
            _run_async(self._cache_set(cache_key, results, ttl=PACKAGE_CACHE_TTL))
            logger.debug(f"[CACHE] Cached {len(results)} packages")

        return results

    def update_package(
        self,
        package_id: int,
        company_schema: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not updates:
            return self.get_package(package_id, [company_schema])

        client = self._get_client()
        try:
            updates["updated_at"] = self._now()
            response = (
                client.schema(company_schema)
                .table("packages")
                .update(updates)
                .eq("id", package_id)
                .execute()
            )
            if response.data:
                result = response.data[0]
                result["company_schema"] = company_schema

                # Invalidate package caches
                _run_async(self._cache_delete_pattern(f"package:{package_id}:*"))
                _run_async(self._cache_delete_pattern(f"packages:*{company_schema}*"))

                return result
            return None
        except Exception as e:
            logger.error(f"[SUPABASE] Failed to update package: {e}")
            return None

    def delete_package(
        self,
        package_id: int,
        company_schema: str,
        hard_delete: bool = False,
    ) -> bool:
        client = self._get_client()
        try:
            if hard_delete:
                response = (
                    client.schema(company_schema)
                    .table("packages")
                    .delete()
                    .eq("id", package_id)
                    .execute()
                )
            else:
                response = (
                    client.schema(company_schema)
                    .table("packages")
                    .update({"is_active": False, "updated_at": self._now()})
                    .eq("id", package_id)
                    .execute()
                )

            success = len(response.data) > 0 if response.data else False

            if success:
                # Invalidate package caches
                _run_async(self._cache_delete_pattern(f"package:{package_id}:*"))
                _run_async(self._cache_delete_pattern(f"packages:*{company_schema}*"))
                _run_async(self._cache_delete_pattern(f"package_items:{package_id}:*"))

            return success
        except Exception as e:
            logger.error(f"[SUPABASE] Failed to delete package: {e}")
            return False

    # =========================================================================
    # PACKAGE ITEMS
    # =========================================================================

    def add_package_item(
        self,
        package_id: int,
        item_type: str,
        company_schema: str,
        network_id: int,
    ) -> dict[str, Any] | None:
        """Add a network to a package.

        After unification, all package items are networks.
        """
        client = self._get_client()
        try:
            data = {
                "package_id": package_id,
                "item_type": "network",  # Always network after unification
                "network_id": network_id,
                "created_at": self._now(),
            }
            response = client.schema(company_schema).table("package_items").insert(data).execute()

            if response.data:
                result = response.data[0]

                # Invalidate package caches
                _run_async(self._cache_delete_pattern(f"package:{package_id}:*"))
                _run_async(self._cache_delete_pattern(f"package_items:{package_id}:*"))

                # Enrich with network name and location count
                network = self.get_network(network_id, [company_schema])
                if network:
                    result["network_name"] = network.get("name")
                    # Get location count for this network
                    assets = self.list_network_assets([company_schema], network_id=network_id)
                    result["location_count"] = len(assets)

                return result
            return None
        except Exception as e:
            logger.error(f"[SUPABASE] Failed to add package item: {e}")
            return None

    def remove_package_item(
        self,
        item_id: int,
        company_schema: str,
        package_id: int | None = None,
    ) -> bool:
        client = self._get_client()
        try:
            # Get package_id before delete if not provided
            if package_id is None:
                existing = (
                    client.schema(company_schema)
                    .table("package_items")
                    .select("package_id")
                    .eq("id", item_id)
                    .single()
                    .execute()
                )
                package_id = existing.data.get("package_id") if existing.data else None

            response = (
                client.schema(company_schema)
                .table("package_items")
                .delete()
                .eq("id", item_id)
                .execute()
            )

            success = len(response.data) > 0 if response.data else False

            if success and package_id:
                # Invalidate package caches
                _run_async(self._cache_delete_pattern(f"package:{package_id}:*"))
                _run_async(self._cache_delete_pattern(f"package_items:{package_id}:*"))

            return success
        except Exception as e:
            logger.error(f"[SUPABASE] Failed to remove package item: {e}")
            return False

    def get_package_items(
        self,
        package_id: int,
        company_schema: str,
    ) -> list[dict[str, Any]]:
        """Get package items (cached).

        After unification, all package items are networks.
        """
        cache_key = f"package_items:{package_id}:{company_schema}"

        # Try cache first
        cached = _run_async(self._cache_get(cache_key))
        if cached is not None:
            logger.debug(f"[CACHE] Package items cache hit: {package_id}")
            return cached

        client = self._get_client()
        try:
            response = (
                client.schema(company_schema)
                .table("package_items")
                .select("*")
                .eq("package_id", package_id)
                .execute()
            )
            items = response.data or []

            # Enrich with network names and asset counts
            for item in items:
                network_id = item.get("network_id")
                if network_id:
                    network = self.get_network(network_id, [company_schema])
                    if network:
                        item["network_name"] = network.get("name")
                    # Count network assets (locations) in this network
                    assets = self.list_network_assets([company_schema], network_id=network_id)
                    item["location_count"] = len(assets)

            # Cache the result
            _run_async(self._cache_set(cache_key, items, ttl=PACKAGE_CACHE_TTL))

            return items
        except Exception as e:
            logger.error(f"[SUPABASE] Failed to get package items: {e}")
            return []

    def get_package_locations(
        self,
        package_id: int,
        company_schema: str,
    ) -> list[dict[str, Any]]:
        """Get all locations in a package (expanded from networks and direct assets)."""
        items = self.get_package_items(package_id, company_schema)
        location_ids = set()
        locations = []

        for item in items:
            if item["item_type"] == "asset" and item.get("location_id"):
                location_ids.add(item["location_id"])
            elif item["item_type"] == "network" and item.get("network_id"):
                # Get all locations in this network
                network_locations = self.list_locations(
                    [company_schema],
                    network_id=item["network_id"],
                )
                for loc in network_locations:
                    if loc["id"] not in location_ids:
                        location_ids.add(loc["id"])
                        locations.append(loc)

        # Add direct asset locations
        for item in items:
            if item["item_type"] == "asset" and item.get("location_id"):
                if item["location_id"] not in {loc["id"] for loc in locations}:
                    loc = self.get_location(item["location_id"], [company_schema])
                    if loc:
                        locations.append(loc)

        return locations

    # =========================================================================
    # ELIGIBILITY
    # =========================================================================

    def check_location_eligibility(
        self,
        location_id: int,
        company_schemas: list[str],
    ) -> dict[str, Any]:
        """
        Check basic location eligibility (local fields only).

        Note: Proposal and mockup eligibility require data from Sales-Module
        (rate_cards, mockup_frames). Use EligibilityService for full checks.
        """
        location = self.get_location(location_id, company_schemas)
        if not location:
            return {
                "item_type": "location",
                "item_id": location_id,
                "error": "Location not found",
                "service_eligibility": {
                    "proposal_generator": False,
                    "mockup_generator": False,
                    "availability_calendar": False,
                },
                "details": [],
            }

        company_schema = location.get("company_schema", "")
        details = []

        # Proposal generator - basic field check only
        # Full eligibility (template, rate_card) checked via Sales-Module
        proposal_missing = []
        if not location.get("display_name"):
            proposal_missing.append("display_name")
        if not location.get("display_type"):
            proposal_missing.append("display_type")

        details.append({
            "service": "proposal_generator",
            "eligible": len(proposal_missing) == 0,
            "missing_fields": proposal_missing,
            "warnings": ["Full eligibility checked via Sales-Module"],
        })

        # Mockup generator - basic field check only
        # Full eligibility (mockup_frames) checked via Sales-Module
        mockup_missing = []
        if not location.get("display_name"):
            mockup_missing.append("display_name")

        details.append({
            "service": "mockup_generator",
            "eligible": len(mockup_missing) == 0,
            "missing_fields": mockup_missing,
            "warnings": ["Full eligibility checked via Sales-Module"],
        })

        # Availability calendar eligibility (local check only)
        calendar_missing = []
        if not location.get("display_name"):
            calendar_missing.append("display_name")

        details.append({
            "service": "availability_calendar",
            "eligible": len(calendar_missing) == 0,
            "missing_fields": calendar_missing,
            "warnings": [],
        })

        return {
            "item_type": "location",
            "item_id": location_id,
            "company": company_schema,
            "name": location.get("display_name", ""),
            "service_eligibility": {
                "proposal_generator": details[0]["eligible"],
                "mockup_generator": details[1]["eligible"],
                "availability_calendar": details[2]["eligible"],
            },
            "details": details,
        }

    def check_network_eligibility(
        self,
        network_id: int,
        company_schemas: list[str],
    ) -> dict[str, Any]:
        network = self.get_network(network_id, company_schemas)
        if not network:
            return {
                "item_type": "network",
                "item_id": network_id,
                "error": "Network not found",
                "service_eligibility": {
                    "proposal_generator": False,
                    "mockup_generator": False,
                    "availability_calendar": False,
                },
                "details": [],
            }

        company_schema = network.get("company_schema", "")
        details = []

        # Get locations in this network
        locations = self.list_locations([company_schema], network_id=network_id)
        total_locations = len(locations)

        # Count eligible locations
        proposal_eligible = 0
        calendar_eligible = 0
        for loc in locations:
            eligibility = self.check_location_eligibility(loc["id"], [company_schema])
            if eligibility["service_eligibility"]["proposal_generator"]:
                proposal_eligible += 1
            if eligibility["service_eligibility"]["availability_calendar"]:
                calendar_eligible += 1

        # Proposal generator
        proposal_missing = []
        if not network.get("name"):
            proposal_missing.append("name")
        if proposal_eligible == 0:
            proposal_missing.append("at_least_one_eligible_location")

        details.append({
            "service": "proposal_generator",
            "eligible": len(proposal_missing) == 0,
            "missing_fields": proposal_missing,
            "warnings": [],
        })

        # Mockup generator - networks not eligible
        details.append({
            "service": "mockup_generator",
            "eligible": False,
            "missing_fields": [],
            "warnings": ["Networks are not eligible for mockup generator"],
        })

        # Availability calendar
        calendar_missing = []
        if not network.get("name"):
            calendar_missing.append("name")
        if calendar_eligible == 0:
            calendar_missing.append("at_least_one_eligible_location")

        details.append({
            "service": "availability_calendar",
            "eligible": len(calendar_missing) == 0,
            "missing_fields": calendar_missing,
            "warnings": [],
        })

        return {
            "item_type": "network",
            "item_id": network_id,
            "company": company_schema,
            "name": network.get("name", ""),
            "service_eligibility": {
                "proposal_generator": details[0]["eligible"],
                "mockup_generator": False,
                "availability_calendar": details[2]["eligible"],
            },
            "details": details,
            "eligible_location_count": max(proposal_eligible, calendar_eligible),
            "total_location_count": total_locations,
        }

    def get_eligible_locations(
        self,
        service: str,
        company_schemas: list[str],
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        # Get all locations then filter by eligibility
        all_locations = self.list_locations(company_schemas, limit=1000)
        eligible = []

        for loc in all_locations:
            eligibility = self.check_location_eligibility(loc["id"], company_schemas)
            if eligibility["service_eligibility"].get(service, False):
                loc["service_eligibility"] = eligibility["service_eligibility"]
                eligible.append(loc)

        return eligible[offset:offset + limit]

    def get_eligible_networks(
        self,
        service: str,
        company_schemas: list[str],
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        all_networks = self.list_networks(company_schemas, limit=1000)
        eligible = []

        for net in all_networks:
            eligibility = self.check_network_eligibility(net["id"], company_schemas)
            if eligibility["service_eligibility"].get(service, False):
                net["service_eligibility"] = eligibility["service_eligibility"]
                eligible.append(net)

        return eligible[offset:offset + limit]

    # =========================================================================
    # CROSS-SERVICE LOOKUPS
    # =========================================================================

    def has_mockup_frame(
        self,
        location_key: str,
        company_schema: str,
    ) -> bool:
        """Check if a location has a mockup frame."""
        frames = self.list_mockup_frames(location_key, company_schema)
        return len(frames) > 0

    # =========================================================================
    # MOCKUP FRAMES
    # =========================================================================

    def list_mockup_frames(
        self,
        location_key: str,
        company_schema: str,
    ) -> list[dict[str, Any]]:
        """List all mockup frames for a location (cached)."""
        cache_key = f"frames:{location_key.lower()}:{company_schema}"

        # Try cache first
        cached = _run_async(self._cache_get(cache_key))
        if cached is not None:
            logger.debug(f"[CACHE] Mockup frames cache hit: {location_key}")
            return cached

        client = self._get_client()
        try:
            response = (
                client.schema(company_schema)
                .table("mockup_frames")
                .select("*")
                .eq("location_key", location_key)
                .execute()
            )
            result = response.data or []

            # Cache the result
            _run_async(self._cache_set(cache_key, result, ttl=FRAME_CACHE_TTL))

            return result
        except Exception as e:
            logger.debug(f"[SUPABASE] Failed to list mockup frames: {e}")
            return []

    def save_mockup_frame(
        self,
        location_key: str,
        photo_filename: str,
        frames_data: list[dict],
        company_schema: str,
        time_of_day: str = "day",
        finish: str = "gold",
        created_by: str | None = None,
        config: dict | None = None,
    ) -> str:
        """Save mockup frame to company-specific schema. Returns auto-numbered filename."""
        import os
        try:
            client = self._get_client()

            # Generate auto-numbered filename
            _, ext = os.path.splitext(photo_filename)
            location_display_name = location_key.replace('_', ' ').title().replace(' ', '')

            # Get existing photos for numbering
            response = (
                client.schema(company_schema)
                .table("mockup_frames")
                .select("photo_filename")
                .eq("location_key", location_key)
                .execute()
            )
            existing_files = [r["photo_filename"] for r in (response.data or [])]

            existing_numbers = []
            for filename in existing_files:
                name_part = os.path.splitext(filename)[0]
                if name_part.startswith(f"{location_display_name}_"):
                    try:
                        num = int(name_part.split('_')[-1])
                        existing_numbers.append(num)
                    except ValueError:
                        pass

            next_num = 1
            while next_num in existing_numbers:
                next_num += 1

            final_filename = f"{location_display_name}_{next_num}{ext}"

            # Insert the record
            client.schema(company_schema).table("mockup_frames").insert({
                "location_key": location_key,
                "time_of_day": time_of_day,
                "finish": finish,
                "photo_filename": final_filename,
                "frames_data": frames_data,
                "created_at": datetime.now().isoformat(),
                "created_by": created_by,
                "config": config,
            }).execute()

            # Invalidate cache for this location
            _run_async(self._cache_delete_pattern(f"frames:{location_key.lower()}:*"))

            logger.info(f"[SUPABASE] Saved mockup frame: {company_schema}.{location_key}/{final_filename}")
            return final_filename
        except Exception as e:
            logger.error(f"[SUPABASE] Failed to save mockup frame for {location_key}: {e}", exc_info=True)
            raise

    def get_mockup_frame(
        self,
        location_key: str,
        company: str,
        time_of_day: str = "day",
        finish: str = "gold",
        photo_filename: str | None = None,
    ) -> dict[str, Any] | None:
        """Get specific mockup frame data (uses cached frames list)."""
        # First try to get from cached frames list (avoids separate DB query)
        frames = self.list_mockup_frames(location_key, company)

        for frame in frames:
            if frame.get("time_of_day") == time_of_day and frame.get("finish") == finish:
                if photo_filename is None or frame.get("photo_filename") == photo_filename:
                    return frame

        # Fallback to direct query if not in cache (shouldn't happen normally)
        client = self._get_client()
        try:
            query = (
                client.schema(company)
                .table("mockup_frames")
                .select("*")
                .eq("location_key", location_key)
                .eq("time_of_day", time_of_day)
                .eq("finish", finish)
            )

            if photo_filename:
                query = query.eq("photo_filename", photo_filename)

            response = query.limit(1).execute()

            if response.data:
                return response.data[0]
            return None
        except Exception as e:
            logger.debug(f"[SUPABASE] Failed to get mockup frame: {e}")
            return None

    def delete_mockup_frame(
        self,
        location_key: str,
        company: str,
        photo_filename: str,
        time_of_day: str = "day",
        finish: str = "gold",
    ) -> bool:
        """Delete a mockup frame."""
        client = self._get_client()
        try:
            response = (
                client.schema(company)
                .table("mockup_frames")
                .delete()
                .eq("location_key", location_key)
                .eq("photo_filename", photo_filename)
                .eq("time_of_day", time_of_day)
                .eq("finish", finish)
                .execute()
            )

            # Invalidate frames cache for this location
            _run_async(self._cache_delete(f"frames:{location_key.lower()}:{company}"))

            logger.info(f"[SUPABASE] Deleted mockup frame: {location_key}/{photo_filename}")
            return True
        except Exception as e:
            logger.error(f"[SUPABASE] Failed to delete mockup frame: {e}")
            return False

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

        Args:
            network_key: Network identifier (same as location_key in VIEW)
            company_schemas: Company schemas to search

        Returns:
            {
                "network_key": str,
                "company": str,
                "is_standalone": bool,
                "storage_keys": list[str],  # network_key for standalone, asset_keys for traditional
                "sample_assets": list[dict],  # For traditional: one per asset_type
            }
        """
        # Get the network
        network = self.get_network_by_key(network_key, company_schemas)
        if not network:
            return None

        company = network.get("company_schema", network.get("company"))
        is_standalone = network.get("standalone", False)
        network_id = network["id"]

        if is_standalone:
            # Standalone networks: mockups at network level
            return {
                "network_key": network_key,
                "company": company,
                "is_standalone": True,
                "storage_keys": [network_key],
                "sample_assets": [],
            }
        else:
            # Traditional networks: mockups at asset level
            # Get asset types for this network
            types = self.list_asset_types([company], network_id=network_id)

            sample_assets = []
            storage_keys = []

            for asset_type in types:
                # Get first asset of each type
                assets = self.list_network_assets(
                    [company],
                    type_id=asset_type["id"],
                    limit=1,
                )
                if assets:
                    asset = assets[0]
                    asset_key = asset["asset_key"]
                    storage_keys.append(asset_key)
                    sample_assets.append({
                        "asset_key": asset_key,
                        "display_name": asset.get("display_name"),
                        "type_name": asset_type.get("name"),
                        "environment": asset.get("environment", "outdoor"),
                    })

            return {
                "network_key": network_key,
                "company": company,
                "is_standalone": False,
                "storage_keys": storage_keys,
                "sample_assets": sample_assets,
            }
