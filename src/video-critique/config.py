"""
Configuration module for the Video Critique Service.

This module handles:
- Environment detection and configuration
- Database backend configuration (Supabase)
- Channel abstraction initialization (Slack + Web)
- LLM provider configuration
- Trello and Dropbox integration settings
- Structured logging setup
"""

import os
from pathlib import Path
from typing import Any

import pytz
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Base paths
BASE_DIR = Path(__file__).parent

# ============================================================================
# ENVIRONMENT DETECTION
# ============================================================================

# Production detection - single source of truth
# We're in production if ANY of these are true:
# 1. Running on Render (has RENDER env var)
# 2. Explicitly set PRODUCTION=true or ENVIRONMENT=production
# NOTE: Do NOT check for PORT (run_service.py sets it) or /data (may exist locally)
IS_PRODUCTION = any([
    os.environ.get("RENDER") == "true",
    os.environ.get("PRODUCTION") == "true",
    os.environ.get("ENVIRONMENT") == "production",
])
IS_DEVELOPMENT = not IS_PRODUCTION

# ============================================================================
# LOGGING SETUP
# ============================================================================

from core.utils.logging import get_logger, setup_logging

_log_level = os.getenv("LOG_LEVEL", "INFO")

setup_logging(
    level=_log_level,
    json_format=IS_PRODUCTION,
    module_levels={
        "httpx": "WARNING",
        "httpcore": "WARNING",
        "urllib3": "WARNING",
        "asyncio": "WARNING",
        "uvicorn.access": "WARNING",
        "openai": "WARNING",
        "openai._base_client": "WARNING",
        "hpack": "WARNING",
        "slack_sdk": "WARNING",
    }
)

logger = get_logger("video-critique")

if IS_PRODUCTION:
    logger.info("[STARTUP] Running in PRODUCTION mode - using /data/ paths")
else:
    logger.info("[STARTUP] Running in DEVELOPMENT mode - using local paths")

# ============================================================================
# TIMEZONE CONFIGURATION
# ============================================================================

UAE_TZ = pytz.timezone('Asia/Dubai')

# ============================================================================
# DATABASE CONFIGURATION (Supabase)
# ============================================================================

DB_BACKEND = os.getenv("DB_BACKEND", "supabase")

# Environment-based Supabase credentials
# DEV branch -> *_DEV_* env vars
# MAIN branch -> *_PROD_* env vars
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

if ENVIRONMENT == "production":
    SUPABASE_URL = os.getenv("VIDEOCRITIQUE_PROD_SUPABASE_URL", "")
    SUPABASE_SERVICE_ROLE_KEY = os.getenv("VIDEOCRITIQUE_PROD_SUPABASE_SERVICE_ROLE_KEY", "")
else:
    SUPABASE_URL = os.getenv("VIDEOCRITIQUE_DEV_SUPABASE_URL", "")
    SUPABASE_SERVICE_ROLE_KEY = os.getenv("VIDEOCRITIQUE_DEV_SUPABASE_SERVICE_ROLE_KEY", "")

# Supabase timeout configuration
SUPABASE_TIMEOUT = int(os.getenv("SUPABASE_TIMEOUT", "30"))

logger.info(f"[STARTUP] Database backend: {DB_BACKEND}")
logger.info(f"[STARTUP] Environment: {ENVIRONMENT}")

# ============================================================================
# CHANNEL CONFIGURATION (Slack + Web)
# ============================================================================

# Slack credentials
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET", "")

# Slack message close behavior: 'delete' or 'resolve'
SLACK_CLOSE_MODE = os.getenv("SLACK_CLOSE_MODE", "delete").lower()
if SLACK_CLOSE_MODE not in ("delete", "resolve"):
    SLACK_CLOSE_MODE = "delete"

# Channel initialization flag
_channel_initialized = False


def init_channels() -> None:
    """
    Initialize the channel abstraction layer.

    Call this once at startup to register all channel adapters.
    """
    global _channel_initialized
    if _channel_initialized:
        return

    from slack_sdk.web.async_client import AsyncWebClient
    from slack_sdk.signature import SignatureVerifier

    from integrations.channels import SlackAdapter, register_channel

    # Initialize Slack adapter
    if SLACK_BOT_TOKEN:
        slack_client = AsyncWebClient(token=SLACK_BOT_TOKEN)
        slack_adapter = SlackAdapter(client=slack_client, bot_token=SLACK_BOT_TOKEN)
        register_channel(slack_adapter)
        logger.info("[CHANNELS] Registered Slack adapter")
    else:
        logger.warning("[CHANNELS] No SLACK_BOT_TOKEN - Slack adapter not registered")

    _channel_initialized = True
    logger.info("[CHANNELS] Channel abstraction initialized")


def get_channel_adapter(channel_type: str | None = None):
    """
    Get a channel adapter.

    Args:
        channel_type: Specific channel type ("slack", "web", etc.) or None for active

    Returns:
        ChannelAdapter instance
    """
    if not _channel_initialized:
        init_channels()

    from integrations.channels import get_channel
    return get_channel(channel_type)


def set_channel_adapter(adapter):
    """
    Set the active channel adapter.

    Used by web chat to register the WebAdapter before calling main_llm_loop,
    ensuring tool execution uses the correct channel.

    Args:
        adapter: ChannelAdapter instance to set as active
    """
    from integrations.channels import register_channel, set_channel
    # Register the adapter first (if not already registered)
    register_channel(adapter)
    # Then set it as active by its channel type
    set_channel(adapter.channel_type.value)


# Signature verifier for Slack webhooks (lazy initialization)
_signature_verifier = None


def get_signature_verifier():
    """Get Slack signature verifier (lazy initialization)."""
    global _signature_verifier
    if _signature_verifier is None and SLACK_SIGNING_SECRET:
        from slack_sdk.signature import SignatureVerifier
        _signature_verifier = SignatureVerifier(SLACK_SIGNING_SECRET)
    return _signature_verifier


# ============================================================================
# LLM PROVIDER CONFIGURATION
# ============================================================================

# Provider selection
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")

# API Keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

# Model configuration
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
OPENAI_VISION_MODEL = os.getenv("OPENAI_VISION_MODEL", "gpt-4o")

logger.info(f"[STARTUP] LLM provider: {LLM_PROVIDER}")

# ============================================================================
# SECURITY CONFIGURATION
# ============================================================================

# Auth provider (supabase to validate UI-issued JWTs)
AUTH_PROVIDER = os.getenv("AUTH_PROVIDER", "supabase")

# UI JWT Secret (for validating tokens issued by UI Supabase)
UI_JWT_SECRET = os.getenv("UI_JWT_SECRET", "")

# Proxy secret (shared with unified-ui to prevent header spoofing)
PROXY_SECRET = os.getenv("PROXY_SECRET", "")

# Security Service URL (for SDK calls)
SECURITY_SERVICE_URL = os.getenv("SECURITY_SERVICE_URL", "https://crm-security-service.onrender.com")

# Asset Management Service URL
ASSET_MGMT_URL = os.getenv("ASSET_MGMT_URL", "https://crm-asset-management.onrender.com")

# Unified UI URL (for channel identity API)
UNIFIED_UI_URL = os.getenv("UNIFIED_UI_URL", "https://crm-unified-ui.onrender.com")

# Inter-service auth secret
INTER_SERVICE_SECRET = os.getenv("INTER_SERVICE_SECRET", "")

# ============================================================================
# TRELLO CONFIGURATION
# ============================================================================

TRELLO_API_KEY = os.getenv("TRELLO_API_KEY", "")
TRELLO_API_TOKEN = os.getenv("TRELLO_API_TOKEN", "")

# Dev vs Prod board names - use separate boards for development
# Set TRELLO_BOARD_NAME_DEV in .env to use a different board in dev mode
_TRELLO_BOARD_PROD = os.getenv("TRELLO_BOARD_NAME", "Amr - Tracker")
_TRELLO_BOARD_DEV = os.getenv("TRELLO_BOARD_NAME_DEV", "Video Critique - DEV")
TRELLO_BOARD_NAME = _TRELLO_BOARD_PROD if IS_PRODUCTION else _TRELLO_BOARD_DEV

logger.info(f"[STARTUP] Trello board: {TRELLO_BOARD_NAME} ({'PROD' if IS_PRODUCTION else 'DEV'})")

# ============================================================================
# DROPBOX CONFIGURATION
# ============================================================================

DROPBOX_APP_KEY = os.getenv("DROPBOX_APP_KEY", "")
DROPBOX_APP_SECRET = os.getenv("DROPBOX_APP_SECRET", "")
DROPBOX_REFRESH_TOKEN = os.getenv("DROPBOX_REFRESH_TOKEN", "")

# Dropbox folder prefix - dev uses /test prefix to avoid touching production folders
# Prod folders: /Site Videos/Raw, /Site Videos/Pending, etc.
# Dev folders:  /test/Site Videos/Raw, /test/Site Videos/Pending, etc.
_DROPBOX_FOLDER_PREFIX_PROD = os.getenv("DROPBOX_FOLDER_PREFIX", "")
_DROPBOX_FOLDER_PREFIX_DEV = os.getenv("DROPBOX_FOLDER_PREFIX_DEV", "/test")
DROPBOX_FOLDER_PREFIX = _DROPBOX_FOLDER_PREFIX_PROD if IS_PRODUCTION else _DROPBOX_FOLDER_PREFIX_DEV

logger.info(f"[STARTUP] Dropbox folder prefix: '{DROPBOX_FOLDER_PREFIX}' ({'PROD' if IS_PRODUCTION else 'DEV'})")

# Legacy: Root folder for general uploads (not used for Site Videos workflow)
DROPBOX_ROOT_FOLDER = os.getenv("DROPBOX_ROOT_FOLDER", "/Video Submissions")

# ============================================================================
# EMAIL CONFIGURATION
# ============================================================================

EMAIL_SENDER = os.getenv("EMAIL_SENDER", "")
EMAIL_APP_PASSWORD = os.getenv("APP_PSWD", "")

# Email recipients
REVIEWER_EMAIL = os.getenv("REVIEWER_EMAIL", "")
HEAD_OF_DEPT_EMAIL = os.getenv("HEAD_OF_DEPT_EMAIL", "")
HEAD_OF_SALES_EMAIL = os.getenv("HEAD_OF_SALES_EMAIL", "")

# ============================================================================
# SCHEDULING CONFIGURATION
# ============================================================================

# UAE weekend days (Friday=4, Saturday=5 in Python weekday())
WEEKEND_DAYS = {4, 5}

# Campaign lookahead for task creation
CAMPAIGN_LOOKAHEAD_WORKING_DAYS = 10

# Planning offset
PLANNING_OFFSET_DAYS = 1

# Video task offset
VIDEO_TASK_OFFSET_WORKING_DAYS = 2

# Testing mode (use shorter delays)
TESTING_MODE = os.getenv("TESTING_MODE", "false").lower() == "true"
ESCALATION_DELAY_SECONDS = 10 if TESTING_MODE else 0

# ============================================================================
# CACHE CONFIGURATION
# ============================================================================

CACHE_BACKEND = os.getenv("CACHE_BACKEND", "memory")
REDIS_URL = os.getenv("REDIS_URL", "")

logger.info(f"[STARTUP] Cache backend: {CACHE_BACKEND}")
