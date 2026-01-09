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
# Unified architecture: standalone assets are merged into networks table
SCHEMA = """
-- Networks table (unified architecture: includes standalone flag and location fields)
CREATE TABLE IF NOT EXISTS networks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    network_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT,
    company TEXT NOT NULL,
    -- Unified architecture: standalone flag (INTERNAL ONLY)
    standalone INTEGER DEFAULT 0,
    -- Location fields (used for standalone networks)
    display_type TEXT CHECK(display_type IS NULL OR display_type IN ('digital', 'static')),
    series TEXT,
    height TEXT,
    width TEXT,
    number_of_faces INTEGER DEFAULT 1,
    spot_duration INTEGER,
    loop_duration INTEGER,
    sov_percent REAL,
    upload_fee REAL,
    city TEXT,
    area TEXT,
    country TEXT,
    address TEXT,
    gps_lat REAL,
    gps_lng REAL,
    template_path TEXT,
    notes TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT
);

-- Asset types table (for traditional networks only)
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

-- Network assets table (physical display units within a network)
CREATE TABLE IF NOT EXISTS network_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_key TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    display_type TEXT NOT NULL CHECK(display_type IN ('digital', 'static')),
    network_id INTEGER NOT NULL,
    type_id INTEGER,
    environment TEXT DEFAULT 'outdoor' CHECK(environment IN ('indoor', 'outdoor')),
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
    area TEXT,
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

-- Package items table (unified: only networks allowed)
CREATE TABLE IF NOT EXISTS package_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    package_id INTEGER NOT NULL,
    item_type TEXT NOT NULL DEFAULT 'network' CHECK(item_type = 'network'),
    network_id INTEGER NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (package_id) REFERENCES packages(id) ON DELETE CASCADE,
    FOREIGN KEY (network_id) REFERENCES networks(id)
);

-- Mockup frames table
CREATE TABLE IF NOT EXISTS mockup_frames (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_key TEXT NOT NULL,
    environment TEXT NOT NULL DEFAULT 'outdoor' CHECK(environment IN ('indoor', 'outdoor')),
    time_of_day TEXT NOT NULL DEFAULT 'day' CHECK(time_of_day IN ('day', 'night')),
    side TEXT NOT NULL DEFAULT 'gold' CHECK(side IN ('gold', 'silver', 'single_side')),
    photo_filename TEXT NOT NULL,
    frames_data TEXT NOT NULL DEFAULT '[]',
    config TEXT,
    company TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT,
    UNIQUE(location_key, environment, time_of_day, side, photo_filename, company)
);

-- Locations VIEW (unified: shows networks as sellable locations)
-- This mirrors the Supabase locations VIEW
CREATE VIEW IF NOT EXISTS locations AS
SELECT
    n.id,
    n.network_key AS location_key,
    n.name AS display_name,
    n.display_type,
    n.id AS network_id,
    NULL AS type_id,
    n.series,
    n.height,
    n.width,
    n.number_of_faces,
    n.spot_duration,
    n.loop_duration,
    n.sov_percent,
    n.upload_fee,
    n.city,
    n.area,
    n.country,
    n.address,
    n.gps_lat,
    n.gps_lng,
    n.template_path,
    n.is_active,
    n.created_at,
    n.updated_at,
    n.created_by,
    n.notes,
    n.company
FROM networks n
WHERE n.is_active = 1;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_networks_company ON networks(company);
CREATE INDEX IF NOT EXISTS idx_networks_key ON networks(network_key);
CREATE INDEX IF NOT EXISTS idx_networks_standalone ON networks(standalone);
CREATE INDEX IF NOT EXISTS idx_asset_types_network ON asset_types(network_id);
CREATE INDEX IF NOT EXISTS idx_asset_types_company ON asset_types(company);
CREATE INDEX IF NOT EXISTS idx_network_assets_network ON network_assets(network_id);
CREATE INDEX IF NOT EXISTS idx_network_assets_type ON network_assets(type_id);
CREATE INDEX IF NOT EXISTS idx_network_assets_company ON network_assets(company);
CREATE INDEX IF NOT EXISTS idx_network_assets_key ON network_assets(location_key);
CREATE INDEX IF NOT EXISTS idx_network_assets_environment ON network_assets(environment);
CREATE INDEX IF NOT EXISTS idx_packages_company ON packages(company);
CREATE INDEX IF NOT EXISTS idx_package_items_package ON package_items(package_id);
CREATE INDEX IF NOT EXISTS idx_mockup_frames_location ON mockup_frames(location_key);
CREATE INDEX IF NOT EXISTS idx_mockup_frames_company ON mockup_frames(company);
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
        conn = self._connect()
        try:
            now = self._now()
            # Build dynamic insert with all unified fields
            fields = ["network_key", "name", "description", "company", "standalone",
                      "created_at", "updated_at", "created_by"]
            values = [network_key, name, description, company_schema, 1 if standalone else 0,
                      now, now, created_by]

            # Add optional fields
            optional = {
                "display_type": display_type,
                "series": series,
                "height": height,
                "width": width,
                "number_of_faces": number_of_faces,
                "spot_duration": spot_duration,
                "loop_duration": loop_duration,
                "sov_percent": sov_percent,
                "upload_fee": upload_fee,
                "city": city,
                "area": area,
                "country": country,
                "address": address,
                "gps_lat": gps_lat,
                "gps_lng": gps_lng,
                "template_path": template_path,
                "notes": notes,
            }
            for field, value in optional.items():
                if value is not None:
                    fields.append(field)
                    values.append(value)

            placeholders = ", ".join("?" * len(values))
            field_names = ", ".join(fields)
            cursor = conn.execute(
                f"INSERT INTO networks ({field_names}) VALUES ({placeholders})",
                values,
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
    # LOCATIONS (Unified: locations = networks)
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
        """Create a location (which is a standalone network in unified architecture)."""
        # In unified architecture, creating a location = creating a standalone network
        return self.create_network(
            network_key=location_key,
            name=display_name,
            company_schema=company_schema,
            created_by=created_by,
            standalone=True,
            display_type=display_type,
            series=kwargs.get("series"),
            height=kwargs.get("height"),
            width=kwargs.get("width"),
            number_of_faces=kwargs.get("number_of_faces"),
            spot_duration=kwargs.get("spot_duration"),
            loop_duration=kwargs.get("loop_duration"),
            sov_percent=kwargs.get("sov_percent"),
            upload_fee=kwargs.get("upload_fee"),
            city=kwargs.get("city"),
            area=kwargs.get("area"),
            country=kwargs.get("country"),
            address=kwargs.get("address"),
            gps_lat=kwargs.get("gps_lat"),
            gps_lng=kwargs.get("gps_lng"),
            template_path=kwargs.get("template_path"),
            notes=kwargs.get("notes"),
        )

    def get_location(
        self,
        location_id: int,
        company_schemas: list[str],
    ) -> dict[str, Any] | None:
        """Get a location by ID (locations = networks in unified architecture)."""
        conn = self._connect()
        try:
            placeholders = ",".join("?" * len(company_schemas))
            cursor = conn.execute(
                f"""
                SELECT * FROM locations
                WHERE id = ? AND company IN ({placeholders})
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
        """Get a location by key (locations = networks in unified architecture)."""
        conn = self._connect()
        try:
            placeholders = ",".join("?" * len(company_schemas))
            cursor = conn.execute(
                f"""
                SELECT * FROM locations
                WHERE location_key = ? AND company IN ({placeholders})
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
        """List locations (locations = networks in unified architecture)."""
        conn = self._connect()
        try:
            placeholders = ",".join("?" * len(company_schemas))
            params = list(company_schemas)
            filters = []

            # Note: locations VIEW already filters is_active=1
            # network_id filter: if provided, filter by network_id (which equals id in locations)
            if network_id is not None:
                filters.append("network_id = ?")
                params.append(network_id)

            where_clause = f"company IN ({placeholders})"
            if filters:
                where_clause += " AND " + " AND ".join(filters)

            cursor = conn.execute(
                f"""
                SELECT * FROM locations
                WHERE {where_clause}
                ORDER BY display_name
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
        """Update a location (updates the networks table in unified architecture)."""
        if not updates:
            return self.get_location(location_id, [company_schema])

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
        """Delete a location (deletes from networks table in unified architecture)."""
        conn = self._connect()
        try:
            if hard_delete:
                cursor = conn.execute(
                    "DELETE FROM networks WHERE id = ? AND company = ?",
                    (location_id, company_schema),
                )
            else:
                cursor = conn.execute(
                    """
                    UPDATE networks
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
        company_schema: str,
        network_id: int,
    ) -> dict[str, Any] | None:
        """Add a network to a package. Unified architecture: only networks allowed."""
        conn = self._connect()
        try:
            now = self._now()
            cursor = conn.execute(
                """
                INSERT INTO package_items (package_id, item_type, network_id, created_at)
                VALUES (?, 'network', ?, ?)
                """,
                (package_id, network_id, now),
            )
            item_id = cursor.lastrowid

            # Fetch the created item with expanded info
            cursor = conn.execute(
                """
                SELECT pi.*, n.name as network_name,
                       (SELECT COUNT(*) FROM network_assets WHERE network_id = pi.network_id AND is_active = 1) as location_count
                FROM package_items pi
                LEFT JOIN networks n ON pi.network_id = n.id
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
        """Get all items in a package. Unified architecture: all items are networks."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT pi.*, n.name as network_name,
                       (SELECT COUNT(*) FROM network_assets WHERE network_id = pi.network_id AND is_active = 1) as location_count
                FROM package_items pi
                LEFT JOIN networks n ON pi.network_id = n.id
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
        """Get all networks in a package.

        Unified architecture: packages contain networks (both standalone and traditional).
        Returns the networks themselves, not expanded to individual assets.
        """
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT DISTINCT n.*
                FROM networks n
                INNER JOIN package_items pi ON n.id = pi.network_id
                WHERE pi.package_id = ? AND n.is_active = 1
                ORDER BY n.name
                """,
                (package_id,),
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
        """
        Check basic location eligibility (local fields only).

        Note: Proposal and mockup eligibility require data from Sales-Module.
        Use EligibilityService for full checks.
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

        # OPTIMIZED: Count eligible locations per service using in-memory check
        # Instead of N DB calls, we compute eligibility from already-fetched data
        proposal_eligible = 0
        calendar_eligible = 0
        for loc in locations:
            service_elig = self._compute_location_eligibility(loc)
            if service_elig.get("proposal_generator"):
                proposal_eligible += 1
            if service_elig.get("availability_calendar"):
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

    def _compute_location_eligibility(self, loc: dict[str, Any]) -> dict[str, bool]:
        """
        Compute eligibility for a location without DB call.

        OPTIMIZED: Works on already-fetched location data to avoid N+1.
        """
        # Proposal generator - basic field check
        proposal_eligible = bool(loc.get("display_name")) and bool(loc.get("display_type"))
        # Mockup generator - basic field check
        mockup_eligible = bool(loc.get("display_name"))
        # Availability calendar - basic field check
        calendar_eligible = bool(loc.get("display_name"))

        return {
            "proposal_generator": proposal_eligible,
            "mockup_generator": mockup_eligible,
            "availability_calendar": calendar_eligible,
        }

    def get_eligible_locations(
        self,
        service: str,
        company_schemas: list[str],
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        # OPTIMIZED: Check eligibility in-memory instead of N DB calls
        all_locations = self.list_locations(company_schemas, limit=1000, offset=0)
        eligible = []

        for loc in all_locations:
            # Compute eligibility without calling get_location again
            service_elig = self._compute_location_eligibility(loc)
            if service_elig.get(service, False):
                loc["service_eligibility"] = service_elig
                eligible.append(loc)

        return eligible[offset:offset + limit]

    def get_eligible_networks(
        self,
        service: str,
        company_schemas: list[str],
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        # OPTIMIZED: Bulk fetch all locations once, then group by network
        all_networks = self.list_networks(company_schemas, limit=1000, offset=0)
        all_locations = self.list_locations(company_schemas, limit=10000, offset=0)

        # Build index: network_id -> list of locations
        locations_by_network: dict[int, list[dict]] = {}
        for loc in all_locations:
            net_id = loc.get("network_id")
            if net_id:
                if net_id not in locations_by_network:
                    locations_by_network[net_id] = []
                locations_by_network[net_id].append(loc)

        eligible = []
        for net in all_networks:
            net_id = net["id"]
            company_schema = net.get("company_schema", "")
            net_locations = locations_by_network.get(net_id, [])

            # Compute network eligibility in-memory
            proposal_eligible = 0
            calendar_eligible = 0
            for loc in net_locations:
                service_elig = self._compute_location_eligibility(loc)
                if service_elig.get("proposal_generator"):
                    proposal_eligible += 1
                if service_elig.get("availability_calendar"):
                    calendar_eligible += 1

            # Check network-level eligibility
            has_name = bool(net.get("name"))
            net_service_elig = {
                "proposal_generator": has_name and proposal_eligible > 0,
                "mockup_generator": False,  # Networks not eligible for mockup
                "availability_calendar": has_name and calendar_eligible > 0,
            }

            if net_service_elig.get(service, False):
                net["service_eligibility"] = net_service_elig
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
        """List all mockup frames for a location."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT * FROM mockup_frames
                WHERE location_key = ? AND company = ?
                ORDER BY environment, time_of_day, side, photo_filename
                """,
                (location_key, company_schema),
            )
            results = self._rows_to_list(cursor.fetchall())
            for r in results:
                r["frames_data"] = json.loads(r.get("frames_data", "[]"))
                if r.get("config"):
                    r["config"] = json.loads(r["config"])
            return results
        finally:
            conn.close()

    def get_locations_with_frames(
        self,
        company_schemas: list[str],
    ) -> list[dict[str, Any]]:
        """
        Get all distinct location_keys that have mockup frames across companies.

        This is a bulk query to avoid N+1 queries when checking eligibility.

        Args:
            company_schemas: List of company schemas to check

        Returns:
            List of dicts with location_key, company, frame_count
        """
        conn = self._connect()
        try:
            placeholders = ",".join(["?" for _ in company_schemas])
            cursor = conn.execute(
                f"""
                SELECT location_key, company, COUNT(*) as frame_count
                FROM mockup_frames
                WHERE company IN ({placeholders})
                GROUP BY location_key, company
                """,
                company_schemas,
            )
            return self._rows_to_list(cursor.fetchall())
        finally:
            conn.close()

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
        conn = self._connect()
        try:
            conn.execute("BEGIN")
            config_json = json.dumps(config) if config else None

            # Generate auto-numbered filename
            _, ext = os.path.splitext(photo_filename)
            location_display_name = location_key.replace('_', ' ').title().replace(' ', '')

            cursor = conn.cursor()
            cursor.execute(
                "SELECT photo_filename FROM mockup_frames WHERE location_key = ? AND company = ?",
                (location_key, company_schema),
            )
            existing_files = [row[0] for row in cursor.fetchall()]

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

            conn.execute(
                """
                INSERT INTO mockup_frames (location_key, company, environment, time_of_day, side, photo_filename, frames_data, created_at, created_by, config)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (location_key, company_schema, environment, time_of_day, side, final_filename,
                 json.dumps(frames_data), datetime.now().isoformat(), created_by, config_json),
            )

            conn.execute("COMMIT")
            logger.info(f"[SQLITE] Saved mockup frame: {company_schema}.{location_key}/{environment}/{final_filename}")
            return final_filename
        except Exception as e:
            conn.execute("ROLLBACK")
            logger.error(f"[SQLITE] Failed to save mockup frame for {location_key}: {e}", exc_info=True)
            raise
        finally:
            conn.close()

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
        conn = self._connect()
        try:
            if environment == "indoor":
                # For indoor, ignore time_of_day and side
                if photo_filename:
                    cursor = conn.execute(
                        """
                        SELECT * FROM mockup_frames
                        WHERE location_key = ? AND company = ?
                        AND environment = ? AND photo_filename = ?
                        LIMIT 1
                        """,
                        (location_key, company, environment, photo_filename),
                    )
                else:
                    cursor = conn.execute(
                        """
                        SELECT * FROM mockup_frames
                        WHERE location_key = ? AND company = ?
                        AND environment = ?
                        LIMIT 1
                        """,
                        (location_key, company, environment),
                    )
            else:
                # For outdoor, match all fields
                if photo_filename:
                    cursor = conn.execute(
                        """
                        SELECT * FROM mockup_frames
                        WHERE location_key = ? AND company = ?
                        AND environment = ? AND time_of_day = ? AND side = ? AND photo_filename = ?
                        LIMIT 1
                        """,
                        (location_key, company, environment, time_of_day, side, photo_filename),
                    )
                else:
                    cursor = conn.execute(
                        """
                        SELECT * FROM mockup_frames
                        WHERE location_key = ? AND company = ?
                        AND environment = ? AND time_of_day = ? AND side = ?
                        LIMIT 1
                        """,
                        (location_key, company, environment, time_of_day, side),
                    )

            row = cursor.fetchone()
            result = self._row_to_dict(row)
            if result:
                result["frames_data"] = json.loads(result.get("frames_data", "[]"))
                if result.get("config"):
                    result["config"] = json.loads(result["config"])
            return result
        finally:
            conn.close()

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
        conn = self._connect()
        try:
            if environment == "indoor":
                # For indoor, ignore time_of_day and side
                conn.execute(
                    """
                    DELETE FROM mockup_frames
                    WHERE location_key = ? AND company = ?
                    AND photo_filename = ? AND environment = ?
                    """,
                    (location_key, company, photo_filename, environment),
                )
            else:
                # For outdoor, match all fields
                conn.execute(
                    """
                    DELETE FROM mockup_frames
                    WHERE location_key = ? AND company = ?
                    AND photo_filename = ? AND environment = ? AND time_of_day = ? AND side = ?
                    """,
                    (location_key, company, photo_filename, environment, time_of_day, side),
                )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"[SQLITE] Failed to delete mockup frame: {e}")
            return False
        finally:
            conn.close()

    # =========================================================================
    # COMPANIES
    # =========================================================================

    def get_companies(
        self,
        active_only: bool = True,
        leaf_only: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Get all companies from config (SQLite doesn't have companies table).

        For SQLite backend, we return the configured COMPANY_SCHEMAS.
        This is a fallback for local development.
        """
        from config import COMPANY_SCHEMAS

        # Return basic company info from config
        return [
            {
                "id": idx,
                "code": code,
                "name": code,  # Use code as name for SQLite
                "country": None,
                "currency": None,
                "is_group": False,
                "is_active": True,
            }
            for idx, code in enumerate(COMPANY_SCHEMAS, start=1)
        ]

    def expand_companies(
        self,
        company_codes: list[str],
    ) -> list[str]:
        """
        Expand company codes to include all accessible leaf companies.

        For SQLite (local dev), we use a hardcoded hierarchy matching production:
        - mmg (group) -> all companies
        - backlite (group) -> backlite_dubai, backlite_ksa, backlite_uk, backlite_abudhabi
        - viola (leaf) -> viola
        - Individual leaf companies -> themselves
        """
        from config import COMPANY_SCHEMAS

        # Define hierarchy for local development
        HIERARCHY = {
            "mmg": COMPANY_SCHEMAS,  # Root gets all
            "backlite": [c for c in COMPANY_SCHEMAS if c.startswith("backlite_")],
        }

        result = set()
        for code in company_codes:
            if code in HIERARCHY:
                # Group company - expand
                result.update(HIERARCHY[code])
            elif code in COMPANY_SCHEMAS:
                # Leaf company - add directly
                result.add(code)
            # Unknown codes are ignored

        return sorted(result)

    def get_company_hierarchy(
        self,
    ) -> list[dict[str, Any]]:
        """
        Get the full company hierarchy tree.

        For SQLite (local dev), returns a hardcoded hierarchy matching production.
        """
        from config import COMPANY_SCHEMAS

        # Build a simple hierarchy for local dev
        companies = [
            {"id": 1, "code": "mmg", "name": "MMG", "parent_id": None, "is_group": True, "is_active": True, "children": ["backlite", "viola"]},
            {"id": 2, "code": "backlite", "name": "Backlite", "parent_id": 1, "is_group": True, "is_active": True, "children": [c for c in COMPANY_SCHEMAS if c.startswith("backlite_")]},
        ]

        # Add leaf companies
        idx = 3
        for code in COMPANY_SCHEMAS:
            if code.startswith("backlite_"):
                companies.append({
                    "id": idx,
                    "code": code,
                    "name": code.replace("_", " ").title(),
                    "parent_id": 2,  # Under backlite
                    "is_group": False,
                    "is_active": True,
                    "children": [],
                })
            elif code == "viola":
                companies.append({
                    "id": idx,
                    "code": code,
                    "name": "Viola",
                    "parent_id": 1,  # Under mmg
                    "is_group": False,
                    "is_active": True,
                    "children": [],
                })
            else:
                # Other leaf companies under mmg
                companies.append({
                    "id": idx,
                    "code": code,
                    "name": code.replace("_", " ").title(),
                    "parent_id": 1,
                    "is_group": False,
                    "is_active": True,
                    "children": [],
                })
            idx += 1

        return companies