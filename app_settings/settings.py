"""
Pydantic Settings for the Sales Proposals Bot.

This module provides type-safe, validated configuration using Pydantic BaseSettings.
Environment variables are automatically loaded and validated at startup.

Usage:
    from app_settings import settings

    # Access settings
    print(settings.slack_bot_token)
    print(settings.is_production)
"""

import os
from pathlib import Path
from typing import Literal, Optional
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    All settings are validated at startup. Missing required settings
    will raise a validation error.
    """

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
        description="Application environment: local (SQLite), development (DEV Supabase), production (PROD Supabase)",
    )
    debug: bool = Field(
        default=False,
        description="Enable debug mode",
    )

    # =========================================================================
    # PATHS
    # =========================================================================

    data_dir: Optional[str] = Field(
        default=None,
        description="Base directory for persistent data (auto-detected if not set)",
    )
    templates_dir: Optional[str] = Field(
        default=None,
        description="Directory containing location templates",
    )

    # =========================================================================
    # DATABASE
    # =========================================================================

    db_backend: Literal["sqlite", "supabase"] = Field(
        default="sqlite",
        description="Database backend to use",
    )
    database_url: Optional[str] = Field(
        default=None,
        description="Database connection URL (for direct DB access)",
    )

    # =========================================================================
    # SALES BOT SUPABASE (Data storage - separate from UI)
    # =========================================================================

    # Development
    salesbot_dev_supabase_url: Optional[str] = Field(
        default=None,
        description="Sales Bot DEV Supabase project URL",
    )
    salesbot_dev_supabase_anon_key: Optional[str] = Field(
        default=None,
        description="Sales Bot DEV Supabase anon key",
    )
    salesbot_dev_supabase_service_role_key: Optional[str] = Field(
        default=None,
        description="Sales Bot DEV Supabase service role key",
    )

    # Production
    salesbot_prod_supabase_url: Optional[str] = Field(
        default=None,
        description="Sales Bot PROD Supabase project URL",
    )
    salesbot_prod_supabase_anon_key: Optional[str] = Field(
        default=None,
        description="Sales Bot PROD Supabase anon key",
    )
    salesbot_prod_supabase_service_role_key: Optional[str] = Field(
        default=None,
        description="Sales Bot PROD Supabase service role key",
    )

    # Legacy single-project config (backwards compatibility)
    supabase_url: Optional[str] = Field(
        default=None,
        description="Supabase project URL (legacy, use SALESBOT_*_SUPABASE_URL instead)",
    )
    supabase_service_key: Optional[str] = Field(
        default=None,
        description="Supabase service role key (legacy)",
    )
    supabase_jwt_secret: Optional[str] = Field(
        default=None,
        description="Supabase JWT secret for token validation",
    )

    # =========================================================================
    # UI JWT SECRET (for validating tokens from UI Supabase)
    # NOTE: proposal-bot only needs the JWT secret to validate tokens.
    # UI Supabase URL/keys are managed by unified-ui (Node.js service).
    # =========================================================================

    ui_jwt_secret: Optional[str] = Field(
        default=None,
        description="JWT secret from UI's Supabase project (for cross-service auth)",
    )

    # =========================================================================
    # AUTHENTICATION
    # =========================================================================

    auth_provider: Literal["local", "supabase"] = Field(
        default="local",
        description="Authentication provider to use",
    )
    jwt_secret: Optional[str] = Field(
        default=None,
        description="JWT secret for token signing (falls back to supabase_jwt_secret)",
    )

    # =========================================================================
    # LLM PROVIDERS
    # =========================================================================

    llm_provider: Literal["openai", "google"] = Field(
        default="openai",
        description="LLM provider for text completions",
    )
    image_provider: Literal["openai", "google"] = Field(
        default="google",
        description="Provider for image generation",
    )

    # OpenAI
    openai_api_key: Optional[str] = Field(
        default=None,
        description="OpenAI API key",
    )

    # Google
    google_api_key: Optional[str] = Field(
        default=None,
        description="Google AI API key",
    )

    # =========================================================================
    # SLACK
    # =========================================================================

    slack_bot_token: Optional[str] = Field(
        default=None,
        description="Slack bot OAuth token",
    )
    slack_signing_secret: Optional[str] = Field(
        default=None,
        description="Slack request signing secret",
    )

    # =========================================================================
    # STORAGE
    # =========================================================================

    storage_provider: Literal["local", "supabase", "s3"] = Field(
        default="local",
        description="File storage provider",
    )

    # AWS S3 (optional)
    aws_access_key_id: Optional[str] = Field(
        default=None,
        description="AWS access key ID",
    )
    aws_secret_access_key: Optional[str] = Field(
        default=None,
        description="AWS secret access key",
    )
    aws_s3_bucket: Optional[str] = Field(
        default=None,
        description="AWS S3 bucket name",
    )
    aws_region: str = Field(
        default="me-south-1",
        description="AWS region",
    )

    # =========================================================================
    # CACHING
    # =========================================================================

    cache_backend: Literal["memory", "redis"] = Field(
        default="memory",
        description="Cache backend: memory (single instance) or redis (distributed)",
    )
    cache_default_ttl: Optional[int] = Field(
        default=300,
        description="Default cache TTL in seconds (None for no expiry)",
    )
    cache_max_size: int = Field(
        default=1000,
        description="Maximum entries for memory cache",
    )

    # =========================================================================
    # REDIS
    # =========================================================================

    redis_url: Optional[str] = Field(
        default=None,
        description="Redis connection URL (e.g., redis://localhost:6379)",
    )

    # =========================================================================
    # RATE LIMITING
    # =========================================================================

    rate_limit_enabled: bool = Field(
        default=True,
        description="Enable rate limiting on API endpoints (enabled by default for security)",
    )
    rate_limit_backend: Literal["memory", "redis"] = Field(
        default="memory",
        description="Rate limit storage backend",
    )
    rate_limit_default: int = Field(
        default=100,
        description="Default requests per minute per client",
    )

    # =========================================================================
    # JOB QUEUE
    # =========================================================================

    job_queue_max_concurrent: int = Field(
        default=5,
        description="Maximum concurrent background jobs",
    )
    job_queue_default_timeout: float = Field(
        default=600.0,
        description="Default job timeout in seconds",
    )

    # =========================================================================
    # API KEYS
    # =========================================================================

    api_key_store: Literal["env", "database", "combined"] = Field(
        default="combined",
        description="API key storage: env (environment), database, or combined",
    )
    api_keys_enabled: bool = Field(
        default=True,
        description="Enable API key authentication",
    )

    # =========================================================================
    # RBAC
    # =========================================================================

    rbac_provider: Literal["local", "database"] = Field(
        default="local",
        description="RBAC provider for role-based access control",
    )

    # =========================================================================
    # PROXY SECURITY
    # =========================================================================

    proxy_secret: Optional[str] = Field(
        default=None,
        description="Shared secret for trusted proxy communication (unified-ui -> proposal-bot)",
    )

    # =========================================================================
    # API SETTINGS
    # =========================================================================

    api_host: str = Field(
        default="0.0.0.0",
        description="API server host",
    )
    api_port: int = Field(
        default=8000,
        description="API server port",
    )
    cors_origins: str = Field(
        default="http://localhost:3005,http://localhost:3000",
        description="Comma-separated list of allowed CORS origins",
    )

    # =========================================================================
    # BUSINESS SETTINGS
    # =========================================================================

    default_currency: str = Field(
        default="AED",
        description="Default currency for proposals",
    )

    # =========================================================================
    # EXTERNAL URLS
    # =========================================================================

    render_external_url: Optional[str] = Field(
        default=None,
        description="External URL for render service (mockup generation)",
    )

    # =========================================================================
    # LOGGING
    # =========================================================================

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Application log level",
    )

    # =========================================================================
    # PDF GENERATION
    # =========================================================================

    pdf_convert_concurrency: int = Field(
        default=3,
        description="Maximum concurrent PDF conversion workers",
    )

    # =========================================================================
    # COSTS / ADMIN
    # =========================================================================

    costs_clear_auth_code: Optional[str] = Field(
        default=None,
        description="Authorization code for clearing AI costs data",
    )

    # =========================================================================
    # COMPUTED PROPERTIES
    # =========================================================================

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment (DEV Supabase)."""
        return self.environment == "development"

    @property
    def is_local(self) -> bool:
        """Check if running in local environment (SQLite)."""
        return self.environment == "local"

    @property
    def base_dir(self) -> Path:
        """Get the project base directory."""
        return Path(__file__).parent.parent

    @property
    def resolved_data_dir(self) -> Path:
        """Get the resolved data directory path."""
        if self.data_dir:
            return Path(self.data_dir)
        # Use /data/ on Render (mounted disk), otherwise local data/
        if os.path.exists("/data/"):
            return Path("/data")
        return self.base_dir / "data"

    @property
    def resolved_templates_dir(self) -> Path:
        """Get the resolved templates directory path."""
        if self.templates_dir:
            return Path(self.templates_dir)
        return self.resolved_data_dir / "templates"

    @property
    def cors_origins_list(self) -> list[str]:
        """Get CORS origins as a list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def effective_jwt_secret(self) -> Optional[str]:
        """Get the JWT secret for validating UI tokens."""
        # Prefer UI JWT secret (for cross-service auth), fall back to legacy
        return self.ui_jwt_secret or self.jwt_secret or self.supabase_jwt_secret

    @property
    def active_supabase_url(self) -> Optional[str]:
        """Get the active Supabase URL based on ENVIRONMENT setting."""
        if self.environment == "production":
            return self.salesbot_prod_supabase_url or self.supabase_url
        elif self.environment == "development":
            return self.salesbot_dev_supabase_url or self.supabase_url
        # local environment - no Supabase, uses SQLite
        return None

    @property
    def active_supabase_anon_key(self) -> Optional[str]:
        """Get the active Supabase anon key based on ENVIRONMENT setting."""
        if self.environment == "production":
            return self.salesbot_prod_supabase_anon_key
        elif self.environment == "development":
            return self.salesbot_dev_supabase_anon_key
        return None

    @property
    def active_supabase_service_key(self) -> Optional[str]:
        """Get the active Supabase service role key based on ENVIRONMENT setting."""
        if self.environment == "production":
            return self.salesbot_prod_supabase_service_role_key or self.supabase_service_key
        elif self.environment == "development":
            return self.salesbot_dev_supabase_service_role_key or self.supabase_service_key
        return None

    # =========================================================================
    # VALIDATION
    # =========================================================================

    @field_validator("default_currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        """Ensure currency is uppercase."""
        return v.upper()

    def validate_production_secrets(self) -> list[str]:
        """
        Validate that required secrets are set in production.

        Returns list of missing secret names, or empty list if all present.
        Call this at startup to fail fast if misconfigured.
        """
        if not self.is_production:
            return []

        missing = []

        # LLM API keys - at least one must be set
        if not self.openai_api_key and not self.google_api_key:
            missing.append("OPENAI_API_KEY or GOOGLE_API_KEY")

        # Database credentials for production
        if self.db_backend == "supabase":
            if not self.active_supabase_url:
                missing.append("SALESBOT_PROD_SUPABASE_URL")
            if not self.active_supabase_service_key:
                missing.append("SALESBOT_PROD_SUPABASE_SERVICE_ROLE_KEY")

        # JWT secret for auth
        if not self.effective_jwt_secret:
            missing.append("UI_JWT_SECRET or JWT_SECRET")

        # Proxy secret for secure communication with unified-ui
        if not self.proxy_secret:
            missing.append("PROXY_SECRET")

        return missing


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Uses lru_cache to ensure settings are only loaded once.
    """
    return Settings()


# Global settings instance
settings = get_settings()

# Validate production secrets at import time
_missing_secrets = settings.validate_production_secrets()
if _missing_secrets:
    import sys
    print(f"[FATAL] Missing required secrets for production: {', '.join(_missing_secrets)}", file=sys.stderr)
    print("[FATAL] Set these environment variables or set ENVIRONMENT to 'development' or 'local'", file=sys.stderr)
    sys.exit(1)
