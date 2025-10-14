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
    time_of_day TEXT NOT NULL DEFAULT 'day',
    finish TEXT NOT NULL DEFAULT 'gold',
    photo_filename TEXT NOT NULL,
    frames_data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT,
    config_json TEXT,
    UNIQUE(location_key, time_of_day, finish, photo_filename)
);

CREATE TABLE IF NOT EXISTS mockup_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    generated_at TEXT NOT NULL,
    location_key TEXT NOT NULL,
    time_of_day TEXT NOT NULL,
    finish TEXT NOT NULL,
    photo_used TEXT NOT NULL,
    creative_type TEXT NOT NULL,
    ai_prompt TEXT,
    template_selected INTEGER NOT NULL DEFAULT 0,
    success INTEGER NOT NULL DEFAULT 1,
    user_ip TEXT,
    CONSTRAINT creative_type_check CHECK (creative_type IN ('uploaded', 'ai_generated'))
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
    """Initialize database with current schema.

    Note: All legacy migrations have been removed since database was reset.
    The SCHEMA constant above contains the complete, current table definitions.
    New databases will be created with the correct schema from the start.
    """
    conn = _connect()
    try:
        # executescript allows multiple SQL statements
        conn.executescript(SCHEMA)
        logger.info("[DB] Database initialized with current schema")
    finally:
        conn.close()


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


def save_mockup_frame(location_key: str, photo_filename: str, frames_data: list, created_by: Optional[str] = None, time_of_day: str = "day", finish: str = "gold", config: Optional[dict] = None) -> str:
    """Save frame coordinates and config for a location photo with time_of_day and finish. Returns the final auto-numbered filename."""
    import json
    import os
    conn = _connect()
    try:
        conn.execute("BEGIN")
        config_json = json.dumps(config) if config else None

        logger.info(f"[DB] save_mockup_frame called: location_key={location_key}, photo_filename={photo_filename}, time_of_day={time_of_day}, finish={finish}, frame_count={len(frames_data)}")

        # Get file extension from original filename
        _, ext = os.path.splitext(photo_filename)
        logger.info(f"[DB] Original filename: {photo_filename}, extension: {ext}")

        # Format location name for filename (e.g., "oryx" -> "Oryx")
        location_display_name = location_key.replace('_', ' ').title().replace(' ', '')
        logger.info(f"[DB] Display name for filename: {location_display_name}")

        # Find all existing photos for this location (across ALL time_of_day/finish) to determine next number
        cursor = conn.cursor()
        cursor.execute(
            "SELECT photo_filename FROM mockup_frames WHERE location_key = ?",
            (location_key,)
        )
        existing_files = [row[0] for row in cursor.fetchall()]
        logger.info(f"[DB] Found {len(existing_files)} existing photos for location: {existing_files}")

        # Extract numbers from existing filenames (e.g., "Oryx_1.jpg" -> 1)
        existing_numbers = []
        for filename in existing_files:
            name_part = os.path.splitext(filename)[0]
            if name_part.startswith(f"{location_display_name}_"):
                try:
                    num = int(name_part.split('_')[-1])
                    existing_numbers.append(num)
                except ValueError:
                    pass
        logger.info(f"[DB] Extracted existing numbers: {existing_numbers}")

        # Find next available number (1-indexed)
        next_num = 1
        while next_num in existing_numbers:
            next_num += 1
        logger.info(f"[DB] Next available number: {next_num}")

        # Create standardized filename: LocationName_Number.ext
        final_filename = f"{location_display_name}_{next_num}{ext}"
        logger.info(f"[DB] Final filename: {final_filename}")

        # Insert new entry with auto-numbered filename
        logger.info(f"[DB] Inserting into database: {location_key}/{time_of_day}/{finish}/{final_filename}")
        conn.execute(
            """
            INSERT INTO mockup_frames (location_key, time_of_day, finish, photo_filename, frames_data, created_at, created_by, config_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (location_key, time_of_day, finish, final_filename, json.dumps(frames_data), datetime.now().isoformat(), created_by, config_json),
        )
        logger.info(f"[DB] ✓ Database insert successful")

        conn.execute("COMMIT")
        logger.info(f"[DB] ✓ Transaction committed, returning filename: {final_filename}")
        return final_filename
    finally:
        conn.close()


def get_mockup_frames(location_key: str, photo_filename: str, time_of_day: str = "day", finish: str = "gold") -> Optional[list]:
    """Get all frame coordinates for a specific location photo with time_of_day and finish. Returns list of frames."""
    import json
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT frames_data FROM mockup_frames WHERE location_key = ? AND time_of_day = ? AND finish = ? AND photo_filename = ?",
            (location_key, time_of_day, finish, photo_filename)
        )
        row = cursor.fetchone()
        return json.loads(row[0]) if row else None
    finally:
        conn.close()


def get_mockup_config(location_key: str, photo_filename: str, time_of_day: str = "day", finish: str = "gold") -> Optional[dict]:
    """Get config for a specific location photo with time_of_day and finish. Returns config dict or None."""
    import json
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT config_json FROM mockup_frames WHERE location_key = ? AND time_of_day = ? AND finish = ? AND photo_filename = ?",
            (location_key, time_of_day, finish, photo_filename)
        )
        row = cursor.fetchone()
        return json.loads(row[0]) if (row and row[0]) else None
    finally:
        conn.close()


def list_mockup_photos(location_key: str, time_of_day: str = "day", finish: str = "gold") -> list:
    """List all photos with frames for a location with time_of_day and finish."""
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT photo_filename FROM mockup_frames WHERE location_key = ? AND time_of_day = ? AND finish = ?",
            (location_key, time_of_day, finish)
        )
        return [row[0] for row in cursor.fetchall()]
    finally:
        conn.close()


def list_mockup_variations(location_key: str) -> dict:
    """List all time_of_day/finish combinations that exist for a location. Returns dict like {'day': ['gold', 'silver'], 'night': ['gold']}."""
    conn = _connect()
    try:
        cursor = conn.cursor()

        # First, get ALL records for this location to see what's in the database
        logger.info(f"[DB VARIATIONS] Querying ALL records for location: {location_key}")
        cursor.execute(
            "SELECT photo_filename, time_of_day, finish, created_at FROM mockup_frames WHERE location_key = ? ORDER BY created_at",
            (location_key,)
        )
        all_records = cursor.fetchall()
        logger.info(f"[DB VARIATIONS] Found {len(all_records)} total records:")
        for record in all_records:
            logger.info(f"[DB VARIATIONS]   - {record[0]} | time_of_day='{record[1]}' | finish='{record[2]}' | created={record[3]}")

        # Now get distinct variations
        cursor.execute(
            "SELECT DISTINCT time_of_day, finish FROM mockup_frames WHERE location_key = ? ORDER BY time_of_day, finish",
            (location_key,)
        )
        variations = {}
        for time_of_day, finish in cursor.fetchall():
            if time_of_day not in variations:
                variations[time_of_day] = []
            variations[time_of_day].append(finish)

        logger.info(f"[DB VARIATIONS] Distinct variations: {variations}")
        return variations
    finally:
        conn.close()


def delete_mockup_frame(location_key: str, photo_filename: str, time_of_day: str = "day", finish: str = "gold") -> None:
    """Delete a mockup frame."""
    conn = _connect()
    try:
        conn.execute("BEGIN")
        conn.execute(
            "DELETE FROM mockup_frames WHERE location_key = ? AND time_of_day = ? AND finish = ? AND photo_filename = ?",
            (location_key, time_of_day, finish, photo_filename)
        )
        conn.execute("COMMIT")
    finally:
        conn.close()


def log_mockup_usage(
    location_key: str,
    time_of_day: str,
    finish: str,
    photo_used: str,
    creative_type: str,
    ai_prompt: Optional[str] = None,
    template_selected: bool = False,
    success: bool = True,
    user_ip: Optional[str] = None
) -> None:
    """Log a mockup generation event for analytics."""
    conn = _connect()
    try:
        conn.execute("BEGIN")
        conn.execute(
            """
            INSERT INTO mockup_usage (generated_at, location_key, time_of_day, finish, photo_used, creative_type, ai_prompt, template_selected, success, user_ip)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (datetime.now().isoformat(), location_key, time_of_day, finish, photo_used, creative_type, ai_prompt, 1 if template_selected else 0, 1 if success else 0, user_ip),
        )
        conn.execute("COMMIT")
        logger.info(f"[DB] Logged mockup usage: {location_key}/{time_of_day}/{finish} - {creative_type} - Success: {success}")
    finally:
        conn.close()


def get_mockup_usage_stats() -> dict:
    """Get analytics and statistics on mockup generation usage."""
    conn = _connect()
    try:
        cursor = conn.cursor()

        # Total mockup generations
        cursor.execute("SELECT COUNT(*) FROM mockup_usage")
        total_count = cursor.fetchone()[0]

        # Successful vs failed
        cursor.execute("SELECT success, COUNT(*) FROM mockup_usage GROUP BY success")
        success_stats = dict(cursor.fetchall())

        # By location
        cursor.execute("""
            SELECT location_key, COUNT(*)
            FROM mockup_usage
            GROUP BY location_key
            ORDER BY COUNT(*) DESC
        """)
        by_location = dict(cursor.fetchall())

        # By creative type
        cursor.execute("""
            SELECT creative_type, COUNT(*)
            FROM mockup_usage
            GROUP BY creative_type
        """)
        by_creative_type = dict(cursor.fetchall())

        # Template usage
        cursor.execute("""
            SELECT template_selected, COUNT(*)
            FROM mockup_usage
            GROUP BY template_selected
        """)
        template_stats = dict(cursor.fetchall())

        # Recent generations
        cursor.execute("""
            SELECT location_key, creative_type, generated_at, success
            FROM mockup_usage
            ORDER BY generated_at DESC
            LIMIT 10
        """)
        recent = cursor.fetchall()

        return {
            "total_generations": total_count,
            "successful": success_stats.get(1, 0),
            "failed": success_stats.get(0, 0),
            "by_location": by_location,
            "by_creative_type": by_creative_type,
            "with_template": template_stats.get(1, 0),
            "without_template": template_stats.get(0, 0),
            "recent_generations": [
                {
                    "location": row[0],
                    "creative_type": row[1],
                    "generated_at": row[2],
                    "success": bool(row[3])
                }
                for row in recent
            ]
        }

    finally:
        conn.close()


def export_mockup_usage_to_excel() -> str:
    """Export mockup usage log to Excel file and return the file path."""
    import pandas as pd
    import tempfile
    from datetime import datetime

    conn = _connect()
    try:
        # Read all mockup usage into a DataFrame
        df = pd.read_sql_query(
            "SELECT * FROM mockup_usage ORDER BY generated_at DESC",
            conn
        )

        # Convert generated_at to datetime for better Excel formatting
        df['generated_at'] = pd.to_datetime(df['generated_at'])

        # Convert boolean columns
        df['template_selected'] = df['template_selected'].map({1: 'Yes', 0: 'No'})
        df['success'] = df['success'].map({1: 'Success', 0: 'Failed'})

        # Create a temporary Excel file
        temp_file = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=f'_mockup_usage_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        )
        temp_file.close()

        # Write to Excel with formatting
        with pd.ExcelWriter(temp_file.name, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Mockup Usage', index=False)

            # Get the workbook and worksheet
            workbook = writer.book
            worksheet = writer.sheets['Mockup Usage']

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


# Initialize DB on import
init_db() 