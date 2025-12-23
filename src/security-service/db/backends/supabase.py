"""
Supabase database backend implementation for Security Service.

This backend uses two Supabase projects:
- Security Supabase (read/write): audit_logs, api_keys, rate_limit_state, security_events
- UI Supabase (read-only): users, profiles, permissions, teams
"""

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Any

from db.base import DatabaseBackend

logger = logging.getLogger("security-service")


class SupabaseOperationError(Exception):
    """Custom exception for Supabase operation failures."""
    pass


class SupabaseBackend(DatabaseBackend):
    """
    Supabase database backend implementation.

    Uses two Supabase clients:
    - _security_client: For audit logs, API keys, rate limits (read/write)
    - _ui_client: For user/profile lookups (read-only)
    """

    def __init__(self):
        """Initialize Supabase backend using config settings."""
        self._security_client = None
        self._ui_client = None
        self._security_initialized = False
        self._ui_initialized = False

    @property
    def name(self) -> str:
        return "supabase"

    def _get_security_client(self):
        """Get or create Security Supabase client (lazy initialization)."""
        if self._security_client is not None:
            return self._security_client

        if self._security_initialized:
            return None

        self._security_initialized = True

        # Import config here to avoid circular imports
        from config import settings

        url = settings.security_supabase_url
        key = settings.security_supabase_key

        if not url or not key:
            logger.warning(
                "[SUPABASE:SECURITY] Credentials not configured. "
                "Audit logging and API key management will be unavailable."
            )
            return None

        try:
            from supabase import create_client
            from supabase.lib.client_options import ClientOptions

            # Use longer timeouts (seconds) to handle slow network conditions
            options = ClientOptions(
                postgrest_client_timeout=30,
                storage_client_timeout=60,
            )
            self._security_client = create_client(url, key, options=options)
            logger.info("[SUPABASE:SECURITY] Client initialized successfully")
            return self._security_client
        except ImportError:
            logger.error("[SUPABASE:SECURITY] supabase package not installed")
            return None
        except Exception as e:
            logger.error(f"[SUPABASE:SECURITY] Failed to initialize: {e}")
            return None

    def _get_ui_client(self):
        """Get or create UI Supabase client (lazy initialization)."""
        if self._ui_client is not None:
            return self._ui_client

        if self._ui_initialized:
            return None

        self._ui_initialized = True

        from config import settings

        url = settings.ui_supabase_url
        key = settings.ui_supabase_key

        if not url or not key:
            logger.warning(
                "[SUPABASE:UI] Credentials not configured. "
                "User lookups will be unavailable."
            )
            return None

        try:
            from supabase import create_client
            from supabase.lib.client_options import ClientOptions

            # Use longer timeouts (seconds) to handle slow network conditions
            options = ClientOptions(
                postgrest_client_timeout=30,
                storage_client_timeout=60,
            )
            self._ui_client = create_client(url, key, options=options)
            logger.info("[SUPABASE:UI] Client initialized successfully (read-only)")
            return self._ui_client
        except ImportError:
            logger.error("[SUPABASE:UI] supabase package not installed")
            return None
        except Exception as e:
            logger.error(f"[SUPABASE:UI] Failed to initialize: {e}")
            return None

    def init_db(self) -> None:
        """
        Initialize Supabase connections.

        Note: Schema is managed through SQL migrations, not here.
        """
        security = self._get_security_client()
        ui = self._get_ui_client()

        if security:
            logger.info("[SUPABASE:SECURITY] Connected - tables: audit_logs, api_keys, rate_limit_state, security_events")
        else:
            logger.warning("[SUPABASE:SECURITY] Not connected - running in degraded mode")

        if ui:
            logger.info("[SUPABASE:UI] Connected (read-only) - tables: users, profiles, permissions, teams")
        else:
            logger.warning("[SUPABASE:UI] Not connected - user lookups unavailable")

    def _now(self) -> str:
        """Get current timestamp in ISO format."""
        return datetime.utcnow().isoformat()

    # =========================================================================
    # AUDIT LOGS
    # =========================================================================

    def create_audit_log(
        self,
        actor_type: str,
        service: str,
        action: str,
        actor_id: str | None = None,
        actor_email: str | None = None,
        actor_ip: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        result: str = "success",
        error_message: str | None = None,
        request_id: str | None = None,
        request_method: str | None = None,
        request_path: str | None = None,
        request_body: dict | None = None,
        response_status: int | None = None,
        duration_ms: int | None = None,
        metadata: dict | None = None,
    ) -> dict[str, Any] | None:
        """Create an audit log entry in Security Supabase."""
        client = self._get_security_client()
        if not client:
            logger.debug(f"[AUDIT] Local only: {actor_type}:{actor_id} {action} {resource_type}/{resource_id}")
            return None

        try:
            data = {
                "timestamp": self._now(),
                "actor_type": actor_type,
                "actor_id": actor_id,
                "actor_email": actor_email,
                "actor_ip": actor_ip,
                "service": service,
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "result": result,
                "error_message": error_message,
                "request_id": request_id,
                "request_method": request_method,
                "request_path": request_path,
                "request_body": request_body,
                "response_status": response_status,
                "duration_ms": duration_ms,
                "metadata": metadata or {},
            }

            response = client.table("audit_logs").insert(data).execute()

            if response.data:
                return response.data[0]
            return None

        except Exception as e:
            logger.error(f"[AUDIT] Failed to create audit log: {e}")
            return None

    def list_audit_logs(
        self,
        actor_id: str | None = None,
        actor_type: str | None = None,
        service: str | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        result: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """List audit logs with filters."""
        client = self._get_security_client()
        if not client:
            return [], 0

        try:
            query = client.table("audit_logs").select("*", count="exact")

            if actor_id:
                query = query.eq("actor_id", actor_id)
            if actor_type:
                query = query.eq("actor_type", actor_type)
            if service:
                query = query.eq("service", service)
            if action:
                query = query.eq("action", action)
            if resource_type:
                query = query.eq("resource_type", resource_type)
            if resource_id:
                query = query.eq("resource_id", resource_id)
            if result:
                query = query.eq("result", result)
            if start_date:
                query = query.gte("timestamp", start_date)
            if end_date:
                query = query.lte("timestamp", end_date)

            query = query.order("timestamp", desc=True).range(offset, offset + limit - 1)
            response = query.execute()

            return response.data or [], response.count or 0

        except Exception as e:
            logger.error(f"[AUDIT] Failed to list audit logs: {e}")
            return [], 0

    def get_audit_log(self, log_id: str) -> dict[str, Any] | None:
        """Get a single audit log by ID."""
        client = self._get_security_client()
        if not client:
            return None

        try:
            response = client.table("audit_logs").select("*").eq("id", log_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"[AUDIT] Failed to get audit log {log_id}: {e}")
            return None

    # =========================================================================
    # API KEYS
    # =========================================================================

    def create_api_key(
        self,
        key_hash: str,
        key_prefix: str,
        name: str,
        scopes: list[str],
        created_by: str | None = None,
        description: str | None = None,
        allowed_services: list[str] | None = None,
        allowed_ips: list[str] | None = None,
        rate_limit_per_minute: int = 100,
        rate_limit_per_day: int = 10000,
        expires_at: str | None = None,
        metadata: dict | None = None,
    ) -> dict[str, Any] | None:
        """Create a new API key record."""
        client = self._get_security_client()
        if not client:
            return None

        try:
            data = {
                "key_hash": key_hash,
                "key_prefix": key_prefix,
                "name": name,
                "description": description,
                "created_by": created_by,
                "scopes": scopes,
                "allowed_services": allowed_services,
                "allowed_ips": allowed_ips,
                "rate_limit_per_minute": rate_limit_per_minute,
                "rate_limit_per_day": rate_limit_per_day,
                "is_active": True,
                "expires_at": expires_at,
                "metadata": metadata or {},
                "created_at": self._now(),
                "updated_at": self._now(),
            }

            response = client.table("api_keys").insert(data).execute()
            return response.data[0] if response.data else None

        except Exception as e:
            logger.error(f"[API_KEY] Failed to create API key: {e}")
            return None

    def get_api_key_by_hash(self, key_hash: str) -> dict[str, Any] | None:
        """Get an API key record by its hash."""
        client = self._get_security_client()
        if not client:
            return None

        try:
            response = (
                client.table("api_keys")
                .select("*")
                .eq("key_hash", key_hash)
                .eq("is_active", True)
                .execute()
            )
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"[API_KEY] Failed to get API key by hash: {e}")
            return None

    def get_api_key(self, key_id: str) -> dict[str, Any] | None:
        """Get an API key record by ID."""
        client = self._get_security_client()
        if not client:
            return None

        try:
            response = client.table("api_keys").select("*").eq("id", key_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"[API_KEY] Failed to get API key {key_id}: {e}")
            return None

    def list_api_keys(
        self,
        created_by: str | None = None,
        is_active: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """List API keys with filters."""
        client = self._get_security_client()
        if not client:
            return [], 0

        try:
            query = client.table("api_keys").select("*", count="exact")

            if created_by:
                query = query.eq("created_by", created_by)
            if is_active is not None:
                query = query.eq("is_active", is_active)

            query = query.order("created_at", desc=True).range(offset, offset + limit - 1)
            response = query.execute()

            return response.data or [], response.count or 0

        except Exception as e:
            logger.error(f"[API_KEY] Failed to list API keys: {e}")
            return [], 0

    def update_api_key(
        self,
        key_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Update an API key."""
        client = self._get_security_client()
        if not client:
            return None

        try:
            updates["updated_at"] = self._now()
            response = client.table("api_keys").update(updates).eq("id", key_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"[API_KEY] Failed to update API key {key_id}: {e}")
            return None

    def delete_api_key(self, key_id: str, hard_delete: bool = False) -> bool:
        """Delete an API key (soft delete by default)."""
        client = self._get_security_client()
        if not client:
            return False

        try:
            if hard_delete:
                client.table("api_keys").delete().eq("id", key_id).execute()
            else:
                client.table("api_keys").update({
                    "is_active": False,
                    "updated_at": self._now(),
                }).eq("id", key_id).execute()
            return True
        except Exception as e:
            logger.error(f"[API_KEY] Failed to delete API key {key_id}: {e}")
            return False

    def log_api_key_usage(
        self,
        key_id: str,
        service: str,
        endpoint: str,
        method: str,
        status_code: int,
        ip_address: str | None = None,
        user_agent: str | None = None,
        duration_ms: int | None = None,
    ) -> None:
        """Log API key usage for analytics."""
        client = self._get_security_client()
        if not client:
            return

        try:
            data = {
                "key_id": key_id,
                "timestamp": self._now(),
                "service": service,
                "endpoint": endpoint,
                "method": method,
                "status_code": status_code,
                "ip_address": ip_address,
                "user_agent": user_agent,
                "duration_ms": duration_ms,
            }
            client.table("api_key_usage").insert(data).execute()

            # Update last_used_at on the key
            client.table("api_keys").update({
                "last_used_at": self._now(),
            }).eq("id", key_id).execute()

        except Exception as e:
            logger.warning(f"[API_KEY] Failed to log usage: {e}")

    def get_api_key_usage(
        self,
        key_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """Get API key usage statistics."""
        client = self._get_security_client()
        if not client:
            return {"key_id": key_id, "total_requests": 0, "requests_today": 0, "requests_this_hour": 0}

        try:
            now = datetime.utcnow()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            hour_start = (now - timedelta(hours=1)).isoformat()

            # Total count
            query = client.table("api_key_usage").select("id", count="exact").eq("key_id", key_id)
            if start_date:
                query = query.gte("timestamp", start_date)
            if end_date:
                query = query.lte("timestamp", end_date)
            total_response = query.execute()

            # Today count
            today_response = (
                client.table("api_key_usage")
                .select("id", count="exact")
                .eq("key_id", key_id)
                .gte("timestamp", today_start)
                .execute()
            )

            # Last hour count
            hour_response = (
                client.table("api_key_usage")
                .select("id", count="exact")
                .eq("key_id", key_id)
                .gte("timestamp", hour_start)
                .execute()
            )

            # Get key info for last_used_at
            key_info = self.get_api_key(key_id)

            return {
                "key_id": key_id,
                "total_requests": total_response.count or 0,
                "requests_today": today_response.count or 0,
                "requests_this_hour": hour_response.count or 0,
                "last_used_at": key_info.get("last_used_at") if key_info else None,
            }

        except Exception as e:
            logger.error(f"[API_KEY] Failed to get usage for {key_id}: {e}")
            return {"key_id": key_id, "total_requests": 0, "requests_today": 0, "requests_this_hour": 0}

    # =========================================================================
    # RATE LIMITING
    # =========================================================================

    def get_rate_limit_count(
        self,
        key: str,
        window_seconds: int = 60,
    ) -> int:
        """Get current request count for a rate limit key."""
        client = self._get_security_client()
        if not client:
            return 0

        try:
            window_start = (datetime.utcnow() - timedelta(seconds=window_seconds)).isoformat()

            response = (
                client.table("rate_limit_state")
                .select("request_count")
                .eq("key", key)
                .gte("window_start", window_start)
                .execute()
            )

            total = sum(r.get("request_count", 0) for r in (response.data or []))
            return total

        except Exception as e:
            logger.error(f"[RATE_LIMIT] Failed to get count for {key}: {e}")
            return 0

    def increment_rate_limit(
        self,
        key: str,
        window_seconds: int = 60,
        increment: int = 1,
    ) -> int:
        """Increment rate limit counter and return new count."""
        client = self._get_security_client()
        if not client:
            return 0

        try:
            now = datetime.utcnow()
            window_start = now.replace(second=0, microsecond=0).isoformat()

            # Try to upsert
            response = (
                client.table("rate_limit_state")
                .upsert({
                    "key": key,
                    "window_start": window_start,
                    "request_count": increment,
                    "updated_at": now.isoformat(),
                }, on_conflict="key,window_start")
                .execute()
            )

            # Get current count
            return self.get_rate_limit_count(key, window_seconds)

        except Exception as e:
            logger.error(f"[RATE_LIMIT] Failed to increment for {key}: {e}")
            return 0

    def cleanup_rate_limits(self) -> int:
        """Clean up expired rate limit windows."""
        client = self._get_security_client()
        if not client:
            return 0

        try:
            cutoff = (datetime.utcnow() - timedelta(minutes=5)).isoformat()
            response = (
                client.table("rate_limit_state")
                .delete()
                .lt("window_start", cutoff)
                .execute()
            )
            count = len(response.data) if response.data else 0
            if count > 0:
                logger.info(f"[RATE_LIMIT] Cleaned up {count} expired windows")
            return count
        except Exception as e:
            logger.error(f"[RATE_LIMIT] Failed to cleanup: {e}")
            return 0

    # =========================================================================
    # SECURITY EVENTS
    # =========================================================================

    def create_security_event(
        self,
        event_type: str,
        severity: str,
        service: str,
        message: str,
        actor_type: str | None = None,
        actor_id: str | None = None,
        ip_address: str | None = None,
        details: dict | None = None,
    ) -> dict[str, Any] | None:
        """Create a security event."""
        client = self._get_security_client()
        if not client:
            logger.warning(f"[SECURITY_EVENT] {severity.upper()}: {message}")
            return None

        try:
            data = {
                "event_type": event_type,
                "severity": severity,
                "service": service,
                "message": message,
                "actor_type": actor_type,
                "actor_id": actor_id,
                "ip_address": ip_address,
                "details": details or {},
                "is_resolved": False,
                "timestamp": self._now(),
            }

            response = client.table("security_events").insert(data).execute()
            return response.data[0] if response.data else None

        except Exception as e:
            logger.error(f"[SECURITY_EVENT] Failed to create: {e}")
            return None

    def list_security_events(
        self,
        event_type: str | None = None,
        severity: str | None = None,
        service: str | None = None,
        is_resolved: bool | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """List security events with filters."""
        client = self._get_security_client()
        if not client:
            return [], 0

        try:
            query = client.table("security_events").select("*", count="exact")

            if event_type:
                query = query.eq("event_type", event_type)
            if severity:
                query = query.eq("severity", severity)
            if service:
                query = query.eq("service", service)
            if is_resolved is not None:
                query = query.eq("is_resolved", is_resolved)
            if start_date:
                query = query.gte("timestamp", start_date)
            if end_date:
                query = query.lte("timestamp", end_date)

            query = query.order("timestamp", desc=True).range(offset, offset + limit - 1)
            response = query.execute()

            return response.data or [], response.count or 0

        except Exception as e:
            logger.error(f"[SECURITY_EVENT] Failed to list: {e}")
            return [], 0

    def resolve_security_event(
        self,
        event_id: str,
        resolved_by: str,
        resolution_notes: str | None = None,
    ) -> dict[str, Any] | None:
        """Mark a security event as resolved."""
        client = self._get_security_client()
        if not client:
            return None

        try:
            response = (
                client.table("security_events")
                .update({
                    "is_resolved": True,
                    "resolved_at": self._now(),
                    "resolved_by": resolved_by,
                    "resolution_notes": resolution_notes,
                })
                .eq("id", event_id)
                .execute()
            )
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"[SECURITY_EVENT] Failed to resolve {event_id}: {e}")
            return None

    # =========================================================================
    # USER LOOKUPS (from UI Supabase - read only)
    # =========================================================================

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        """Get user info from UI Supabase."""
        client = self._get_ui_client()
        if not client:
            return None

        try:
            response = client.table("users").select("*").eq("id", user_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"[UI] Failed to get user {user_id}: {e}")
            return None

    def get_user_profile(self, user_id: str) -> dict[str, Any] | None:
        """Get user's RBAC profile from UI Supabase."""
        client = self._get_ui_client()
        if not client:
            return None

        try:
            # Get user's profile_id
            user = self.get_user(user_id)
            if not user or not user.get("profile_id"):
                return None

            response = (
                client.table("profiles")
                .select("*, profile_permissions(permission_id, permissions(name, description))")
                .eq("id", user["profile_id"])
                .execute()
            )
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"[UI] Failed to get profile for user {user_id}: {e}")
            return None

    def get_user_permissions(self, user_id: str) -> list[str]:
        """Get user's combined permissions from UI Supabase."""
        client = self._get_ui_client()
        if not client:
            return []

        try:
            permissions = set()

            # Get profile permissions
            profile = self.get_user_profile(user_id)
            if profile:
                for pp in profile.get("profile_permissions", []):
                    perm = pp.get("permissions", {})
                    if perm.get("name"):
                        permissions.add(perm["name"])

            # Get permission set permissions
            # (would need to query user_permission_sets -> permission_sets -> permissions)

            return list(permissions)

        except Exception as e:
            logger.error(f"[UI] Failed to get permissions for user {user_id}: {e}")
            return []

    def get_user_teams(self, user_id: str) -> list[dict[str, Any]]:
        """Get user's teams from UI Supabase."""
        client = self._get_ui_client()
        if not client:
            return []

        try:
            response = (
                client.table("team_members")
                .select("role, teams(id, name, display_name, parent_team_id)")
                .eq("user_id", user_id)
                .execute()
            )

            teams = []
            for tm in response.data or []:
                team = tm.get("teams", {})
                if team:
                    team["role"] = tm.get("role")
                    teams.append(team)
            return teams

        except Exception as e:
            logger.error(f"[UI] Failed to get teams for user {user_id}: {e}")
            return []

    def get_user_subordinates(self, user_id: str) -> list[str]:
        """Get user's subordinate IDs from UI Supabase."""
        client = self._get_ui_client()
        if not client:
            return []

        try:
            response = (
                client.table("users")
                .select("id")
                .eq("manager_id", user_id)
                .execute()
            )
            return [u["id"] for u in (response.data or [])]
        except Exception as e:
            logger.error(f"[UI] Failed to get subordinates for user {user_id}: {e}")
            return []

    def get_user_companies(self, user_id: str) -> list[str]:
        """Get user's accessible company schemas from UI Supabase."""
        client = self._get_ui_client()
        if not client:
            return []

        try:
            response = (
                client.table("user_companies")
                .select("company_schema")
                .eq("user_id", user_id)
                .eq("is_active", True)
                .execute()
            )
            return [uc["company_schema"] for uc in (response.data or [])]
        except Exception as e:
            logger.error(f"[UI] Failed to get companies for user {user_id}: {e}")
            return []

    def get_full_user_context(self, user_id: str) -> dict[str, Any] | None:
        """
        Get complete user context for RBAC.

        Returns all 5 levels of RBAC data.
        """
        user = self.get_user(user_id)
        if not user:
            return None

        profile = self.get_user_profile(user_id)
        permissions = self.get_user_permissions(user_id)
        teams = self.get_user_teams(user_id)
        subordinates = self.get_user_subordinates(user_id)
        companies = self.get_user_companies(user_id)

        return {
            # Level 1: Identity
            "user_id": user_id,
            "email": user.get("email", ""),
            "name": user.get("name"),
            "profile": profile.get("name") if profile else None,

            # Level 2: Permissions
            "permissions": permissions,
            "permission_sets": [],  # TODO: Add permission sets

            # Level 3: Teams & Hierarchy
            "teams": teams,
            "team_ids": [t.get("id") for t in teams if t.get("id")],
            "manager_id": user.get("manager_id"),
            "subordinate_ids": subordinates,

            # Level 4: Sharing
            "sharing_rules": [],  # TODO: Add sharing rules
            "shared_records": {},
            "shared_from_user_ids": [],

            # Level 5: Companies
            "companies": companies,
        }
