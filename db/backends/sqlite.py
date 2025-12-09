"""
SQLite database backend implementation.
"""

import sqlite3
import json
import os
import logging
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional

from db.base import DatabaseBackend
from db.schema import get_sqlite_schema
from utils.time import UAE_TZ, get_uae_time

logger = logging.getLogger("proposal-bot")


# Schema is now generated from the unified schema definition in db/schema.py
# To modify the schema, edit db/schema.py and run: python -m db.schema --generate sqlite
SCHEMA = get_sqlite_schema()


class SQLiteBackend(DatabaseBackend):
    """SQLite database backend implementation."""

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize SQLite backend.

        Args:
            db_path: Optional path to database file. If not provided,
                     uses environment-based defaults.
        """
        if db_path:
            self._db_path = db_path
        else:
            # Use environment-specific database paths
            environment = os.getenv("ENVIRONMENT", "development")

            if os.path.exists("/data/"):
                # Production or test on Render
                if environment == "test":
                    self._db_path = Path("/data/proposals_test.db")
                    logger.info("[DB] Using TEST database at /data/proposals_test.db")
                else:
                    self._db_path = Path("/data/proposals.db")
                    logger.info("[DB] Using production database at /data/proposals.db")
            else:
                # Local development
                if environment == "test":
                    self._db_path = Path(__file__).parent.parent / "proposals_test.db"
                    logger.info(f"[DB] Using local TEST database at {self._db_path}")
                else:
                    self._db_path = Path(__file__).parent.parent / "proposals.db"
                    logger.info(f"[DB] Using local development database at {self._db_path}")

    @property
    def name(self) -> str:
        return "sqlite"

    def _connect(self) -> sqlite3.Connection:
        """Create a database connection."""
        conn = sqlite3.connect(self._db_path, timeout=5.0, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA cache_size=-2000;")
        return conn

    def init_db(self) -> None:
        """Initialize database with schema."""
        conn = self._connect()
        try:
            self._run_migrations(conn)
            conn.executescript(SCHEMA)
            logger.info("[DB] Database initialized with current schema")
        finally:
            conn.close()

    def _run_migrations(self, conn: sqlite3.Connection) -> None:
        """Run database migrations for existing tables."""
        cursor = conn.cursor()

        # Check if ai_costs table exists first
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ai_costs'")
        if not cursor.fetchone():
            logger.debug("[DB MIGRATION] ai_costs table doesn't exist yet, skipping migrations")
            return

        # Get existing columns
        cursor.execute("PRAGMA table_info(ai_costs)")
        columns = [row[1] for row in cursor.fetchall()]

        # Migration 1: Add workflow column
        try:
            if 'workflow' not in columns:
                logger.info("[DB MIGRATION] Adding workflow column to ai_costs table")
                cursor.execute("ALTER TABLE ai_costs ADD COLUMN workflow TEXT")
                conn.commit()
        except Exception as e:
            logger.error(f"[DB MIGRATION] Failed to add workflow column: {e}")

        # Migration 2: Add cached_input_tokens column
        try:
            cursor.execute("PRAGMA table_info(ai_costs)")
            columns = [row[1] for row in cursor.fetchall()]

            if 'cached_input_tokens' not in columns:
                logger.info("[DB MIGRATION] Adding cached_input_tokens column")
                cursor.execute("ALTER TABLE ai_costs ADD COLUMN cached_input_tokens INTEGER DEFAULT 0")
                conn.commit()
        except Exception as e:
            logger.error(f"[DB MIGRATION] Failed to add cached_input_tokens column: {e}")

        # Migration 3: Add user_id column to ai_costs
        try:
            cursor.execute("PRAGMA table_info(ai_costs)")
            columns = [row[1] for row in cursor.fetchall()]

            if 'user_id' not in columns:
                logger.info("[DB MIGRATION] Adding user_id column to ai_costs")
                cursor.execute("ALTER TABLE ai_costs ADD COLUMN user_id TEXT")
                conn.commit()
        except Exception as e:
            logger.error(f"[DB MIGRATION] Failed to add user_id column: {e}")

        # Migration 4: Add user_id column to proposals_log
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='proposals_log'")
            if cursor.fetchone():
                cursor.execute("PRAGMA table_info(proposals_log)")
                columns = [row[1] for row in cursor.fetchall()]
                if 'user_id' not in columns:
                    logger.info("[DB MIGRATION] Adding user_id column to proposals_log")
                    cursor.execute("ALTER TABLE proposals_log ADD COLUMN user_id TEXT")
                    conn.commit()
        except Exception as e:
            logger.error(f"[DB MIGRATION] Failed to add user_id to proposals_log: {e}")

        # Migration 5: Add user_id column to mockup_frames
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mockup_frames'")
            if cursor.fetchone():
                cursor.execute("PRAGMA table_info(mockup_frames)")
                columns = [row[1] for row in cursor.fetchall()]
                if 'user_id' not in columns:
                    logger.info("[DB MIGRATION] Adding user_id column to mockup_frames")
                    cursor.execute("ALTER TABLE mockup_frames ADD COLUMN user_id TEXT")
                    conn.commit()
        except Exception as e:
            logger.error(f"[DB MIGRATION] Failed to add user_id to mockup_frames: {e}")

        # Migration 6: Add user_id column to mockup_usage
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mockup_usage'")
            if cursor.fetchone():
                cursor.execute("PRAGMA table_info(mockup_usage)")
                columns = [row[1] for row in cursor.fetchall()]
                if 'user_id' not in columns:
                    logger.info("[DB MIGRATION] Adding user_id column to mockup_usage")
                    cursor.execute("ALTER TABLE mockup_usage ADD COLUMN user_id TEXT")
                    conn.commit()
        except Exception as e:
            logger.error(f"[DB MIGRATION] Failed to add user_id to mockup_usage: {e}")

        # Migration 7: Add user_id column to booking_orders
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='booking_orders'")
            if cursor.fetchone():
                cursor.execute("PRAGMA table_info(booking_orders)")
                columns = [row[1] for row in cursor.fetchall()]
                if 'user_id' not in columns:
                    logger.info("[DB MIGRATION] Adding user_id column to booking_orders")
                    cursor.execute("ALTER TABLE booking_orders ADD COLUMN user_id TEXT")
                    conn.commit()
        except Exception as e:
            logger.error(f"[DB MIGRATION] Failed to add user_id to booking_orders: {e}")

        # Migration 8: Migrate invite_tokens from profile_id to profile_name
        # (Part of RBAC v2 migration - roles -> profiles)
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='invite_tokens'")
            if cursor.fetchone():
                cursor.execute("PRAGMA table_info(invite_tokens)")
                columns = [row[1] for row in cursor.fetchall()]

                # Check if we still have profile_id (old schema)
                if 'profile_id' in columns and 'profile_name' not in columns:
                    logger.info("[DB MIGRATION] Migrating invite_tokens: profile_id -> profile_name")
                    # SQLite doesn't support DROP COLUMN, so we need to recreate the table
                    # First backup existing data
                    cursor.execute("ALTER TABLE invite_tokens RENAME TO invite_tokens_backup")
                    conn.commit()

                    # Create new table with profile_name (will be created by schema)
                    # The executescript below will create the new table
                    logger.info("[DB MIGRATION] invite_tokens table renamed to backup, new table will be created by schema")
                elif 'profile_id' in columns and 'profile_name' in columns:
                    # Transitional state - remove old column by recreating table
                    logger.info("[DB MIGRATION] Cleaning up invite_tokens: removing legacy profile_id column")
                    cursor.execute("ALTER TABLE invite_tokens RENAME TO invite_tokens_old")
                    conn.commit()
        except Exception as e:
            logger.error(f"[DB MIGRATION] Failed to migrate invite_tokens: {e}")

        # Migration 9: Drop legacy RBAC tables (roles, user_roles, role_permissions)
        try:
            for table in ['role_permissions', 'user_roles', 'roles']:
                cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
                if cursor.fetchone():
                    logger.info(f"[DB MIGRATION] Dropping legacy table: {table}")
                    cursor.execute(f"DROP TABLE IF EXISTS {table}")
                    conn.commit()
        except Exception as e:
            logger.error(f"[DB MIGRATION] Failed to drop legacy RBAC tables: {e}")

    # =========================================================================
    # PROPOSALS
    # =========================================================================

    def log_proposal(
        self,
        submitted_by: str,
        client_name: str,
        package_type: str,
        locations: str,
        total_amount: str,
        date_generated: Optional[str] = None,
    ) -> None:
        if not date_generated:
            date_generated = datetime.now().isoformat()

        conn = self._connect()
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
            logger.info(f"[SQLITE] Logged proposal for client: {client_name}")
        except Exception as e:
            conn.execute("ROLLBACK")
            logger.error(f"[SQLITE] Failed to log proposal for {client_name}: {e}", exc_info=True)
            raise
        finally:
            conn.close()

    def get_proposals_summary(self) -> Dict[str, Any]:
        conn = self._connect()
        try:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM proposals_log")
            total_count = cursor.fetchone()[0]

            cursor.execute("""
                SELECT package_type, COUNT(*)
                FROM proposals_log
                GROUP BY package_type
            """)
            by_type = dict(cursor.fetchall())

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
                    {"client": row[0], "locations": row[1], "date": row[2]}
                    for row in recent
                ]
            }
        finally:
            conn.close()

    def export_to_excel(self) -> str:
        import pandas as pd
        import tempfile

        conn = self._connect()
        try:
            df = pd.read_sql_query(
                "SELECT * FROM proposals_log ORDER BY date_generated DESC",
                conn
            )
            df['date_generated'] = pd.to_datetime(df['date_generated'])

            temp_file = tempfile.NamedTemporaryFile(
                delete=False,
                suffix=f'_proposals_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
            )
            temp_file.close()

            with pd.ExcelWriter(temp_file.name, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Proposals', index=False)
                worksheet = writer.sheets['Proposals']
                for column in worksheet.columns:
                    max_length = max(len(str(cell.value or "")) for cell in column)
                    worksheet.column_dimensions[column[0].column_letter].width = min(max_length + 2, 50)
                worksheet.auto_filter.ref = worksheet.dimensions

            return temp_file.name
        finally:
            conn.close()

    # =========================================================================
    # BOOKING ORDERS
    # =========================================================================

    def generate_next_bo_ref(self) -> str:
        current_year = datetime.now().year
        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT bo_ref FROM booking_orders WHERE bo_ref LIKE ? ORDER BY bo_ref DESC LIMIT 1",
                (f"BO-{current_year}-%",)
            )
            row = cursor.fetchone()
            if row:
                last_num = int(row[0].split("-")[-1])
                next_num = last_num + 1
            else:
                next_num = 1
            return f"BO-{current_year}-{next_num:04d}"
        finally:
            conn.close()

    def save_booking_order(self, data: Dict[str, Any]) -> str:
        conn = self._connect()
        try:
            conn.execute("BEGIN")

            search_text = " ".join([
                str(data.get("bo_ref", "")),
                str(data.get("client", "")),
                str(data.get("brand_campaign", "")),
                str(data.get("bo_number", "")),
            ]).lower()

            locations_json = json.dumps(data.get("locations", []))
            warnings_json = json.dumps(data.get("warnings", []))
            missing_json = json.dumps(data.get("missing_required", []))

            asset = data.get("asset")
            if isinstance(asset, list):
                asset = json.dumps(asset)

            conn.execute(
                """
                INSERT OR REPLACE INTO booking_orders (
                    bo_ref, company, original_file_path, original_file_type, original_file_size, original_filename,
                    parsed_excel_path, bo_number, bo_date, client, agency, brand_campaign, category, asset,
                    net_pre_vat, vat_value, gross_amount, sla_pct, payment_terms, sales_person, commission_pct,
                    notes, locations_json, extraction_method, extraction_confidence, warnings_json, missing_fields_json,
                    vat_calc, gross_calc, sla_deduction, net_excl_sla_calc, parsed_at, parsed_by,
                    source_classification, classification_confidence, needs_review, search_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["bo_ref"], data["company"], data["original_file_path"],
                    data["original_file_type"], data.get("original_file_size"),
                    data.get("original_filename"), data["parsed_excel_path"],
                    data.get("bo_number"), data.get("bo_date"), data.get("client"),
                    data.get("agency"), data.get("brand_campaign"), data.get("category"),
                    asset, data.get("net_pre_vat"), data.get("vat_value"),
                    data.get("gross_amount"), data.get("sla_pct"), data.get("payment_terms"),
                    data.get("sales_person"), data.get("commission_pct"), data.get("notes"),
                    locations_json, data.get("extraction_method", "llm"),
                    data.get("extraction_confidence", "medium"), warnings_json, missing_json,
                    data.get("vat_calc"), data.get("gross_calc"), data.get("sla_deduction"),
                    data.get("net_excl_sla_calc"), data.get("parsed_at", datetime.now().isoformat()),
                    data.get("parsed_by"), data.get("source_classification"),
                    data.get("classification_confidence"), int(data.get("needs_review", False)),
                    search_text,
                ),
            )
            conn.execute("COMMIT")
            logger.info(f"[DB] Saved booking order: {data['bo_ref']}")
            return data["bo_ref"]
        except Exception as e:
            conn.execute("ROLLBACK")
            logger.error(f"[DB] Error saving booking order: {e}", exc_info=True)
            raise
        finally:
            conn.close()

    def get_booking_order(self, bo_ref: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM booking_orders WHERE bo_ref = ?", (bo_ref,))
            row = cursor.fetchone()
            if not row:
                return None

            columns = [desc[0] for desc in cursor.description]
            record = dict(zip(columns, row))

            if record.get("locations_json"):
                record["locations"] = json.loads(record["locations_json"])
            if record.get("warnings_json"):
                record["warnings"] = json.loads(record["warnings_json"])
            if record.get("missing_fields_json"):
                record["missing_required"] = json.loads(record["missing_fields_json"])

            return record
        finally:
            conn.close()

    def get_booking_order_by_number(self, bo_number: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM booking_orders WHERE TRIM(bo_number) = TRIM(?) COLLATE NOCASE",
                (bo_number,)
            )
            row = cursor.fetchone()
            if not row:
                return None

            columns = [desc[0] for desc in cursor.description]
            record = dict(zip(columns, row))

            if record.get("locations_json"):
                record["locations"] = json.loads(record["locations_json"])
            if record.get("warnings_json"):
                record["warnings"] = json.loads(record["warnings_json"])
            if record.get("missing_fields_json"):
                record["missing_required"] = json.loads(record["missing_fields_json"])

            return record
        finally:
            conn.close()

    def export_booking_orders_to_excel(self) -> str:
        import pandas as pd
        import tempfile

        conn = self._connect()
        try:
            df = pd.read_sql_query(
                "SELECT bo_ref, bo_number, company, client, brand_campaign, category, gross_amount, "
                "net_pre_vat, vat_value, sales_person, parsed_at, notes "
                "FROM booking_orders ORDER BY parsed_at DESC",
                conn
            )
            df['parsed_at'] = pd.to_datetime(df['parsed_at'])
            df.columns = ['BO Reference', 'BO Number', 'Company', 'Client', 'Campaign', 'Category',
                          'Gross Total (AED)', 'Net (AED)', 'VAT (AED)', 'Sales Person',
                          'Created Date', 'Notes']

            temp_file = tempfile.NamedTemporaryFile(
                delete=False,
                suffix=f'_booking_orders_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
            )
            temp_file.close()

            with pd.ExcelWriter(temp_file.name, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Booking Orders', index=False)
                worksheet = writer.sheets['Booking Orders']
                for column in worksheet.columns:
                    max_length = max(len(str(cell.value or "")) for cell in column)
                    worksheet.column_dimensions[column[0].column_letter].width = min(max_length + 2, 50)
                worksheet.auto_filter.ref = worksheet.dimensions

            return temp_file.name
        finally:
            conn.close()

    # =========================================================================
    # MOCKUP FRAMES
    # =========================================================================

    def save_mockup_frame(
        self,
        location_key: str,
        photo_filename: str,
        frames_data: List[Dict],
        created_by: Optional[str] = None,
        time_of_day: str = "day",
        finish: str = "gold",
        config: Optional[Dict] = None,
    ) -> str:
        conn = self._connect()
        try:
            conn.execute("BEGIN")
            config_json = json.dumps(config) if config else None

            _, ext = os.path.splitext(photo_filename)
            location_display_name = location_key.replace('_', ' ').title().replace(' ', '')

            cursor = conn.cursor()
            cursor.execute(
                "SELECT photo_filename FROM mockup_frames WHERE location_key = ?",
                (location_key,)
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
                INSERT INTO mockup_frames (location_key, time_of_day, finish, photo_filename, frames_data, created_at, created_by, config_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (location_key, time_of_day, finish, final_filename, json.dumps(frames_data), datetime.now().isoformat(), created_by, config_json),
            )

            conn.execute("COMMIT")
            logger.info(f"[SQLITE] Saved mockup frame: {location_key}/{final_filename}")
            return final_filename
        except Exception as e:
            conn.execute("ROLLBACK")
            logger.error(f"[SQLITE] Failed to save mockup frame for {location_key}: {e}", exc_info=True)
            raise
        finally:
            conn.close()

    def get_mockup_frames(
        self,
        location_key: str,
        photo_filename: str,
        time_of_day: str = "day",
        finish: str = "gold",
    ) -> Optional[List[Dict]]:
        conn = self._connect()
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

    def get_mockup_config(
        self,
        location_key: str,
        photo_filename: str,
        time_of_day: str = "day",
        finish: str = "gold",
    ) -> Optional[Dict]:
        conn = self._connect()
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

    def list_mockup_photos(
        self,
        location_key: str,
        time_of_day: str = "day",
        finish: str = "gold",
    ) -> List[str]:
        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT photo_filename FROM mockup_frames WHERE location_key = ? AND time_of_day = ? AND finish = ?",
                (location_key, time_of_day, finish)
            )
            return [row[0] for row in cursor.fetchall()]
        finally:
            conn.close()

    def list_mockup_variations(self, location_key: str) -> Dict[str, List[str]]:
        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT DISTINCT time_of_day, finish FROM mockup_frames WHERE location_key = ? ORDER BY time_of_day, finish",
                (location_key,)
            )
            variations = {}
            for time_of_day, finish in cursor.fetchall():
                if time_of_day not in variations:
                    variations[time_of_day] = []
                variations[time_of_day].append(finish)
            return variations
        finally:
            conn.close()

    def delete_mockup_frame(
        self,
        location_key: str,
        photo_filename: str,
        time_of_day: str = "day",
        finish: str = "gold",
    ) -> None:
        conn = self._connect()
        try:
            conn.execute("BEGIN")
            conn.execute(
                "DELETE FROM mockup_frames WHERE location_key = ? AND time_of_day = ? AND finish = ? AND photo_filename = ?",
                (location_key, time_of_day, finish, photo_filename)
            )
            conn.execute("COMMIT")
            logger.info(f"[SQLITE] Deleted mockup frame: {location_key}/{photo_filename}")
        except Exception as e:
            conn.execute("ROLLBACK")
            logger.error(f"[SQLITE] Failed to delete mockup frame {location_key}/{photo_filename}: {e}", exc_info=True)
            raise
        finally:
            conn.close()

    # =========================================================================
    # MOCKUP USAGE
    # =========================================================================

    def log_mockup_usage(
        self,
        location_key: str,
        time_of_day: str,
        finish: str,
        photo_used: str,
        creative_type: str,
        ai_prompt: Optional[str] = None,
        template_selected: bool = False,
        success: bool = True,
        user_ip: Optional[str] = None,
    ) -> None:
        conn = self._connect()
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
            logger.debug(f"[SQLITE] Logged mockup usage: {location_key}/{photo_used}")
        except Exception as e:
            conn.execute("ROLLBACK")
            logger.error(f"[SQLITE] Failed to log mockup usage for {location_key}: {e}", exc_info=True)
            # Don't raise - usage logging is non-critical
        finally:
            conn.close()

    def get_mockup_usage_stats(self) -> Dict[str, Any]:
        conn = self._connect()
        try:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM mockup_usage")
            total_count = cursor.fetchone()[0]

            cursor.execute("SELECT success, COUNT(*) FROM mockup_usage GROUP BY success")
            success_stats = dict(cursor.fetchall())

            cursor.execute("""
                SELECT location_key, COUNT(*)
                FROM mockup_usage
                GROUP BY location_key
                ORDER BY COUNT(*) DESC
            """)
            by_location = dict(cursor.fetchall())

            cursor.execute("""
                SELECT creative_type, COUNT(*)
                FROM mockup_usage
                GROUP BY creative_type
            """)
            by_creative_type = dict(cursor.fetchall())

            cursor.execute("""
                SELECT template_selected, COUNT(*)
                FROM mockup_usage
                GROUP BY template_selected
            """)
            template_stats = dict(cursor.fetchall())

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

    def export_mockup_usage_to_excel(self) -> str:
        import pandas as pd
        import tempfile

        conn = self._connect()
        try:
            df = pd.read_sql_query(
                "SELECT * FROM mockup_usage ORDER BY generated_at DESC",
                conn
            )
            df['generated_at'] = pd.to_datetime(df['generated_at'])
            df['template_selected'] = df['template_selected'].map({1: 'Yes', 0: 'No'})
            df['success'] = df['success'].map({1: 'Success', 0: 'Failed'})

            temp_file = tempfile.NamedTemporaryFile(
                delete=False,
                suffix=f'_mockup_usage_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
            )
            temp_file.close()

            with pd.ExcelWriter(temp_file.name, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Mockup Usage', index=False)
                worksheet = writer.sheets['Mockup Usage']
                for column in worksheet.columns:
                    max_length = max(len(str(cell.value or "")) for cell in column)
                    worksheet.column_dimensions[column[0].column_letter].width = min(max_length + 2, 50)
                worksheet.auto_filter.ref = worksheet.dimensions

            return temp_file.name
        finally:
            conn.close()

    # =========================================================================
    # BO WORKFLOWS
    # =========================================================================

    def save_bo_workflow(
        self,
        workflow_id: str,
        workflow_data: str,
        updated_at: str,
    ) -> None:
        conn = self._connect()
        try:
            conn.execute("BEGIN")
            # Check if workflow exists to determine created_at
            cursor = conn.cursor()
            cursor.execute("SELECT created_at FROM bo_approval_workflows WHERE workflow_id = ?", (workflow_id,))
            existing = cursor.fetchone()
            created_at = existing[0] if existing else updated_at

            conn.execute(
                """
                INSERT OR REPLACE INTO bo_approval_workflows
                (workflow_id, workflow_data, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (workflow_id, workflow_data, created_at, updated_at),
            )
            conn.execute("COMMIT")
        except Exception as e:
            conn.execute("ROLLBACK")
            logger.error(f"[DB] Error saving BO workflow: {e}", exc_info=True)
            raise
        finally:
            conn.close()

    def get_bo_workflow(self, workflow_id: str) -> Optional[str]:
        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT workflow_data FROM bo_approval_workflows WHERE workflow_id = ?",
                (workflow_id,)
            )
            row = cursor.fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    def get_all_active_bo_workflows(self) -> List[tuple]:
        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT workflow_id, workflow_data FROM bo_approval_workflows ORDER BY updated_at DESC"
            )
            return cursor.fetchall()
        finally:
            conn.close()

    def delete_bo_workflow(self, workflow_id: str) -> None:
        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM bo_approval_workflows WHERE workflow_id = ?", (workflow_id,))
            conn.commit()
        finally:
            conn.close()

    # =========================================================================
    # AI COSTS
    # =========================================================================

    def log_ai_cost(
        self,
        call_type: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        reasoning_tokens: int,
        input_cost: float,
        output_cost: float,
        reasoning_cost: float,
        total_cost: float,
        user_id: Optional[str] = None,
        workflow: Optional[str] = None,
        cached_input_tokens: int = 0,
        context: Optional[str] = None,
        metadata_json: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> None:
        if not timestamp:
            timestamp = get_uae_time().isoformat()

        total_tokens = input_tokens + output_tokens + reasoning_tokens

        conn = self._connect()
        try:
            conn.execute("BEGIN")
            conn.execute(
                """
                INSERT INTO ai_costs (
                    timestamp, call_type, workflow, model, user_id, context,
                    input_tokens, cached_input_tokens, output_tokens, reasoning_tokens, total_tokens,
                    input_cost, output_cost, reasoning_cost, total_cost,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp, call_type, workflow, model, user_id, context,
                    input_tokens, cached_input_tokens, output_tokens, reasoning_tokens, total_tokens,
                    input_cost, output_cost, reasoning_cost, total_cost,
                    metadata_json
                )
            )
            conn.execute("COMMIT")
            row_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            logger.info(f"[COSTS] Logged {call_type} call (row_id={row_id}): ${total_cost:.4f}")
        except Exception as e:
            conn.execute("ROLLBACK")
            logger.error(f"[COSTS] Failed to log AI cost: {e}", exc_info=True)
            raise
        finally:
            conn.close()

    def get_ai_costs_summary(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        call_type: Optional[str] = None,
        workflow: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        conn = self._connect()
        try:
            where_parts = []
            params = []

            if start_date:
                where_parts.append("timestamp >= ?")
                params.append(start_date)
            if end_date:
                end_date_full = f"{end_date}T23:59:59" if 'T' not in end_date else end_date
                where_parts.append("timestamp <= ?")
                params.append(end_date_full)
            if call_type:
                where_parts.append("call_type = ?")
                params.append(call_type)
            if workflow:
                where_parts.append("workflow = ?")
                params.append(workflow)
            if user_id:
                where_parts.append("user_id = ?")
                params.append(user_id)

            where_clause = " AND ".join(where_parts) if where_parts else "1=1"

            cursor = conn.cursor()

            # Get totals
            cursor.execute(
                f"""
                SELECT
                    COUNT(*) as total_calls,
                    SUM(total_tokens) as total_tokens,
                    SUM(total_cost) as total_cost,
                    SUM(input_tokens) as total_input_tokens,
                    SUM(output_tokens) as total_output_tokens,
                    SUM(reasoning_tokens) as total_reasoning_tokens
                FROM ai_costs
                WHERE {where_clause}
                """,
                params
            )
            row = cursor.fetchone()

            # Get breakdown by call_type
            cursor.execute(
                f"""
                SELECT call_type, COUNT(*) as calls, SUM(total_tokens) as tokens, SUM(total_cost) as cost
                FROM ai_costs WHERE {where_clause}
                GROUP BY call_type ORDER BY cost DESC
                """,
                params
            )
            by_call_type = {r[0]: {"calls": r[1], "tokens": r[2], "cost": r[3]} for r in cursor.fetchall()}

            # Get breakdown by workflow
            cursor.execute(
                f"""
                SELECT workflow, COUNT(*) as calls, SUM(total_tokens) as tokens, SUM(total_cost) as cost
                FROM ai_costs WHERE {where_clause}
                GROUP BY workflow ORDER BY cost DESC
                """,
                params
            )
            by_workflow = {r[0]: {"calls": r[1], "tokens": r[2], "cost": r[3]} for r in cursor.fetchall()}

            # Get breakdown by model
            cursor.execute(
                f"""
                SELECT model, COUNT(*) as calls, SUM(total_tokens) as tokens, SUM(total_cost) as cost
                FROM ai_costs WHERE {where_clause}
                GROUP BY model ORDER BY cost DESC
                """,
                params
            )
            by_model = {r[0]: {"calls": r[1], "tokens": r[2], "cost": r[3]} for r in cursor.fetchall()}

            # Get breakdown by user
            cursor.execute(
                f"""
                SELECT user_id, COUNT(*) as calls, SUM(total_tokens) as tokens, SUM(total_cost) as cost
                FROM ai_costs WHERE {where_clause} AND user_id IS NOT NULL
                GROUP BY user_id ORDER BY cost DESC
                """,
                params
            )
            by_user = {r[0]: {"calls": r[1], "tokens": r[2], "cost": r[3]} for r in cursor.fetchall()}

            # Get daily breakdown
            cursor.execute(
                f"""
                SELECT DATE(timestamp) as date, COUNT(*) as calls, SUM(total_cost) as cost
                FROM ai_costs WHERE {where_clause}
                GROUP BY DATE(timestamp) ORDER BY date ASC
                """,
                params
            )
            daily_costs = [{"date": r[0], "calls": r[1], "cost": r[2]} for r in cursor.fetchall()]

            # Get cached tokens total
            cursor.execute(
                f"SELECT SUM(cached_input_tokens) FROM ai_costs WHERE {where_clause}",
                params
            )
            total_cached_tokens = cursor.fetchone()[0] or 0

            # Get recent calls
            cursor.execute(
                f"""
                SELECT id, timestamp, call_type, workflow, model, input_tokens, output_tokens,
                       reasoning_tokens, cached_input_tokens, total_cost, user_id
                FROM ai_costs WHERE {where_clause}
                ORDER BY timestamp DESC LIMIT 100
                """,
                params
            )
            calls = [{
                "id": r[0], "timestamp": r[1], "call_type": r[2], "workflow": r[3],
                "model": r[4], "input_tokens": r[5], "output_tokens": r[6],
                "reasoning_tokens": r[7], "cached_input_tokens": r[8],
                "total_cost": r[9], "user_id": r[10]
            } for r in cursor.fetchall()]

            return {
                "total_calls": row[0] or 0,
                "total_tokens": row[1] or 0,
                "total_cost": row[2] or 0.0,
                "total_input_tokens": row[3] or 0,
                "total_output_tokens": row[4] or 0,
                "total_reasoning_tokens": row[5] or 0,
                "total_cached_tokens": total_cached_tokens,
                "by_call_type": by_call_type,
                "by_workflow": by_workflow,
                "by_model": by_model,
                "by_user": by_user,
                "daily_costs": daily_costs,
                "calls": calls
            }
        finally:
            conn.close()

    def clear_ai_costs(self) -> None:
        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM ai_costs")
            conn.commit()
            logger.info("[DB] Cleared all AI cost tracking data")
        finally:
            conn.close()

    # =========================================================================
    # USER MANAGEMENT
    # =========================================================================

    def upsert_user(
        self,
        user_id: str,
        email: str,
        full_name: Optional[str] = None,
        avatar_url: Optional[str] = None,
        created_at: Optional[str] = None,
        last_login: Optional[str] = None,
    ) -> bool:
        now = datetime.now().isoformat()
        if not created_at:
            created_at = now
        if not last_login:
            last_login = now

        conn = self._connect()
        try:
            conn.execute("BEGIN")
            conn.execute(
                """
                INSERT INTO users (id, email, name, avatar_url, created_at, updated_at, last_login_at, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(id) DO UPDATE SET
                    email = excluded.email,
                    name = excluded.name,
                    avatar_url = excluded.avatar_url,
                    updated_at = excluded.updated_at,
                    last_login_at = excluded.last_login_at
                """,
                (user_id, email, full_name, avatar_url, created_at, now, last_login),
            )
            conn.execute("COMMIT")
            logger.info(f"[DB] Upserted user: {email}")
            return True
        except Exception as e:
            conn.execute("ROLLBACK")
            logger.error(f"[DB] Error upserting user: {e}")
            return False
        finally:
            conn.close()

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            row = cursor.fetchone()
            if not row:
                return None
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))
        finally:
            conn.close()

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE email = ? COLLATE NOCASE", (email,))
            row = cursor.fetchone()
            if not row:
                return None
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))
        finally:
            conn.close()

    # =========================================================================
    # RBAC: PERMISSIONS
    # =========================================================================

    def list_permissions(self) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM permissions ORDER BY name")
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
        finally:
            conn.close()

    def create_permission(
        self,
        name: str,
        resource: str,
        action: str,
        description: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> Optional[str]:
        if not created_at:
            created_at = datetime.now().isoformat()

        conn = self._connect()
        try:
            conn.execute("BEGIN")
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO permissions (name, resource, action, description, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET description = excluded.description
                """,
                (name, resource, action, description, created_at),
            )
            conn.execute("COMMIT")

            cursor.execute("SELECT id FROM permissions WHERE name = ?", (name,))
            row = cursor.fetchone()
            perm_id = str(row[0]) if row else None

            logger.debug(f"[DB] Created/updated permission: {name}")
            return perm_id
        except Exception as e:
            conn.execute("ROLLBACK")
            logger.error(f"[DB] Error creating permission {name}: {e}", exc_info=True)
            return None
        finally:
            conn.close()

    # =========================================================================
    # API KEYS
    # =========================================================================

    def create_api_key(
        self,
        key_hash: str,
        key_prefix: str,
        name: str,
        scopes: List[Dict],
        description: Optional[str] = None,
        rate_limit: Optional[int] = None,
        expires_at: Optional[str] = None,
        created_by: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> Optional[int]:
        created_at = datetime.now().isoformat()
        scopes_json = json.dumps(scopes)
        metadata_json = json.dumps(metadata) if metadata else None

        conn = self._connect()
        try:
            conn.execute("BEGIN")
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO api_keys (
                    key_hash, key_prefix, name, description, scopes_json,
                    rate_limit, is_active, created_at, created_by,
                    expires_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
                """,
                (
                    key_hash, key_prefix, name, description, scopes_json,
                    rate_limit, created_at, created_by, expires_at, metadata_json
                ),
            )
            conn.execute("COMMIT")
            key_id = cursor.lastrowid
            logger.info(f"[DB] Created API key: {name} (id={key_id})")
            return key_id
        except Exception as e:
            conn.execute("ROLLBACK")
            logger.error(f"[DB] Error creating API key: {e}")
            return None
        finally:
            conn.close()

    def get_api_key_by_hash(self, key_hash: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM api_keys WHERE key_hash = ? AND is_active = 1",
                (key_hash,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            columns = [desc[0] for desc in cursor.description]
            record = dict(zip(columns, row))
            # Parse JSON fields
            if record.get("scopes_json"):
                record["scopes"] = json.loads(record["scopes_json"])
            if record.get("metadata_json"):
                record["metadata"] = json.loads(record["metadata_json"])
            return record
        finally:
            conn.close()

    def get_api_key_by_id(self, key_id: int) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM api_keys WHERE id = ?", (key_id,))
            row = cursor.fetchone()
            if not row:
                return None
            columns = [desc[0] for desc in cursor.description]
            record = dict(zip(columns, row))
            if record.get("scopes_json"):
                record["scopes"] = json.loads(record["scopes_json"])
            if record.get("metadata_json"):
                record["metadata"] = json.loads(record["metadata_json"])
            return record
        finally:
            conn.close()

    def list_api_keys(
        self,
        created_by: Optional[str] = None,
        include_inactive: bool = False,
    ) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            cursor = conn.cursor()
            query = "SELECT * FROM api_keys"
            params = []
            conditions = []

            if not include_inactive:
                conditions.append("is_active = 1")
            if created_by:
                conditions.append("created_by = ?")
                params.append(created_by)

            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY created_at DESC"

            cursor.execute(query, params)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]

            results = []
            for row in rows:
                record = dict(zip(columns, row))
                if record.get("scopes_json"):
                    record["scopes"] = json.loads(record["scopes_json"])
                if record.get("metadata_json"):
                    record["metadata"] = json.loads(record["metadata_json"])
                results.append(record)
            return results
        finally:
            conn.close()

    def update_api_key(
        self,
        key_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        scopes: Optional[List[str]] = None,
        rate_limit: Optional[int] = None,
        is_active: Optional[bool] = None,
        expires_at: Optional[str] = None,
    ) -> bool:
        updates = []
        params = []

        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if scopes is not None:
            updates.append("scopes_json = ?")
            params.append(json.dumps(scopes))
        if rate_limit is not None:
            updates.append("rate_limit = ?")
            params.append(rate_limit)
        if is_active is not None:
            updates.append("is_active = ?")
            params.append(1 if is_active else 0)
        if expires_at is not None:
            updates.append("expires_at = ?")
            params.append(expires_at)

        if not updates:
            return True  # Nothing to update

        params.append(key_id)

        conn = self._connect()
        try:
            conn.execute("BEGIN")
            conn.execute(
                f"UPDATE api_keys SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            conn.execute("COMMIT")
            logger.info(f"[DB] Updated API key: {key_id}")
            return True
        except Exception as e:
            conn.execute("ROLLBACK")
            logger.error(f"[DB] Error updating API key: {e}")
            return False
        finally:
            conn.close()

    def update_api_key_last_used(self, key_id: int, timestamp: str) -> bool:
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE api_keys SET last_used_at = ? WHERE id = ?",
                (timestamp, key_id),
            )
            return True
        except Exception as e:
            logger.error(f"[DB] Error updating API key last_used: {e}")
            return False
        finally:
            conn.close()

    def rotate_api_key(
        self,
        key_id: int,
        new_key_hash: str,
        new_key_prefix: str,
        rotated_at: str,
    ) -> bool:
        conn = self._connect()
        try:
            conn.execute("BEGIN")
            conn.execute(
                """
                UPDATE api_keys
                SET key_hash = ?, key_prefix = ?, last_rotated_at = ?
                WHERE id = ?
                """,
                (new_key_hash, new_key_prefix, rotated_at, key_id),
            )
            conn.execute("COMMIT")
            logger.info(f"[DB] Rotated API key: {key_id}")
            return True
        except Exception as e:
            conn.execute("ROLLBACK")
            logger.error(f"[DB] Error rotating API key: {e}")
            return False
        finally:
            conn.close()

    def delete_api_key(self, key_id: int) -> bool:
        conn = self._connect()
        try:
            conn.execute("BEGIN")
            # Delete usage logs first
            conn.execute("DELETE FROM api_key_usage WHERE api_key_id = ?", (key_id,))
            # Delete the key
            conn.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
            conn.execute("COMMIT")
            logger.info(f"[DB] Deleted API key: {key_id}")
            return True
        except Exception as e:
            conn.execute("ROLLBACK")
            logger.error(f"[DB] Error deleting API key: {e}")
            return False
        finally:
            conn.close()

    def deactivate_api_key(self, key_id: int) -> bool:
        return self.update_api_key(key_id, is_active=False)

    # =========================================================================
    # API KEY USAGE LOGGING
    # =========================================================================

    def log_api_key_usage(
        self,
        api_key_id: int,
        endpoint: str,
        method: str,
        status_code: Optional[int] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        response_time_ms: Optional[int] = None,
        request_size: Optional[int] = None,
        response_size: Optional[int] = None,
        timestamp: Optional[str] = None,
    ) -> None:
        if not timestamp:
            timestamp = datetime.now().isoformat()

        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO api_key_usage (
                    api_key_id, timestamp, endpoint, method, status_code,
                    ip_address, user_agent, response_time_ms,
                    request_size, response_size
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    api_key_id, timestamp, endpoint, method, status_code,
                    ip_address, user_agent, response_time_ms,
                    request_size, response_size
                ),
            )
            conn.commit()
        except Exception as e:
            logger.error(f"[DB] Error logging API key usage: {e}")
        finally:
            conn.close()

    def get_api_key_usage_stats(
        self,
        api_key_id: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        conn = self._connect()
        try:
            where_parts = []
            params = []

            if api_key_id:
                where_parts.append("api_key_id = ?")
                params.append(api_key_id)
            if start_date:
                where_parts.append("timestamp >= ?")
                params.append(start_date)
            if end_date:
                end_date_full = f"{end_date}T23:59:59" if 'T' not in end_date else end_date
                where_parts.append("timestamp <= ?")
                params.append(end_date_full)

            where_clause = " AND ".join(where_parts) if where_parts else "1=1"

            cursor = conn.cursor()

            # Total requests
            cursor.execute(
                f"SELECT COUNT(*) FROM api_key_usage WHERE {where_clause}",
                params
            )
            total_requests = cursor.fetchone()[0]

            # By status code
            cursor.execute(
                f"""
                SELECT status_code, COUNT(*)
                FROM api_key_usage
                WHERE {where_clause}
                GROUP BY status_code
                ORDER BY COUNT(*) DESC
                """,
                params
            )
            by_status = {str(r[0]): r[1] for r in cursor.fetchall()}

            # By endpoint
            cursor.execute(
                f"""
                SELECT endpoint, COUNT(*)
                FROM api_key_usage
                WHERE {where_clause}
                GROUP BY endpoint
                ORDER BY COUNT(*) DESC
                LIMIT 20
                """,
                params
            )
            by_endpoint = {r[0]: r[1] for r in cursor.fetchall()}

            # Average response time
            cursor.execute(
                f"""
                SELECT AVG(response_time_ms)
                FROM api_key_usage
                WHERE {where_clause} AND response_time_ms IS NOT NULL
                """,
                params
            )
            avg_response_time = cursor.fetchone()[0]

            # Recent requests
            cursor.execute(
                f"""
                SELECT api_key_id, timestamp, endpoint, method, status_code, response_time_ms
                FROM api_key_usage
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT 50
                """,
                params
            )
            recent = [
                {
                    "api_key_id": r[0], "timestamp": r[1], "endpoint": r[2],
                    "method": r[3], "status_code": r[4], "response_time_ms": r[5]
                }
                for r in cursor.fetchall()
            ]

            return {
                "total_requests": total_requests,
                "by_status_code": by_status,
                "by_endpoint": by_endpoint,
                "avg_response_time_ms": avg_response_time,
                "recent_requests": recent,
            }
        finally:
            conn.close()

    # =========================================================================
    # AUDIT LOGGING
    # =========================================================================

    def log_audit_event(
        self,
        timestamp: str,
        action: str,
        user_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        details_json: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """Log an audit event to the audit_log table."""
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO audit_log (
                    timestamp, user_id, action, resource_type, resource_id,
                    details_json, ip_address, user_agent
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp, user_id, action, resource_type, resource_id,
                    details_json, ip_address, user_agent
                ),
            )
            conn.commit()
        except Exception as e:
            logger.error(f"[DB] Error logging audit event: {e}")
        finally:
            conn.close()

    def query_audit_log(
        self,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Query audit log entries with optional filters."""
        conn = self._connect()
        try:
            where_parts = []
            params = []

            if user_id:
                where_parts.append("user_id = ?")
                params.append(user_id)
            if action:
                # Support prefix matching (e.g., "user.*" matches "user.login", "user.logout")
                if action.endswith("*"):
                    where_parts.append("action LIKE ?")
                    params.append(action[:-1] + "%")
                else:
                    where_parts.append("action = ?")
                    params.append(action)
            if resource_type:
                where_parts.append("resource_type = ?")
                params.append(resource_type)
            if resource_id:
                where_parts.append("resource_id = ?")
                params.append(resource_id)
            if start_date:
                where_parts.append("timestamp >= ?")
                params.append(start_date)
            if end_date:
                end_date_full = f"{end_date}T23:59:59" if 'T' not in end_date else end_date
                where_parts.append("timestamp <= ?")
                params.append(end_date_full)

            where_clause = " AND ".join(where_parts) if where_parts else "1=1"

            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT id, timestamp, user_id, action, resource_type, resource_id,
                       details_json, ip_address, user_agent
                FROM audit_log
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
                """,
                params + [limit, offset]
            )

            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]

            results = []
            for row in rows:
                record = dict(zip(columns, row))
                # Parse JSON details
                if record.get("details_json"):
                    try:
                        record["details"] = json.loads(record["details_json"])
                    except json.JSONDecodeError:
                        record["details"] = {}
                else:
                    record["details"] = {}
                results.append(record)

            return results
        except Exception as e:
            logger.error(f"[DB] Error querying audit log: {e}")
            return []
        finally:
            conn.close()
