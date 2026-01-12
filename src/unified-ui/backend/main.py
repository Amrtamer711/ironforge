"""
FastAPI application entry point for unified-ui.

[VERIFIED] Mirrors server.js application setup:
- Environment detection (lines 14-20)
- CORS configuration (lines 104-148)
- Static file serving (line 807)
- Health endpoints (lines 813-834)
- SPA catch-all (lines 4148-4159)
- Error handling (lines 4161-4170)

Routers:
- /api/modules/* - modules.py (1 endpoint)
- /api/sales/* - proxy.py (proxies to proposal-bot)
- /api/base/auth/* - auth.py (12 endpoints)
- /api/admin/* - admin.py (8 endpoints)
- /api/rbac/* - rbac/ (43 endpoints: profiles, permission_sets, teams, sharing, users)
- /api/channel-identity/* - channel_identity.py (9 endpoints)
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from backend.config import get_settings

# Import routers
from backend.routers import admin, auth, channel_identity, modules, proxy
from backend.routers.rbac import router as rbac_router
from backend.services.supabase_client import get_supabase

# Dev panel (only loaded in development)
import os
if os.getenv("ENVIRONMENT", "local") in ("local", "development", "test"):
    from backend.routers import dev_panel
    DEV_PANEL_ENABLED = True
else:
    DEV_PANEL_ENABLED = False

# Configure logging
_log_level = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, _log_level.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("unified-ui")

# Quiet down noisy third-party loggers
for _logger_name in [
    "httpx", "httpcore", "httpcore.http2", "httpcore.connection",
    "urllib3", "hpack", "hpack.hpack", "hpack.table",
    "openai", "openai._base_client",
]:
    logging.getLogger(_logger_name).setLevel(logging.WARNING)


# Filter to silence health check logs in uvicorn
class HealthCheckFilter(logging.Filter):
    """Filter out health check endpoint logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        # Skip health check logs in development
        if not get_settings().is_production and "/health" in message:
            return False
        return True


# Apply filter to uvicorn access logger
logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())


# =============================================================================
# LIFESPAN - Startup/shutdown events
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    settings = get_settings()

    # Startup
    settings.log_config()
    # Rate limiting uses on-demand cleanup via shared security module

    # Initialize cache (Redis or memory fallback)
    from crm_cache import get_cache, close_cache
    cache = get_cache()
    logger.info("[CACHE] Initialized cache backend")

    # Check Supabase connection
    supabase = get_supabase()
    if supabase:
        logger.info("[UI] Supabase: Connected")

        # Sync permissions from code to database
        from backend.services.permissions import sync_permissions_to_database
        await sync_permissions_to_database()
    else:
        logger.warning("[UI] Supabase: Not configured")

    logger.info(f"[UI] Sales Module URL: {settings.SALES_MODULE_URL}")
    logger.info(f"Unified UI running on port {settings.PORT}")

    yield

    # Shutdown
    from backend.routers.proxy import close_proxy_client
    await close_proxy_client()
    logger.info("[UI] Closed proxy HTTP client")

    await close_cache()
    logger.info("[UI] Shutting down...")


# =============================================================================
# APP INITIALIZATION
# =============================================================================

app = FastAPI(
    title="Unified UI",
    description="Unified UI backend for authentication, RBAC, and proxying",
    version="1.0.0",
    lifespan=lifespan,
)

# =============================================================================
# CORS CONFIGURATION - server.js:104-148
# =============================================================================

settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins or ["*"],  # Fall back to all if empty
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key", "X-Request-ID"],
)


# =============================================================================
# SECURITY HEADERS MIDDLEWARE - server.js:151-167 (helmet)
# =============================================================================

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers similar to helmet.js."""
    response = await call_next(request)

    # X-Content-Type-Options - Prevent MIME sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"

    # X-Frame-Options - Prevent clickjacking
    response.headers["X-Frame-Options"] = "SAMEORIGIN"

    # X-XSS-Protection - Enable XSS filter (legacy but still useful)
    response.headers["X-XSS-Protection"] = "1; mode=block"

    # Referrer-Policy - Control referrer information
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # Permissions-Policy - Restrict browser features
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

    # Content-Security-Policy - Only in production
    if settings.is_production:
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
            "img-src 'self' data: blob: https:",
            f"connect-src 'self' {settings.supabase_url or ''} https://*.supabase.co",
            "font-src 'self' https: data: https://fonts.gstatic.com",
            "object-src 'none'",
            "upgrade-insecure-requests",
        ]
        response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

    return response


# =============================================================================
# REQUEST LOGGING MIDDLEWARE - server.js:724-737
# =============================================================================

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests with timing."""
    import time
    start = time.time()

    # Skip health check logging in non-production
    skip_paths = {"/health", "/health/ready", "/health/auth"}

    response = await call_next(request)

    if settings.is_production or request.url.path not in skip_paths:
        duration = (time.time() - start) * 1000
        logger.info(f"[UI] {request.method} {request.url.path} -> {response.status_code} ({duration:.0f}ms)")

    return response


# =============================================================================
# INCLUDE ROUTERS
# =============================================================================

# Auth router - /api/base/auth/*
app.include_router(auth.router)

# Modules router - /api/modules/*
app.include_router(modules.router)

# Proxy router - /api/sales/* -> proposal-bot
app.include_router(proxy.router)

# Admin router - /api/admin/*
app.include_router(admin.router)

# RBAC router - /api/rbac/*
app.include_router(rbac_router)

# Channel Identity router - /api/channel-identity/*
app.include_router(channel_identity.router)

# Dev Panel router - /api/dev/* (only in development)
if DEV_PANEL_ENABLED:
    app.include_router(dev_panel.router)
    logger.info("[UI] Dev Panel enabled at /api/dev/*")


# =============================================================================
# HEALTH ENDPOINTS - server.js:813-822
# =============================================================================

@app.get("/health")
async def health_check():
    """
    Health check endpoint.
    Mirrors server.js:813-822
    """
    settings = get_settings()
    supabase = get_supabase()

    return {
        "status": "ok",
        "service": "unified-ui",
        "supabase": supabase is not None,
        "sales_module_url": settings.SALES_MODULE_URL,
        "environment": settings.ENVIRONMENT,
    }


# =============================================================================
# SUPABASE CONFIG ENDPOINT - server.js:824-834
# =============================================================================

@app.get("/api/base/config.js")
async def get_supabase_config():
    """
    Serve public Supabase credentials to frontend as JavaScript.

    Mirrors server.js:824-834

    IMPORTANT: Only expose SUPABASE_URL and SUPABASE_ANON_KEY (public),
    never SERVICE_KEY.
    """
    settings = get_settings()
    import json

    js_content = f"""// Supabase configuration (auto-generated)
// Environment: {settings.ENVIRONMENT}
window.SUPABASE_URL = {json.dumps(settings.supabase_url or '')};
window.SUPABASE_ANON_KEY = {json.dumps(settings.supabase_anon_key or '')};
"""

    return Response(
        content=js_content,
        media_type="application/javascript",
    )


# =============================================================================
# STATIC FILES - server.js:807
# =============================================================================

# Determine frontend path
# In development: unified-ui/public
# In production/docker: frontend/ (next to backend/)
FRONTEND_PATH = Path(__file__).parent.parent / "public"
if not FRONTEND_PATH.exists():
    FRONTEND_PATH = Path(__file__).parent.parent / "frontend"

if FRONTEND_PATH.exists():
    # Serve static assets (CSS, JS, images)
    css_path = FRONTEND_PATH / "css"
    js_path = FRONTEND_PATH / "js"
    images_path = FRONTEND_PATH / "images"

    if css_path.exists():
        app.mount("/css", StaticFiles(directory=str(css_path)), name="css")
    if js_path.exists():
        app.mount("/js", StaticFiles(directory=str(js_path)), name="js")
    if images_path.exists():
        app.mount("/images", StaticFiles(directory=str(images_path)), name="images")

    logger.info(f"[UI] Serving static files from: {FRONTEND_PATH}")
else:
    logger.warning(f"[UI] Frontend path not found: {FRONTEND_PATH}")


# =============================================================================
# DEV TOOLS - Explicit routes for development panels
# =============================================================================

# Dev tools are stored separately from Vite build output to avoid being deleted
DEV_TOOLS_PATH = Path(__file__).parent.parent / "dev-tools"


@app.get("/logs-panel.html")
async def serve_logs_panel():
    """Serve the logs panel directly (bypasses SPA routing)."""
    logger.info("[UI] Serving /logs-panel.html (explicit route)")
    logs_panel = DEV_TOOLS_PATH / "logs-panel.html"
    if logs_panel.exists():
        # Prevent caching in development to ensure fresh content
        headers = {}
        if not settings.is_production:
            headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            headers["Pragma"] = "no-cache"
            headers["Expires"] = "0"
        return FileResponse(logs_panel, media_type="text/html", headers=headers)
    raise HTTPException(status_code=404, detail="Logs panel not found")


@app.get("/dev-panel.html")
async def serve_dev_panel():
    """Serve the dev panel directly (bypasses SPA routing)."""
    logger.info("[UI] Serving /dev-panel.html (explicit route)")
    dev_panel_file = DEV_TOOLS_PATH / "dev-panel.html"
    if dev_panel_file.exists():
        # Prevent caching in development to ensure fresh content
        headers = {}
        if not settings.is_production:
            headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            headers["Pragma"] = "no-cache"
            headers["Expires"] = "0"
        return FileResponse(dev_panel_file, media_type="text/html", headers=headers)
    raise HTTPException(status_code=404, detail="Dev panel not found")


# =============================================================================
# SPA CATCH-ALL - server.js:4148-4159
# =============================================================================

@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    """
    Serve index.html for all non-API routes (SPA routing).

    Mirrors server.js:4148-4159

    This enables client-side routing and handles Supabase auth redirects.
    """
    logger.info(f"[UI] SPA catch-all hit: /{full_path}")

    # Don't catch API routes
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")

    # Prepare cache headers for development (no caching for HTML/JS/CSS)
    def get_dev_headers(file_path: str) -> dict:
        """Get cache-control headers for development mode."""
        if settings.is_production:
            return {}
        # Disable caching for HTML, JS, CSS in development
        if file_path.endswith((".html", ".js", ".css", ".json")):
            return {
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            }
        return {}

    # Check for static file first (icons, etc.)
    if FRONTEND_PATH.exists():
        static_file = FRONTEND_PATH / full_path
        if static_file.exists() and static_file.is_file():
            logger.info(f"[UI] Serving static file: {static_file}")
            return FileResponse(static_file, headers=get_dev_headers(full_path))

        # Serve index.html for SPA routing
        index_path = FRONTEND_PATH / "index.html"
        if index_path.exists():
            logger.info(f"[UI] Falling back to index.html for: /{full_path}")
            return FileResponse(index_path, headers=get_dev_headers("index.html"))

    raise HTTPException(status_code=404, detail="Frontend not found")


# =============================================================================
# ERROR HANDLING - server.js:4161-4170
# =============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global error handler.
    Mirrors server.js:4161-4170
    """
    settings = get_settings()
    logger.error(f"Server error: {exc}")

    # In production, hide internal error details from client
    if settings.is_production:
        return JSONResponse(
            status_code=500,
            content={"error": "An internal error occurred"},
        )
    else:
        return JSONResponse(
            status_code=500,
            content={"error": str(exc) or "Internal server error"},
        )


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=not settings.is_production,
    )
