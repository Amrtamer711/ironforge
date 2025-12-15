"""
FastAPI Server - Main Application Entry Point.

This module sets up the FastAPI application with all routers,
middleware, and background tasks.
"""

import asyncio
from datetime import datetime, timedelta
import subprocess
import shutil
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.middleware.security_headers import SecurityHeadersMiddleware
import config
from app_settings import settings
from font_utils import install_custom_fonts
from utils.time import get_uae_time
from utils.logging import logging_middleware_helper, get_logger

# Import routers
from api.routers import (
    slack_router,
    health_router,
    costs_router,
    mockups_router,
    chat_router,
    auth_router,
    proposals_router,
    files_router,
    admin_router,
    modules_router,
)

# Install custom fonts on startup
install_custom_fonts()

# Load location templates
config.refresh_templates()

# Check LibreOffice installation
logger = get_logger("api.server")
logger.info("[STARTUP] Checking LibreOffice installation...")
libreoffice_found = False
for cmd in ['libreoffice', 'soffice', '/usr/bin/libreoffice']:
    if shutil.which(cmd) or subprocess.run(['which', cmd], capture_output=True).returncode == 0:
        try:
            result = subprocess.run([cmd, '--version'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                logger.info(f"[STARTUP] LibreOffice found at '{cmd}': {result.stdout.strip()}")
                libreoffice_found = True
                break
        except Exception as e:
            logger.debug(f"[STARTUP] Error checking {cmd}: {e}")

if not libreoffice_found:
    logger.warning("[STARTUP] LibreOffice not found! PDF conversion will use fallback method.")
else:
    logger.info("[STARTUP] LibreOffice is ready for PDF conversion.")


async def periodic_cleanup():
    """Background task to clean up old data periodically."""
    while True:
        await asyncio.sleep(300)  # Every 5 minutes
        try:
            # Clean up old user histories
            from db.cache import user_history, pending_location_additions

            # Clean user histories older than 1 hour
            cutoff = get_uae_time() - timedelta(hours=1)
            expired_users = []
            for uid, history in user_history.items():
                if history and hasattr(history[-1], 'get'):
                    timestamp_str = history[-1].get('timestamp')
                    if timestamp_str:
                        try:
                            last_time = datetime.fromisoformat(timestamp_str)
                            if last_time < cutoff:
                                expired_users.append(uid)
                        except (ValueError, TypeError):
                            pass  # Invalid timestamp format, skip

            for uid in expired_users:
                del user_history[uid]

            if expired_users:
                logger.info(f"[CLEANUP] Removed {len(expired_users)} old user histories")

            # Clean pending locations older than 10 minutes
            location_cutoff = get_uae_time() - timedelta(minutes=10)
            expired_locations = [
                uid for uid, data in pending_location_additions.items()
                if data.get("timestamp", get_uae_time()) < location_cutoff
            ]
            for uid in expired_locations:
                del pending_location_additions[uid]

            if expired_locations:
                logger.info(f"[CLEANUP] Removed {len(expired_locations)} pending locations")

            # Clean up old temporary files
            import tempfile
            import time
            import os
            temp_dir = tempfile.gettempdir()
            now = time.time()

            cleaned_files = 0
            for filename in os.listdir(temp_dir):
                filepath = os.path.join(temp_dir, filename)
                # Clean files older than 1 hour that match our patterns
                if (filename.endswith(('.pptx', '.pdf', '.bin')) and
                    os.path.isfile(filepath) and
                    os.stat(filepath).st_mtime < now - 3600):
                    try:
                        os.unlink(filepath)
                        cleaned_files += 1
                    except OSError:
                        pass  # File in use or permission denied

            if cleaned_files > 0:
                logger.info(f"[CLEANUP] Removed {cleaned_files} old temporary files")

        except Exception as e:
            logger.error(f"[CLEANUP] Error in periodic cleanup: {e}")


async def initialize_storage():
    """Initialize storage client and ensure buckets exist."""
    try:
        from integrations.storage import get_storage_client
        storage = get_storage_client()
        logger.info(f"[STARTUP] Storage provider: {storage.provider_name}")

        if storage.provider_name != "local":
            # Ensure required buckets exist for Supabase/S3
            required_buckets = ["proposals", "uploads"]
            for bucket in required_buckets:
                try:
                    await storage.ensure_bucket(bucket)
                    logger.info(f"[STARTUP] Storage bucket '{bucket}' ready")
                except Exception as e:
                    logger.warning(f"[STARTUP] Could not ensure bucket '{bucket}': {e}")
    except Exception as e:
        logger.warning(f"[STARTUP] Storage initialization skipped: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown events."""
    # Startup
    cleanup_task = asyncio.create_task(periodic_cleanup())
    logger.info("[STARTUP] Started background cleanup task")

    # Initialize storage (for Supabase/S3 bucket setup)
    await initialize_storage()

    # Load active workflows from database to restore state after restart
    from workflows import bo_approval
    await bo_approval.load_workflows_from_db()

    yield

    # Shutdown
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        logger.info("[SHUTDOWN] Background cleanup task cancelled")


# Create FastAPI app
app = FastAPI(title="Proposal Bot API", lifespan=lifespan)

# Add CORS middleware for unified UI
# Origins configured via CORS_ORIGINS environment variable
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key", "X-Request-ID"],
)
logger.info(f"[CORS] Allowed origins: {settings.cors_origins_list}")

# Add security headers middleware
app.add_middleware(SecurityHeadersMiddleware)
logger.info("[SECURITY] Security headers middleware enabled")


# Add request logging middleware
@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """Log all HTTP requests with request ID tracking."""
    return await logging_middleware_helper(request, call_next)


# Paths that don't require proxy secret (have their own auth)
PROXY_SECRET_EXEMPT_PATHS = {
    "/health",
    "/slack/events",
    "/slack/interactions",
    "/slack/commands",
}


def _is_proxy_secret_exempt(path: str) -> bool:
    """Check if path is exempt from proxy secret validation."""
    # Exact matches
    if path in PROXY_SECRET_EXEMPT_PATHS:
        return True
    # Prefix matches for slack routes
    if path.startswith("/slack/"):
        return True
    return False


# Add trusted user context middleware (set RBAC context from unified-ui headers)
@app.middleware("http")
async def trusted_user_middleware(request: Request, call_next):
    """
    Extract trusted user context from proxy headers.

    Security: Only trusts X-Trusted-User-* headers if accompanied by valid X-Proxy-Secret.
    This prevents header spoofing attacks when proposal-bot is publicly accessible.

    Exempt paths (Slack webhooks, health checks) have their own authentication.

    unified-ui validates JWT and injects these headers:
    - X-Proxy-Secret: Shared secret to verify request is from unified-ui
    - X-Trusted-User-Id
    - X-Trusted-User-Email
    - X-Trusted-User-Name
    - X-Trusted-User-Profile
    - X-Trusted-User-Permissions (Level 1+2: combined profile + permission set permissions)
    - X-Trusted-User-Permission-Sets (Level 2: active permission sets)
    - X-Trusted-User-Teams (Level 3: user's teams)
    - X-Trusted-User-Team-Ids (Level 3: team IDs)
    - X-Trusted-User-Manager-Id (Level 3: user's manager)
    - X-Trusted-User-Subordinate-Ids (Level 3: user's direct reports + team members)
    """
    import json
    from integrations.rbac.providers.database import set_user_context, clear_user_context

    path = request.url.path

    # Skip proxy secret validation for exempt paths
    if not _is_proxy_secret_exempt(path):
        # Validate proxy secret if configured
        expected_secret = settings.proxy_secret
        if expected_secret:
            provided_secret = request.headers.get("x-proxy-secret")
            if provided_secret != expected_secret:
                # If trusted user headers are present without valid secret, reject
                if request.headers.get("x-trusted-user-id"):
                    logger.warning(f"[SECURITY] Blocked spoofed trusted headers on {path}")
                    return JSONResponse(
                        status_code=403,
                        content={"error": "Invalid proxy secret"}
                    )

    user_id = request.headers.get("x-trusted-user-id")

    if user_id:
        # Only set context if proxy secret is valid (or not configured)
        expected_secret = settings.proxy_secret
        provided_secret = request.headers.get("x-proxy-secret")

        if not expected_secret or provided_secret == expected_secret:
            profile = request.headers.get("x-trusted-user-profile", "")

            # Level 1+2: Combined permissions (profile + permission sets)
            permissions_json = request.headers.get("x-trusted-user-permissions", "[]")
            try:
                permissions = json.loads(permissions_json)
            except json.JSONDecodeError:
                permissions = []

            # Level 2: Active permission sets
            permission_sets_json = request.headers.get("x-trusted-user-permission-sets", "[]")
            try:
                permission_sets = json.loads(permission_sets_json)
            except json.JSONDecodeError:
                permission_sets = []

            # Level 3: Teams
            teams_json = request.headers.get("x-trusted-user-teams", "[]")
            try:
                teams = json.loads(teams_json)
            except json.JSONDecodeError:
                teams = []

            team_ids_json = request.headers.get("x-trusted-user-team-ids", "[]")
            try:
                team_ids = json.loads(team_ids_json)
            except json.JSONDecodeError:
                team_ids = []

            # Level 3: Hierarchy
            manager_id = request.headers.get("x-trusted-user-manager-id")

            subordinate_ids_json = request.headers.get("x-trusted-user-subordinate-ids", "[]")
            try:
                subordinate_ids = json.loads(subordinate_ids_json)
            except json.JSONDecodeError:
                subordinate_ids = []

            # Level 4: Sharing Rules & Record Shares
            sharing_rules_json = request.headers.get("x-trusted-user-sharing-rules", "[]")
            try:
                sharing_rules = json.loads(sharing_rules_json)
            except json.JSONDecodeError:
                sharing_rules = []

            shared_records_json = request.headers.get("x-trusted-user-shared-records", "{}")
            try:
                shared_records = json.loads(shared_records_json)
            except json.JSONDecodeError:
                shared_records = {}

            shared_from_user_ids_json = request.headers.get("x-trusted-user-shared-from-user-ids", "[]")
            try:
                shared_from_user_ids = json.loads(shared_from_user_ids_json)
            except json.JSONDecodeError:
                shared_from_user_ids = []

            # Set full RBAC context (all 4 levels)
            set_user_context(
                user_id=user_id,
                profile=profile,
                permissions=permissions,
                permission_sets=permission_sets,
                teams=teams,
                team_ids=team_ids,
                manager_id=manager_id,
                subordinate_ids=subordinate_ids,
                sharing_rules=sharing_rules,
                shared_records=shared_records,
                shared_from_user_ids=shared_from_user_ids,
            )

    try:
        response = await call_next(request)
        return response
    finally:
        clear_user_context()

# Setup centralized exception handlers
from api.exceptions import setup_exception_handlers
setup_exception_handlers(app)

# Include routers
app.include_router(slack_router)
app.include_router(health_router)
app.include_router(costs_router)
app.include_router(mockups_router)
app.include_router(chat_router)
app.include_router(auth_router)
app.include_router(proposals_router)
app.include_router(files_router)
app.include_router(admin_router)
app.include_router(modules_router)
