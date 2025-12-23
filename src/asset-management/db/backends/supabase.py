"""
Supabase database backend implementation for Asset Management.

This backend uses Supabase for cloud-hosted PostgreSQL storage with
multi-schema support for company isolation.
"""

import json
import logging
import os
from datetime import datetime
from typing import Any

from config import COMPANY_SCHEMAS
from db.base import DatabaseBackend

logger = logging.getLogger("asset-management")


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
        """Initialize Supabase backend using environment variables."""
        self._client = None

        # Get credentials from environment
        self._url = os.getenv("SUPABASE_URL", "")
        self._key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "") or os.getenv("SUPABASE_KEY", "")

        if not self._url or not self._key:
            logger.warning(
                "[SUPABASE] Credentials not configured. "
                "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables."
            )

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
            self._client = create_client(self._url, self._key)
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
        Search for a record across all company schemas with access control.

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

        for schema in COMPANY_SCHEMAS:
            try:
                query = client.schema(schema).table(table).select(select)
                for col, val in filters.items():
                    query = query.eq(col, val)
                response = query.execute()

                if response.data:
                    if schema in user_companies:
                        result = response.data[0] if len(response.data) == 1 else response.data
                        if isinstance(result, dict):
                            result["company_schema"] = schema
                        elif isinstance(result, list):
                            for item in result:
                                item["company_schema"] = schema
                        return (result, schema, "found")
                    else:
                        return (None, schema, "access_denied")
            except Exception as e:
                logger.debug(f"[SUPABASE] Error searching {schema}.{table}: {e}")
                continue

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
        Query a table across multiple company schemas and aggregate results.

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
        all_results = []

        for schema in company_schemas:
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
                        all_results.append(record)
            except Exception as e:
                logger.error(f"[SUPABASE] Error querying {schema}.{table}: {e}")
                continue

        return all_results

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
            }
            response = client.schema(company_schema).table("networks").insert(data).execute()

            if response.data:
                result = response.data[0]
                result["company_schema"] = company_schema
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
        result, _, status = self._find_in_schemas(
            "networks",
            {"id": network_id, "is_active": True},
            company_schemas,
        )
        return result if status == "found" else None

    def get_network_by_key(
        self,
        network_key: str,
        company_schemas: list[str],
    ) -> dict[str, Any] | None:
        result, _, status = self._find_in_schemas(
            "networks",
            {"network_key": network_key, "is_active": True},
            company_schemas,
        )
        return result if status == "found" else None

    def list_networks(
        self,
        company_schemas: list[str],
        include_inactive: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        filters = {} if include_inactive else {"is_active": True}
        results = self._query_schemas(
            "networks",
            company_schemas,
            filters=filters,
            order_by="name",
            limit=limit,
            offset=offset,
        )
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
            return len(response.data) > 0 if response.data else False
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
        result, schema, status = self._find_in_schemas(
            "asset_types",
            {"id": type_id, "is_active": True},
            company_schemas,
        )
        if status == "found" and result:
            # Fetch network name
            network = self.get_network(result.get("network_id"), [schema])
            if network:
                result["network_name"] = network.get("name")
        return result if status == "found" else None

    def list_asset_types(
        self,
        company_schemas: list[str],
        network_id: int | None = None,
        include_inactive: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
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

        # Enrich with network names
        for r in results:
            network = self.get_network(r.get("network_id"), [r.get("company_schema")])
            if network:
                r["network_name"] = network.get("name")

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
            return len(response.data) > 0 if response.data else False
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
            return len(response.data) > 0 if response.data else False
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
        result, schema, status = self._find_in_schemas(
            "locations",
            {"id": location_id, "is_active": True},
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
        return result if status == "found" else None

    def get_location_by_key(
        self,
        location_key: str,
        company_schemas: list[str],
    ) -> dict[str, Any] | None:
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

        # Enrich with network and type names (batch for efficiency)
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
            return len(response.data) > 0 if response.data else False
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
        result, schema, status = self._find_in_schemas(
            "packages",
            {"id": package_id, "is_active": True},
            company_schemas,
        )
        if status == "found" and result:
            result["items"] = self.get_package_items(package_id, schema)
        return result if status == "found" else None

    def list_packages(
        self,
        company_schemas: list[str],
        include_inactive: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        filters = {} if include_inactive else {"is_active": True}
        return self._query_schemas(
            "packages",
            company_schemas,
            filters=filters,
            order_by="name",
            limit=limit,
            offset=offset,
        )

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
            return len(response.data) > 0 if response.data else False
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
        network_id: int | None = None,
        location_id: int | None = None,
    ) -> dict[str, Any] | None:
        client = self._get_client()
        try:
            data = {
                "package_id": package_id,
                "item_type": item_type,
                "network_id": network_id,
                "location_id": location_id,
                "created_at": self._now(),
            }
            response = client.schema(company_schema).table("package_items").insert(data).execute()

            if response.data:
                result = response.data[0]
                # Enrich with names
                if network_id:
                    network = self.get_network(network_id, [company_schema])
                    if network:
                        result["network_name"] = network.get("name")
                if location_id:
                    location = self.get_location(location_id, [company_schema])
                    if location:
                        result["location_name"] = location.get("display_name")
                return result
            return None
        except Exception as e:
            logger.error(f"[SUPABASE] Failed to add package item: {e}")
            return None

    def remove_package_item(
        self,
        item_id: int,
        company_schema: str,
    ) -> bool:
        client = self._get_client()
        try:
            response = (
                client.schema(company_schema)
                .table("package_items")
                .delete()
                .eq("id", item_id)
                .execute()
            )
            return len(response.data) > 0 if response.data else False
        except Exception as e:
            logger.error(f"[SUPABASE] Failed to remove package item: {e}")
            return False

    def get_package_items(
        self,
        package_id: int,
        company_schema: str,
    ) -> list[dict[str, Any]]:
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

            # Enrich with names and location counts
            for item in items:
                if item.get("network_id"):
                    network = self.get_network(item["network_id"], [company_schema])
                    if network:
                        item["network_name"] = network.get("name")
                    # Count locations in network
                    locations = self.list_locations([company_schema], network_id=item["network_id"])
                    item["location_count"] = len(locations)
                if item.get("location_id"):
                    location = self.get_location(item["location_id"], [company_schema])
                    if location:
                        item["location_name"] = location.get("display_name")

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
