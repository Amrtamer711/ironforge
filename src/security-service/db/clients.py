"""
Supabase Client Providers.

Provides lazy-initialized Supabase clients for both:
- Security Supabase (audit_logs, api_keys, rate_limit_state, security_events)
- UI Supabase (read-only: users, profiles, permissions, teams)
"""

import logging
from functools import lru_cache
from typing import Any

logger = logging.getLogger("security-service")

# Module-level client storage
_security_client = None
_ui_client = None
_security_initialized = False
_ui_initialized = False


def get_security_client() -> Any | None:
    """
    Get the Security Supabase client.

    Returns:
        Supabase client for Security database, or None if not configured.
    """
    global _security_client, _security_initialized

    if _security_client is not None:
        return _security_client

    if _security_initialized:
        return None

    _security_initialized = True

    from config import settings

    url = settings.security_supabase_url
    key = settings.security_supabase_key

    if not url or not key:
        logger.warning(
            "[SUPABASE:SECURITY] Credentials not configured. "
            "Set SECURITY_DEV_SUPABASE_URL/KEY or SECURITY_PROD_SUPABASE_URL/KEY."
        )
        return None

    try:
        from supabase import create_client
        _security_client = create_client(url, key)
        logger.info("[SUPABASE:SECURITY] Client initialized")
        return _security_client
    except ImportError:
        logger.error("[SUPABASE:SECURITY] supabase package not installed")
        return None
    except Exception as e:
        logger.error(f"[SUPABASE:SECURITY] Failed to initialize: {e}")
        return None


def get_ui_client() -> Any | None:
    """
    Get the UI Supabase client (read-only).

    Returns:
        Supabase client for UI database, or None if not configured.
    """
    global _ui_client, _ui_initialized

    if _ui_client is not None:
        return _ui_client

    if _ui_initialized:
        return None

    _ui_initialized = True

    from config import settings

    url = settings.ui_supabase_url
    key = settings.ui_supabase_key

    if not url or not key:
        logger.warning(
            "[SUPABASE:UI] Credentials not configured. "
            "Set UI_DEV_SUPABASE_URL/KEY or UI_PROD_SUPABASE_URL/KEY."
        )
        return None

    try:
        from supabase import create_client
        _ui_client = create_client(url, key)
        logger.info("[SUPABASE:UI] Client initialized (read-only)")
        return _ui_client
    except ImportError:
        logger.error("[SUPABASE:UI] supabase package not installed")
        return None
    except Exception as e:
        logger.error(f"[SUPABASE:UI] Failed to initialize: {e}")
        return None


# Aliases for backward compatibility
security_client = property(lambda self: get_security_client())
ui_client = property(lambda self: get_ui_client())
