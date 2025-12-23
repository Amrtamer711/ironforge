"""
FastAPI Server - Main Application Entry Point.

This module sets up the FastAPI application with all routers,
middleware, and background tasks.
"""

import asyncio
import shutil
import subprocess
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

import config

# Use crm-security SDK middleware
from crm_security import SecurityHeadersMiddleware, TrustedUserMiddleware

# Import routers
from api.routers import (
    admin_router,
    auth_router,
    chat_router,
    costs_router,
    files_router,
    health_router,
    mockups_router,
    modules_router,
    proposals_router,
    slack_router,
)
from app_settings import settings
from utils.font_utils import install_custom_fonts
from utils.logging import get_logger, logging_middleware_helper
from utils.time import get_uae_time

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
            from db.cache import pending_location_additions, user_history

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
            import os
            import tempfile
            import time
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


# Create FastAPI app with dev auth docs (if enabled)
swagger_ui_parameters = None
if settings.dev_auth_enabled and settings.environment == "development":
    # Show dev token info in Swagger UI
    swagger_ui_parameters = {
        "persistAuthorization": True,
    }

app = FastAPI(
    title="Proposal Bot API",
    lifespan=lifespan,
    swagger_ui_parameters=swagger_ui_parameters,
    description=(
        "## Dev Auth (Development Only)\n\n"
        "Add header `X-Dev-Token: <token>` to authenticate.\n\n"
        "The token is configured via `DEV_AUTH_TOKEN` env var."
        if settings.dev_auth_enabled and settings.environment == "development"
        else None
    ),
)

# Add CORS middleware for unified UI
# Origins configured via CORS_ORIGINS environment variable
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key", "X-Request-ID", "X-Dev-Token"],
)
logger.info(f"[CORS] Allowed origins: {settings.cors_origins_list}")

# Add security headers middleware
app.add_middleware(SecurityHeadersMiddleware)
logger.info("[SECURITY] Security headers middleware enabled")

# Add trusted user context middleware (authentication + RBAC context)
app.add_middleware(
    TrustedUserMiddleware,
    exempt_paths={"/health", "/slack/events", "/slack/interactions", "/slack/commands"},
    exempt_prefixes=["/slack/"],
)
logger.info("[SECURITY] Trusted user middleware enabled")


# Add dev auth security scheme to OpenAPI (for Swagger UI Authorize button)
if settings.dev_auth_enabled and settings.environment == "development":
    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        from fastapi.openapi.utils import get_openapi
        openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        # Add X-Dev-Token as API key security scheme
        openapi_schema["components"] = openapi_schema.get("components", {})
        openapi_schema["components"]["securitySchemes"] = {
            "DevToken": {
                "type": "apiKey",
                "in": "header",
                "name": "X-Dev-Token",
                "description": "Dev auth token (set DEV_AUTH_TOKEN env var)",
            }
        }
        # Apply security globally to all endpoints
        openapi_schema["security"] = [{"DevToken": []}]
        app.openapi_schema = openapi_schema
        return app.openapi_schema
    app.openapi = custom_openapi
    logger.info("[DEV-AUTH] Swagger UI dev auth enabled - use Authorize button with X-Dev-Token")


# Add request logging middleware
@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """Log all HTTP requests with request ID tracking."""
    return await logging_middleware_helper(request, call_next)


# Setup centralized exception handlers
from api.exceptions import setup_exception_handlers

setup_exception_handlers(app)

# Include routers
app.include_router(slack_router)
app.include_router(health_router)
app.include_router(locations_router)
app.include_router(costs_router)
app.include_router(mockups_router)
app.include_router(chat_router)
app.include_router(auth_router)
app.include_router(proposals_router)
app.include_router(files_router)
app.include_router(admin_router)
app.include_router(modules_router)
