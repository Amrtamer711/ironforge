"""
Migration Runner.

Handles discovery, execution, and tracking of database migrations.
"""

import importlib.util
import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from utils.logging import get_logger

logger = get_logger("db.migrations")

# Migration directory
MIGRATIONS_DIR = Path(__file__).parent / "versions"


@dataclass
class Migration:
    """Represents a single migration."""

    version: str  # e.g., "001"
    name: str  # e.g., "add_workflow_column"
    upgrade: Callable[[sqlite3.Connection], None]
    downgrade: Callable[[sqlite3.Connection], None]
    description: str = ""

    @property
    def full_name(self) -> str:
        """Get full migration name (version_name)."""
        return f"{self.version}_{self.name}"


class MigrationRunner:
    """
    Runs database migrations.

    Features:
    - Discovers migrations from db/migrations/versions/
    - Tracks applied migrations in _migrations table
    - Supports upgrade (forward) and downgrade (rollback)
    - Transactional migrations with automatic rollback on error
    """

    MIGRATIONS_TABLE = "_migrations"

    def __init__(self, db_path: str):
        """
        Initialize migration runner.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
        self._migrations: list[Migration] = []
        self._ensure_migrations_table()
        self._discover_migrations()

    def _connect(self) -> sqlite3.Connection:
        """Get database connection."""
        # Ensure parent directory exists
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_migrations_table(self) -> None:
        """Create migrations tracking table if it doesn't exist."""
        conn = self._connect()
        try:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.MIGRATIONS_TABLE} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    applied_at TEXT NOT NULL,
                    checksum TEXT
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def _discover_migrations(self) -> None:
        """Discover migration files from versions directory."""
        self._migrations = []

        if not MIGRATIONS_DIR.exists():
            MIGRATIONS_DIR.mkdir(parents=True, exist_ok=True)
            logger.info(f"[MIGRATIONS] Created versions directory: {MIGRATIONS_DIR}")
            return

        # Pattern: NNN_name.py (e.g., 001_initial.py)
        pattern = re.compile(r"^(\d{3})_([a-z0-9_]+)\.py$")

        for file_path in sorted(MIGRATIONS_DIR.glob("*.py")):
            if file_path.name.startswith("_"):
                continue

            match = pattern.match(file_path.name)
            if not match:
                logger.warning(
                    f"[MIGRATIONS] Skipping invalid migration file: {file_path.name}"
                )
                continue

            version = match.group(1)
            name = match.group(2)

            # Load migration module
            try:
                spec = importlib.util.spec_from_file_location(
                    f"migration_{version}_{name}", file_path
                )
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                    # Get upgrade/downgrade functions
                    upgrade_fn = getattr(module, "upgrade", None)
                    downgrade_fn = getattr(module, "downgrade", None)
                    description = getattr(module, "DESCRIPTION", "")

                    if not upgrade_fn:
                        logger.warning(
                            f"[MIGRATIONS] Migration {file_path.name} missing upgrade function"
                        )
                        continue

                    migration = Migration(
                        version=version,
                        name=name,
                        upgrade=upgrade_fn,
                        downgrade=downgrade_fn or (lambda conn: None),
                        description=description,
                    )
                    self._migrations.append(migration)
                    logger.debug(f"[MIGRATIONS] Discovered: {migration.full_name}")

            except Exception as e:
                logger.error(f"[MIGRATIONS] Failed to load {file_path.name}: {e}")

        logger.info(f"[MIGRATIONS] Discovered {len(self._migrations)} migrations")

    def get_applied_migrations(self) -> list[str]:
        """Get list of applied migration versions."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                f"SELECT version FROM {self.MIGRATIONS_TABLE} ORDER BY version"
            )
            return [row["version"] for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_pending_migrations(self) -> list[Migration]:
        """Get list of pending (unapplied) migrations."""
        applied = set(self.get_applied_migrations())
        return [m for m in self._migrations if m.version not in applied]

    def get_status(self) -> dict[str, Any]:
        """Get migration status."""
        applied = self.get_applied_migrations()
        pending = self.get_pending_migrations()

        conn = self._connect()
        try:
            cursor = conn.execute(
                f"SELECT * FROM {self.MIGRATIONS_TABLE} ORDER BY version DESC LIMIT 1"
            )
            last_applied = cursor.fetchone()
        finally:
            conn.close()

        return {
            "total_migrations": len(self._migrations),
            "applied_count": len(applied),
            "pending_count": len(pending),
            "applied_versions": applied,
            "pending_migrations": [
                {"version": m.version, "name": m.name, "description": m.description}
                for m in pending
            ],
            "last_applied": (
                {
                    "version": last_applied["version"],
                    "name": last_applied["name"],
                    "applied_at": last_applied["applied_at"],
                }
                if last_applied
                else None
            ),
        }

    def migrate(self, target_version: str | None = None) -> tuple[int, list[str]]:
        """
        Run pending migrations.

        Args:
            target_version: Optional target version (runs all if not specified)

        Returns:
            Tuple of (count of applied migrations, list of applied versions)
        """
        pending = self.get_pending_migrations()

        if target_version:
            pending = [m for m in pending if m.version <= target_version]

        if not pending:
            logger.info("[MIGRATIONS] No pending migrations")
            return 0, []

        applied = []
        conn = self._connect()

        try:
            for migration in pending:
                logger.info(
                    f"[MIGRATIONS] Applying {migration.full_name}: {migration.description}"
                )

                try:
                    # Start transaction
                    conn.execute("BEGIN")

                    # Run upgrade
                    migration.upgrade(conn)

                    # Record migration
                    conn.execute(
                        f"""
                        INSERT INTO {self.MIGRATIONS_TABLE} (version, name, applied_at)
                        VALUES (?, ?, ?)
                        """,
                        (
                            migration.version,
                            migration.name,
                            datetime.now().isoformat(),
                        ),
                    )

                    conn.execute("COMMIT")
                    applied.append(migration.version)
                    logger.info(f"[MIGRATIONS] Applied {migration.full_name}")

                except Exception as e:
                    conn.execute("ROLLBACK")
                    logger.error(
                        f"[MIGRATIONS] Failed to apply {migration.full_name}: {e}"
                    )
                    raise

        finally:
            conn.close()

        return len(applied), applied

    def rollback(self, steps: int = 1) -> tuple[int, list[str]]:
        """
        Rollback migrations.

        Args:
            steps: Number of migrations to rollback

        Returns:
            Tuple of (count of rolled back migrations, list of versions)
        """
        applied = self.get_applied_migrations()

        if not applied:
            logger.info("[MIGRATIONS] No migrations to rollback")
            return 0, []

        # Get migrations to rollback (in reverse order)
        to_rollback = []
        for version in reversed(applied[-steps:]):
            migration = next((m for m in self._migrations if m.version == version), None)
            if migration:
                to_rollback.append(migration)

        if not to_rollback:
            logger.warning("[MIGRATIONS] No matching migrations found for rollback")
            return 0, []

        rolled_back = []
        conn = self._connect()

        try:
            for migration in to_rollback:
                logger.info(f"[MIGRATIONS] Rolling back {migration.full_name}")

                try:
                    conn.execute("BEGIN")

                    # Run downgrade
                    migration.downgrade(conn)

                    # Remove migration record
                    conn.execute(
                        f"DELETE FROM {self.MIGRATIONS_TABLE} WHERE version = ?",
                        (migration.version,),
                    )

                    conn.execute("COMMIT")
                    rolled_back.append(migration.version)
                    logger.info(f"[MIGRATIONS] Rolled back {migration.full_name}")

                except Exception as e:
                    conn.execute("ROLLBACK")
                    logger.error(
                        f"[MIGRATIONS] Failed to rollback {migration.full_name}: {e}"
                    )
                    raise

        finally:
            conn.close()

        return len(rolled_back), rolled_back


# Global runner instance
_runner: MigrationRunner | None = None


def get_migration_runner() -> MigrationRunner:
    """Get or create migration runner."""
    global _runner
    if _runner is None:
        # Get database path from settings or environment
        from app_settings import settings

        db_path = str(settings.resolved_data_dir / "app.db")
        _runner = MigrationRunner(db_path)
    return _runner


def run_migrations(target_version: str | None = None) -> tuple[int, list[str]]:
    """Run pending migrations (convenience function)."""
    runner = get_migration_runner()
    return runner.migrate(target_version)


def rollback_migration(steps: int = 1) -> tuple[int, list[str]]:
    """Rollback migrations (convenience function)."""
    runner = get_migration_runner()
    return runner.rollback(steps)


def get_migration_status() -> dict[str, Any]:
    """Get migration status (convenience function)."""
    runner = get_migration_runner()
    return runner.get_status()
