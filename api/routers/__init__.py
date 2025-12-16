"""
FastAPI Routers Package.

This package contains modular routers that split up the API endpoints
by domain for better organization and maintainability.
"""

from api.routers.admin import router as admin_router
from api.routers.auth_routes import router as auth_router
from api.routers.chat import router as chat_router
from api.routers.costs import router as costs_router
from api.routers.files import router as files_router
from api.routers.health import router as health_router
from api.routers.mockups import router as mockups_router
from api.routers.modules import router as modules_router
from api.routers.proposals import router as proposals_router
from api.routers.slack import router as slack_router

__all__ = [
    "slack_router",
    "health_router",
    "costs_router",
    "mockups_router",
    "chat_router",
    "auth_router",
    "proposals_router",
    "files_router",
    "admin_router",
    "modules_router",
]
