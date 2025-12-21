"""
Main entry point for the Security Service.
"""

import uvicorn

from config import settings

if __name__ == "__main__":
    uvicorn.run(
        "api.server:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=not settings.is_production,
    )
