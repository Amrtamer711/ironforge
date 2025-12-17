"""
Environment configuration for unified-ui FastAPI backend.

[VERIFIED] Mirrors server.js lines 14-148:
- Environment detection (lines 14-20)
- Supabase configuration (lines 22-47)
- Service registry (lines 49-62)
- Rate limiting config (lines 64-102)
- CORS configuration (lines 104-148)
"""

import logging
from functools import lru_cache

from pydantic_settings import BaseSettings

logger = logging.getLogger("unified-ui")


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Mirrors server.js environment handling exactly.
    """

    # ==========================================================================
    # ENVIRONMENT DETECTION - server.js:14-20
    # ==========================================================================
    ENVIRONMENT: str = "development"  # 'local', 'development', 'production'

    # Port - server.js:12
    PORT: int = 3005

    # ==========================================================================
    # UI SUPABASE CONFIGURATION - server.js:22-47
    # unified-ui owns authentication - these are for the UI Supabase project
    # ==========================================================================

    # Production keys (used when ENVIRONMENT == 'production')
    UI_PROD_SUPABASE_URL: str | None = None
    UI_PROD_SUPABASE_SERVICE_ROLE_KEY: str | None = None
    UI_PROD_SUPABASE_ANON_KEY: str | None = None

    # Development keys (used when ENVIRONMENT != 'production')
    UI_DEV_SUPABASE_URL: str | None = None
    UI_DEV_SUPABASE_SERVICE_ROLE_KEY: str | None = None
    UI_DEV_SUPABASE_ANON_KEY: str | None = None

    # Fallback keys (for backwards compatibility) - server.js:28-37
    SUPABASE_URL: str | None = None
    SUPABASE_SERVICE_KEY: str | None = None
    SUPABASE_ANON_KEY: str | None = None

    # ==========================================================================
    # SERVICE REGISTRY - server.js:49-55
    # URL for the backend API service (proxied requests)
    # ==========================================================================
    SALES_BOT_URL: str | None = None  # Required: set via environment variable

    # ==========================================================================
    # PROXY SECRET - server.js:57-62
    # Shared secret for trusted proxy communication
    # ==========================================================================
    PROXY_SECRET: str | None = None

    # ==========================================================================
    # RATE LIMITING - server.js:64-102
    # Simple in-memory rate limiter configuration
    # ==========================================================================
    RATE_LIMIT_WINDOW_MS: int = 60000  # 1 minute (60 * 1000)
    RATE_LIMIT_MAX_REQUESTS: int = 10  # max requests per window for auth endpoints

    # ==========================================================================
    # CORS CONFIGURATION - server.js:104-148
    # ==========================================================================
    CORS_ORIGINS: str = ""  # Comma-separated list of additional origins
    RENDER_EXTERNAL_URL: str | None = None  # Auto-set by Render

    # ==========================================================================
    # RBAC CACHE - server.js:519-521
    # ==========================================================================
    RBAC_CACHE_TTL_SECONDS: int = 30  # 30 second TTL - reduced for faster permission propagation

    class Config:
        env_file = ".env"
        extra = "ignore"

    # ==========================================================================
    # COMPUTED PROPERTIES - Mirror server.js logic exactly
    # ==========================================================================

    @property
    def is_production(self) -> bool:
        """
        Check if running in production.
        Mirrors: server.js:18 - const IS_PRODUCTION = ENVIRONMENT === 'production';
        """
        return self.ENVIRONMENT == "production"

    @property
    def is_local(self) -> bool:
        """
        Check if running in local environment.
        Mirrors: server.js:108 - const IS_LOCAL = ENVIRONMENT === 'local';
        """
        return self.ENVIRONMENT == "local"

    @property
    def supabase_url(self) -> str | None:
        """
        Get the appropriate Supabase URL based on environment.

        Mirrors server.js:27-29:
        const supabaseUrl = IS_PRODUCTION
          ? (process.env.UI_PROD_SUPABASE_URL || process.env.SUPABASE_URL)
          : (process.env.UI_DEV_SUPABASE_URL || process.env.SUPABASE_URL);
        """
        if self.is_production:
            return self.UI_PROD_SUPABASE_URL or self.SUPABASE_URL
        return self.UI_DEV_SUPABASE_URL or self.SUPABASE_URL

    @property
    def supabase_service_key(self) -> str | None:
        """
        Get the appropriate Supabase service key based on environment.

        Mirrors server.js:31-33:
        const supabaseServiceKey = IS_PRODUCTION
          ? (process.env.UI_PROD_SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_SERVICE_KEY)
          : (process.env.UI_DEV_SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_SERVICE_KEY);
        """
        if self.is_production:
            return self.UI_PROD_SUPABASE_SERVICE_ROLE_KEY or self.SUPABASE_SERVICE_KEY
        return self.UI_DEV_SUPABASE_SERVICE_ROLE_KEY or self.SUPABASE_SERVICE_KEY

    @property
    def supabase_anon_key(self) -> str | None:
        """
        Get the appropriate Supabase anon key based on environment.

        Mirrors server.js:35-37:
        const supabaseAnonKey = IS_PRODUCTION
          ? (process.env.UI_PROD_SUPABASE_ANON_KEY || process.env.SUPABASE_ANON_KEY)
          : (process.env.UI_DEV_SUPABASE_ANON_KEY || process.env.SUPABASE_ANON_KEY);
        """
        if self.is_production:
            return self.UI_PROD_SUPABASE_ANON_KEY or self.SUPABASE_ANON_KEY
        return self.UI_DEV_SUPABASE_ANON_KEY or self.SUPABASE_ANON_KEY

    @property
    def allowed_origins(self) -> list[str]:
        """
        Get allowed CORS origins based on environment.

        Mirrors server.js:111-124:
        if (IS_LOCAL) {
          ALLOWED_ORIGINS = ['http://localhost:3000', 'http://localhost:3005', ...];
        } else {
          if (RENDER_EXTERNAL_URL) { ALLOWED_ORIGINS.push(RENDER_EXTERNAL_URL); }
          const extraOrigins = (process.env.CORS_ORIGINS || '').split(',')...;
          ALLOWED_ORIGINS.push(...extraOrigins);
        }
        """
        if self.is_local:
            return [
                "http://localhost:3000",
                "http://localhost:3005",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:3005",
            ]

        origins = []
        if self.RENDER_EXTERNAL_URL:
            origins.append(self.RENDER_EXTERNAL_URL)

        if self.CORS_ORIGINS:
            extra = [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]
            origins.extend(extra)

        return origins

    def log_config(self) -> None:
        """
        Log configuration on startup.
        Mirrors server.js:20, 148, 4173-4176
        """
        logger.info(f"[UI] Environment: {self.ENVIRONMENT} (production: {self.is_production})")

        if not self.supabase_url or not self.supabase_service_key:
            logger.warning("Warning: UI Supabase credentials not configured.")
            logger.warning(
                "Set UI_DEV_SUPABASE_URL and UI_DEV_SUPABASE_SERVICE_ROLE_KEY "
                "(or UI_PROD_* for production)"
            )

        if not self.PROXY_SECRET:
            logger.warning(
                "[UI] WARNING: PROXY_SECRET not set. "
                "Trusted headers may be vulnerable to spoofing."
            )
            logger.warning(
                "[UI] Set PROXY_SECRET environment variable "
                "(must match the backend API service)"
            )

        if not self.is_local and not self.allowed_origins:
            logger.warning(
                "[UI] WARNING: No CORS origins configured. "
                "Ensure RENDER_EXTERNAL_URL is set or add CORS_ORIGINS."
            )

        origins_str = (
            ", ".join(self.allowed_origins)
            if self.allowed_origins
            else "(all - development mode)"
        )
        logger.info(f"[UI] CORS allowed origins: {origins_str}")
        logger.info(f"[UI] Backend API URL: {self.SALES_BOT_URL or '(not configured)'}")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
