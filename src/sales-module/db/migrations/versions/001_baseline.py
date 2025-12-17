"""
Migration: baseline
Version: 001
Created: 2024-12-06

Description:
    Baseline migration - marks the starting point for new databases.
    For existing databases, this consolidates all previously applied
    ad-hoc migrations (workflow, cached_input_tokens, user_id columns).
"""

DESCRIPTION = "Baseline migration for existing schema"


def upgrade(conn):
    """
    Apply the migration.

    This is a baseline migration - it doesn't modify the schema,
    but marks the point from which new migrations are tracked.

    For existing databases with ad-hoc migrations already applied,
    this acts as a checkpoint.
    """
    cursor = conn.cursor()

    # Check if tables exist to determine if this is an existing database
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='ai_costs'"
    )
    if not cursor.fetchone():
        # New database - schema will be created by init_db
        return

    # Existing database - ensure all previously ad-hoc columns exist
    # This makes the migration idempotent

    # Check ai_costs columns
    cursor.execute("PRAGMA table_info(ai_costs)")
    columns = {row[1] for row in cursor.fetchall()}

    if "workflow" not in columns:
        cursor.execute("ALTER TABLE ai_costs ADD COLUMN workflow TEXT")

    if "cached_input_tokens" not in columns:
        cursor.execute(
            "ALTER TABLE ai_costs ADD COLUMN cached_input_tokens INTEGER DEFAULT 0"
        )

    if "user_id" not in columns:
        cursor.execute("ALTER TABLE ai_costs ADD COLUMN user_id TEXT")

    # Check proposals_log
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='proposals_log'"
    )
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(proposals_log)")
        columns = {row[1] for row in cursor.fetchall()}
        if "user_id" not in columns:
            cursor.execute("ALTER TABLE proposals_log ADD COLUMN user_id TEXT")

    # Check mockup_frames
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='mockup_frames'"
    )
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(mockup_frames)")
        columns = {row[1] for row in cursor.fetchall()}
        if "user_id" not in columns:
            cursor.execute("ALTER TABLE mockup_frames ADD COLUMN user_id TEXT")


def downgrade(conn):
    """
    Reverse the migration.

    Baseline migrations typically shouldn't be rolled back as they
    represent the starting point of the migration system.
    """
    # SQLite doesn't support DROP COLUMN easily
    # This would require recreating tables, which is destructive
    # For baseline, we leave it as a no-op
    pass
