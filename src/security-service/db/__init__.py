"""
Security Service Database Layer.

Provides access to:
- Security Supabase: audit_logs, api_keys, rate_limit_state, security_events
- UI Supabase (read-only): users, profiles, permissions, teams

Usage:
    from db import db

    # Audit logging
    db.create_audit_log(actor_type="user", service="sales-module", action="create")

    # API key management
    key = db.get_api_key_by_hash(hash)

    # User context
    context = db.get_full_user_context(user_id)
"""

from .database import db
from .clients import get_security_client, get_ui_client

__all__ = [
    "db",
    "get_security_client",
    "get_ui_client",
]
