"""
API Middleware Package.

Provides middleware and dependencies for:
- API Key authentication
- Rate limiting
- Request logging
"""

from api.middleware.api_key import (
    require_api_key,
    get_api_key,
    generate_api_key,
    APIKeyScope,
    APIKeyInfo,
    APIKeyStore,
    EnvAPIKeyStore,
    DatabaseAPIKeyStore,
    CombinedAPIKeyStore,
    set_api_key_store,
)

from api.middleware.rate_limit import (
    rate_limit,
    RateLimiter,
    RateLimitInfo,
    RateLimitBackend,
    MemoryRateLimitBackend,
    RedisRateLimitBackend,
    get_rate_limiter,
    set_rate_limit_backend,
)

__all__ = [
    # API Key
    "require_api_key",
    "get_api_key",
    "generate_api_key",
    "APIKeyScope",
    "APIKeyInfo",
    "APIKeyStore",
    "EnvAPIKeyStore",
    "DatabaseAPIKeyStore",
    "CombinedAPIKeyStore",
    "set_api_key_store",
    # Rate Limiting
    "rate_limit",
    "RateLimiter",
    "RateLimitInfo",
    "RateLimitBackend",
    "MemoryRateLimitBackend",
    "RedisRateLimitBackend",
    "get_rate_limiter",
    "set_rate_limit_backend",
]
