import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional
import os
import logging

logger = logging.getLogger("proposal-bot")

# Use environment-specific database paths
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

if os.path.exists("/data/"):
    # Production or test on Render
    if ENVIRONMENT == "test":
        DB_PATH = Path("/data/proposals_test.db")
        logger.info("[DB] Using TEST database at /data/proposals_test.db")
    else:
        DB_PATH = Path("/data/proposals.db")
        logger.info("[DB] Using production database at /data/proposals.db")
else:
    # Local development
    if ENVIRONMENT == "test":
        DB_PATH = Path(__file__).parent / "proposals_test.db"
        logger.info(f"[DB] Using local TEST database at {DB_PATH}")
    else:
        DB_PATH = Path(__file__).parent / "proposals.db"
        logger.info(f"[DB] Using local development database at {DB_PATH}")

SCHEMA = """
CREATE TABLE IF NOT EXISTS proposals_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    submitted_by TEXT NOT NULL,
    client_name TEXT NOT NULL,
    date_generated TEXT NOT NULL,
    package_type TEXT NOT NULL,
    locations TEXT NOT NULL,
    total_amount TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mockup_frames (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_key TEXT NOT NULL,
    subfolder TEXT NOT NULL DEFAULT 'all',
    photo_filename TEXT NOT NULL,
    frames_data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT,
    UNIQUE(location_key, subfolder, photo_filename)
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=5.0, isolation_level=None)
    # Enable WAL and set busy timeout
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    # Limit connection cache size to prevent memory growth
    conn.execute("PRAGMA cache_size=-2000;")  # 2MB cache
    return conn


def init_db() -> None:
    conn = _connect()
    try:
        # executescript allows multiple SQL statements
        conn.executescript(SCHEMA)

        # Run migrations
        _migrate_add_subfolder_column(conn)
    finally:
        conn.close()


def _migrate_add_subfolder_column(conn: sqlite3.Connection) -> None:
    """Migration: Add subfolder column to mockup_frames if it doesn't exist"""
    try:
        # Check if subfolder column exists
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(mockup_frames)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'subfolder' not in columns:
            logger.info("[DB MIGRATION] Adding 'subfolder' column to mockup_frames table")

            # Add subfolder column with default 'all'
            conn.execute("ALTER TABLE mockup_frames ADD COLUMN subfolder TEXT NOT NULL DEFAULT 'all'")

            # Drop the old unique constraint and create new one with subfolder
            # SQLite doesn't support DROP CONSTRAINT, so we need to recreate the table
            conn.execute("BEGIN")

            # Create temporary table with new schema
            conn.execute("""
                CREATE TABLE mockup_frames_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    location_key TEXT NOT NULL,
                    subfolder TEXT NOT NULL DEFAULT 'all',
                    photo_filename TEXT NOT NULL,
                    frames_data TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    created_by TEXT,
                    UNIQUE(location_key, subfolder, photo_filename)
                )
            """)

            # Copy data from old table
            conn.execute("""
                INSERT INTO mockup_frames_new
                SELECT id, location_key, subfolder, photo_filename, frames_data, created_at, created_by
                FROM mockup_frames
            """)

            # Drop old table and rename new one
            conn.execute("DROP TABLE mockup_frames")
            conn.execute("ALTER TABLE mockup_frames_new RENAME TO mockup_frames")

            conn.execute("COMMIT")

            logger.info("[DB MIGRATION] Successfully added 'subfolder' column and updated unique constraint")
        else:
            logger.debug("[DB MIGRATION] 'subfolder' column already exists, skipping migration")

    except Exception as e:
        logger.error(f"[DB MIGRATION] Error adding subfolder column: {e}", exc_info=True)
        try:
            conn.execute("ROLLBACK")
        except:
            pass


def log_proposal(
    submitted_by: str,
    client_name: str,
    package_type: str,
    locations: str,
    total_amount: str,
    date_generated: Optional[str] = None,
) -> None:
    if not date_generated:
        date_generated = datetime.now().isoformat()

    conn = _connect()
    try:
        conn.execute("BEGIN")
        conn.execute(
            """
            INSERT INTO proposals_log (submitted_by, client_name, date_generated, package_type, locations, total_amount)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (submitted_by, client_name, date_generated, package_type, locations, total_amount),
        )
        conn.execute("COMMIT")
    finally:
        conn.close()


def export_to_excel() -> str:
    """Export proposals log to Excel file and return the file path."""
    import pandas as pd
    import tempfile
    from datetime import datetime
    
    conn = _connect()
    try:
        # Read all proposals into a DataFrame
        df = pd.read_sql_query(
            "SELECT * FROM proposals_log ORDER BY date_generated DESC",
            conn
        )
        
        # Convert date_generated to datetime for better Excel formatting
        df['date_generated'] = pd.to_datetime(df['date_generated'])
        
        # Create a temporary Excel file
        temp_file = tempfile.NamedTemporaryFile(
            delete=False, 
            suffix=f'_proposals_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        )
        temp_file.close()
        
        # Write to Excel with formatting
        with pd.ExcelWriter(temp_file.name, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Proposals', index=False)
            
            # Get the workbook and worksheet
            workbook = writer.book
            worksheet = writer.sheets['Proposals']
            
            # Auto-adjust column widths
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column_letter].width = adjusted_width
            
            # Add filters
            worksheet.auto_filter.ref = worksheet.dimensions
        
        return temp_file.name
        
    finally:
        conn.close()


def get_proposals_summary() -> dict:
    """Get a summary of proposals for display."""
    conn = _connect()
    try:
        cursor = conn.cursor()
        
        # Total count
        cursor.execute("SELECT COUNT(*) FROM proposals_log")
        total_count = cursor.fetchone()[0]
        
        # Count by package type
        cursor.execute("""
            SELECT package_type, COUNT(*) 
            FROM proposals_log 
            GROUP BY package_type
        """)
        by_type = dict(cursor.fetchall())
        
        # Recent proposals
        cursor.execute("""
            SELECT client_name, locations, date_generated 
            FROM proposals_log 
            ORDER BY date_generated DESC 
            LIMIT 5
        """)
        recent = cursor.fetchall()
        
        return {
            "total_proposals": total_count,
            "by_package_type": by_type,
            "recent_proposals": [
                {
                    "client": row[0],
                    "locations": row[1],
                    "date": row[2]
                }
                for row in recent
            ]
        }
        
    finally:
        conn.close()


def save_mockup_frame(location_key: str, photo_filename: str, frames_data: list, created_by: Optional[str] = None, subfolder: str = "all") -> None:
    """Save frame coordinates for a location photo in a subfolder. frames_data is a list of frame point arrays."""
    import json
    conn = _connect()
    try:
        conn.execute("BEGIN")
        conn.execute(
            """
            INSERT OR REPLACE INTO mockup_frames (location_key, subfolder, photo_filename, frames_data, created_at, created_by)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (location_key, subfolder, photo_filename, json.dumps(frames_data), datetime.now().isoformat(), created_by),
        )
        conn.execute("COMMIT")
    finally:
        conn.close()


def get_mockup_frames(location_key: str, photo_filename: str, subfolder: str = "all") -> Optional[list]:
    """Get all frame coordinates for a specific location photo in a subfolder. Returns list of frames."""
    import json
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT frames_data FROM mockup_frames WHERE location_key = ? AND subfolder = ? AND photo_filename = ?",
            (location_key, subfolder, photo_filename)
        )
        row = cursor.fetchone()
        return json.loads(row[0]) if row else None
    finally:
        conn.close()


def list_mockup_photos(location_key: str, subfolder: str = "all") -> list:
    """List all photos with frames for a location in a specific subfolder."""
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT photo_filename FROM mockup_frames WHERE location_key = ? AND subfolder = ?",
            (location_key, subfolder)
        )
        return [row[0] for row in cursor.fetchall()]
    finally:
        conn.close()


def list_mockup_subfolders(location_key: str) -> list:
    """List all subfolders for a location."""
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT DISTINCT subfolder FROM mockup_frames WHERE location_key = ? ORDER BY subfolder",
            (location_key,)
        )
        return [row[0] for row in cursor.fetchall()]
    finally:
        conn.close()


def delete_mockup_frame(location_key: str, photo_filename: str, subfolder: str = "all") -> None:
    """Delete a mockup frame."""
    conn = _connect()
    try:
        conn.execute("BEGIN")
        conn.execute(
            "DELETE FROM mockup_frames WHERE location_key = ? AND subfolder = ? AND photo_filename = ?",
            (location_key, subfolder, photo_filename)
        )
        conn.execute("COMMIT")
    finally:
        conn.close()


# Initialize DB on import
init_db() 