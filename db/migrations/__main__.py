"""
Migration CLI.

Usage:
    python -m db.migrations migrate              # Run all pending migrations
    python -m db.migrations rollback             # Rollback last migration
    python -m db.migrations rollback --steps 3   # Rollback 3 migrations
    python -m db.migrations status               # Show migration status
    python -m db.migrations create "name"        # Create new migration file
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

# Ensure project root is in path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def cmd_migrate(args):
    """Run pending migrations."""
    from db.migrations import run_migrations

    target = args.target if hasattr(args, "target") else None
    count, versions = run_migrations(target)

    if count > 0:
        print(f"✓ Applied {count} migration(s): {', '.join(versions)}")
    else:
        print("✓ No pending migrations")


def cmd_rollback(args):
    """Rollback migrations."""
    from db.migrations import rollback_migration

    steps = args.steps if hasattr(args, "steps") else 1
    count, versions = rollback_migration(steps)

    if count > 0:
        print(f"✓ Rolled back {count} migration(s): {', '.join(versions)}")
    else:
        print("✓ No migrations to rollback")


def cmd_status(args):
    """Show migration status."""
    from db.migrations import get_migration_status

    status = get_migration_status()

    print("\n=== Migration Status ===\n")
    print(f"Total migrations:   {status['total_migrations']}")
    print(f"Applied:            {status['applied_count']}")
    print(f"Pending:            {status['pending_count']}")

    if status["last_applied"]:
        last = status["last_applied"]
        print(f"\nLast applied: {last['version']}_{last['name']} ({last['applied_at']})")

    if status["pending_migrations"]:
        print("\nPending migrations:")
        for m in status["pending_migrations"]:
            desc = f" - {m['description']}" if m["description"] else ""
            print(f"  • {m['version']}_{m['name']}{desc}")

    print()


def cmd_create(args):
    """Create a new migration file."""
    from db.migrations.runner import MIGRATIONS_DIR

    name = args.name.lower().replace(" ", "_").replace("-", "_")

    # Find next version number
    existing = sorted(MIGRATIONS_DIR.glob("*.py"))
    if existing:
        # Extract version from last file
        last_file = existing[-1].name
        last_version = int(last_file.split("_")[0])
        next_version = last_version + 1
    else:
        next_version = 1

    version = f"{next_version:03d}"
    filename = f"{version}_{name}.py"
    filepath = MIGRATIONS_DIR / filename

    # Create versions directory if needed
    MIGRATIONS_DIR.mkdir(parents=True, exist_ok=True)

    # Generate migration template
    template = f'''"""
Migration: {name}
Version: {version}
Created: {datetime.now().isoformat()}

Description:
    TODO: Describe what this migration does
"""

DESCRIPTION = "TODO: Brief description"


def upgrade(conn):
    """
    Apply the migration.

    Args:
        conn: SQLite connection (already in transaction)
    """
    cursor = conn.cursor()

    # TODO: Write your upgrade SQL here
    # Example:
    # cursor.execute("""
    #     ALTER TABLE users ADD COLUMN preferences TEXT
    # """)


def downgrade(conn):
    """
    Reverse the migration.

    Args:
        conn: SQLite connection (already in transaction)
    """
    cursor = conn.cursor()

    # TODO: Write your downgrade SQL here
    # Note: SQLite has limited ALTER TABLE support
    # For column removal, you may need to recreate the table
'''

    filepath.write_text(template)
    print(f"✓ Created migration: {filepath}")
    print(f"  Edit the file to add your migration logic")


def main():
    parser = argparse.ArgumentParser(
        description="Database migration management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m db.migrations migrate              Run all pending migrations
    python -m db.migrations migrate --target 003 Run migrations up to version 003
    python -m db.migrations rollback             Rollback last migration
    python -m db.migrations rollback --steps 3   Rollback last 3 migrations
    python -m db.migrations status               Show migration status
    python -m db.migrations create "add users"   Create new migration file
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # migrate command
    migrate_parser = subparsers.add_parser("migrate", help="Run pending migrations")
    migrate_parser.add_argument(
        "--target", "-t", help="Target version to migrate to"
    )
    migrate_parser.set_defaults(func=cmd_migrate)

    # rollback command
    rollback_parser = subparsers.add_parser("rollback", help="Rollback migrations")
    rollback_parser.add_argument(
        "--steps", "-s", type=int, default=1, help="Number of migrations to rollback"
    )
    rollback_parser.set_defaults(func=cmd_rollback)

    # status command
    status_parser = subparsers.add_parser("status", help="Show migration status")
    status_parser.set_defaults(func=cmd_status)

    # create command
    create_parser = subparsers.add_parser("create", help="Create new migration")
    create_parser.add_argument("name", help="Migration name (e.g., 'add_user_preferences')")
    create_parser.set_defaults(func=cmd_create)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
