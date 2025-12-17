"""
Database Router - Selects and exposes the appropriate database backend.

This module provides a unified interface to the database, automatically
selecting between SQLite and Supabase based on environment configuration.

Usage:
    from db.database import db

    # All methods are exposed directly:
    db.log_proposal(...)
    db.save_booking_order(...)
    db.get_ai_costs_summary(...)

Configuration:
    Set DB_BACKEND environment variable:
    - "sqlite" (default): Use local SQLite database
    - "supabase": Use Supabase cloud database

    For Supabase, also set:
    - SUPABASE_URL: Your Supabase project URL
    - SUPABASE_SERVICE_KEY: Your Supabase service role key
"""

import logging
import os
from typing import Any

from db.backends.sqlite import SQLiteBackend
from db.base import DatabaseBackend

logger = logging.getLogger("proposal-bot")

# Backend selection from environment
DB_BACKEND = os.getenv("DB_BACKEND", "sqlite").lower()


def _get_backend() -> DatabaseBackend:
    """
    Get the configured database backend.

    Returns:
        DatabaseBackend instance based on DB_BACKEND environment variable.

    Raises:
        RuntimeError: In production if Supabase credentials are missing
    """
    environment = os.getenv("ENVIRONMENT", "local")
    is_production = environment == "production"

    if DB_BACKEND == "supabase":
        # Check if credentials are available using app_settings (handles dev/prod env vars)
        try:
            from app_settings import settings
            supabase_url = settings.active_supabase_url or ""
            supabase_key = settings.active_supabase_service_key or ""
        except ImportError:
            # Fallback to direct env vars (legacy)
            supabase_url = os.getenv("SUPABASE_URL", "") or os.getenv("SALESBOT_DEV_SUPABASE_URL", "")
            supabase_key = os.getenv("SUPABASE_SERVICE_KEY", "") or os.getenv("SALESBOT_DEV_SUPABASE_SERVICE_ROLE_KEY", "")

        if not supabase_url or not supabase_key:
            # In production, fail loudly - don't silently fall back to SQLite
            if is_production:
                raise RuntimeError(
                    "[DB] FATAL: Supabase credentials missing in production. "
                    "Set SALESBOT_PROD_SUPABASE_URL and SALESBOT_PROD_SUPABASE_SERVICE_ROLE_KEY, "
                    "or set DB_BACKEND=sqlite if SQLite is intended."
                )
            logger.warning("[DB] Supabase credentials not set, falling back to SQLite (non-production only)")
            return SQLiteBackend()

        try:
            from db.backends.supabase import SupabaseBackend
            logger.info("[DB] Using Supabase backend")
            return SupabaseBackend()
        except ImportError as e:
            if is_production:
                raise RuntimeError(f"[DB] FATAL: Supabase package not installed in production: {e}")
            logger.warning(f"[DB] Supabase package not installed ({e}), falling back to SQLite")
            return SQLiteBackend()
        except Exception as e:
            if is_production:
                raise RuntimeError(f"[DB] FATAL: Failed to initialize Supabase backend in production: {e}")
            logger.error(f"[DB] Failed to initialize Supabase backend: {e}")
            logger.info("[DB] Falling back to SQLite backend")
            return SQLiteBackend()
    else:
        logger.info("[DB] Using SQLite backend")
        return SQLiteBackend()


# Create the backend instance
_backend = _get_backend()

# Initialize the database
_backend.init_db()


class _DatabaseNamespace:
    """
    Namespace wrapper to expose backend methods as db.method() calls.

    This maintains backward compatibility with existing code that uses:
        from db.database import db
        db.log_proposal(...)
    """

    def __init__(self, backend: DatabaseBackend):
        self._backend = backend

    @property
    def backend_name(self) -> str:
        """Get the name of the current backend."""
        return self._backend.name

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
        date_generated: str | None = None,
    ) -> None:
        return self._backend.log_proposal(
            submitted_by, client_name, package_type,
            locations, total_amount, date_generated
        )

    def get_proposals_summary(self) -> dict[str, Any]:
        return self._backend.get_proposals_summary()

    def export_to_excel(self) -> str:
        return self._backend.export_to_excel()

    def get_proposals(
        self,
        limit: int = 50,
        offset: int = 0,
        user_ids: str | list[str] | None = None,
        client_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get proposals with optional filtering. user_ids can be a single ID or list for team access."""
        return self._backend.get_proposals(limit, offset, user_ids, client_name)

    def get_proposal_by_id(self, proposal_id: int) -> dict[str, Any] | None:
        """Get a single proposal by ID."""
        return self._backend.get_proposal_by_id(proposal_id)

    def get_proposal_locations(self, proposal_id: int) -> list[dict[str, Any]]:
        """Get locations for a specific proposal."""
        return self._backend.get_proposal_locations(proposal_id)

    def delete_proposal(self, proposal_id: int) -> bool:
        """Delete a proposal by ID."""
        return self._backend.delete_proposal(proposal_id)

    # =========================================================================
    # BOOKING ORDERS
    # =========================================================================

    def generate_next_bo_ref(self) -> str:
        return self._backend.generate_next_bo_ref()

    def save_booking_order(self, data: dict[str, Any]) -> str:
        return self._backend.save_booking_order(data)

    def get_booking_order(self, bo_ref: str) -> dict[str, Any] | None:
        return self._backend.get_booking_order(bo_ref)

    def get_booking_order_by_number(self, bo_number: str) -> dict[str, Any] | None:
        return self._backend.get_booking_order_by_number(bo_number)

    def export_booking_orders_to_excel(self) -> str:
        return self._backend.export_booking_orders_to_excel()

    # =========================================================================
    # LOCATIONS
    # =========================================================================

    def get_locations_for_companies(
        self,
        company_schemas: list[str],
    ) -> list[dict[str, Any]]:
        return self._backend.get_locations_for_companies(company_schemas)

    def get_location_by_key(
        self,
        location_key: str,
        company_schemas: list[str],
    ) -> dict[str, Any] | None:
        return self._backend.get_location_by_key(location_key, company_schemas)

    # =========================================================================
    # MOCKUP FRAMES (Company-scoped)
    # =========================================================================

    def save_mockup_frame(
        self,
        location_key: str,
        photo_filename: str,
        frames_data: list[dict],
        company_schema: str,
        created_by: str | None = None,
        time_of_day: str = "day",
        finish: str = "gold",
        config: dict | None = None,
    ) -> str:
        return self._backend.save_mockup_frame(
            location_key, photo_filename, frames_data, company_schema,
            created_by, time_of_day, finish, config
        )

    def get_mockup_frames(
        self,
        location_key: str,
        photo_filename: str,
        company_schema: str,
        time_of_day: str = "day",
        finish: str = "gold",
    ) -> list[dict] | None:
        return self._backend.get_mockup_frames(
            location_key, photo_filename, company_schema, time_of_day, finish
        )

    def get_mockup_config(
        self,
        location_key: str,
        photo_filename: str,
        company_schema: str,
        time_of_day: str = "day",
        finish: str = "gold",
    ) -> dict | None:
        return self._backend.get_mockup_config(
            location_key, photo_filename, company_schema, time_of_day, finish
        )

    def list_mockup_photos(
        self,
        location_key: str,
        company_schemas: list[str],
        time_of_day: str = "day",
        finish: str = "gold",
    ) -> list[str]:
        return self._backend.list_mockup_photos(
            location_key, company_schemas, time_of_day, finish
        )

    def list_mockup_variations(
        self,
        location_key: str,
        company_schemas: list[str],
    ) -> dict[str, list[str]]:
        return self._backend.list_mockup_variations(location_key, company_schemas)

    def delete_mockup_frame(
        self,
        location_key: str,
        photo_filename: str,
        company_schema: str,
        time_of_day: str = "day",
        finish: str = "gold",
    ) -> None:
        return self._backend.delete_mockup_frame(
            location_key, photo_filename, company_schema, time_of_day, finish
        )

    # =========================================================================
    # MOCKUP USAGE (Company-scoped)
    # =========================================================================

    def log_mockup_usage(
        self,
        location_key: str,
        time_of_day: str,
        finish: str,
        photo_used: str,
        creative_type: str,
        company_schema: str,
        ai_prompt: str | None = None,
        template_selected: bool = False,
        success: bool = True,
        user_ip: str | None = None,
    ) -> None:
        return self._backend.log_mockup_usage(
            location_key, time_of_day, finish, photo_used,
            creative_type, company_schema, ai_prompt, template_selected, success, user_ip
        )

    def get_mockup_usage_stats(
        self,
        company_schemas: list[str],
    ) -> dict[str, Any]:
        return self._backend.get_mockup_usage_stats(company_schemas)

    def export_mockup_usage_to_excel(
        self,
        company_schemas: list[str],
    ) -> str:
        return self._backend.export_mockup_usage_to_excel(company_schemas)

    # =========================================================================
    # BO WORKFLOWS
    # =========================================================================

    def save_bo_workflow(
        self,
        workflow_id: str,
        workflow_data: str,
        updated_at: str,
    ) -> None:
        return self._backend.save_bo_workflow(workflow_id, workflow_data, updated_at)

    def get_bo_workflow(self, workflow_id: str) -> str | None:
        return self._backend.get_bo_workflow(workflow_id)

    def get_all_active_bo_workflows(self) -> list[tuple]:
        return self._backend.get_all_active_bo_workflows()

    def delete_bo_workflow(self, workflow_id: str) -> None:
        return self._backend.delete_bo_workflow(workflow_id)

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
        user_id: str | None = None,
        workflow: str | None = None,
        cached_input_tokens: int = 0,
        context: str | None = None,
        metadata_json: str | None = None,
        timestamp: str | None = None,
    ) -> None:
        return self._backend.log_ai_cost(
            call_type, model, input_tokens, output_tokens, reasoning_tokens,
            input_cost, output_cost, reasoning_cost, total_cost,
            user_id, workflow, cached_input_tokens, context, metadata_json, timestamp
        )

    def get_ai_costs_summary(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        call_type: str | None = None,
        workflow: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        return self._backend.get_ai_costs_summary(
            start_date, end_date, call_type, workflow, user_id
        )

    def clear_ai_costs(self) -> None:
        return self._backend.clear_ai_costs()

    # =========================================================================
    # BACKWARD COMPATIBILITY - Direct connection access (SQLite only)
    # =========================================================================

    def _connect(self):
        """
        Get direct database connection (SQLite only).

        Warning: This breaks the abstraction. Use only when necessary
        for performance or features not in the interface.
        """
        if hasattr(self._backend, '_connect'):
            return self._backend._connect()
        raise NotImplementedError(
            f"Direct connection not supported by {self._backend.name} backend"
        )

    # =========================================================================
    # GENERIC QUERY EXECUTION (for invite tokens)
    # =========================================================================

    def execute_query(
        self,
        query: str,
        params: tuple = (),
    ) -> list[dict[str, Any]] | None:
        """
        Execute a raw SQL query for invite_tokens table.
        Bridges SQLite (?) and Supabase syntax.
        """
        if self._backend.name == "sqlite":
            conn = self._connect()
            cursor = conn.cursor()
            cursor.execute(query, params)
            if cursor.description:
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
                conn.commit()
                return [dict(zip(columns, row, strict=False)) for row in rows]
            conn.commit()
            return None

        elif self._backend.name == "supabase":
            client = self._backend._get_client()
            query_lower = query.lower().strip()

            # Handle SELECT on invite_tokens
            if query_lower.startswith("select") and "invite_tokens" in query_lower:
                builder = client.table("invite_tokens").select("*")

                if "where token = ?" in query_lower and params:
                    builder = builder.eq("token", params[0])
                elif "where id = ?" in query_lower and params:
                    builder = builder.eq("id", params[0])
                elif "where email = ?" in query_lower and params:
                    builder = builder.eq("email", params[0])
                    if "used_at is null" in query_lower:
                        builder = builder.is_("used_at", "null")
                    if "is_revoked = 0" in query_lower:
                        builder = builder.eq("is_revoked", False)
                    if "expires_at > ?" in query_lower and len(params) >= 2:
                        builder = builder.gt("expires_at", params[1])
                elif "used_at is null" in query_lower:
                    builder = builder.is_("used_at", "null")
                    if "is_revoked = 0" in query_lower:
                        builder = builder.eq("is_revoked", False)

                if "order by created_at desc" in query_lower:
                    builder = builder.order("created_at", desc=True)

                return builder.execute().data or []

            # Handle INSERT into invite_tokens
            elif query_lower.startswith("insert") and "invite_tokens" in query_lower and len(params) >= 6:
                client.table("invite_tokens").insert({
                    "token": params[0],
                    "email": params[1],
                    "profile_name": params[2],
                    "created_by": params[3],
                    "created_at": params[4],
                    "expires_at": params[5],
                }).execute()
                return None

            # Handle UPDATE invite_tokens
            elif query_lower.startswith("update") and "invite_tokens" in query_lower:
                if "is_revoked = 1" in query_lower and params:
                    client.table("invite_tokens").update({"is_revoked": True}).eq("id", params[0]).execute()
                elif "used_at = ?" in query_lower and len(params) >= 2:
                    client.table("invite_tokens").update({"used_at": params[0]}).eq("id", params[1]).execute()
                return None

            return []
        else:
            raise NotImplementedError(f"execute_query not supported for {self._backend.name}")

    # =========================================================================
    # AUDIT LOGGING
    # =========================================================================

    def log_audit_event(
        self,
        timestamp: str,
        action: str,
        user_id: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        details_json: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        return self._backend.log_audit_event(
            timestamp, action, user_id, resource_type, resource_id,
            details_json, ip_address, user_agent
        )

    def query_audit_log(
        self,
        user_id: str | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        return self._backend.query_audit_log(
            user_id, action, resource_type, resource_id,
            start_date, end_date, limit, offset
        )

    # =========================================================================
    # CHAT SESSIONS
    # =========================================================================

    def save_chat_session(
        self,
        user_id: str,
        messages: list[dict[str, Any]],
        session_id: str | None = None,
    ) -> bool:
        """Save or update a user's chat session."""
        return self._backend.save_chat_session(user_id, messages, session_id)

    def get_chat_session(self, user_id: str) -> dict[str, Any] | None:
        """Get a user's chat session."""
        return self._backend.get_chat_session(user_id)

    def delete_chat_session(self, user_id: str) -> bool:
        """Delete a user's chat session."""
        return self._backend.delete_chat_session(user_id)

    # =========================================================================
    # DOCUMENT MANAGEMENT
    # =========================================================================

    def create_document(
        self,
        file_id: str,
        user_id: str,
        original_filename: str,
        file_type: str,
        storage_provider: str,
        storage_bucket: str,
        storage_key: str,
        file_size: int | None = None,
        file_extension: str | None = None,
        file_hash: str | None = None,
        document_type: str | None = None,
        bo_id: int | None = None,
        proposal_id: int | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> int | None:
        """Create a new document record."""
        return self._backend.create_document(
            file_id, user_id, original_filename, file_type,
            storage_provider, storage_bucket, storage_key,
            file_size, file_extension, file_hash, document_type,
            bo_id, proposal_id, metadata_json
        )

    def get_document(self, file_id: str) -> dict[str, Any] | None:
        """Get a document by file_id."""
        return self._backend.get_document(file_id)

    def get_document_by_hash(self, file_hash: str) -> dict[str, Any] | None:
        """Get a document by file hash (for deduplication)."""
        return self._backend.get_document_by_hash(file_hash)

    def soft_delete_document(self, file_id: str) -> bool:
        """Soft delete a document."""
        return self._backend.soft_delete_document(file_id)

    def hard_delete_document(self, file_id: str) -> bool:
        """Hard delete a document record."""
        return self._backend.hard_delete_document(file_id)


# Create the singleton database interface
db = _DatabaseNamespace(_backend)
