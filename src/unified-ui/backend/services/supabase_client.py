"""
Supabase client wrapper for unified-ui.

[VERIFIED] Mirrors server.js lines 44-47:
```javascript
// Service role client for server-side operations
const supabase = supabaseUrl && supabaseServiceKey
  ? createClient(supabaseUrl, supabaseServiceKey)
  : null;
```

The client is created once and reused (singleton pattern).
Returns None if credentials are not configured (mirrors Node.js null check).
"""

import logging

from supabase import Client, create_client

from backend.config import get_settings

logger = logging.getLogger("unified-ui")

# Global client instance (singleton)
_client: Client | None = None


def get_supabase() -> Client | None:
    """
    Get or create the Supabase client.

    Mirrors server.js:44-47:
    - Returns None if URL or service key not configured
    - Creates client once and reuses (singleton pattern)

    Returns:
        Supabase Client instance, or None if not configured
    """
    global _client

    if _client is not None:
        return _client

    settings = get_settings()

    # Mirror Node.js null check: supabase = supabaseUrl && supabaseServiceKey ? createClient(...) : null;
    if not settings.supabase_url or not settings.supabase_service_key:
        logger.warning("[Supabase] Client not configured - missing URL or service key")
        return None

    try:
        _client = create_client(
            settings.supabase_url,
            settings.supabase_service_key,
        )
        logger.info(f"[Supabase] Client created for {settings.supabase_url}")
        return _client
    except Exception as e:
        logger.error(f"[Supabase] Failed to create client: {e}")
        return None


def reset_client() -> None:
    """
    Reset the client (useful for testing or credential rotation).
    """
    global _client
    _client = None
    logger.info("[Supabase] Client reset")
