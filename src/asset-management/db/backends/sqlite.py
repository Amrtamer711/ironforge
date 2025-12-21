"""
SQLite database backend implementation for Asset Management.

Note: SQLite backend is primarily for local development and testing.
Production uses Supabase with multi-schema support.
"""

import json
import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from db.base import DatabaseBackend

logger = logging.getLogger("asset-management")


# SQLite schema for asset management tables
SCHEMA = """
-- Networks table
CREATE TABLE IF NOT EXISTS networks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    network_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT,
    company TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT
);

-- Asset types table
CREATE TABLE IF NOT EXISTS asset_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type_key TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    specs TEXT DEFAULT '{}',
    network_id INTEGER NOT NULL,
    company TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT,
    FOREIGN KEY (network_id) REFERENCES networks(id),
    UNIQUE(type_key, network_id)
);

-- Locations table
CREATE TABLE IF NOT EXISTS locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_key TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    display_type TEXT NOT NULL CHECK(display_type IN ('digital', 'static')),
    network_id INTEGER,
    type_id INTEGER,
    series TEXT,
    height TEXT,
    width TEXT,
    number_of_faces INTEGER DEFAULT 1,
    spot_duration INTEGER,
    loop_duration INTEGER,
    sov_percent REAL,
    upload_fee REAL,
    address TEXT,
    city TEXT,
    country TEXT,
    gps_lat REAL,
    gps_lng REAL,
    template_path TEXT,
    notes TEXT,
    company TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT,
    FOREIGN KEY (network_id) REFERENCES networks(id),
    FOREIGN KEY (type_id) REFERENCES asset_types(id)
);

-- Packages table
CREATE TABLE IF NOT EXISTS packages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    package_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT,
    company TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT
);

-- Package items junction table
CREATE TABLE IF NOT EXISTS package_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    package_id INTEGER NOT NULL,
    item_type TEXT NOT NULL CHECK(item_type IN ('network', 'asset')),
    network_id INTEGER,
    location_id INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (package_id) REFERENCES packages(id) ON DELETE CASCADE,
    FOREIGN KEY (network_id) REFERENCES networks(id),
    FOREIGN KEY (location_id) REFERENCES locations(id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_networks_company ON networks(company);
CREATE INDEX IF NOT EXISTS idx_networks_key ON networks(network_key);
CREATE INDEX IF NOT EXISTS idx_asset_types_network ON asset_types(network_id);
CREATE INDEX IF NOT EXISTS idx_asset_types_company ON asset_types(company);
CREATE INDEX IF NOT EXISTS idx_locations_network ON locations(network_id);
CREATE INDEX IF NOT EXISTS idx_locations_type ON locations(type_id);
CREATE INDEX IF NOT EXISTS idx_locations_company ON locations(company);
CREATE INDEX IF NOT EXISTS idx_locations_key ON locations(location_key);
CREATE INDEX IF NOT EXISTS idx_packages_company ON packages(company);
CREATE INDEX IF NOT EXISTS idx_package_items_package ON package_items(package_id);
"""


class SQLiteBackend(DatabaseBackend):
    """SQLite database backend for local development."""

    def __init__(self, db_path: Path | None = None):
        """
        Initialize SQLite backend.

        Args:
            db_path: Optional path to database file.
        """
        if db_path:
            self._db_path = db_path
        else:
            environment = os.getenv("ENVIRONMENT", "development")
            base_dir = Path(__file__).parent.parent

            if environment == "test":
                self._db_path = base_dir / "assets_test.db"
            else:
                self._db_path = base_dir / "assets.db"

            logger.info(f"[SQLITE] Using database at {self._db_path}")

    @property
    def name(self) -> str:
        return "sqlite"

    def _connect(self) -> sqlite3.Connection:
        """Create a database connection."""
        conn = sqlite3.connect(self._db_path, timeout=5.0, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        """Initialize database with schema."""
        conn = self._connect()
        try:
            conn.executescript(SCHEMA)
            logger.info("[SQLITE] Database initialized with schema")
        finally:
            conn.close()

    def _row_to_dict(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        """Convert a sqlite3.Row to a dict."""
        if row is None:
            return None
        return dict(row)

    def _rows_to_list(self, rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
        """Convert list of sqlite3.Row to list of dicts."""
        return [dict(row) for row in rows]

    def _now(self) -> str:
        """Get current timestamp."""
        return datetime.utcnow().isoformat()

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
        conn = self._connect()
        try:
            now = self._now()
            cursor = conn.execute(
                """
                INSERT INTO networks (network_key, name, description, company, created_at, updated_at, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (network_key, name, description, company_schema, now, now, created_by),
            )
            network_id = cursor.lastrowid
            return self.get_network(network_id, [company_schema])
        except sqlite3.IntegrityError as e:
            logger.error(f"[SQLITE] Failed to create network: {e}")
            return None
        finally:
            conn.close()

    def get_network(
        self,
        network_id: int,
        company_schemas: list[str],
    ) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            placeholders = ",".join("?" * len(company_schemas))
            cursor = conn.execute(
                f"""
                SELECT * FROM networks
                WHERE id = ? AND company IN ({placeholders}) AND is_active = 1
                """,
                (network_id, *company_schemas),
            )
            row = cursor.fetchone()
            result = self._row_to_dict(row)
            if result:
                result["company_schema"] = result.pop("company", None)
            return result
        finally:
            conn.close()

    def get_network_by_key(
        self,
        network_key: str,
        company_schemas: list[str],
    ) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            placeholders = ",".join("?" * len(company_schemas))
            cursor = conn.execute(
                f"""
                SELECT * FROM networks
                WHERE network_key = ? AND company IN ({placeholders}) AND is_active = 1
                """,
                (network_key, *company_schemas),
            )
            row = cursor.fetchone()
            result = self._row_to_dict(row)
            if result:
                result["company_schema"] = result.pop("company", None)
            return result
        finally:
            conn.close()

    def list_networks(
        self,
        company_schemas: list[str],
        include_inactive: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            placeholders = ",".join("?" * len(company_schemas))
            active_filter = "" if include_inactive else "AND is_active = 1"
            cursor = conn.execute(
                f"""
                SELECT * FROM networks
                WHERE company IN ({placeholders}) {active_filter}
                ORDER BY name
                LIMIT ? OFFSET ?
                """,
                (*company_schemas, limit, offset),
            )
            results = self._rows_to_list(cursor.fetchall())
            for r in results:
                r["company_schema"] = r.pop("company", None)
            return results
        finally:
            conn.close()

    def update_network(
        self,
        network_id: int,
        company_schema: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not updates:
            return self.get_network(network_id, [company_schema])

        conn = self._connect()
        try:
            updates["updated_at"] = self._now()
            set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
            values = list(updates.values())

            conn.execute(
                f"""
                UPDATE networks
                SET {set_clause}
                WHERE id = ? AND company = ?
                """,
                (*values, network_id, company_schema),
            )
            return self.get_network(network_id, [company_schema])
        finally:
            conn.close()

    def delete_network(
        self,
        network_id: int,
        company_schema: str,
        hard_delete: bool = False,
    ) -> bool:
        conn = self._connect()
        try:
            if hard_delete:
                cursor = conn.execute(
                    "DELETE FROM networks WHERE id = ? AND company = ?",
                    (network_id, company_schema),
                )
            else:
                cursor = conn.execute(
                    """
                    UPDATE networks
                    SET is_active = 0, updated_at = ?
                    WHERE id = ? AND company = ?
                    """,
                    (self._now(), network_id, company_schema),
                )
            return cursor.rowcount > 0
        finally:
            conn.close()

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
        conn = self._connect()
        try:
            now = self._now()
            specs_json = json.dumps(specs or {})
            cursor = conn.execute(
                """
                INSERT INTO asset_types (type_key, name, description, specs, network_id, company, created_at, updated_at, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (type_key, name, description, specs_json, network_id, company_schema, now, now, created_by),
            )
            type_id = cursor.lastrowid
            return self.get_asset_type(type_id, [company_schema])
        except sqlite3.IntegrityError as e:
            logger.error(f"[SQLITE] Failed to create asset type: {e}")
            return None
        finally:
            conn.close()

    def get_asset_type(
        self,
        type_id: int,
        company_schemas: list[str],
    ) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            placeholders = ",".join("?" * len(company_schemas))
            cursor = conn.execute(
                f"""
                SELECT at.*, n.name as network_name
                FROM asset_types at
                LEFT JOIN networks n ON at.network_id = n.id
                WHERE at.id = ? AND at.company IN ({placeholders}) AND at.is_active = 1
                """,
                (type_id, *company_schemas),
            )
            row = cursor.fetchone()
            result = self._row_to_dict(row)
            if result:
                result["company_schema"] = result.pop("company", None)
                result["specs"] = json.loads(result.get("specs", "{}"))
            return result
        finally:
            conn.close()

    def list_asset_types(
        self,
        company_schemas: list[str],
        network_id: int | None = None,
        include_inactive: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            placeholders = ",".join("?" * len(company_schemas))
            params = list(company_schemas)
            active_filter = "" if include_inactive else "AND at.is_active = 1"
            network_filter = ""
            if network_id is not None:
                network_filter = "AND at.network_id = ?"
                params.append(network_id)

            cursor = conn.execute(
                f"""
                SELECT at.*, n.name as network_name
                FROM asset_types at
                LEFT JOIN networks n ON at.network_id = n.id
                WHERE at.company IN ({placeholders}) {active_filter} {network_filter}
                ORDER BY at.name
                LIMIT ? OFFSET ?
                """,
                (*params, limit, offset),
            )
            results = self._rows_to_list(cursor.fetchall())
            for r in results:
                r["company_schema"] = r.pop("company", None)
                r["specs"] = json.loads(r.get("specs", "{}"))
            return results
        finally:
            conn.close()

    def update_asset_type(
        self,
        type_id: int,
        company_schema: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not updates:
            return self.get_asset_type(type_id, [company_schema])

        conn = self._connect()
        try:
            updates["updated_at"] = self._now()
            if "specs" in updates:
                updates["specs"] = json.dumps(updates["specs"])
            set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
            values = list(updates.values())

            conn.execute(
                f"""
                UPDATE asset_types
                SET {set_clause}
                WHERE id = ? AND company = ?
                """,
                (*values, type_id, company_schema),
            )
            return self.get_asset_type(type_id, [company_schema])
        finally:
            conn.close()

    def delete_asset_type(
        self,
        type_id: int,
        company_schema: str,
        hard_delete: bool = False,
    ) -> bool:
        conn = self._connect()
        try:
            if hard_delete:
                cursor = conn.execute(
                    "DELETE FROM asset_types WHERE id = ? AND company = ?",
                    (type_id, company_schema),
                )
            else:
                cursor = conn.execute(
                    """
                    UPDATE asset_types
                    SET is_active = 0, updated_at = ?
                    WHERE id = ? AND company = ?
                    """,
                    (self._now(), type_id, company_schema),
                )
            return cursor.rowcount > 0
        finally:
            conn.close()

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
        conn = self._connect()
        try:
            now = self._now()
            columns = [
                "location_key", "display_name", "display_type", "company",
                "network_id", "type_id", "created_at", "updated_at", "created_by"
            ]
            values = [
                location_key, display_name, display_type, company_schema,
                network_id, type_id, now, now, created_by
            ]

            # Add optional fields
            optional_fields = [
                "series", "height", "width", "number_of_faces", "spot_duration",
                "loop_duration", "sov_percent", "upload_fee", "address", "city",
                "country", "gps_lat", "gps_lng", "template_path", "notes"
            ]
            for field in optional_fields:
                if field in kwargs and kwargs[field] is not None:
                    columns.append(field)
                    values.append(kwargs[field])

            placeholders = ",".join("?" * len(values))
            columns_str = ", ".join(columns)

            cursor = conn.execute(
                f"INSERT INTO locations ({columns_str}) VALUES ({placeholders})",
                values,
            )
            location_id = cursor.lastrowid
            return self.get_location(location_id, [company_schema])
        except sqlite3.IntegrityError as e:
            logger.error(f"[SQLITE] Failed to create location: {e}")
            return None
        finally:
            conn.close()

    def get_location(
        self,
        location_id: int,
        company_schemas: list[str],
    ) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            placeholders = ",".join("?" * len(company_schemas))
            cursor = conn.execute(
                f"""
                SELECT l.*, n.name as network_name, at.name as type_name
                FROM locations l
                LEFT JOIN networks n ON l.network_id = n.id
                LEFT JOIN asset_types at ON l.type_id = at.id
                WHERE l.id = ? AND l.company IN ({placeholders}) AND l.is_active = 1
                """,
                (location_id, *company_schemas),
            )
            row = cursor.fetchone()
            result = self._row_to_dict(row)
            if result:
                result["company_schema"] = result.pop("company", None)
            return result
        finally:
            conn.close()

    def get_location_by_key(
        self,
        location_key: str,
        company_schemas: list[str],
    ) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            placeholders = ",".join("?" * len(company_schemas))
            cursor = conn.execute(
                f"""
                SELECT l.*, n.name as network_name, at.name as type_name
                FROM locations l
                LEFT JOIN networks n ON l.network_id = n.id
                LEFT JOIN asset_types at ON l.type_id = at.id
                WHERE l.location_key = ? AND l.company IN ({placeholders}) AND l.is_active = 1
                """,
                (location_key, *company_schemas),
            )
            row = cursor.fetchone()
            result = self._row_to_dict(row)
            if result:
                result["company_schema"] = result.pop("company", None)
            return result
        finally:
            conn.close()

    def list_locations(
        self,
        company_schemas: list[str],
        network_id: int | None = None,
        type_id: int | None = None,
        include_inactive: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            placeholders = ",".join("?" * len(company_schemas))
            params = list(company_schemas)
            filters = []

            if not include_inactive:
                filters.append("l.is_active = 1")
            if network_id is not None:
                filters.append("l.network_id = ?")
                params.append(network_id)
            if type_id is not None:
                filters.append("l.type_id = ?")
                params.append(type_id)

            where_clause = f"l.company IN ({placeholders})"
            if filters:
                where_clause += " AND " + " AND ".join(filters)

            cursor = conn.execute(
                f"""
                SELECT l.*, n.name as network_name, at.name as type_name
                FROM locations l
                LEFT JOIN networks n ON l.network_id = n.id
                LEFT JOIN asset_types at ON l.type_id = at.id
                WHERE {where_clause}
                ORDER BY l.display_name
                LIMIT ? OFFSET ?
                """,
                (*params, limit, offset),
            )
            results = self._rows_to_list(cursor.fetchall())
            for r in results:
                r["company_schema"] = r.pop("company", None)
            return results
        finally:
            conn.close()

    def update_location(
        self,
        location_id: int,
        company_schema: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not updates:
            return self.get_location(location_id, [company_schema])

        conn = self._connect()
        try:
            updates["updated_at"] = self._now()
            set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
            values = list(updates.values())

            conn.execute(
                f"""
                UPDATE locations
                SET {set_clause}
                WHERE id = ? AND company = ?
                """,
                (*values, location_id, company_schema),
            )
            return self.get_location(location_id, [company_schema])
        finally:
            conn.close()

    def delete_location(
        self,
        location_id: int,
        company_schema: str,
        hard_delete: bool = False,
    ) -> bool:
        conn = self._connect()
        try:
            if hard_delete:
                cursor = conn.execute(
                    "DELETE FROM locations WHERE id = ? AND company = ?",
                    (location_id, company_schema),
                )
            else:
                cursor = conn.execute(
                    """
                    UPDATE locations
                    SET is_active = 0, updated_at = ?
                    WHERE id = ? AND company = ?
                    """,
                    (self._now(), location_id, company_schema),
                )
            return cursor.rowcount > 0
        finally:
            conn.close()

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
        conn = self._connect()
        try:
            now = self._now()
            cursor = conn.execute(
                """
                INSERT INTO packages (package_key, name, description, company, created_at, updated_at, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (package_key, name, description, company_schema, now, now, created_by),
            )
            package_id = cursor.lastrowid
            return self.get_package(package_id, [company_schema])
        except sqlite3.IntegrityError as e:
            logger.error(f"[SQLITE] Failed to create package: {e}")
            return None
        finally:
            conn.close()

    def get_package(
        self,
        package_id: int,
        company_schemas: list[str],
    ) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            placeholders = ",".join("?" * len(company_schemas))
            cursor = conn.execute(
                f"""
                SELECT * FROM packages
                WHERE id = ? AND company IN ({placeholders}) AND is_active = 1
                """,
                (package_id, *company_schemas),
            )
            row = cursor.fetchone()
            result = self._row_to_dict(row)
            if result:
                result["company_schema"] = result.pop("company", None)
                result["items"] = self.get_package_items(package_id, result["company_schema"])
            return result
        finally:
            conn.close()

    def list_packages(
        self,
        company_schemas: list[str],
        include_inactive: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            placeholders = ",".join("?" * len(company_schemas))
            active_filter = "" if include_inactive else "AND is_active = 1"
            cursor = conn.execute(
                f"""
                SELECT * FROM packages
                WHERE company IN ({placeholders}) {active_filter}
                ORDER BY name
                LIMIT ? OFFSET ?
                """,
                (*company_schemas, limit, offset),
            )
            results = self._rows_to_list(cursor.fetchall())
            for r in results:
                r["company_schema"] = r.pop("company", None)
            return results
        finally:
            conn.close()

    def update_package(
        self,
        package_id: int,
        company_schema: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not updates:
            return self.get_package(package_id, [company_schema])

        conn = self._connect()
        try:
            updates["updated_at"] = self._now()
            set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
            values = list(updates.values())

            conn.execute(
                f"""
                UPDATE packages
                SET {set_clause}
                WHERE id = ? AND company = ?
                """,
                (*values, package_id, company_schema),
            )
            return self.get_package(package_id, [company_schema])
        finally:
            conn.close()

    def delete_package(
        self,
        package_id: int,
        company_schema: str,
        hard_delete: bool = False,
    ) -> bool:
        conn = self._connect()
        try:
            if hard_delete:
                cursor = conn.execute(
                    "DELETE FROM packages WHERE id = ? AND company = ?",
                    (package_id, company_schema),
                )
            else:
                cursor = conn.execute(
                    """
                    UPDATE packages
                    SET is_active = 0, updated_at = ?
                    WHERE id = ? AND company = ?
                    """,
                    (self._now(), package_id, company_schema),
                )
            return cursor.rowcount > 0
        finally:
            conn.close()

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
        conn = self._connect()
        try:
            now = self._now()
            cursor = conn.execute(
                """
                INSERT INTO package_items (package_id, item_type, network_id, location_id, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (package_id, item_type, network_id, location_id, now),
            )
            item_id = cursor.lastrowid

            # Fetch the created item with expanded info
            cursor = conn.execute(
                """
                SELECT pi.*, n.name as network_name, l.display_name as location_name
                FROM package_items pi
                LEFT JOIN networks n ON pi.network_id = n.id
                LEFT JOIN locations l ON pi.location_id = l.id
                WHERE pi.id = ?
                """,
                (item_id,),
            )
            return self._row_to_dict(cursor.fetchone())
        except sqlite3.IntegrityError as e:
            logger.error(f"[SQLITE] Failed to add package item: {e}")
            return None
        finally:
            conn.close()

    def remove_package_item(
        self,
        item_id: int,
        company_schema: str,
    ) -> bool:
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                DELETE FROM package_items
                WHERE id = ? AND package_id IN (
                    SELECT id FROM packages WHERE company = ?
                )
                """,
                (item_id, company_schema),
            )
            return cursor.rowcount > 0
        finally:
            conn.close()

    def get_package_items(
        self,
        package_id: int,
        company_schema: str,
    ) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT pi.*, n.name as network_name, l.display_name as location_name,
                       (SELECT COUNT(*) FROM locations WHERE network_id = pi.network_id AND is_active = 1) as location_count
                FROM package_items pi
                LEFT JOIN networks n ON pi.network_id = n.id
                LEFT JOIN locations l ON pi.location_id = l.id
                WHERE pi.package_id = ?
                """,
                (package_id,),
            )
            return self._rows_to_list(cursor.fetchall())
        finally:
            conn.close()

    def get_package_locations(
        self,
        package_id: int,
        company_schema: str,
    ) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            # Get all locations: direct assets + locations from included networks
            cursor = conn.execute(
                """
                SELECT DISTINCT l.*, n.name as network_name, at.name as type_name
                FROM locations l
                LEFT JOIN networks n ON l.network_id = n.id
                LEFT JOIN asset_types at ON l.type_id = at.id
                WHERE l.is_active = 1 AND (
                    -- Direct asset references
                    l.id IN (
                        SELECT location_id FROM package_items
                        WHERE package_id = ? AND item_type = 'asset'
                    )
                    OR
                    -- Locations belonging to included networks
                    l.network_id IN (
                        SELECT network_id FROM package_items
                        WHERE package_id = ? AND item_type = 'network'
                    )
                )
                ORDER BY l.display_name
                """,
                (package_id, package_id),
            )
            results = self._rows_to_list(cursor.fetchall())
            for r in results:
                r["company_schema"] = r.pop("company", None)
            return results
        finally:
            conn.close()

    # =========================================================================
    # ELIGIBILITY
    # =========================================================================

    def check_location_eligibility(
        self,
        location_id: int,
        company_schemas: list[str],
    ) -> dict[str, Any]:
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

        # Check proposal_generator eligibility
        proposal_missing = []
        if not location.get("display_name"):
            proposal_missing.append("display_name")
        if not location.get("display_type"):
            proposal_missing.append("display_type")
        has_rate = self.has_rate_card(location_id, company_schema)
        if not has_rate:
            proposal_missing.append("rate_card")

        details.append({
            "service": "proposal_generator",
            "eligible": len(proposal_missing) == 0,
            "missing_fields": proposal_missing,
            "warnings": [],
        })

        # Check mockup_generator eligibility
        mockup_missing = []
        if not location.get("display_name"):
            mockup_missing.append("display_name")
        if not location.get("template_path"):
            mockup_missing.append("template_path")
        has_mockup = self.has_mockup_frame(location.get("location_key", ""), company_schema)
        if not has_mockup:
            mockup_missing.append("mockup_frame")

        details.append({
            "service": "mockup_generator",
            "eligible": len(mockup_missing) == 0,
            "missing_fields": mockup_missing,
            "warnings": [],
        })

        # Check availability_calendar eligibility
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

        # Count eligible locations per service
        proposal_eligible = sum(
            1 for loc in locations
            if self.check_location_eligibility(loc["id"], [company_schema])["service_eligibility"]["proposal_generator"]
        )
        calendar_eligible = sum(
            1 for loc in locations
            if self.check_location_eligibility(loc["id"], [company_schema])["service_eligibility"]["availability_calendar"]
        )

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

        # Mockup generator - networks are not eligible
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
        # For SQLite, we do in-memory filtering since we don't have rate_cards/mockup_frames tables
        all_locations = self.list_locations(company_schemas, limit=1000, offset=0)
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
        all_networks = self.list_networks(company_schemas, limit=1000, offset=0)
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

    def has_rate_card(
        self,
        location_id: int,
        company_schema: str,
    ) -> bool:
        """
        Check if location has rate card.
        In SQLite mode, always returns True (for local dev without sales-module).
        """
        # SQLite doesn't have cross-service rate_cards table
        # Return True to allow local development
        return True

    def has_mockup_frame(
        self,
        location_key: str,
        company_schema: str,
    ) -> bool:
        """
        Check if location has mockup frame.
        In SQLite mode, always returns True (for local dev without sales-module).
        """
        # SQLite doesn't have cross-service mockup_frames table
        # Return True to allow local development
        return True
