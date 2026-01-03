"""
Video Critique API Routers.

Contains all API route definitions.
"""

from api.routers.slack import router as slack_router
from api.routers.chat import router as chat_router
from api.routers.tasks import router as tasks_router
from api.routers.videos import router as videos_router
from api.routers.dashboard import router as dashboard_router
from api.routers.health import router as health_router

__all__ = [
    "slack_router",
    "chat_router",
    "tasks_router",
    "videos_router",
    "dashboard_router",
    "health_router",
]
