"""
Configuration module for Asset Management Service.

Handles environment configuration and Supabase connection settings.
"""

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# Load environment
load_dotenv()

# Base paths
BASE_DIR = Path(__file__).parent

# =============================================================================
# ENVIRONMENT
# =============================================================================

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
IS_DEVELOPMENT = ENVIRONMENT == "development"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# =============================================================================
# SERVER
# =============================================================================

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8001"))

# =============================================================================
# SUPABASE (Asset Management Database)
# =============================================================================

# Development Supabase
ASSETMGMT_DEV_SUPABASE_URL = os.getenv("ASSETMGMT_DEV_SUPABASE_URL", "")
ASSETMGMT_DEV_SUPABASE_SERVICE_ROLE_KEY = os.getenv("ASSETMGMT_DEV_SUPABASE_SERVICE_ROLE_KEY", "")

# Production Supabase
ASSETMGMT_PROD_SUPABASE_URL = os.getenv("ASSETMGMT_PROD_SUPABASE_URL", "")
ASSETMGMT_PROD_SUPABASE_SERVICE_ROLE_KEY = os.getenv("ASSETMGMT_PROD_SUPABASE_SERVICE_ROLE_KEY", "")

# Active environment (auto-selected based on ENVIRONMENT)
SUPABASE_URL = (
    ASSETMGMT_PROD_SUPABASE_URL if ENVIRONMENT == "production"
    else ASSETMGMT_DEV_SUPABASE_URL
)
SUPABASE_SERVICE_KEY = (
    ASSETMGMT_PROD_SUPABASE_SERVICE_ROLE_KEY if ENVIRONMENT == "production"
    else ASSETMGMT_DEV_SUPABASE_SERVICE_ROLE_KEY
)

# =============================================================================
# COMPANY SCHEMAS
# =============================================================================

# Company hierarchy (same as sales-module):
#   MMG (is_group=true)
#   ├── Backlite (is_group=true)
#   │   ├── backlite_dubai (is_group=false) → has schema
#   │   ├── backlite_uk (is_group=false) → has schema
#   │   └── backlite_abudhabi (is_group=false) → has schema
#   └── viola (is_group=false) → has schema

COMPANY_SCHEMAS = ["backlite_dubai", "backlite_uk", "backlite_abudhabi", "viola"]

# =============================================================================
# INTER-SERVICE COMMUNICATION
# =============================================================================

SALES_MODULE_URL = os.getenv("SALES_MODULE_URL", "http://localhost:8000")
UNIFIED_UI_URL = os.getenv("UNIFIED_UI_URL", "http://localhost:3005")

# =============================================================================
# SECURITY
# =============================================================================

PROXY_SECRET = os.getenv("PROXY_SECRET", "")
INTER_SERVICE_SECRET = os.getenv("INTER_SERVICE_SECRET", "")
SERVICE_NAME = "asset-management"

# =============================================================================
# CORS
# =============================================================================

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "")


def get_cors_origins_list() -> list[str]:
    """Parse CORS_ORIGINS env var into a list."""
    if not CORS_ORIGINS:
        if IS_DEVELOPMENT:
            return ["*"]
        return [UNIFIED_UI_URL]
    return [origin.strip() for origin in CORS_ORIGINS.split(",") if origin.strip()]


# =============================================================================
# LOGGING SETUP
# =============================================================================

import logging

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# Quiet down noisy third-party loggers
for _logger_name in [
    "httpx", "httpcore", "httpcore.http2", "httpcore.connection",
    "urllib3", "hpack", "hpack.hpack", "hpack.table",
    "openai", "openai._base_client",
]:
    logging.getLogger(_logger_name).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name."""
    return logging.getLogger(name)


logger = get_logger("asset-management")
