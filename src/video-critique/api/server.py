"""
Video Critique API Server.

FastAPI application setup with middleware, lifespan, and routers.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import config
from core.utils.logging import get_logger
from db.database import get_database

logger = get_logger(__name__)


# ============================================================================
# LIFESPAN
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.

    Handles startup and shutdown events.
    """
    # Startup
    logger.info("[Server] Starting Video Critique API...")

    # Initialize database
    try:
        db = get_database()
        await db.initialize()
        logger.info("[Server] Database initialized")
    except Exception as e:
        logger.error(f"[Server] Database initialization failed: {e}")

    # Recover pending workflows
    try:
        from core.workflows.approval_flow import ApprovalWorkflow
        workflow = ApprovalWorkflow()
        recovered = await workflow.recover_pending_workflows()
        if recovered > 0:
            logger.info(f"[Server] Recovered {recovered} pending workflows")
    except Exception as e:
        logger.warning(f"[Server] Could not recover workflows: {e}")

    # Start background tasks
    app.state.background_tasks = []

    # Assignment check scheduler (runs daily)
    async def run_daily_assignment():
        while True:
            try:
                await asyncio.sleep(3600)  # Check every hour
                # Only run during business hours
                from datetime import datetime
                now = datetime.now(config.UAE_TZ)
                if 8 <= now.hour <= 18 and now.weekday() < 5:
                    from core.services.assignment_service import AssignmentService
                    service = AssignmentService()
                    await service.run_assignment_check()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Server] Assignment check error: {e}")

    # Start assignment task in background
    if not getattr(config, "DISABLE_BACKGROUND_TASKS", False):
        task = asyncio.create_task(run_daily_assignment())
        app.state.background_tasks.append(task)

    logger.info("[Server] Video Critique API ready")

    yield

    # Shutdown
    logger.info("[Server] Shutting down Video Critique API...")

    # Cancel background tasks
    for task in app.state.background_tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # Close database connections
    try:
        db = get_database()
        await db.close()
    except Exception as e:
        logger.warning(f"[Server] Error closing database: {e}")

    logger.info("[Server] Shutdown complete")


# ============================================================================
# APPLICATION
# ============================================================================

app = FastAPI(
    title="Video Critique API",
    description="Video production workflow management service",
    version="2.0.0",
    lifespan=lifespan,
)


# ============================================================================
# MIDDLEWARE
# ============================================================================

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure properly in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log incoming requests."""
    logger.debug(f"[Server] {request.method} {request.url.path}")

    response = await call_next(request)

    return response


# Error handling middleware
@app.middleware("http")
async def handle_errors(request: Request, call_next):
    """Handle uncaught exceptions."""
    try:
        return await call_next(request)
    except Exception as e:
        logger.error(f"[Server] Unhandled error: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "detail": str(e)},
        )


# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to responses."""
    response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"

    return response


# ============================================================================
# ROUTERS
# ============================================================================

# Import routers after app is created to avoid circular imports
from api.routers.slack import router as slack_router
from api.routers.chat import router as chat_router
from api.routers.tasks import router as tasks_router
from api.routers.videos import router as videos_router
from api.routers.dashboard import router as dashboard_router
from api.routers.health import router as health_router

# Include routers
app.include_router(health_router)
app.include_router(slack_router)
app.include_router(chat_router)
app.include_router(tasks_router)
app.include_router(videos_router)
app.include_router(dashboard_router)


# ============================================================================
# ROOT ENDPOINT
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "video-critique",
        "version": "2.0.0",
        "status": "running",
    }
