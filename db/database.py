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

import os
import logging
from typing import Any, Dict, List, Optional

from db.base import DatabaseBackend
from db.backends.sqlite import SQLiteBackend

logger = logging.getLogger("proposal-bot")

# Backend selection from environment
DB_BACKEND = os.getenv("DB_BACKEND", "sqlite").lower()


def _get_backend() -> DatabaseBackend:
    """
    Get the configured database backend.

    Returns:
        DatabaseBackend instance based on DB_BACKEND environment variable.
    """
    if DB_BACKEND == "supabase":
        # Check if credentials are available before trying to import
        supabase_url = os.getenv("SUPABASE_URL", "")
        supabase_key = os.getenv("SUPABASE_SERVICE_KEY", "")

        if not supabase_url or not supabase_key:
            logger.warning("[DB] Supabase credentials not set, falling back to SQLite")
            return SQLiteBackend()

        try:
            from db.backends.supabase import SupabaseBackend
            logger.info("[DB] Using Supabase backend")
            return SupabaseBackend()
        except ImportError as e:
            logger.warning(f"[DB] Supabase package not installed ({e}), falling back to SQLite")
            return SQLiteBackend()
        except Exception as e:
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
        date_generated: Optional[str] = None,
    ) -> None:
        return self._backend.log_proposal(
            submitted_by, client_name, package_type,
            locations, total_amount, date_generated
        )

    def get_proposals_summary(self) -> Dict[str, Any]:
        return self._backend.get_proposals_summary()

    def export_to_excel(self) -> str:
        return self._backend.export_to_excel()

    # =========================================================================
    # BOOKING ORDERS
    # =========================================================================

    def generate_next_bo_ref(self) -> str:
        return self._backend.generate_next_bo_ref()

    def save_booking_order(self, data: Dict[str, Any]) -> str:
        return self._backend.save_booking_order(data)

    def get_booking_order(self, bo_ref: str) -> Optional[Dict[str, Any]]:
        return self._backend.get_booking_order(bo_ref)

    def get_booking_order_by_number(self, bo_number: str) -> Optional[Dict[str, Any]]:
        return self._backend.get_booking_order_by_number(bo_number)

    def export_booking_orders_to_excel(self) -> str:
        return self._backend.export_booking_orders_to_excel()

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
        return self._backend.save_mockup_frame(
            location_key, photo_filename, frames_data,
            created_by, time_of_day, finish, config
        )

    def get_mockup_frames(
        self,
        location_key: str,
        photo_filename: str,
        time_of_day: str = "day",
        finish: str = "gold",
    ) -> Optional[List[Dict]]:
        return self._backend.get_mockup_frames(
            location_key, photo_filename, time_of_day, finish
        )

    def get_mockup_config(
        self,
        location_key: str,
        photo_filename: str,
        time_of_day: str = "day",
        finish: str = "gold",
    ) -> Optional[Dict]:
        return self._backend.get_mockup_config(
            location_key, photo_filename, time_of_day, finish
        )

    def list_mockup_photos(
        self,
        location_key: str,
        time_of_day: str = "day",
        finish: str = "gold",
    ) -> List[str]:
        return self._backend.list_mockup_photos(
            location_key, time_of_day, finish
        )

    def list_mockup_variations(self, location_key: str) -> Dict[str, List[str]]:
        return self._backend.list_mockup_variations(location_key)

    def delete_mockup_frame(
        self,
        location_key: str,
        photo_filename: str,
        time_of_day: str = "day",
        finish: str = "gold",
    ) -> None:
        return self._backend.delete_mockup_frame(
            location_key, photo_filename, time_of_day, finish
        )

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
        return self._backend.log_mockup_usage(
            location_key, time_of_day, finish, photo_used,
            creative_type, ai_prompt, template_selected, success, user_ip
        )

    def get_mockup_usage_stats(self) -> Dict[str, Any]:
        return self._backend.get_mockup_usage_stats()

    def export_mockup_usage_to_excel(self) -> str:
        return self._backend.export_mockup_usage_to_excel()

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

    def get_bo_workflow(self, workflow_id: str) -> Optional[str]:
        return self._backend.get_bo_workflow(workflow_id)

    def get_all_active_bo_workflows(self) -> List[tuple]:
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
        user_id: Optional[str] = None,
        workflow: Optional[str] = None,
        cached_input_tokens: int = 0,
        context: Optional[str] = None,
        metadata_json: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> None:
        return self._backend.log_ai_cost(
            call_type, model, input_tokens, output_tokens, reasoning_tokens,
            input_cost, output_cost, reasoning_cost, total_cost,
            user_id, workflow, cached_input_tokens, context, metadata_json, timestamp
        )

    def get_ai_costs_summary(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        call_type: Optional[str] = None,
        workflow: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
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
        return self._backend.log_audit_event(
            timestamp, action, user_id, resource_type, resource_id,
            details_json, ip_address, user_agent
        )

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
        return self._backend.query_audit_log(
            user_id, action, resource_type, resource_id,
            start_date, end_date, limit, offset
        )


# Create the singleton database interface
db = _DatabaseNamespace(_backend)
