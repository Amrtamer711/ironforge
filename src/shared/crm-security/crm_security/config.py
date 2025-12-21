"""
Security SDK Configuration.

Loaded from environment variables with sensible defaults.

Note: The SDK is a thin client that calls the security-service via HTTP.
Database connections (Supabase, Redis) are handled by the security-service,
not the SDK.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SecurityConfig(BaseSettings):
    """Security-related configuration for SDK clients."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # =========================================================================
    # ENVIRONMENT
    # =========================================================================

    environment: Literal["local", "development", "production"] = Field(
        default="local",
        description="Deployment environment",
    )

    # =========================================================================
    # PROXY TRUST (for trusted headers from gateway)
    # =========================================================================

    proxy_secret: str | None = Field(
        default=None,
        description="Shared secret from unified-ui gateway (X-Proxy-Secret header)",
    )
    trust_proxy_headers: bool = Field(
        default=True,
        description="Whether to trust X-Trusted-User-* headers from gateway",
    )

    # =========================================================================
    # SECURITY SERVICE (HTTP client settings)
    # =========================================================================

    security_service_url: str = Field(
        default="http://localhost:8002",
        description="URL of the security-service for audit logs, API keys, rate limits",
    )
    service_api_secret: str | None = Field(
        default=None,
        description="Shared secret for authenticating to security-service (X-Service-Secret)",
    )
    service_name: str = Field(
        default="unknown",
        description="This service's name (for identifying caller in logs)",
    )

    # =========================================================================
    # INTER-SERVICE AUTHENTICATION (JWT tokens)
    # =========================================================================

    inter_service_secret: str | None = Field(
        default=None,
        description="Shared secret for signing inter-service JWT tokens",
    )
    service_token_expiry_seconds: int = Field(
        default=60,
        description="How long inter-service tokens are valid (seconds)",
    )

    # =========================================================================
    # FEATURE FLAGS (local bypass settings)
    # =========================================================================

    audit_enabled: bool = Field(
        default=True,
        description="Enable audit logging (send events to security-service)",
    )
    api_keys_enabled: bool = Field(
        default=True,
        description="Enable API key authentication (validate via security-service)",
    )
    rate_limit_enabled: bool = Field(
        default=True,
        description="Enable rate limiting (check via security-service)",
    )
    rate_limit_default: int = Field(
        default=100,
        description="Default requests per minute per client",
    )

    # =========================================================================
    # DEV AUTH (for API testing via /docs in development)
    # =========================================================================

    dev_auth_enabled: bool = Field(
        default=False,
        description="Enable dev auth for testing API via /docs (only works in non-production)",
    )
    dev_auth_token: str = Field(
        default="dev-test-token-change-me",
        description="Static token for dev auth (X-Dev-Token header)",
    )
    dev_auth_user_id: str = Field(
        default="dev-user-00000000-0000-0000-0000-000000000000",
        description="User ID for dev auth test user",
    )
    dev_auth_user_email: str = Field(
        default="dev@test.local",
        description="Email for dev auth test user",
    )
    dev_auth_user_name: str = Field(
        default="Dev Tester",
        description="Display name for dev auth test user",
    )
    dev_auth_user_profile: str = Field(
        default="system_admin",
        description="RBAC profile for dev auth test user",
    )
    dev_auth_user_permissions: str = Field(
        default='["*:*:*"]',
        description="JSON array of permissions for dev auth test user",
    )
    dev_auth_user_companies: str = Field(
        default='["backlite_dubai"]',
        description="JSON array of company schemas for dev auth test user",
    )

    # =========================================================================
    # COMPUTED PROPERTIES
    # =========================================================================

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def is_local(self) -> bool:
        return self.environment == "local"


@lru_cache
def get_security_config() -> SecurityConfig:
    """Get cached security config instance."""
    return SecurityConfig()


# Global instance
security_config = get_security_config()
