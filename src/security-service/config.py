"""
Environment configuration for security-service.

Centralized auth, RBAC, and audit logging service.
All other services communicate with this via REST API.
"""

import logging
from functools import lru_cache

from pydantic_settings import BaseSettings

logger = logging.getLogger("security-service")


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    """

    # ==========================================================================
    # ENVIRONMENT DETECTION
    # ==========================================================================
    ENVIRONMENT: str = "local"  # 'local', 'development', 'production'
    HOST: str = "0.0.0.0"
    PORT: int = 8002
    LOG_LEVEL: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL

    # ==========================================================================
    # SERVICE IDENTIFICATION
    # Used for inter-service authentication and audit logging
    # ==========================================================================
    SERVICE_NAME: str = "security-service"
    INTER_SERVICE_SECRET: str | None = None  # Shared secret for inter-service auth

    # ==========================================================================
    # UI SUPABASE (Read-only)
    # For user/profile lookups - security-service reads from UI Supabase
    # ==========================================================================

    # Production keys (used when ENVIRONMENT == 'production')
    UI_PROD_SUPABASE_URL: str | None = None
    UI_PROD_SUPABASE_SERVICE_ROLE_KEY: str | None = None

    # Development keys (used when ENVIRONMENT != 'production')
    UI_DEV_SUPABASE_URL: str | None = None
    UI_DEV_SUPABASE_SERVICE_ROLE_KEY: str | None = None

    # ==========================================================================
    # SECURITY SUPABASE (Read/Write)
    # Owns audit_logs, api_keys, rate_limit_state, security_events tables
    # ==========================================================================

    # Production keys (used when ENVIRONMENT == 'production')
    SECURITY_PROD_SUPABASE_URL: str | None = None
    SECURITY_PROD_SUPABASE_SERVICE_ROLE_KEY: str | None = None

    # Development keys (used when ENVIRONMENT != 'production')
    SECURITY_DEV_SUPABASE_URL: str | None = None
    SECURITY_DEV_SUPABASE_SERVICE_ROLE_KEY: str | None = None

    # ==========================================================================
    # JWT CONFIGURATION
    # For service-to-service token signing
    # ==========================================================================
    JWT_SECRET: str | None = None  # Falls back to SERVICE_API_SECRET if not set
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_SECONDS: int = 3600  # 1 hour for user tokens
    SERVICE_TOKEN_EXPIRY_SECONDS: int = 60  # Short-lived for service tokens

    # ==========================================================================
    # AUDIT LOGGING CONFIGURATION
    # ==========================================================================
    AUDIT_ENABLED: bool = True
    AUDIT_LOG_REQUEST_BODY: bool = False  # Careful with PII
    AUDIT_RETENTION_DAYS: int = 90

    # ==========================================================================
    # RATE LIMITING CONFIGURATION
    # ==========================================================================
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_DEFAULT: int = 100  # Max requests per window
    RATE_LIMIT_WINDOW_SECONDS: int = 60  # Window size (1 minute)
    RATE_LIMIT_DEFAULT_PER_MINUTE: int = 100
    RATE_LIMIT_DEFAULT_PER_DAY: int = 10000

    # ==========================================================================
    # CORS CONFIGURATION
    # ==========================================================================
    CORS_ORIGINS: str = ""  # Comma-separated list of allowed origins

    class Config:
        env_file = ".env"
        extra = "ignore"

    # ==========================================================================
    # COMPUTED PROPERTIES
    # ==========================================================================

    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.ENVIRONMENT == "production"

    @property
    def is_local(self) -> bool:
        """Check if running in local environment."""
        return self.ENVIRONMENT == "local"

    @property
    def ui_supabase_url(self) -> str | None:
        """Get the appropriate UI Supabase URL based on environment."""
        if self.is_production:
            return self.UI_PROD_SUPABASE_URL
        return self.UI_DEV_SUPABASE_URL

    @property
    def ui_supabase_key(self) -> str | None:
        """Get the appropriate UI Supabase service key based on environment."""
        if self.is_production:
            return self.UI_PROD_SUPABASE_SERVICE_ROLE_KEY
        return self.UI_DEV_SUPABASE_SERVICE_ROLE_KEY

    @property
    def security_supabase_url(self) -> str | None:
        """Get the appropriate Security Supabase URL based on environment."""
        if self.is_production:
            return self.SECURITY_PROD_SUPABASE_URL
        return self.SECURITY_DEV_SUPABASE_URL

    @property
    def security_supabase_key(self) -> str | None:
        """Get the appropriate Security Supabase service key based on environment."""
        if self.is_production:
            return self.SECURITY_PROD_SUPABASE_SERVICE_ROLE_KEY
        return self.SECURITY_DEV_SUPABASE_SERVICE_ROLE_KEY

    @property
    def jwt_signing_secret(self) -> str | None:
        """Get JWT signing secret, falling back to INTER_SERVICE_SECRET."""
        return self.JWT_SECRET or self.INTER_SERVICE_SECRET

    @property
    def allowed_origins(self) -> list[str]:
        """Get allowed CORS origins based on environment."""
        if self.is_local:
            return [
                "http://localhost:3000",
                "http://localhost:3005",
                "http://localhost:8000",
                "http://localhost:8001",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:3005",
            ]

        if not self.CORS_ORIGINS:
            return []

        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    def log_config(self) -> None:
        """Log configuration on startup."""
        logger.info(f"[SECURITY] Environment: {self.ENVIRONMENT} (production: {self.is_production})")
        logger.info(f"[SECURITY] Host: {self.HOST}:{self.PORT}")

        # Check UI Supabase
        if not self.ui_supabase_url or not self.ui_supabase_key:
            logger.warning("[SECURITY] WARNING: UI Supabase credentials not configured.")
            logger.warning("[SECURITY] User/profile lookups will not work.")

        # Check Security Supabase
        if not self.security_supabase_url or not self.security_supabase_key:
            logger.warning("[SECURITY] WARNING: Security Supabase credentials not configured.")
            logger.warning("[SECURITY] Audit logs and API keys will use local-only mode.")

        # Check service secret
        if not self.INTER_SERVICE_SECRET:
            logger.warning("[SECURITY] WARNING: INTER_SERVICE_SECRET not set.")
            logger.warning("[SECURITY] Inter-service authentication will be disabled.")

        # Log feature status
        logger.info(f"[SECURITY] Audit logging: {'enabled' if self.AUDIT_ENABLED else 'disabled'}")
        logger.info(f"[SECURITY] Rate limiting: {'enabled' if self.RATE_LIMIT_ENABLED else 'disabled'}")

        origins_str = ", ".join(self.allowed_origins) if self.allowed_origins else "(local only)"
        logger.info(f"[SECURITY] CORS allowed origins: {origins_str}")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Global settings instance
settings = get_settings()


# ==========================================================================
# LOGGING HELPERS
# ==========================================================================

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Configure root logger
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format=LOG_FORMAT,
)

# Quiet down noisy third-party loggers
for _logger_name in [
    "httpx", "httpcore", "httpcore.http2", "httpcore.connection",
    "urllib3", "hpack", "hpack.hpack", "hpack.table",
    "openai", "openai._base_client",
]:
    logging.getLogger(_logger_name).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a configured logger instance."""
    log = logging.getLogger(name)
    if not log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        log.addHandler(handler)
        log.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
    return log
