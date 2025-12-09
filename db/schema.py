"""
Unified Database Schema Definition

This is the SINGLE SOURCE OF TRUTH for all database tables.
Both SQLite and Supabase backends read from this file.

ARCHITECTURE:
- UI Supabase: Core/Auth tables (users, roles, permissions, modules, invite_tokens, etc.)
- Sales Bot Supabase: Business data tables (proposals, mockups, booking_orders, ai_costs)

To add a new table or modify schema:
1. Update the appropriate TABLES dictionary below (CORE_TABLES or SALES_TABLES)
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
# CORE/AUTH TABLES - For UI Supabase (authentication, authorization, modules)
# =============================================================================

CORE_TABLES: Dict[str, Table] = {
    # -------------------------------------------------------------------------
    # USERS - Synced with Supabase Auth (auth.users)
    # -------------------------------------------------------------------------
    "users": Table(
        name="users",
        columns=[
            Column("id", ColumnType.TEXT, primary_key=True),  # UUID from Supabase Auth
            Column("email", ColumnType.TEXT, nullable=False, unique=True),
            Column("name", ColumnType.TEXT),
            Column("avatar_url", ColumnType.TEXT),
            Column("is_active", ColumnType.INTEGER, nullable=False, default=1),
            Column("created_at", ColumnType.TEXT, nullable=False),
            Column("updated_at", ColumnType.TEXT, nullable=False),
            Column("last_login_at", ColumnType.TEXT),
            Column("metadata_json", ColumnType.TEXT),
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
            Column("display_name", ColumnType.TEXT),
            Column("description", ColumnType.TEXT),
            Column("module", ColumnType.TEXT),  # NULL = system-wide, 'sales' = module-specific
            Column("is_system", ColumnType.INTEGER, nullable=False, default=0),
            Column("created_at", ColumnType.TEXT, nullable=False),
        ],
        indexes=[
            Index("idx_roles_name", ["name"]),
            Index("idx_roles_module", ["module"]),
        ],
    ),

    # -------------------------------------------------------------------------
    # USER_ROLES - Junction table for user-role assignments
    # -------------------------------------------------------------------------
    "user_roles": Table(
        name="user_roles",
        columns=[
            Column("id", ColumnType.INTEGER, primary_key=True),
            Column("user_id", ColumnType.TEXT, nullable=False),
            Column("role_id", ColumnType.INTEGER, nullable=False),
            Column("granted_by", ColumnType.TEXT),
            Column("granted_at", ColumnType.TEXT, nullable=False),
            Column("expires_at", ColumnType.TEXT),
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
            Column("name", ColumnType.TEXT, nullable=False, unique=True),  # e.g., 'sales:proposals:create'
            Column("description", ColumnType.TEXT),
            Column("module", ColumnType.TEXT, nullable=False),  # 'core', 'sales', etc.
            Column("resource", ColumnType.TEXT, nullable=False),  # 'proposals', 'users', etc.
            Column("action", ColumnType.TEXT, nullable=False),  # 'create', 'read', 'update', 'delete', 'manage'
            Column("created_at", ColumnType.TEXT, nullable=False),
        ],
        indexes=[
            Index("idx_permissions_name", ["name"]),
            Index("idx_permissions_module", ["module"]),
            Index("idx_permissions_resource", ["resource"]),
        ],
        unique_constraints=[["module", "resource", "action"]],
    ),

    # -------------------------------------------------------------------------
    # ROLE_PERMISSIONS - Junction table for role-permission assignments
    # -------------------------------------------------------------------------
    "role_permissions": Table(
        name="role_permissions",
        columns=[
            Column("id", ColumnType.INTEGER, primary_key=True),
            Column("role_id", ColumnType.INTEGER, nullable=False),
            Column("permission_id", ColumnType.INTEGER, nullable=False),
            Column("granted_at", ColumnType.TEXT, nullable=False),
        ],
        indexes=[
            Index("idx_role_permissions_role", ["role_id"]),
            Index("idx_role_permissions_permission", ["permission_id"]),
        ],
        unique_constraints=[["role_id", "permission_id"]],
    ),

    # -------------------------------------------------------------------------
    # MODULES - Define available application modules
    # -------------------------------------------------------------------------
    "modules": Table(
        name="modules",
        columns=[
            Column("id", ColumnType.INTEGER, primary_key=True),
            Column("name", ColumnType.TEXT, nullable=False, unique=True),  # 'sales', 'crm', 'analytics'
            Column("display_name", ColumnType.TEXT, nullable=False),
            Column("description", ColumnType.TEXT),
            Column("icon", ColumnType.TEXT),
            Column("is_active", ColumnType.INTEGER, nullable=False, default=1),
            Column("is_default", ColumnType.INTEGER, nullable=False, default=0),
            Column("sort_order", ColumnType.INTEGER, nullable=False, default=0),
            Column("required_permission", ColumnType.TEXT),  # e.g., 'sales:*:read'
            Column("config_json", ColumnType.TEXT),
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
            Column("user_id", ColumnType.TEXT, nullable=False),
            Column("module_id", ColumnType.INTEGER, nullable=False),
            Column("is_default", ColumnType.INTEGER, nullable=False, default=0),
            Column("granted_by", ColumnType.TEXT),
            Column("granted_at", ColumnType.TEXT, nullable=False),
        ],
        indexes=[
            Index("idx_user_modules_user", ["user_id"]),
            Index("idx_user_modules_module", ["module_id"]),
        ],
        unique_constraints=[["user_id", "module_id"]],
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
            Column("role_id", ColumnType.INTEGER, nullable=False),
            Column("created_by", ColumnType.TEXT, nullable=False),
            Column("created_at", ColumnType.TEXT, nullable=False),
            Column("expires_at", ColumnType.TEXT, nullable=False),
            Column("used_at", ColumnType.TEXT),
            Column("used_by_user_id", ColumnType.TEXT),
            Column("is_revoked", ColumnType.INTEGER, nullable=False, default=0),
        ],
        indexes=[
            Index("idx_invite_tokens_token", ["token"]),
            Index("idx_invite_tokens_email", ["email"]),
            Index("idx_invite_tokens_expires", ["expires_at"]),
        ],
    ),

    # -------------------------------------------------------------------------
    # AUDIT_LOG - Track important actions for security
    # -------------------------------------------------------------------------
    "audit_log": Table(
        name="audit_log",
        columns=[
            Column("id", ColumnType.INTEGER, primary_key=True),
            Column("timestamp", ColumnType.TEXT, nullable=False),
            Column("user_id", ColumnType.TEXT),
            Column("action", ColumnType.TEXT, nullable=False),
            Column("resource_type", ColumnType.TEXT),
            Column("resource_id", ColumnType.TEXT),
            Column("details_json", ColumnType.TEXT),
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

    # -------------------------------------------------------------------------
    # API_KEYS - For programmatic API access
    # -------------------------------------------------------------------------
    "api_keys": Table(
        name="api_keys",
        columns=[
            Column("id", ColumnType.INTEGER, primary_key=True),
            Column("key_hash", ColumnType.TEXT, nullable=False, unique=True),
            Column("key_prefix", ColumnType.TEXT, nullable=False),
            Column("name", ColumnType.TEXT, nullable=False),
            Column("description", ColumnType.TEXT),
            Column("scopes_json", ColumnType.TEXT, nullable=False),
            Column("rate_limit", ColumnType.INTEGER),
            Column("is_active", ColumnType.INTEGER, nullable=False, default=1),
            Column("created_at", ColumnType.TEXT, nullable=False),
            Column("created_by", ColumnType.TEXT),
            Column("expires_at", ColumnType.TEXT),
            Column("last_used_at", ColumnType.TEXT),
            Column("last_rotated_at", ColumnType.TEXT),
            Column("metadata_json", ColumnType.TEXT),
        ],
        indexes=[
            Index("idx_api_keys_hash", ["key_hash"]),
            Index("idx_api_keys_name", ["name"]),
            Index("idx_api_keys_active", ["is_active"]),
            Index("idx_api_keys_created_by", ["created_by"]),
        ],
    ),

    # -------------------------------------------------------------------------
    # API_KEY_USAGE - Audit trail for API key usage
    # -------------------------------------------------------------------------
    "api_key_usage": Table(
        name="api_key_usage",
        columns=[
            Column("id", ColumnType.INTEGER, primary_key=True),
            Column("api_key_id", ColumnType.INTEGER, nullable=False),
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
}


# =============================================================================
# SALES MODULE TABLES - For Sales Bot Supabase (business data)
# =============================================================================

SALES_TABLES: Dict[str, Table] = {
    # -------------------------------------------------------------------------
    # PROPOSALS_LOG
    # -------------------------------------------------------------------------
    "proposals_log": Table(
        name="proposals_log",
        columns=[
            Column("id", ColumnType.INTEGER, primary_key=True),
            Column("user_id", ColumnType.TEXT),
            Column("submitted_by", ColumnType.TEXT, nullable=False),
            Column("client_name", ColumnType.TEXT, nullable=False),
            Column("date_generated", ColumnType.TEXT, nullable=False),
            Column("package_type", ColumnType.TEXT, nullable=False),
            Column("locations", ColumnType.TEXT, nullable=False),
            Column("total_amount", ColumnType.TEXT, nullable=False),
            Column("proposal_data", ColumnType.TEXT),  # JSON
            Column("created_at", ColumnType.TEXT),
        ],
        indexes=[
            Index("idx_proposals_user", ["user_id"]),
            Index("idx_proposals_client", ["client_name"]),
            Index("idx_proposals_date", ["date_generated"]),
        ],
    ),

    # -------------------------------------------------------------------------
    # MOCKUP_FRAMES
    # -------------------------------------------------------------------------
    "mockup_frames": Table(
        name="mockup_frames",
        columns=[
            Column("id", ColumnType.INTEGER, primary_key=True),
            Column("user_id", ColumnType.TEXT),
            Column("location_key", ColumnType.TEXT, nullable=False),
            Column("time_of_day", ColumnType.TEXT, nullable=False, default="day"),
            Column("finish", ColumnType.TEXT, nullable=False, default="gold"),
            Column("photo_filename", ColumnType.TEXT, nullable=False),
            Column("frames_data", ColumnType.TEXT, nullable=False),
            Column("created_at", ColumnType.TEXT, nullable=False),
            Column("created_by", ColumnType.TEXT),
            Column("config_json", ColumnType.TEXT),
        ],
        indexes=[
            Index("idx_mockup_frames_user", ["user_id"]),
            Index("idx_mockup_frames_location", ["location_key"]),
        ],
        unique_constraints=[["location_key", "time_of_day", "finish", "photo_filename"]],
    ),

    # -------------------------------------------------------------------------
    # MOCKUP_USAGE
    # -------------------------------------------------------------------------
    "mockup_usage": Table(
        name="mockup_usage",
        columns=[
            Column("id", ColumnType.INTEGER, primary_key=True),
            Column("user_id", ColumnType.TEXT),
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
            Column("metadata_json", ColumnType.TEXT),
        ],
        indexes=[
            Index("idx_mockup_usage_user", ["user_id"]),
            Index("idx_mockup_usage_date", ["generated_at"]),
            Index("idx_mockup_usage_location", ["location_key"]),
        ],
    ),

    # -------------------------------------------------------------------------
    # BOOKING_ORDERS
    # -------------------------------------------------------------------------
    "booking_orders": Table(
        name="booking_orders",
        columns=[
            Column("id", ColumnType.INTEGER, primary_key=True),
            Column("user_id", ColumnType.TEXT),
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
            Index("idx_booking_orders_sales_person", ["sales_person"]),
        ],
    ),

    # -------------------------------------------------------------------------
    # BO_APPROVAL_WORKFLOWS
    # -------------------------------------------------------------------------
    "bo_approval_workflows": Table(
        name="bo_approval_workflows",
        columns=[
            Column("workflow_id", ColumnType.TEXT, primary_key=True),
            Column("workflow_data", ColumnType.TEXT, nullable=False),
            Column("status", ColumnType.TEXT, nullable=False, default="pending",
                   check="status IN ('pending', 'approved', 'rejected', 'cancelled')"),
            Column("created_at", ColumnType.TEXT, nullable=False),
            Column("updated_at", ColumnType.TEXT, nullable=False),
        ],
        indexes=[
            Index("idx_bo_workflows_status", ["status"]),
            Index("idx_bo_workflows_updated", ["updated_at"]),
        ],
    ),

    # -------------------------------------------------------------------------
    # AI_COSTS
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
            Index("idx_ai_costs_model", ["model"]),
        ],
    ),
}


# =============================================================================
# COMBINED TABLES (for backwards compatibility with existing code)
# =============================================================================

TABLES: Dict[str, Table] = {**CORE_TABLES, **SALES_TABLES}


# =============================================================================
# SQL GENERATORS
# =============================================================================

class SQLGenerator:
    """Base class for SQL generation."""

    def generate_create_table(self, table: Table) -> str:
        raise NotImplementedError

    def generate_create_index(self, table_name: str, index: Index) -> str:
        raise NotImplementedError

    def generate_schema(self, tables: Dict[str, Table]) -> str:
        """Generate schema SQL for given tables."""
        statements = []
        for table in tables.values():
            statements.append(self.generate_create_table(table))
            for index in table.indexes:
                statements.append(self.generate_create_index(table.name, index))
        return "\n\n".join(statements)

    def generate_full_schema(self) -> str:
        """Generate complete schema SQL (all tables)."""
        return self.generate_schema(TABLES)

    def generate_core_schema(self) -> str:
        """Generate schema SQL for core/auth tables only."""
        return self.generate_schema(CORE_TABLES)

    def generate_sales_schema(self) -> str:
        """Generate schema SQL for sales tables only."""
        return self.generate_schema(SALES_TABLES)


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


def get_core_sqlite_schema() -> str:
    """Get SQLite schema for core/auth tables only."""
    return SQLiteGenerator().generate_core_schema()


def get_core_postgres_schema() -> str:
    """Get PostgreSQL schema for core/auth tables only."""
    return PostgresGenerator().generate_core_schema()


def get_sales_sqlite_schema() -> str:
    """Get SQLite schema for sales tables only."""
    return SQLiteGenerator().generate_sales_schema()


def get_sales_postgres_schema() -> str:
    """Get PostgreSQL schema for sales tables only."""
    return PostgresGenerator().generate_sales_schema()


def get_table_names() -> List[str]:
    """Get list of all table names."""
    return list(TABLES.keys())


def get_core_table_names() -> List[str]:
    """Get list of core/auth table names."""
    return list(CORE_TABLES.keys())


def get_sales_table_names() -> List[str]:
    """Get list of sales table names."""
    return list(SALES_TABLES.keys())


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
        "--tables", "-t",
        choices=["all", "core", "sales"],
        default="all",
        help="Which tables to generate (all, core/auth only, or sales only)"
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file (default: stdout)"
    )

    args = parser.parse_args()

    output_lines = []

    # Determine which generator methods to use
    if args.tables == "core":
        sqlite_fn = get_core_sqlite_schema
        postgres_fn = get_core_postgres_schema
        label = "Core/Auth"
    elif args.tables == "sales":
        sqlite_fn = get_sales_sqlite_schema
        postgres_fn = get_sales_postgres_schema
        label = "Sales"
    else:
        sqlite_fn = get_sqlite_schema
        postgres_fn = get_postgres_schema
        label = "All"

    if args.generate in ("sqlite", "both"):
        output_lines.append(f"-- ===========================================")
        output_lines.append(f"-- SQLite Schema ({label} Tables)")
        output_lines.append(f"-- ===========================================")
        output_lines.append("")
        output_lines.append(sqlite_fn())
        output_lines.append("")

    if args.generate in ("postgres", "both"):
        output_lines.append(f"-- ===========================================")
        output_lines.append(f"-- PostgreSQL/Supabase Schema ({label} Tables)")
        output_lines.append(f"-- ===========================================")
        output_lines.append("")
        output_lines.append(postgres_fn())
        output_lines.append("")

    output = "\n".join(output_lines)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        print(f"Schema written to {args.output}")
    else:
        print(output)
