"""
Authentication Integration Layer.

Provides abstracted access to authentication providers with a unified interface.
Follows the same pattern as integrations/llm/ and integrations/channels/.

Supported Providers:
- Supabase (SupabaseAuthProvider): Production Supabase Auth
- Local Dev (LocalDevAuthProvider): Development with hardcoded users

Usage:
    from integrations.auth import get_auth_client, AuthUser, AuthResult

    # Get the configured auth client
    auth = get_auth_client()

    # Verify a token
    result = await auth.verify_token(token)
    if result.success:
        user = result.user
        print(f"Authenticated: {user.email}")

    # Or use the convenience function
    from integrations.auth import verify_token, get_current_user

    result = await verify_token(token)
    user = await get_current_user(token)

Configuration:
    Set AUTH_PROVIDER environment variable:
    - "local_dev" (default): Use local development auth
    - "supabase": Use Supabase Auth

    For Supabase, also set:
    - SUPABASE_URL: Your Supabase project URL
    - SUPABASE_SERVICE_KEY: Your Supabase service role key
    - SUPABASE_JWT_SECRET: (Optional) JWT secret for local validation
"""

from integrations.auth.base import (
    AuthProvider,
    AuthResult,
    AuthStatus,
    AuthUser,
    TokenPayload,
)
from integrations.auth.client import (
    AuthClient,
    get_auth_client,
    get_current_user,
    reset_auth_client,
    set_auth_client,
    verify_token,
)
from integrations.auth.providers import (
    LocalDevAuthProvider,
    SupabaseAuthProvider,
)

__all__ = [
    # Base types
    "AuthProvider",
    "AuthUser",
    "AuthResult",
    "AuthStatus",
    "TokenPayload",
    # Client
    "AuthClient",
    "get_auth_client",
    "set_auth_client",
    "reset_auth_client",
    # Convenience functions
    "verify_token",
    "get_current_user",
    # Providers
    "SupabaseAuthProvider",
    "LocalDevAuthProvider",
]
