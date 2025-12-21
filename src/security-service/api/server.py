"""
FastAPI Server - Security Service Entry Point.

Centralized authentication, RBAC, and audit logging service.
All other services communicate with this via REST API.
"""

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

import config
from api.routers import (
    health_router,
    auth_router,
    rbac_router,
    audit_router,
    api_keys_router,
    rate_limit_router,
)

logger = config.get_logger("api.server")


# =============================================================================
# SECURITY HEADERS MIDDLEWARE
# =============================================================================


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds security headers to all responses.

    Headers added:
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - X-XSS-Protection: 1; mode=block
    - Referrer-Policy: strict-origin-when-cross-origin
    - X-Request-ID: request correlation ID
    - X-Response-Time: processing time
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Generate or extract request ID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        # Start timing
        start_time = time.time()

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)

        # Core security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # HSTS - only in production
        if config.settings.is_production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        # Request/Response correlation
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration_ms}ms"

        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for logging requests and responses.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.time()
        request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())

        # Get calling service name
        service_name = request.headers.get("X-Service-Name", "-")

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)

        # Log request
        logger.info(
            f"[HTTP] {request.method} {request.url.path} "
            f"-> {response.status_code} ({duration_ms}ms) "
            f"service={service_name} request_id={request_id}"
        )

        return response


# =============================================================================
# LIFESPAN
# =============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown events."""
    logger.info(f"[STARTUP] Security Service starting (env={config.settings.ENVIRONMENT})")
    config.settings.log_config()
    yield
    logger.info("[SHUTDOWN] Security Service shutting down")


# =============================================================================
# APPLICATION
# =============================================================================


app = FastAPI(
    title="Security Service",
    description="Centralized authentication, RBAC, and audit logging for CRM platform",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if not config.settings.is_production else None,
    redoc_url="/redoc" if not config.settings.is_production else None,
)


# Security headers middleware (adds X-Request-ID, X-Response-Time, security headers)
app.add_middleware(SecurityHeadersMiddleware)
logger.info("[SECURITY] SecurityHeadersMiddleware enabled")

# Request logging middleware
app.add_middleware(RequestLoggingMiddleware)
logger.info("[SECURITY] RequestLoggingMiddleware enabled")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "Authorization",
        "X-Service-Secret",
        "X-Service-Name",
        "X-Request-ID",
    ],
)
logger.info(f"[CORS] Allowed origins: {config.settings.allowed_origins}")


# =============================================================================
# ROUTERS
# =============================================================================

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(rbac_router)
app.include_router(audit_router)
app.include_router(api_keys_router)
app.include_router(rate_limit_router)

logger.info("[ROUTERS] All routers registered")
