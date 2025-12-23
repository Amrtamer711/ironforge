"""
FastAPI Server - Main Application Entry Point.

Asset Management Service for centralized management of:
- Networks (sellable groupings)
- Asset Types (organizational categories)
- Locations/Assets (individual sellable units)
- Packages (bundles of networks/assets)
- Eligibility (service visibility criteria)
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import config
from crm_security import SecurityHeadersMiddleware, TrustedUserMiddleware, RequestLoggingMiddleware
from api.routers import (
    asset_types_router,
    eligibility_router,
    health_router,
    locations_router,
    network_assets_router,
    networks_router,
    packages_router,
)

logger = config.get_logger("api.server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown events."""
    logger.info(f"[STARTUP] Asset Management Service starting (env={config.ENVIRONMENT})")
    logger.info(f"[STARTUP] Supabase URL: {config.SUPABASE_URL[:50]}..." if config.SUPABASE_URL else "[STARTUP] No Supabase URL configured")
    yield
    logger.info("[SHUTDOWN] Asset Management Service shutting down")


app = FastAPI(
    title="Asset Management Service",
    description="Centralized asset/location management for CRM platform",
    version="0.1.0",
    lifespan=lifespan,
)

# Security headers middleware (adds X-Request-ID, X-Response-Time, security headers)
app.add_middleware(SecurityHeadersMiddleware)
logger.info("[SECURITY] SecurityHeadersMiddleware enabled")

# Request logging middleware (audit trail)
app.add_middleware(RequestLoggingMiddleware)
logger.info("[SECURITY] RequestLoggingMiddleware enabled")

# Trusted user context middleware (authentication + RBAC context)
app.add_middleware(
    TrustedUserMiddleware,
    exempt_paths={"/health"},
)
logger.info("[SECURITY] TrustedUserMiddleware enabled - proxy secret validation active")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.get_cors_origins_list(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key", "X-Request-ID", "X-Proxy-Secret"],
)
logger.info(f"[CORS] Allowed origins: {config.get_cors_origins_list()}")

# Include routers
app.include_router(health_router)
app.include_router(networks_router)
app.include_router(asset_types_router)
app.include_router(network_assets_router)
app.include_router(locations_router)
app.include_router(packages_router)
app.include_router(eligibility_router)
