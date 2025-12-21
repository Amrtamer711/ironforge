"""
Security Context - Thread-local storage for user context.

Provides a way to store and access user context anywhere in the code
without passing it through function arguments.

Usage:
    from security import get_user_context, set_user_context, clear_user_context

    # In middleware
    set_user_context(user_id="123", profile="admin", permissions=["*:*:*"])

    # Anywhere in code
    ctx = get_user_context()
    if ctx:
        print(f"Current user: {ctx['user_id']}")

    # At end of request
    clear_user_context()
"""

import json
import logging
from contextvars import ContextVar
from typing import Any

from .config import security_config

logger = logging.getLogger(__name__)

# Context variable for storing current user info
_user_context: ContextVar[dict[str, Any] | None] = ContextVar("user_context", default=None)


def set_user_context(
    user_id: str,
    profile: str = "",
    permissions: list[str] | None = None,
    permission_sets: list[str] | None = None,
    teams: list[dict] | None = None,
    team_ids: list[int] | None = None,
    manager_id: str | None = None,
    subordinate_ids: list[str] | None = None,
    sharing_rules: list[dict] | None = None,
    shared_records: dict[str, list[str]] | None = None,
    shared_from_user_ids: list[str] | None = None,
    companies: list[str] | None = None,
    email: str = "",
    name: str = "",
    **extra: Any,
) -> None:
    """
    Set the current user context for this request.

    Call this from middleware after validating the user.
    The context is automatically cleared at the end of the request.

    Args:
        user_id: User's unique identifier
        profile: User's RBAC profile name (e.g., "system_admin", "sales_rep")
        permissions: Combined list of permission strings
        permission_sets: List of active permission set names
        teams: List of team objects user belongs to
        team_ids: List of team IDs
        manager_id: User's manager's ID
        subordinate_ids: IDs of user's direct reports
        sharing_rules: Active sharing rules for the user
        shared_records: Records shared with this user {record_type: [record_ids]}
        shared_from_user_ids: User IDs who have shared records with this user
        companies: Company schemas the user can access
        email: User's email address
        name: User's display name
        **extra: Additional context data
    """
    context = {
        # Level 1: Identity
        "user_id": user_id,
        "email": email,
        "name": name,
        "profile": profile,
        # Level 2: Permissions
        "permissions": permissions or [],
        "permission_sets": permission_sets or [],
        # Level 3: Teams & Hierarchy
        "teams": teams or [],
        "team_ids": team_ids or [],
        "manager_id": manager_id,
        "subordinate_ids": subordinate_ids or [],
        # Level 4: Sharing
        "sharing_rules": sharing_rules or [],
        "shared_records": shared_records or {},
        "shared_from_user_ids": shared_from_user_ids or [],
        # Level 5: Companies
        "companies": companies or [],
        # Extra data
        **extra,
    }
    _user_context.set(context)


def get_user_context() -> dict[str, Any] | None:
    """
    Get the current user context.

    Returns None if no user context is set (unauthenticated request).

    Returns:
        Dict with user context or None
    """
    return _user_context.get()


def clear_user_context() -> None:
    """
    Clear the current user context.

    Call this at the end of each request to prevent context leakage.
    """
    _user_context.set(None)


def get_current_user_id() -> str | None:
    """Get the current user's ID, or None if not authenticated."""
    ctx = get_user_context()
    return ctx.get("user_id") if ctx else None


def get_current_user_permissions() -> list[str]:
    """Get the current user's permissions, or empty list if not authenticated."""
    ctx = get_user_context()
    return ctx.get("permissions", []) if ctx else []


def get_current_user_companies() -> list[str]:
    """Get the current user's accessible companies, or empty list if not authenticated."""
    ctx = get_user_context()
    return ctx.get("companies", []) if ctx else []


def get_current_user_profile() -> str | None:
    """Get the current user's profile name, or None if not authenticated."""
    ctx = get_user_context()
    return ctx.get("profile") if ctx else None


def is_authenticated() -> bool:
    """Check if there is an authenticated user in the current context."""
    return get_user_context() is not None


def set_dev_auth_context() -> None:
    """
    Set user context from dev auth configuration.

    Used when dev auth is enabled and a valid dev token is provided.
    """
    try:
        permissions = json.loads(security_config.dev_auth_user_permissions)
    except json.JSONDecodeError:
        permissions = ["*:*:*"]

    try:
        companies = json.loads(security_config.dev_auth_user_companies)
    except json.JSONDecodeError:
        companies = ["backlite_dubai"]

    set_user_context(
        user_id=security_config.dev_auth_user_id,
        email=security_config.dev_auth_user_email,
        name=security_config.dev_auth_user_name,
        profile=security_config.dev_auth_user_profile,
        permissions=permissions,
        companies=companies,
        # Simplified RBAC context for dev auth
        permission_sets=[],
        teams=[],
        team_ids=[],
        manager_id=None,
        subordinate_ids=[],
        sharing_rules=[],
        shared_records={},
        shared_from_user_ids=[],
    )
    logger.info(f"[DEV-AUTH] Set context for dev user: {security_config.dev_auth_user_email}")
