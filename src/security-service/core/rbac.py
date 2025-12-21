"""
RBAC (Role-Based Access Control) Service.

Handles permission checking and access control logic.
"""

import logging
from typing import Any

from db import db
from models.rbac import (
    matches_wildcard,
    has_permission,
    has_any_permission,
    has_all_permissions,
)

logger = logging.getLogger("security-service")


class RBACService:
    """
    RBAC service for permission checking and access control.

    Implements the 5-level RBAC model:
    1. Profiles (base permissions)
    2. Permission Sets (additional permissions)
    3. Teams & Hierarchy (manager/subordinate)
    4. Sharing Rules (record-level access)
    5. Companies (multi-tenant isolation)
    """

    # =========================================================================
    # PERMISSION CHECKING
    # =========================================================================

    def check_permission(
        self,
        user_id: str,
        permission: str,
    ) -> dict[str, Any]:
        """
        Check if a user has a specific permission.

        Args:
            user_id: User ID
            permission: Permission string (e.g., "sales:proposals:create")

        Returns:
            {
                "allowed": bool,
                "matched_by": Permission that granted access (if allowed)
            }
        """
        permissions = db.get_user_permissions(user_id)

        if not permissions:
            logger.debug(f"[RBAC] User {user_id} has no permissions")
            return {"allowed": False}

        # Check for matching permission
        for perm in permissions:
            if matches_wildcard(perm, permission):
                logger.debug(f"[RBAC] User {user_id} granted {permission} via {perm}")
                return {"allowed": True, "matched_by": perm}

        logger.debug(f"[RBAC] User {user_id} denied {permission}")
        return {"allowed": False}

    def check_any_permission(
        self,
        user_id: str,
        permissions_required: list[str],
    ) -> dict[str, Any]:
        """
        Check if a user has any of the specified permissions.

        Args:
            user_id: User ID
            permissions_required: List of permissions (any one grants access)

        Returns:
            {
                "allowed": bool,
                "matched_by": Permission that granted access (if allowed)
            }
        """
        user_permissions = db.get_user_permissions(user_id)

        if not user_permissions:
            return {"allowed": False}

        for required in permissions_required:
            for perm in user_permissions:
                if matches_wildcard(perm, required):
                    return {"allowed": True, "matched_by": perm}

        return {"allowed": False}

    def check_all_permissions(
        self,
        user_id: str,
        permissions_required: list[str],
    ) -> dict[str, Any]:
        """
        Check if a user has all of the specified permissions.

        Args:
            user_id: User ID
            permissions_required: List of permissions (all required)

        Returns:
            {
                "allowed": bool,
                "missing": List of missing permissions (if denied)
            }
        """
        user_permissions = db.get_user_permissions(user_id)

        if not user_permissions:
            return {"allowed": False, "missing": permissions_required}

        missing = []
        for required in permissions_required:
            found = any(matches_wildcard(p, required) for p in user_permissions)
            if not found:
                missing.append(required)

        if missing:
            return {"allowed": False, "missing": missing}

        return {"allowed": True}

    # =========================================================================
    # RECORD-LEVEL ACCESS
    # =========================================================================

    def check_record_access(
        self,
        user_id: str,
        object_type: str,
        record_id: str,
        record_owner_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Check if a user can access a specific record.

        Uses the 5-level RBAC model:
        1. Admin access (system_admin profile)
        2. Own record (user is the owner)
        3. Subordinate access (manager viewing subordinate's record)
        4. Sharing rules (explicit record/object sharing)
        5. Team access (same team membership)

        Args:
            user_id: User requesting access
            object_type: Type of record (e.g., "proposal", "booking_order")
            record_id: ID of the specific record
            record_owner_id: ID of the record's owner (optional)

        Returns:
            {
                "allowed": bool,
                "reason": Reason for access decision
            }
        """
        context = db.get_full_user_context(user_id)
        if not context:
            return {"allowed": False, "reason": "user_not_found"}

        # Level 1: Admin access
        if context.get("profile") == "system_admin":
            return {"allowed": True, "reason": "admin"}

        # Level 2: Own record
        if record_owner_id and record_owner_id == user_id:
            return {"allowed": True, "reason": "owner"}

        # Level 3: Subordinate access (manager viewing subordinate's record)
        subordinate_ids = context.get("subordinate_ids", [])
        if record_owner_id and record_owner_id in subordinate_ids:
            return {"allowed": True, "reason": "subordinate_access"}

        # Level 4: Sharing rules - check if record is explicitly shared
        shared_records = context.get("shared_records", {})
        if object_type in shared_records:
            if record_id in shared_records[object_type]:
                return {"allowed": True, "reason": "sharing_rule"}

        # Level 4b: Sharing from other users
        shared_from_user_ids = context.get("shared_from_user_ids", [])
        if record_owner_id and record_owner_id in shared_from_user_ids:
            return {"allowed": True, "reason": "shared_by_user"}

        # Level 5: No access
        return {"allowed": False, "reason": "no_access"}

    # =========================================================================
    # ACCESSIBLE USERS
    # =========================================================================

    def get_accessible_user_ids(self, user_id: str) -> list[str] | None:
        """
        Get list of user IDs that the given user can access data for.

        This is used for filtering queries to show only accessible records.

        Returns:
            - None if user is admin (can access all)
            - List of user IDs the user can access (self + subordinates + shared)
        """
        context = db.get_full_user_context(user_id)
        if not context:
            return []

        # Admins can access all
        if context.get("profile") == "system_admin":
            return None  # None means "all"

        # Build list of accessible user IDs
        accessible = {user_id}  # Always include self

        # Add subordinates
        for sub_id in context.get("subordinate_ids", []):
            accessible.add(sub_id)

        # Add users who shared with this user
        for shared_id in context.get("shared_from_user_ids", []):
            accessible.add(shared_id)

        return list(accessible)

    # =========================================================================
    # COMPANY ACCESS
    # =========================================================================

    def check_company_access(
        self,
        user_id: str,
        company: str,
    ) -> dict[str, Any]:
        """
        Check if a user can access a specific company schema.

        Args:
            user_id: User ID
            company: Company schema name

        Returns:
            {
                "allowed": bool,
                "companies": List of user's accessible companies
            }
        """
        companies = db.get_user_companies(user_id)

        allowed = company in companies

        if not allowed:
            logger.debug(f"[RBAC] User {user_id} denied access to company {company}")

        return {
            "allowed": allowed,
            "companies": companies,
        }

    def get_user_companies(self, user_id: str) -> list[str]:
        """
        Get list of company schemas a user can access.

        Args:
            user_id: User ID

        Returns:
            List of company schema names
        """
        return db.get_user_companies(user_id)

    # =========================================================================
    # FULL CONTEXT
    # =========================================================================

    def get_user_context(self, user_id: str) -> dict[str, Any] | None:
        """
        Get full RBAC context for a user.

        Returns all 5 levels of RBAC data for injection into headers.
        """
        return db.get_full_user_context(user_id)


# Singleton instance
rbac_service = RBACService()
