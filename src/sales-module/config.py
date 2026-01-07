"""
Configuration module for the BackLite Media Sales Operations Bot.

This module handles:
- Environment configuration
- Channel abstraction initialization
- LLM provider configuration
- Currency management
- Template discovery
- User permissions
"""

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from slack_sdk.signature import SignatureVerifier

# Load environment
load_dotenv()

# Base paths
BASE_DIR = Path(__file__).parent

# Set up structured logging
from core.utils.logging import get_logger, setup_logging

# Determine if we should use JSON format (production) or console format (development)
_is_production = os.path.exists("/data/") or os.getenv("ENVIRONMENT") == "production"
IS_DEVELOPMENT = not _is_production  # Exposed for OpenAI store parameter etc.
_log_level = os.getenv("LOG_LEVEL", "INFO")

setup_logging(
    level=_log_level,
    json_format=_is_production,
    module_levels={
        "httpx": "WARNING",
        "httpcore": "WARNING",
        "urllib3": "WARNING",
        "asyncio": "WARNING",
        "uvicorn.access": "WARNING",
        "openai": "WARNING",  # Suppress verbose OpenAI SDK request logging
        "openai._base_client": "WARNING",
        "hpack": "WARNING",  # HTTP/2 header encoding spam
    }
)

# Get the main application logger
logger = get_logger("proposal-bot")

# Use /data/ in production, local paths in development
if os.path.exists("/data/"):
    # Production paths
    TEMPLATES_DIR = Path(os.getenv("TEMPLATES_DIR", "/data/templates"))
    HOS_CONFIG_FILE = Path("/data/hos_config.json")
    logger.info("[STARTUP] Running in PRODUCTION mode - using /data/ paths")
else:
    # Development paths
    TEMPLATES_DIR = Path(os.getenv("TEMPLATES_DIR", str(BASE_DIR / "data" / "templates")))
    HOS_CONFIG_FILE = BASE_DIR / "data" / "hos_config.json"
    logger.info("[STARTUP] Running in DEVELOPMENT mode - using local paths")

logger.info(f"[STARTUP] Templates directory: {TEMPLATES_DIR}")
logger.info(f"[STARTUP] HOS config file: {HOS_CONFIG_FILE}")

# ============================================================================
# CHANNEL CONFIGURATION
# ============================================================================

# Slack credentials (used by SlackAdapter)
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET", "")

# Signature verifier for Slack webhooks
signature_verifier = SignatureVerifier(SLACK_SIGNING_SECRET)

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


# ============================================================================
# LLM PROVIDER CONFIGURATION
# ============================================================================

# Just specify which provider to use - models are fixed per provider internally
# Options: "openai", "google"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")  # For text completions
IMAGE_PROVIDER = os.getenv("IMAGE_PROVIDER", "google")  # For image generation

# API Keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

# ============================================================================
# COMPANY SCHEMAS (Hybrid Multi-tenant Architecture)
# ============================================================================

# Company hierarchy (managed in database `companies` table):
#   MMG (is_group=true)
#   ├── Backlite (is_group=true)
#   │   ├── backlite_dubai (is_group=false) → has schema
#   │   ├── backlite_uk (is_group=false) → has schema
#   │   └── backlite_abudhabi (is_group=false) → has schema
#   └── viola (is_group=false) → has schema
#
# Groups (is_group=true) are organizational only - no data schema.
# Leaf companies (is_group=false) have actual PostgreSQL schemas with data.
# The `get_accessible_schemas` SQL function expands groups to leaf schemas.
# User.companies already contains resolved leaf schemas from RBAC.
#
# HYBRID ARCHITECTURE:
# - Company schemas contain: locations, mockup_frames, mockup_usage,
#   location_photos, rate_cards, location_occupations
# - Public schema contains: proposals_log, proposal_locations, booking_orders,
#   bo_locations, bo_approval_workflows, ai_costs, documents, mockup_files
#
# WHY: Proposals/BOs can include locations from MULTIPLE companies.
#      AI costs are tracked by user (users can belong to multiple companies).
COMPANY_SCHEMAS = ['backlite_dubai', 'backlite_uk', 'backlite_abudhabi', 'viola']

# ============================================================================
# LOCATION DATA
# ============================================================================

# Dynamic data populated from templates directory
UPLOAD_FEES_MAPPING: dict[str, int] = {}
LOCATION_DETAILS: dict[str, str] = {}
LOCATION_METADATA: dict[str, dict[str, object]] = {}

# Cache for templates
_MAPPING_CACHE: dict[str, str] | None = None
_DISPLAY_CACHE: list[str] | None = None

# HOS config
_HOS_CONFIG: dict[str, dict[str, dict[str, object]]] = {}

# ============================================================================
# CURRENCY CONFIGURATION
# ============================================================================

if os.path.exists("/data/"):
    CURRENCY_CONFIG_FILE = Path("/data/currency_config.json")
else:
    CURRENCY_CONFIG_FILE = BASE_DIR / "render_main_data" / "currency_config.json"

DEFAULT_CURRENCY: str = os.getenv("DEFAULT_CURRENCY", "AED").upper()
CURRENCY_CONFIG: dict[str, Any] = {}
CURRENCY_PROMPT_CONTEXT: str = ""


def _default_currency_config() -> dict[str, Any]:
    """Static fallback currency configuration (base AED)."""
    return {
        "base_currency": "AED",
        "currencies": {
            "AED": {
                "symbol": "AED",
                "position": "suffix",
                "decimals": 2,
                "aed_per_unit": 1.0
            },
            "USD": {
                "symbol": "$",
                "position": "prefix",
                "decimals": 2,
                "aed_per_unit": 3.6725
            },
            "EUR": {
                "symbol": "€",
                "position": "prefix",
                "decimals": 2,
                "aed_per_unit": 3.97
            },
            "GBP": {
                "symbol": "£",
                "position": "prefix",
                "decimals": 2,
                "aed_per_unit": 4.62
            }
        }
    }


def _apply_currency_config(config_data: dict[str, Any], source: str = "static") -> None:
    """Normalize and cache currency config (supports dynamic overrides)."""
    global CURRENCY_CONFIG, CURRENCY_PROMPT_CONTEXT, DEFAULT_CURRENCY

    base_currency = str(config_data.get("base_currency", DEFAULT_CURRENCY or "AED")).upper()
    currencies_in = config_data.get("currencies", {}) or {}

    normalized: dict[str, dict[str, Any]] = {}
    for code, meta in currencies_in.items():
        if not isinstance(meta, dict):
            continue
        code_upper = str(code).upper()
        normalized[code_upper] = {
            "symbol": meta.get("symbol", code_upper),
            "position": str(meta.get("position", "suffix")).lower(),
            "decimals": int(meta.get("decimals", 2)),
            "aed_per_unit": float(meta.get("aed_per_unit", 1.0)) or 1.0
        }

    # Ensure base currency exists
    if base_currency not in normalized:
        normalized[base_currency] = {
            "symbol": base_currency,
            "position": "suffix",
            "decimals": 2,
            "aed_per_unit": 1.0
        }

    DEFAULT_CURRENCY = base_currency
    CURRENCY_CONFIG = {
        "base_currency": base_currency,
        "currencies": normalized,
        "source": source
    }

    # Build prompt reference for LLM instructions
    lines: list[str] = []
    lines.append("**CURRENCY REFERENCE**")
    lines.append(f"Base currency: {base_currency}. Amounts default to this unless explicitly changed.")
    lines.append("For conversions use the ratios below (AED per 1 unit). Keep numeric fields as pure numbers without symbols.")

    for code in sorted(normalized.keys()):
        meta = normalized[code]
        aed_per_unit = float(meta.get("aed_per_unit", 1.0)) or 1.0
        inverse = 0.0 if aed_per_unit == 0 else 1 / aed_per_unit
        lines.append(
            f"- {code}: symbol '{meta.get('symbol', code)}' ({meta.get('position', 'suffix')}), "
            f"1 {code} = {aed_per_unit:.4f} AED | 1 AED = {inverse:.4f} {code}"
        )

    lines.append("If a requested currency is missing, tell the user conversion is not supported yet.")
    lines.append("Always include a top-level 'currency' field using ISO codes.")

    CURRENCY_PROMPT_CONTEXT = "\n".join(lines)
    logger.info(f"[CURRENCY] Applied currency config (base: {base_currency}, currencies: {len(normalized)})")


def load_currency_config() -> None:
    """Load currency config from static file (with safe defaults)."""
    config_data = _default_currency_config()

    if CURRENCY_CONFIG_FILE.exists():
        try:
            file_data = json.loads(CURRENCY_CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(file_data, dict):
                config_data.update({k: v for k, v in file_data.items() if k != "currencies"})
                file_currencies = file_data.get("currencies", {})
                if isinstance(file_currencies, dict):
                    config_data["currencies"].update({str(k).upper(): v for k, v in file_currencies.items()})
        except Exception as e:
            logger.warning(f"[CURRENCY] Failed to load {CURRENCY_CONFIG_FILE}: {e}")

    _apply_currency_config(config_data)


def update_currency_config(config_data: dict[str, Any], source: str = "dynamic") -> None:
    """Allow runtime overrides (e.g., future API fetch)."""
    if not isinstance(config_data, dict):
        raise ValueError("Currency config must be a dict")
    merged = _default_currency_config()
    merged.update({k: v for k, v in config_data.items() if k != "currencies"})
    if "currencies" in config_data and isinstance(config_data["currencies"], dict):
        merged["currencies"].update({str(k).upper(): v for k, v in config_data["currencies"].items()})
    _apply_currency_config(merged, source=source)


def get_currency_metadata(currency: str | None) -> dict[str, Any]:
    """Return metadata for currency (falls back to default)."""
    code = str(currency or DEFAULT_CURRENCY).upper()
    currencies = CURRENCY_CONFIG.get("currencies", {})
    meta = currencies.get(code)
    if not meta:
        meta = currencies.get(DEFAULT_CURRENCY, {
            "symbol": DEFAULT_CURRENCY,
            "position": "suffix",
            "decimals": 2,
            "aed_per_unit": 1.0
        })
        code = DEFAULT_CURRENCY
    return {**meta, "code": code}


def convert_currency_value(amount: float | None, from_currency: str | None, to_currency: str | None) -> float | None:
    """Convert using AED as intermediary. Returns rounded amount."""
    if amount is None:
        return None

    from_meta = get_currency_metadata(from_currency)
    to_meta = get_currency_metadata(to_currency)

    if from_meta["code"] == to_meta["code"]:
        return round(float(amount), int(to_meta.get("decimals", 2)))

    amount_aed = float(amount) * float(from_meta.get("aed_per_unit", 1.0))
    converted = amount_aed / float(to_meta.get("aed_per_unit", 1.0))
    return round(converted, int(to_meta.get("decimals", 2)))


def format_currency_value(amount: float | None, currency: str | None = None) -> str:
    """Format amount with currency symbol and correct placement."""
    if amount is None:
        amount = 0.0

    meta = get_currency_metadata(currency)
    decimals = int(meta.get("decimals", 2))
    value = f"{float(amount):,.{decimals}f}"
    symbol = str(meta.get("symbol", meta["code"]))
    position = str(meta.get("position", "suffix")).lower()

    if position == "prefix":
        return f"{symbol}{value}"
    return f"{value} {symbol}".strip()


# Load currency config on import
load_currency_config()

# ============================================================================
# HOS CONFIG & PERMISSIONS
# ============================================================================

def load_hos_config() -> None:
    global _HOS_CONFIG
    try:
        logger.info(f"[HOS_CONFIG] Looking for config at: {HOS_CONFIG_FILE}")
        if HOS_CONFIG_FILE.exists():
            logger.info(f"[HOS_CONFIG] Found config at: {HOS_CONFIG_FILE}")
            _HOS_CONFIG = json.loads(HOS_CONFIG_FILE.read_text(encoding="utf-8"))
            logger.info(f"[HOS_CONFIG] Loaded config: {list(_HOS_CONFIG.keys())}")
        else:
            logger.warning(f"[HOS_CONFIG] Config file not found at: {HOS_CONFIG_FILE}")
            _HOS_CONFIG = {}
    except Exception as e:
        logger.warning(f"Failed to load hos_config.json: {e}")
        _HOS_CONFIG = {}


def can_manage_locations(user_id: str) -> bool:
    """Check if user can manage locations (user_id is platform-agnostic)."""
    if not _HOS_CONFIG:
        load_hos_config()
    groups = _HOS_CONFIG.get("permissions", {}).get("manage_locations", [])
    allowed_ids = set()
    for group in groups:
        members = _HOS_CONFIG.get(group, {})
        for _, info in members.items():
            if info.get("active"):
                # Check both slack_user_id and generic user_id
                if info.get("slack_user_id"):
                    allowed_ids.add(info["slack_user_id"])
                if info.get("user_id"):
                    allowed_ids.add(info["user_id"])
    return user_id in allowed_ids


def is_admin(user_id: str) -> bool:
    """Check if user has admin privileges (user_id is platform-agnostic)."""
    if not _HOS_CONFIG:
        logger.info("[ADMIN_CHECK] Loading HOS config")
        load_hos_config()

    # Admin users are those in the 'admin' group
    admin_members = _HOS_CONFIG.get("admin", {})
    logger.info(f"[ADMIN_CHECK] Checking if {user_id} is admin")
    logger.info(f"[ADMIN_CHECK] Admin members: {list(admin_members.keys())}")

    for name, info in admin_members.items():
        # Check both slack_user_id and generic user_id
        slack_id = info.get("slack_user_id")
        generic_id = info.get("user_id")
        is_active = info.get("active")
        logger.info(f"[ADMIN_CHECK] Checking {name}: slack_id={slack_id}, user_id={generic_id}, active={is_active}")

        if is_active and (user_id in (slack_id, generic_id)):
            logger.info(f"[ADMIN_CHECK] User {user_id} is admin!")
            return True

    logger.info(f"[ADMIN_CHECK] User {user_id} is NOT admin")
    return False


# ============================================================================
# TEMPLATE DISCOVERY
# ============================================================================

def _normalize_key(name: str) -> str:
    return os.path.splitext(name)[0].strip().lower()


def _parse_metadata_file(folder: Path) -> dict[str, object]:
    meta: dict[str, object] = {}
    path = folder / "metadata.txt"
    if not path.exists():
        return meta

    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            key = k.strip().lower().replace(" ", "_")
            val = v.strip()
            meta[key] = val
    except Exception as e:
        logger.warning(f"Failed to parse metadata at {path}: {e}")
        return meta

    # Parse specific fields
    upload_fee: int | None = None
    uf = str(meta.get("upload_fee", "")).replace(",", "").strip()
    if uf.isdigit():
        upload_fee = int(uf)

    sov_text = str(meta.get("sov", "16.6%"))
    try:
        base_sov = float(sov_text.replace("%", "").strip())
    except Exception:
        base_sov = 16.6

    display_name = str(meta.get("display_name", meta.get("location_name", ""))).strip()

    # Parse new fields
    series = str(meta.get("series", "")).strip()
    height = str(meta.get("height", "")).strip()
    width = str(meta.get("width", "")).strip()
    number_of_faces = 1
    if meta.get("number_of_faces"):
        try:
            number_of_faces = int(meta.get("number_of_faces"))
        except (ValueError, TypeError):
            number_of_faces = 1

    display_type = str(meta.get("display_type", "Digital")).strip()
    spot_duration = 16
    if meta.get("spot_duration"):
        try:
            spot_duration = int(meta.get("spot_duration"))
        except (ValueError, TypeError):
            spot_duration = 16

    loop_duration = 96
    if meta.get("loop_duration"):
        try:
            loop_duration = int(meta.get("loop_duration"))
        except (ValueError, TypeError):
            loop_duration = 96

    return {
        "display_name": display_name,
        "upload_fee": upload_fee,
        "sov": f"{base_sov}%",
        "series": series,
        "height": height,
        "width": width,
        "number_of_faces": number_of_faces,
        "display_type": display_type,
        "spot_duration": spot_duration,
        "loop_duration": loop_duration,
        "folder": str(folder.name),
    }


def _discover_templates() -> tuple[dict[str, str], list[str]]:
    """
    Discover templates from Asset-Management API.

    Falls back to local filesystem scanning if Asset-Management is unavailable.
    """
    logger.info("[DISCOVER] Starting template discovery from Asset-Management")
    key_to_relpath: dict[str, str] = {}
    display_names: list[str] = []

    UPLOAD_FEES_MAPPING.clear()
    LOCATION_DETAILS.clear()
    LOCATION_METADATA.clear()

    # Try to fetch from Asset-Management API
    locations = _fetch_locations_from_asset_management()

    if locations:
        logger.info(f"[DISCOVER] Got {len(locations)} locations from Asset-Management")
        for loc in locations:
            key = loc.get("location_key", "")
            if not key:
                continue

            display_name = loc.get("display_name", key)
            display_names.append(display_name)

            # Build description
            display_type = loc.get("display_type", "Digital")
            sov = loc.get("sov_percent") or 16.6
            spot = loc.get("spot_duration") or 16
            description = f"{display_name} - {display_type} Display - 1 Spot - {spot} Seconds - {sov}% SOV"
            LOCATION_DETAILS[key] = description

            # Upload fee (may come as float string like "3000.0")
            upload_fee = loc.get("upload_fee")
            upload_fee_int = int(float(upload_fee)) if upload_fee else 3000
            UPLOAD_FEES_MAPPING[key] = upload_fee_int

            # Build metadata dict matching the old format
            LOCATION_METADATA[key] = {
                "display_name": display_name,
                "upload_fee": upload_fee_int if upload_fee else None,
                "sov": f"{sov}%",
                "series": loc.get("series", ""),
                "height": loc.get("height", ""),
                "width": loc.get("width", ""),
                "number_of_faces": loc.get("number_of_faces", 1),
                "display_type": display_type,
                "spot_duration": loc.get("spot_duration") or 16,
                "loop_duration": loc.get("loop_duration") or 96,
                "template_path": loc.get("template_path", ""),
                "company": loc.get("company", ""),
            }

            # Template path for compatibility
            if loc.get("template_path"):
                key_to_relpath[key] = loc["template_path"]
            else:
                key_to_relpath[key] = f"{key}/{key}.pptx"

        logger.info(f"[DISCOVER] Discovery complete. Found {len(key_to_relpath)} templates")
        return key_to_relpath, display_names

    # Fallback to local filesystem (legacy mode)
    logger.warning("[DISCOVER] Asset-Management unavailable, falling back to local filesystem")
    return _discover_templates_from_filesystem()


def _fetch_locations_from_asset_management() -> list[dict]:
    """
    Fetch locations from Asset-Management internal API.

    Uses service JWT auth for machine-to-machine communication.
    Calls /api/internal/locations which doesn't require user permissions.
    """
    import httpx
    import jwt
    from datetime import datetime, timedelta, timezone

    # Get Asset-Management URL (use ASSET_MGMT_URL to match settings.py)
    asset_mgmt_url = os.getenv("ASSET_MGMT_URL", "http://localhost:8001")

    # Get inter-service secret for JWT auth
    inter_service_secret = os.getenv("INTER_SERVICE_SECRET", "")

    if not inter_service_secret:
        logger.warning("[DISCOVER] No INTER_SERVICE_SECRET, cannot call Asset-Management")
        return []

    try:
        # Create short-lived service JWT (matching ServiceAuthClient format)
        payload = {
            "service": "sales-module",
            "type": "service",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        }
        token = jwt.encode(payload, inter_service_secret, algorithm="HS256")

        # Call internal endpoint (service-to-service, no user permissions required)
        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                f"{asset_mgmt_url}/api/internal/locations",
                headers={"Authorization": f"Bearer {token}"},
                params={"active_only": "true"},
            )
            response.raise_for_status()
            return response.json()

    except httpx.ConnectError:
        logger.warning(f"[DISCOVER] Cannot connect to Asset-Management at {asset_mgmt_url}")
        return []
    except Exception as e:
        logger.warning(f"[DISCOVER] Failed to fetch from Asset-Management: {e}")
        return []


def _discover_templates_from_filesystem() -> tuple[dict[str, str], list[str]]:
    """
    Legacy: Discover templates from local filesystem.

    Only used as fallback when Asset-Management is unavailable.
    """
    logger.info(f"[DISCOVER] Scanning local filesystem: '{TEMPLATES_DIR}'")
    key_to_relpath: dict[str, str] = {}
    display_names: list[str] = []

    if not TEMPLATES_DIR.exists():
        logger.warning(f"[DISCOVER] Templates directory does not exist: '{TEMPLATES_DIR}'")
        return key_to_relpath, display_names

    for pptx_path in TEMPLATES_DIR.rglob("*.pptx"):
        try:
            rel_path = pptx_path.relative_to(TEMPLATES_DIR)
        except Exception:
            rel_path = pptx_path
        key = _normalize_key(pptx_path.stem)
        key_to_relpath[key] = str(rel_path)

        meta = _parse_metadata_file(pptx_path.parent)

        display_name = meta.get("display_name") or pptx_path.stem
        description = meta.get("description") or f"{pptx_path.stem} - Digital Display - 1 Spot - 16 Seconds - 16.6% SOV"

        display_names.append(str(display_name))
        LOCATION_DETAILS[key] = str(description)

        if meta.get("upload_fee") is not None:
            UPLOAD_FEES_MAPPING[key] = int(meta.get("upload_fee"))
        else:
            UPLOAD_FEES_MAPPING[key] = 3000

        LOCATION_METADATA[key] = meta
        LOCATION_METADATA[key]["pptx_rel_path"] = str(rel_path)

    logger.info(f"[DISCOVER] Filesystem scan complete. Found {len(key_to_relpath)} templates")
    return key_to_relpath, display_names


def refresh_templates() -> None:
    global _MAPPING_CACHE, _DISPLAY_CACHE
    logger.info("[REFRESH] Refreshing templates cache")
    mapping, names = _discover_templates()
    _MAPPING_CACHE = mapping
    _DISPLAY_CACHE = names
    logger.info(f"[REFRESH] Templates cache refreshed: {len(mapping)} templates")
    logger.info(f"[REFRESH] Cached mapping: {mapping}")
    logger.info(f"[REFRESH] Upload fees: {UPLOAD_FEES_MAPPING}")
    logger.info(f"[REFRESH] Location metadata: {LOCATION_METADATA}")


def get_location_mapping() -> dict[str, str]:
    global _MAPPING_CACHE
    if _MAPPING_CACHE is None:
        logger.info("[GET_MAPPING] Cache is empty, refreshing templates")
        refresh_templates()
    else:
        logger.info(f"[GET_MAPPING] Using cached mapping with {len(_MAPPING_CACHE)} entries")
    return _MAPPING_CACHE or {}


def available_location_names() -> list[str]:
    global _DISPLAY_CACHE
    if _DISPLAY_CACHE is None:
        refresh_templates()
    return _DISPLAY_CACHE or []


def get_location_key_from_display_name(display_name: str) -> str | None:
    """Convert a display name back to its location key."""
    # Ensure metadata is loaded
    if not LOCATION_METADATA:
        refresh_templates()

    # Normalize the input
    display_name_lower = display_name.lower().strip()

    # First try exact match
    for key, meta in LOCATION_METADATA.items():
        if meta.get('display_name', '').lower() == display_name_lower:
            return key

    # Then try partial matches
    for key, meta in LOCATION_METADATA.items():
        meta_display = meta.get('display_name', '').lower()
        if display_name_lower in meta_display or meta_display in display_name_lower:
            return key

    # Also check if the display name is actually a key
    for key in LOCATION_METADATA:
        if key == display_name_lower:
            return key

    return None
