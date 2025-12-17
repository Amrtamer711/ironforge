"""
Trusted Header Contract - sales-module (Consumer)

This module defines the header contract for authenticated proxy requests.
sales-module CONSUMES these headers from upstream proxy services.

Header Names:
    X-Proxy-Secret: Shared secret proving request origin
    X-Trusted-User-*: User identity and RBAC context

Usage:
    from contracts.trusted_headers import TRUSTED_HEADERS, parse_user_context

Version: 1.0.0
"""

import json
from typing import TypedDict


class TrustedUserContext(TypedDict, total=False):
    """Type definition for trusted user context received via headers."""

    # Level 1: User Identity
    id: str
    email: str
    name: str
    profile: str

    # Level 2: Permissions
    permissions: list[str]
    permission_sets: list[str]

    # Level 3: Teams & Hierarchy
    teams: list[dict]
    team_ids: list[int]
    manager_id: str | None
    subordinate_ids: list[str]

    # Level 4: Sharing
    sharing_rules: list[dict]
    shared_records: dict[str, list[str]]
    shared_from_user_ids: list[str]

    # Level 5: Companies
    companies: list[str]


# =============================================================================
# HEADER NAME CONSTANTS
# =============================================================================
# These MUST match the producer service's header names exactly.
# Any changes here require coordination with upstream proxy services.
# =============================================================================

HEADER_PROXY_SECRET = "X-Proxy-Secret"

# Level 1: User Identity
HEADER_USER_ID = "X-Trusted-User-Id"
HEADER_USER_EMAIL = "X-Trusted-User-Email"
HEADER_USER_NAME = "X-Trusted-User-Name"
HEADER_USER_PROFILE = "X-Trusted-User-Profile"

# Level 2: Permissions
HEADER_USER_PERMISSIONS = "X-Trusted-User-Permissions"
HEADER_USER_PERMISSION_SETS = "X-Trusted-User-Permission-Sets"

# Level 3: Teams & Hierarchy
HEADER_USER_TEAMS = "X-Trusted-User-Teams"
HEADER_USER_TEAM_IDS = "X-Trusted-User-Team-Ids"
HEADER_USER_MANAGER_ID = "X-Trusted-User-Manager-Id"
HEADER_USER_SUBORDINATE_IDS = "X-Trusted-User-Subordinate-Ids"

# Level 4: Sharing
HEADER_USER_SHARING_RULES = "X-Trusted-User-Sharing-Rules"
HEADER_USER_SHARED_RECORDS = "X-Trusted-User-Shared-Records"
HEADER_USER_SHARED_FROM_USER_IDS = "X-Trusted-User-Shared-From-User-Ids"

# Level 5: Companies
HEADER_USER_COMPANIES = "X-Trusted-User-Companies"

# All header names for reference
TRUSTED_HEADERS = {
    "proxy_secret": HEADER_PROXY_SECRET,
    "user_id": HEADER_USER_ID,
    "user_email": HEADER_USER_EMAIL,
    "user_name": HEADER_USER_NAME,
    "user_profile": HEADER_USER_PROFILE,
    "user_permissions": HEADER_USER_PERMISSIONS,
    "user_permission_sets": HEADER_USER_PERMISSION_SETS,
    "user_teams": HEADER_USER_TEAMS,
    "user_team_ids": HEADER_USER_TEAM_IDS,
    "user_manager_id": HEADER_USER_MANAGER_ID,
    "user_subordinate_ids": HEADER_USER_SUBORDINATE_IDS,
    "user_sharing_rules": HEADER_USER_SHARING_RULES,
    "user_shared_records": HEADER_USER_SHARED_RECORDS,
    "user_shared_from_user_ids": HEADER_USER_SHARED_FROM_USER_IDS,
    "user_companies": HEADER_USER_COMPANIES,
}


# Lowercase versions for header lookup (HTTP headers are case-insensitive)
HEADER_LOOKUP = {k.lower(): k for k in TRUSTED_HEADERS.values()}


def _safe_json_parse(value: str | None, default):
    """Safely parse JSON string, returning default on failure."""
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def parse_user_context(headers: dict[str, str]) -> TrustedUserContext | None:
    """
    Parse trusted user context from request headers.

    Args:
        headers: Request headers dictionary (case-insensitive keys)

    Returns:
        TrustedUserContext if user headers present, None otherwise
    """
    # Normalize header keys to lowercase for lookup
    normalized = {k.lower(): v for k, v in headers.items()}

    user_id = normalized.get(HEADER_USER_ID.lower())
    if not user_id:
        return None

    return TrustedUserContext(
        # Level 1
        id=user_id,
        email=normalized.get(HEADER_USER_EMAIL.lower(), ""),
        name=normalized.get(HEADER_USER_NAME.lower(), ""),
        profile=normalized.get(HEADER_USER_PROFILE.lower(), ""),
        # Level 2
        permissions=_safe_json_parse(
            normalized.get(HEADER_USER_PERMISSIONS.lower()), []
        ),
        permission_sets=_safe_json_parse(
            normalized.get(HEADER_USER_PERMISSION_SETS.lower()), []
        ),
        # Level 3
        teams=_safe_json_parse(normalized.get(HEADER_USER_TEAMS.lower()), []),
        team_ids=_safe_json_parse(normalized.get(HEADER_USER_TEAM_IDS.lower()), []),
        manager_id=normalized.get(HEADER_USER_MANAGER_ID.lower()),
        subordinate_ids=_safe_json_parse(
            normalized.get(HEADER_USER_SUBORDINATE_IDS.lower()), []
        ),
        # Level 4
        sharing_rules=_safe_json_parse(
            normalized.get(HEADER_USER_SHARING_RULES.lower()), []
        ),
        shared_records=_safe_json_parse(
            normalized.get(HEADER_USER_SHARED_RECORDS.lower()), {}
        ),
        shared_from_user_ids=_safe_json_parse(
            normalized.get(HEADER_USER_SHARED_FROM_USER_IDS.lower()), []
        ),
        # Level 5
        companies=_safe_json_parse(
            normalized.get(HEADER_USER_COMPANIES.lower()), []
        ),
    )
