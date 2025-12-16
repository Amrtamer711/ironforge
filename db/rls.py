"""
Row Level Security (RLS) Policy Generator for Supabase.

Generates PostgreSQL RLS policies based on the unified schema.
These policies enforce data isolation and access control at the database level.

Usage:
    # Generate RLS SQL for all tables
    python -m db.rls --generate

    # Generate for specific tables
    python -m db.rls --generate --tables proposals_log,booking_orders

    # Output to file
    python -m db.rls --generate --output rls_policies.sql

Apply the generated SQL in the Supabase dashboard SQL editor.
"""

import argparse
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class PolicyType(str, Enum):
    """RLS policy types."""
    SELECT = "SELECT"
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    ALL = "ALL"


@dataclass
class RLSPolicy:
    """Definition of an RLS policy."""
    name: str
    table: str
    policy_type: PolicyType
    role: str = "authenticated"  # PostgreSQL role
    using_clause: Optional[str] = None  # For SELECT, UPDATE, DELETE
    check_clause: Optional[str] = None  # For INSERT, UPDATE
    comment: Optional[str] = None


# =============================================================================
# TABLES WITH USER_ID COLUMN (require user-based RLS)
# =============================================================================

# Tables that have a user_id column for ownership
TABLES_WITH_USER_ID = {
    "proposals_log",
    "mockup_frames",
    "mockup_usage",
    "booking_orders",
    "audit_log",
}

# Tables that are auth/RBAC system tables
AUTH_TABLES = {
    "users",
    "roles",
    "user_roles",
    "permissions",
    "role_permissions",
}

# Tables without user_id (shared/system data)
SHARED_TABLES = {
    "bo_workflows",
    "ai_costs",
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_auth_uid() -> str:
    """Get the Supabase auth.uid() expression."""
    return "auth.uid()::text"


def get_admin_check() -> str:
    """
    SQL expression to check if user has admin role.

    Uses the user_roles and roles tables from the unified schema.
    """
    return """
        EXISTS (
            SELECT 1 FROM user_roles ur
            JOIN roles r ON r.id = ur.role_id
            WHERE ur.user_id = auth.uid()::text
            AND r.name = 'admin'
            AND (ur.expires_at IS NULL OR ur.expires_at > NOW())
        )
    """.strip()


def get_role_check(role_names: list[str]) -> str:
    """
    SQL expression to check if user has any of the specified roles.

    Args:
        role_names: List of role names to check
    """
    roles_list = ", ".join(f"'{r}'" for r in role_names)
    return f"""
        EXISTS (
            SELECT 1 FROM user_roles ur
            JOIN roles r ON r.id = ur.role_id
            WHERE ur.user_id = auth.uid()::text
            AND r.name IN ({roles_list})
            AND (ur.expires_at IS NULL OR ur.expires_at > NOW())
        )
    """.strip()


# =============================================================================
# POLICY DEFINITIONS
# =============================================================================

def generate_user_owned_policies(table: str) -> list[RLSPolicy]:
    """
    Generate standard policies for user-owned tables.

    - Users can SELECT their own records
    - Users can INSERT records with their own user_id
    - Users can UPDATE their own records
    - Admins/HOS can SELECT all records
    """
    policies = []

    # Users can see their own records
    policies.append(RLSPolicy(
        name=f"{table}_select_own",
        table=table,
        policy_type=PolicyType.SELECT,
        using_clause=f"user_id = {get_auth_uid()}",
        comment=f"Users can view their own {table.replace('_', ' ')}",
    ))

    # Users can insert records with their own user_id
    policies.append(RLSPolicy(
        name=f"{table}_insert_own",
        table=table,
        policy_type=PolicyType.INSERT,
        check_clause=f"user_id = {get_auth_uid()}",
        comment=f"Users can create {table.replace('_', ' ')} with their own user_id",
    ))

    # Users can update their own records
    policies.append(RLSPolicy(
        name=f"{table}_update_own",
        table=table,
        policy_type=PolicyType.UPDATE,
        using_clause=f"user_id = {get_auth_uid()}",
        check_clause=f"user_id = {get_auth_uid()}",
        comment=f"Users can update their own {table.replace('_', ' ')}",
    ))

    # Admins and HOS can see all records
    policies.append(RLSPolicy(
        name=f"{table}_admin_hos_select",
        table=table,
        policy_type=PolicyType.SELECT,
        using_clause=get_role_check(["admin", "hos"]),
        comment=f"Admins and HOS can view all {table.replace('_', ' ')}",
    ))

    # Admins can do everything
    policies.append(RLSPolicy(
        name=f"{table}_admin_all",
        table=table,
        policy_type=PolicyType.ALL,
        using_clause=get_admin_check(),
        check_clause=f"({get_admin_check()})",
        comment=f"Admins have full access to {table.replace('_', ' ')}",
    ))

    return policies


def generate_auth_table_policies() -> list[RLSPolicy]:
    """Generate policies for auth/RBAC tables."""
    policies = []

    # Users table - users can see their own record, admins can see all
    policies.append(RLSPolicy(
        name="users_select_own",
        table="users",
        policy_type=PolicyType.SELECT,
        using_clause=f"id = {get_auth_uid()}",
        comment="Users can view their own profile",
    ))

    policies.append(RLSPolicy(
        name="users_select_admin",
        table="users",
        policy_type=PolicyType.SELECT,
        using_clause=get_admin_check(),
        comment="Admins can view all users",
    ))

    policies.append(RLSPolicy(
        name="users_update_own",
        table="users",
        policy_type=PolicyType.UPDATE,
        using_clause=f"id = {get_auth_uid()}",
        check_clause=f"id = {get_auth_uid()}",
        comment="Users can update their own profile",
    ))

    policies.append(RLSPolicy(
        name="users_admin_all",
        table="users",
        policy_type=PolicyType.ALL,
        using_clause=get_admin_check(),
        check_clause=f"({get_admin_check()})",
        comment="Admins have full access to users",
    ))

    # Roles table - everyone can read, only admins can modify
    policies.append(RLSPolicy(
        name="roles_select_all",
        table="roles",
        policy_type=PolicyType.SELECT,
        using_clause="true",  # Everyone can see available roles
        comment="All authenticated users can see roles",
    ))

    policies.append(RLSPolicy(
        name="roles_admin_modify",
        table="roles",
        policy_type=PolicyType.ALL,
        using_clause=get_admin_check(),
        check_clause=f"({get_admin_check()})",
        comment="Only admins can modify roles",
    ))

    # User roles - users can see their own, admins can see/modify all
    policies.append(RLSPolicy(
        name="user_roles_select_own",
        table="user_roles",
        policy_type=PolicyType.SELECT,
        using_clause=f"user_id = {get_auth_uid()}",
        comment="Users can see their own role assignments",
    ))

    policies.append(RLSPolicy(
        name="user_roles_admin_all",
        table="user_roles",
        policy_type=PolicyType.ALL,
        using_clause=get_admin_check(),
        check_clause=f"({get_admin_check()})",
        comment="Admins have full access to user role assignments",
    ))

    # Permissions - everyone can read
    policies.append(RLSPolicy(
        name="permissions_select_all",
        table="permissions",
        policy_type=PolicyType.SELECT,
        using_clause="true",
        comment="All authenticated users can see permissions",
    ))

    policies.append(RLSPolicy(
        name="permissions_admin_modify",
        table="permissions",
        policy_type=PolicyType.ALL,
        using_clause=get_admin_check(),
        check_clause=f"({get_admin_check()})",
        comment="Only admins can modify permissions",
    ))

    # Role permissions - everyone can read
    policies.append(RLSPolicy(
        name="role_permissions_select_all",
        table="role_permissions",
        policy_type=PolicyType.SELECT,
        using_clause="true",
        comment="All authenticated users can see role permissions",
    ))

    policies.append(RLSPolicy(
        name="role_permissions_admin_modify",
        table="role_permissions",
        policy_type=PolicyType.ALL,
        using_clause=get_admin_check(),
        check_clause=f"({get_admin_check()})",
        comment="Only admins can modify role permissions",
    ))

    return policies


def generate_shared_table_policies() -> list[RLSPolicy]:
    """Generate policies for shared/system tables."""
    policies = []

    # AI costs - readable by admin/hos/finance, only system can insert
    policies.append(RLSPolicy(
        name="ai_costs_select_authorized",
        table="ai_costs",
        policy_type=PolicyType.SELECT,
        using_clause=get_role_check(["admin", "hos", "finance"]),
        comment="Admins, HOS, and Finance can view AI costs",
    ))

    policies.append(RLSPolicy(
        name="ai_costs_insert_service",
        table="ai_costs",
        policy_type=PolicyType.INSERT,
        check_clause="true",  # Service role can insert
        comment="Service role can insert AI cost records",
    ))

    policies.append(RLSPolicy(
        name="ai_costs_admin_all",
        table="ai_costs",
        policy_type=PolicyType.ALL,
        using_clause=get_admin_check(),
        check_clause=f"({get_admin_check()})",
        comment="Admins have full access to AI costs",
    ))

    # BO Workflows - readable by all, modifiable by assigned users/admins
    policies.append(RLSPolicy(
        name="bo_workflows_select_all",
        table="bo_workflows",
        policy_type=PolicyType.SELECT,
        using_clause="true",
        comment="All authenticated users can view BO workflows",
    ))

    policies.append(RLSPolicy(
        name="bo_workflows_modify_authorized",
        table="bo_workflows",
        policy_type=PolicyType.ALL,
        using_clause=get_role_check(["admin", "hos", "coordinator"]),
        check_clause=f"({get_role_check(['admin', 'hos', 'coordinator'])})",
        comment="Admins, HOS, and Coordinators can modify workflows",
    ))

    return policies


# =============================================================================
# SQL GENERATION
# =============================================================================

def generate_enable_rls_sql(tables: list[str]) -> str:
    """Generate SQL to enable RLS on tables."""
    lines = ["-- Enable Row Level Security on tables"]
    for table in tables:
        lines.append(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
    lines.append("")
    return "\n".join(lines)


def generate_policy_sql(policy: RLSPolicy) -> str:
    """Generate SQL for a single RLS policy."""
    lines = []

    # Add comment
    if policy.comment:
        lines.append(f"-- {policy.comment}")

    # Drop existing policy if exists
    lines.append(f"DROP POLICY IF EXISTS \"{policy.name}\" ON {policy.table};")

    # Build CREATE POLICY statement
    sql = f"CREATE POLICY \"{policy.name}\" ON {policy.table}"
    sql += f"\n    FOR {policy.policy_type.value}"
    sql += f"\n    TO {policy.role}"

    if policy.using_clause:
        sql += f"\n    USING ({policy.using_clause})"

    if policy.check_clause:
        sql += f"\n    WITH CHECK {policy.check_clause}"

    sql += ";"
    lines.append(sql)
    lines.append("")

    return "\n".join(lines)


def generate_all_policies_sql(tables: Optional[set[str]] = None) -> str:
    """
    Generate complete RLS policy SQL for all or specified tables.

    Args:
        tables: Optional set of table names to generate for.
                If None, generates for all tables.
    """
    all_tables = TABLES_WITH_USER_ID | AUTH_TABLES | SHARED_TABLES

    if tables:
        all_tables = all_tables & tables

    output = []
    output.append("-- =============================================================================")
    output.append("-- Row Level Security (RLS) Policies for Sales Proposals Platform")
    output.append("-- Generated by db/rls.py")
    output.append("-- =============================================================================")
    output.append("")
    output.append("-- NOTE: Run this SQL in your Supabase SQL Editor")
    output.append("-- These policies enforce data isolation at the database level.")
    output.append("")

    # Enable RLS
    output.append(generate_enable_rls_sql(sorted(all_tables)))

    # User-owned tables
    user_tables = sorted(TABLES_WITH_USER_ID & all_tables)
    if user_tables:
        output.append("-- =============================================================================")
        output.append("-- USER-OWNED TABLES (with user_id column)")
        output.append("-- =============================================================================")
        output.append("")

        for table in user_tables:
            output.append(f"-- ---- {table.upper()} ----")
            for policy in generate_user_owned_policies(table):
                output.append(generate_policy_sql(policy))

    # Auth tables
    auth_tables = sorted(AUTH_TABLES & all_tables)
    if auth_tables:
        output.append("-- =============================================================================")
        output.append("-- AUTHENTICATION & RBAC TABLES")
        output.append("-- =============================================================================")
        output.append("")

        for policy in generate_auth_table_policies():
            if policy.table in auth_tables:
                output.append(generate_policy_sql(policy))

    # Shared tables
    shared_tables = sorted(SHARED_TABLES & all_tables)
    if shared_tables:
        output.append("-- =============================================================================")
        output.append("-- SHARED/SYSTEM TABLES")
        output.append("-- =============================================================================")
        output.append("")

        for policy in generate_shared_table_policies():
            if policy.table in shared_tables:
                output.append(generate_policy_sql(policy))

    return "\n".join(output)


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Generate RLS policies for Supabase",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m db.rls --generate                    # Generate all policies
  python -m db.rls --generate --output rls.sql   # Output to file
  python -m db.rls --generate --tables proposals_log,booking_orders
        """
    )

    parser.add_argument(
        "--generate",
        action="store_true",
        help="Generate RLS policy SQL",
    )
    parser.add_argument(
        "--tables",
        type=str,
        help="Comma-separated list of tables to generate policies for",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        help="Output file path (default: stdout)",
    )
    parser.add_argument(
        "--list-tables",
        action="store_true",
        help="List all tables that need RLS",
    )

    args = parser.parse_args()

    if args.list_tables:
        print("Tables with user_id (user-owned):")
        for t in sorted(TABLES_WITH_USER_ID):
            print(f"  - {t}")
        print("\nAuth/RBAC tables:")
        for t in sorted(AUTH_TABLES):
            print(f"  - {t}")
        print("\nShared tables:")
        for t in sorted(SHARED_TABLES):
            print(f"  - {t}")
        return

    if args.generate:
        tables = None
        if args.tables:
            tables = set(args.tables.split(","))

        sql = generate_all_policies_sql(tables)

        if args.output:
            with open(args.output, "w") as f:
                f.write(sql)
            print(f"RLS policies written to {args.output}")
        else:
            print(sql)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
