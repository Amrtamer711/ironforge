"""
FastAPI Routers Package.

Modular routers for asset management endpoints.
"""

from api.routers.asset_types import router as asset_types_router
from api.routers.eligibility import router as eligibility_router
from api.routers.health import router as health_router
from api.routers.locations import router as locations_router
from api.routers.network_assets import router as network_assets_router
from api.routers.networks import router as networks_router
from api.routers.packages import router as packages_router

__all__ = [
    "health_router",
    "networks_router",
    "asset_types_router",
    "network_assets_router",
    "locations_router",
    "packages_router",
    "eligibility_router",
]
