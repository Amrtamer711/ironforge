"""
Database Migrations System.

Provides versioned, trackable database migrations with:
- Forward migrations (upgrade)
- Backward migrations (rollback)
- Migration history tracking
- CLI for running migrations

Usage:
    # Run all pending migrations
    python -m db.migrations migrate

    # Rollback last migration
    python -m db.migrations rollback

    # Show migration status
    python -m db.migrations status

    # Create new migration
    python -m db.migrations create "add_user_preferences"
"""

from db.migrations.runner import (
    Migration,
    MigrationRunner,
    get_migration_runner,
    get_migration_status,
    rollback_migration,
    run_migrations,
)

__all__ = [
    "MigrationRunner",
    "Migration",
    "get_migration_runner",
    "run_migrations",
    "rollback_migration",
    "get_migration_status",
]
