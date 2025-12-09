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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown events."""
    # Startup
    cleanup_task = asyncio.create_task(periodic_cleanup())
    logger.info("[STARTUP] Started background cleanup task")

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
