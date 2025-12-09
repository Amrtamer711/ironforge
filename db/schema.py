"""
Unified Database Schema Definition

This is the SINGLE SOURCE OF TRUTH for all database tables.
Both SQLite and Supabase backends read from this file.

To add a new table or modify schema:
1. Update the TABLES dictionary below
2. Run: python -m db.schema --generate sqlite   (for SQLite SQL)
3. Run: python -m db.schema --generate postgres (for Supabase/PostgreSQL SQL)
4. Apply migrations as needed

Column types are defined in a backend-agnostic way and translated
to the appropriate SQL dialect when generating schema.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum


class ColumnType(Enum):
    """Backend-agnostic column types."""
    INTEGER = "integer"
    TEXT = "text"
    REAL = "real"          # Float/decimal
    BOOLEAN = "boolean"
    TIMESTAMP = "timestamp"
    JSON = "json"


@dataclass
class Column:
    """Column definition."""
    name: str
    type: ColumnType
    nullable: bool = True
    default: Optional[Any] = None
    primary_key: bool = False
    unique: bool = False
    check: Optional[str] = None  # CHECK constraint expression


@dataclass
class Index:
    """Index definition."""
    name: str
    columns: List[str]
    unique: bool = False


@dataclass
class Table:
    """Table definition."""
    name: str
    columns: List[Column]
    indexes: List[Index] = field(default_factory=list)
    unique_constraints: List[List[str]] = field(default_factory=list)  # Composite unique


# =============================================================================
# SCHEMA DEFINITIONS - Edit these to change the database structure
# =============================================================================

TABLES: Dict[str, Table] = {
    # =========================================================================
    # AUTHENTICATION & AUTHORIZATION TABLES
    # =========================================================================

    # -------------------------------------------------------------------------
    # USERS - Synced with Supabase Auth (auth.users)
    # For SQLite: standalone user table
    # For Supabase: references auth.users via trigger
    # -------------------------------------------------------------------------
    "users": Table(
        name="users",
        columns=[
            Column("id", ColumnType.TEXT, primary_key=True),  # UUID from Supabase Auth or generated
            Column("email", ColumnType.TEXT, nullable=False, unique=True),
            Column("name", ColumnType.TEXT),
            Column("avatar_url", ColumnType.TEXT),
            Column("is_active", ColumnType.INTEGER, nullable=False, default=1),  # Boolean as int
            Column("created_at", ColumnType.TEXT, nullable=False),
            Column("updated_at", ColumnType.TEXT, nullable=False),
            Column("last_login_at", ColumnType.TEXT),
            Column("metadata_json", ColumnType.TEXT),  # Additional user metadata
        ],
        indexes=[
            Index("idx_users_email", ["email"]),
            Index("idx_users_is_active", ["is_active"]),
        ],
    ),

    # -------------------------------------------------------------------------
    # ROLES - Define available roles in the system
    # -------------------------------------------------------------------------
    "roles": Table(
        name="roles",
        columns=[
            Column("id", ColumnType.INTEGER, primary_key=True),
            Column("name", ColumnType.TEXT, nullable=False, unique=True),
            Column("description", ColumnType.TEXT),
            Column("is_system", ColumnType.INTEGER, nullable=False, default=0),  # System roles can't be deleted
            Column("created_at", ColumnType.TEXT, nullable=False),
        ],
        indexes=[
            Index("idx_roles_name", ["name"]),
        ],
    ),

    # -------------------------------------------------------------------------
    # USER_ROLES - Junction table for user-role assignments
    # -------------------------------------------------------------------------
    "user_roles": Table(
        name="user_roles",
        columns=[
            Column("id", ColumnType.INTEGER, primary_key=True),
            Column("user_id", ColumnType.TEXT, nullable=False),  # FK to users.id
            Column("role_id", ColumnType.INTEGER, nullable=False),  # FK to roles.id
            Column("granted_by", ColumnType.TEXT),  # User who granted this role
            Column("granted_at", ColumnType.TEXT, nullable=False),
            Column("expires_at", ColumnType.TEXT),  # Optional expiration
        ],
        indexes=[
            Index("idx_user_roles_user", ["user_id"]),
            Index("idx_user_roles_role", ["role_id"]),
        ],
        unique_constraints=[["user_id", "role_id"]],
    ),

    # -------------------------------------------------------------------------
    # PERMISSIONS - Define granular permissions
    # -------------------------------------------------------------------------
    "permissions": Table(
        name="permissions",
        columns=[
            Column("id", ColumnType.INTEGER, primary_key=True),
            Column("name", ColumnType.TEXT, nullable=False, unique=True),
            Column("description", ColumnType.TEXT),
            Column("resource", ColumnType.TEXT, nullable=False),  # e.g., 'proposals', 'booking_orders', 'mockups'
            Column("action", ColumnType.TEXT, nullable=False),  # e.g., 'create', 'read', 'update', 'delete', 'manage'
            Column("created_at", ColumnType.TEXT, nullable=False),
        ],
        indexes=[
            Index("idx_permissions_name", ["name"]),
            Index("idx_permissions_resource", ["resource"]),
        ],
        unique_constraints=[["resource", "action"]],
    ),

    # -------------------------------------------------------------------------
    # ROLE_PERMISSIONS - Junction table for role-permission assignments
    # -------------------------------------------------------------------------
    "role_permissions": Table(
        name="role_permissions",
        columns=[
            Column("id", ColumnType.INTEGER, primary_key=True),
            Column("role_id", ColumnType.INTEGER, nullable=False),  # FK to roles.id
            Column("permission_id", ColumnType.INTEGER, nullable=False),  # FK to permissions.id
            Column("granted_at", ColumnType.TEXT, nullable=False),
        ],
        indexes=[
            Index("idx_role_permissions_role", ["role_id"]),
            Index("idx_role_permissions_permission", ["permission_id"]),
        ],
        unique_constraints=[["role_id", "permission_id"]],
    ),

    # -------------------------------------------------------------------------
    # INVITE_TOKENS - For user signup invitations
    # -------------------------------------------------------------------------
    "invite_tokens": Table(
        name="invite_tokens",
        columns=[
            Column("id", ColumnType.INTEGER, primary_key=True),
            Column("token", ColumnType.TEXT, nullable=False, unique=True),
            Column("email", ColumnType.TEXT, nullable=False),
            Column("role_id", ColumnType.INTEGER, nullable=False),  # FK to roles.id
            Column("created_by", ColumnType.TEXT, nullable=False),  # FK to users.id
            Column("created_at", ColumnType.TEXT, nullable=False),
            Column("expires_at", ColumnType.TEXT, nullable=False),
            Column("used_at", ColumnType.TEXT),  # NULL until used
            Column("is_revoked", ColumnType.INTEGER, nullable=False, default=0),
        ],
        indexes=[
            Index("idx_invite_tokens_token", ["token"]),
            Index("idx_invite_tokens_email", ["email"]),
        ],
    ),

    # -------------------------------------------------------------------------
    # MODULES - Define available application modules
    # -------------------------------------------------------------------------
    "modules": Table(
        name="modules",
        columns=[
            Column("id", ColumnType.INTEGER, primary_key=True),
            Column("name", ColumnType.TEXT, nullable=False, unique=True),  # e.g., 'sales', 'crm', 'analytics'
            Column("display_name", ColumnType.TEXT, nullable=False),  # e.g., 'Sales Bot'
            Column("description", ColumnType.TEXT),
            Column("icon", ColumnType.TEXT),  # Icon identifier for frontend
            Column("is_active", ColumnType.INTEGER, nullable=False, default=1),  # Whether module is enabled
            Column("is_default", ColumnType.INTEGER, nullable=False, default=0),  # Default landing module
            Column("sort_order", ColumnType.INTEGER, nullable=False, default=0),  # Display order
            Column("required_permission", ColumnType.TEXT),  # Permission needed to access (e.g., 'sales:*:read')
            Column("config_json", ColumnType.TEXT),  # Module-specific configuration
            Column("created_at", ColumnType.TEXT, nullable=False),
        ],
        indexes=[
            Index("idx_modules_name", ["name"]),
            Index("idx_modules_active", ["is_active"]),
        ],
    ),

    # -------------------------------------------------------------------------
    # USER_MODULES - Junction table for user-module access
    # -------------------------------------------------------------------------
    "user_modules": Table(
        name="user_modules",
        columns=[
            Column("id", ColumnType.INTEGER, primary_key=True),
            Column("user_id", ColumnType.TEXT, nullable=False),  # FK to users.id
            Column("module_id", ColumnType.INTEGER, nullable=False),  # FK to modules.id
            Column("is_default", ColumnType.INTEGER, nullable=False, default=0),  # User's default module
            Column("granted_by", ColumnType.TEXT),  # User who granted access
            Column("granted_at", ColumnType.TEXT, nullable=False),
        ],
        indexes=[
            Index("idx_user_modules_user", ["user_id"]),
            Index("idx_user_modules_module", ["module_id"]),
        ],
        unique_constraints=[["user_id", "module_id"]],
    ),

    # -------------------------------------------------------------------------
    # AUDIT_LOG - Track important actions for security
    # -------------------------------------------------------------------------
    "audit_log": Table(
        name="audit_log",
        columns=[
            Column("id", ColumnType.INTEGER, primary_key=True),
            Column("timestamp", ColumnType.TEXT, nullable=False),
            Column("user_id", ColumnType.TEXT),  # FK to users.id (nullable for system actions)
            Column("action", ColumnType.TEXT, nullable=False),  # e.g., 'login', 'logout', 'create', 'update', 'delete'
            Column("resource_type", ColumnType.TEXT),  # e.g., 'user', 'role', 'proposal', 'booking_order'
            Column("resource_id", ColumnType.TEXT),  # ID of the affected resource
            Column("details_json", ColumnType.TEXT),  # Additional context (old/new values, etc.)
            Column("ip_address", ColumnType.TEXT),
            Column("user_agent", ColumnType.TEXT),
        ],
        indexes=[
            Index("idx_audit_log_timestamp", ["timestamp"]),
            Index("idx_audit_log_user", ["user_id"]),
            Index("idx_audit_log_action", ["action"]),
            Index("idx_audit_log_resource", ["resource_type", "resource_id"]),
        ],
    ),

    # =========================================================================
    # BUSINESS DATA TABLES
    # =========================================================================

    # -------------------------------------------------------------------------
    # PROPOSALS LOG
    # -------------------------------------------------------------------------
    "proposals_log": Table(
        name="proposals_log",
        columns=[
            Column("id", ColumnType.INTEGER, primary_key=True),
            Column("user_id", ColumnType.TEXT),  # FK to users.id (owner)
            Column("submitted_by", ColumnType.TEXT, nullable=False),  # Display name
            Column("client_name", ColumnType.TEXT, nullable=False),
            Column("date_generated", ColumnType.TEXT, nullable=False),
            Column("package_type", ColumnType.TEXT, nullable=False),
            Column("locations", ColumnType.TEXT, nullable=False),
            Column("total_amount", ColumnType.TEXT, nullable=False),
        ],
        indexes=[
            Index("idx_proposals_user", ["user_id"]),
        ],
    ),

    # -------------------------------------------------------------------------
    # MOCKUP FRAMES
    # -------------------------------------------------------------------------
    "mockup_frames": Table(
        name="mockup_frames",
        columns=[
            Column("id", ColumnType.INTEGER, primary_key=True),
            Column("user_id", ColumnType.TEXT),  # FK to users.id (owner)
            Column("location_key", ColumnType.TEXT, nullable=False),
            Column("time_of_day", ColumnType.TEXT, nullable=False, default="day"),
            Column("finish", ColumnType.TEXT, nullable=False, default="gold"),
            Column("photo_filename", ColumnType.TEXT, nullable=False),
            Column("frames_data", ColumnType.TEXT, nullable=False),  # JSON stored as text
            Column("created_at", ColumnType.TEXT, nullable=False),
            Column("created_by", ColumnType.TEXT),  # Display name (kept for backwards compat)
            Column("config_json", ColumnType.TEXT),
        ],
        indexes=[
            Index("idx_mockup_frames_user", ["user_id"]),
        ],
        unique_constraints=[["location_key", "time_of_day", "finish", "photo_filename"]],
    ),

    # -------------------------------------------------------------------------
    # MOCKUP USAGE ANALYTICS
    # -------------------------------------------------------------------------
    "mockup_usage": Table(
        name="mockup_usage",
        columns=[
            Column("id", ColumnType.INTEGER, primary_key=True),
            Column("user_id", ColumnType.TEXT),  # FK to users.id
            Column("generated_at", ColumnType.TEXT, nullable=False),
            Column("location_key", ColumnType.TEXT, nullable=False),
            Column("time_of_day", ColumnType.TEXT, nullable=False),
            Column("finish", ColumnType.TEXT, nullable=False),
            Column("photo_used", ColumnType.TEXT, nullable=False),
            Column("creative_type", ColumnType.TEXT, nullable=False,
                   check="creative_type IN ('uploaded', 'ai_generated')"),
            Column("ai_prompt", ColumnType.TEXT),
            Column("template_selected", ColumnType.INTEGER, nullable=False, default=0),
            Column("success", ColumnType.INTEGER, nullable=False, default=1),
            Column("user_ip", ColumnType.TEXT),
        ],
        indexes=[
            Index("idx_mockup_usage_user", ["user_id"]),
        ],
    ),

    # -------------------------------------------------------------------------
    # BOOKING ORDERS
    # -------------------------------------------------------------------------
    "booking_orders": Table(
        name="booking_orders",
        columns=[
            Column("id", ColumnType.INTEGER, primary_key=True),
            Column("user_id", ColumnType.TEXT),  # FK to users.id (owner/submitter)
            Column("bo_ref", ColumnType.TEXT, nullable=False, unique=True),
            Column("company", ColumnType.TEXT, nullable=False),
            Column("original_file_path", ColumnType.TEXT, nullable=False),
            Column("original_file_type", ColumnType.TEXT, nullable=False),
            Column("original_file_size", ColumnType.INTEGER),
            Column("original_filename", ColumnType.TEXT),
            Column("parsed_excel_path", ColumnType.TEXT, nullable=False),
            Column("bo_number", ColumnType.TEXT),
            Column("bo_date", ColumnType.TEXT),
            Column("client", ColumnType.TEXT),
            Column("agency", ColumnType.TEXT),
            Column("brand_campaign", ColumnType.TEXT),
            Column("category", ColumnType.TEXT),
            Column("asset", ColumnType.TEXT),
            Column("net_pre_vat", ColumnType.REAL),
            Column("vat_value", ColumnType.REAL),
            Column("gross_amount", ColumnType.REAL),
            Column("sla_pct", ColumnType.REAL),
            Column("payment_terms", ColumnType.TEXT),
            Column("sales_person", ColumnType.TEXT),
            Column("commission_pct", ColumnType.REAL),
            Column("notes", ColumnType.TEXT),
            Column("locations_json", ColumnType.TEXT),
            Column("extraction_method", ColumnType.TEXT),
            Column("extraction_confidence", ColumnType.TEXT),
            Column("warnings_json", ColumnType.TEXT),
            Column("missing_fields_json", ColumnType.TEXT),
            Column("vat_calc", ColumnType.REAL),
            Column("gross_calc", ColumnType.REAL),
            Column("sla_deduction", ColumnType.REAL),
            Column("net_excl_sla_calc", ColumnType.REAL),
            Column("parsed_at", ColumnType.TEXT, nullable=False),
            Column("parsed_by", ColumnType.TEXT),
            Column("source_classification", ColumnType.TEXT),
            Column("classification_confidence", ColumnType.TEXT),
            Column("needs_review", ColumnType.INTEGER, default=0),
            Column("search_text", ColumnType.TEXT),
        ],
        indexes=[
            Index("idx_booking_orders_user", ["user_id"]),
            Index("idx_booking_orders_bo_ref", ["bo_ref"]),
            Index("idx_booking_orders_company", ["company"]),
            Index("idx_booking_orders_client", ["client"]),
            Index("idx_booking_orders_parsed_at", ["parsed_at"]),
        ],
    ),

    # -------------------------------------------------------------------------
    # BO APPROVAL WORKFLOWS
    # -------------------------------------------------------------------------
    "bo_approval_workflows": Table(
        name="bo_approval_workflows",
        columns=[
            Column("workflow_id", ColumnType.TEXT, primary_key=True),
            Column("workflow_data", ColumnType.TEXT, nullable=False),
            Column("created_at", ColumnType.TEXT, nullable=False),
            Column("updated_at", ColumnType.TEXT, nullable=False),
        ],
        indexes=[
            Index("idx_bo_workflows_updated", ["updated_at"]),
        ],
    ),

    # -------------------------------------------------------------------------
    # API KEYS - For programmatic API access
    # -------------------------------------------------------------------------
    "api_keys": Table(
        name="api_keys",
        columns=[
            Column("id", ColumnType.INTEGER, primary_key=True),
            Column("key_hash", ColumnType.TEXT, nullable=False, unique=True),  # SHA256 hash of the key
            Column("key_prefix", ColumnType.TEXT, nullable=False),  # First 8 chars for identification
            Column("name", ColumnType.TEXT, nullable=False),  # Client/app name
            Column("description", ColumnType.TEXT),
            Column("scopes_json", ColumnType.TEXT, nullable=False),  # JSON array of scopes
            Column("rate_limit", ColumnType.INTEGER),  # Requests per minute (null = unlimited)
            Column("is_active", ColumnType.INTEGER, nullable=False, default=1),
            Column("created_at", ColumnType.TEXT, nullable=False),
            Column("created_by", ColumnType.TEXT),  # FK to users.id
            Column("expires_at", ColumnType.TEXT),  # Optional expiration
            Column("last_used_at", ColumnType.TEXT),
            Column("last_rotated_at", ColumnType.TEXT),  # For key rotation tracking
            Column("metadata_json", ColumnType.TEXT),  # Additional metadata
        ],
        indexes=[
            Index("idx_api_keys_hash", ["key_hash"]),
            Index("idx_api_keys_name", ["name"]),
            Index("idx_api_keys_active", ["is_active"]),
            Index("idx_api_keys_created_by", ["created_by"]),
        ],
    ),

    # -------------------------------------------------------------------------
    # API KEY USAGE LOG - Audit trail for API key usage
    # -------------------------------------------------------------------------
    "api_key_usage": Table(
        name="api_key_usage",
        columns=[
            Column("id", ColumnType.INTEGER, primary_key=True),
            Column("api_key_id", ColumnType.INTEGER, nullable=False),  # FK to api_keys.id
            Column("timestamp", ColumnType.TEXT, nullable=False),
            Column("endpoint", ColumnType.TEXT, nullable=False),
            Column("method", ColumnType.TEXT, nullable=False),
            Column("status_code", ColumnType.INTEGER),
            Column("ip_address", ColumnType.TEXT),
            Column("user_agent", ColumnType.TEXT),
            Column("response_time_ms", ColumnType.INTEGER),
            Column("request_size", ColumnType.INTEGER),
            Column("response_size", ColumnType.INTEGER),
        ],
        indexes=[
            Index("idx_api_key_usage_key", ["api_key_id"]),
            Index("idx_api_key_usage_timestamp", ["timestamp"]),
            Index("idx_api_key_usage_endpoint", ["endpoint"]),
        ],
    ),

    # -------------------------------------------------------------------------
    # AI COSTS TRACKING
    # -------------------------------------------------------------------------
    "ai_costs": Table(
        name="ai_costs",
        columns=[
            Column("id", ColumnType.INTEGER, primary_key=True),
            Column("timestamp", ColumnType.TEXT, nullable=False),
            Column("call_type", ColumnType.TEXT, nullable=False,
                   check="call_type IN ('classification', 'parsing', 'coordinator_thread', 'main_llm', 'mockup_analysis', 'image_generation', 'bo_edit', 'other')"),
            Column("workflow", ColumnType.TEXT,
                   check="workflow IN ('mockup_upload', 'mockup_ai', 'bo_parsing', 'bo_editing', 'bo_revision', 'proposal_generation', 'general_chat', 'location_management') OR workflow IS NULL"),
            Column("model", ColumnType.TEXT, nullable=False),
            Column("user_id", ColumnType.TEXT),
            Column("context", ColumnType.TEXT),
            Column("input_tokens", ColumnType.INTEGER),
            Column("cached_input_tokens", ColumnType.INTEGER, default=0),
            Column("output_tokens", ColumnType.INTEGER),
            Column("reasoning_tokens", ColumnType.INTEGER, default=0),
            Column("total_tokens", ColumnType.INTEGER),
            Column("input_cost", ColumnType.REAL),
            Column("output_cost", ColumnType.REAL),
            Column("reasoning_cost", ColumnType.REAL, default=0),
            Column("total_cost", ColumnType.REAL),
            Column("metadata_json", ColumnType.TEXT),
        ],
        indexes=[
            Index("idx_ai_costs_timestamp", ["timestamp"]),
            Index("idx_ai_costs_call_type", ["call_type"]),
            Index("idx_ai_costs_user", ["user_id"]),
            Index("idx_ai_costs_workflow", ["workflow"]),
        ],
    ),
}


# =============================================================================
# SQL GENERATORS
# =============================================================================

class SQLGenerator:
    """Base class for SQL generation."""

    def generate_create_table(self, table: Table) -> str:
        raise NotImplementedError

    def generate_create_index(self, table_name: str, index: Index) -> str:
        raise NotImplementedError

    def generate_full_schema(self) -> str:
        """Generate complete schema SQL."""
        statements = []
        for table in TABLES.values():
            statements.append(self.generate_create_table(table))
            for index in table.indexes:
                statements.append(self.generate_create_index(table.name, index))
        return "\n\n".join(statements)


class SQLiteGenerator(SQLGenerator):
    """Generate SQLite-compatible SQL."""

    TYPE_MAP = {
        ColumnType.INTEGER: "INTEGER",
        ColumnType.TEXT: "TEXT",
        ColumnType.REAL: "REAL",
        ColumnType.BOOLEAN: "INTEGER",  # SQLite uses 0/1
        ColumnType.TIMESTAMP: "TEXT",   # ISO format string
        ColumnType.JSON: "TEXT",        # JSON stored as text
    }

    def generate_create_table(self, table: Table) -> str:
        lines = [f"CREATE TABLE IF NOT EXISTS {table.name} ("]
        col_defs = []

        for col in table.columns:
            col_def = f"    {col.name} {self.TYPE_MAP[col.type]}"

            if col.primary_key:
                col_def += " PRIMARY KEY"
                if col.type == ColumnType.INTEGER:
                    col_def += " AUTOINCREMENT"

            if not col.nullable and not col.primary_key:
                col_def += " NOT NULL"

            if col.default is not None:
                if isinstance(col.default, str):
                    col_def += f" DEFAULT '{col.default}'"
                else:
                    col_def += f" DEFAULT {col.default}"

            if col.unique and not col.primary_key:
                col_def += " UNIQUE"

            col_defs.append(col_def)

        # Add CHECK constraints
        for col in table.columns:
            if col.check:
                col_defs.append(f"    CONSTRAINT {col.name}_check CHECK ({col.check})")

        # Add composite unique constraints
        for cols in table.unique_constraints:
            col_defs.append(f"    UNIQUE({', '.join(cols)})")

        lines.append(",\n".join(col_defs))
        lines.append(");")
        return "\n".join(lines)

    def generate_create_index(self, table_name: str, index: Index) -> str:
        unique = "UNIQUE " if index.unique else ""
        cols = ", ".join(index.columns)
        return f"CREATE {unique}INDEX IF NOT EXISTS {index.name} ON {table_name}({cols});"


class PostgresGenerator(SQLGenerator):
    """Generate PostgreSQL/Supabase-compatible SQL."""

    TYPE_MAP = {
        ColumnType.INTEGER: "BIGINT",
        ColumnType.TEXT: "TEXT",
        ColumnType.REAL: "DOUBLE PRECISION",
        ColumnType.BOOLEAN: "BOOLEAN",
        ColumnType.TIMESTAMP: "TIMESTAMPTZ",
        ColumnType.JSON: "JSONB",
    }

    def generate_create_table(self, table: Table) -> str:
        lines = [f"CREATE TABLE IF NOT EXISTS {table.name} ("]
        col_defs = []

        for col in table.columns:
            if col.primary_key and col.type == ColumnType.INTEGER:
                col_def = f"    {col.name} BIGSERIAL PRIMARY KEY"
            elif col.primary_key:
                col_def = f"    {col.name} {self.TYPE_MAP[col.type]} PRIMARY KEY"
            else:
                col_def = f"    {col.name} {self.TYPE_MAP[col.type]}"

                if not col.nullable:
                    col_def += " NOT NULL"

                if col.default is not None:
                    if isinstance(col.default, str):
                        col_def += f" DEFAULT '{col.default}'"
                    elif col.type == ColumnType.BOOLEAN:
                        col_def += f" DEFAULT {str(col.default).lower()}"
                    else:
                        col_def += f" DEFAULT {col.default}"

                if col.unique:
                    col_def += " UNIQUE"

            col_defs.append(col_def)

        # Add CHECK constraints
        for col in table.columns:
            if col.check:
                # Translate SQLite-style checks to PostgreSQL
                check_expr = col.check
                col_defs.append(f"    CONSTRAINT {table.name}_{col.name}_check CHECK ({check_expr})")

        # Add composite unique constraints
        for cols in table.unique_constraints:
            constraint_name = f"{table.name}_{'_'.join(cols)}_unique"
            col_defs.append(f"    CONSTRAINT {constraint_name} UNIQUE ({', '.join(cols)})")

        lines.append(",\n".join(col_defs))
        lines.append(");")
        return "\n".join(lines)

    def generate_create_index(self, table_name: str, index: Index) -> str:
        unique = "UNIQUE " if index.unique else ""
        cols = ", ".join(index.columns)
        return f"CREATE {unique}INDEX IF NOT EXISTS {index.name} ON {table_name}({cols});"


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_sqlite_schema() -> str:
    """Get complete SQLite schema SQL."""
    return SQLiteGenerator().generate_full_schema()


def get_postgres_schema() -> str:
    """Get complete PostgreSQL/Supabase schema SQL."""
    return PostgresGenerator().generate_full_schema()


def get_table_names() -> List[str]:
    """Get list of all table names."""
    return list(TABLES.keys())


def get_table(name: str) -> Optional[Table]:
    """Get a table definition by name."""
    return TABLES.get(name)


# =============================================================================
# CLI - Run with: python -m db.schema
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate database schema SQL")
    parser.add_argument(
        "--generate", "-g",
        choices=["sqlite", "postgres", "both"],
        default="both",
        help="Which SQL dialect to generate"
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file (default: stdout)"
    )

    args = parser.parse_args()

    output_lines = []

    if args.generate in ("sqlite", "both"):
        output_lines.append("-- ===========================================")
        output_lines.append("-- SQLite Schema")
        output_lines.append("-- ===========================================")
        output_lines.append("")
        output_lines.append(get_sqlite_schema())
        output_lines.append("")

    if args.generate in ("postgres", "both"):
        output_lines.append("-- ===========================================")
        output_lines.append("-- PostgreSQL/Supabase Schema")
        output_lines.append("-- ===========================================")
        output_lines.append("")
        output_lines.append(get_postgres_schema())
        output_lines.append("")

    output = "\n".join(output_lines)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        print(f"Schema written to {args.output}")
    else:
        print(output)
