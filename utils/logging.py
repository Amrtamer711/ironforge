"""
Structured logging configuration for the Sales Proposals Bot.

This module provides:
- JSON-formatted logs for production
- Human-readable logs for development
- Request ID tracking across logs
- Log level configuration per module

Usage:
    from utils.logging import setup_logging, get_logger, get_request_id

    # Setup once at application startup
    setup_logging()

    # Get a logger for your module
    logger = get_logger(__name__)
    logger.info("Processing request", extra={"user_id": "123"})

    # In request handlers, use request_id context
    with request_context(request_id="abc-123"):
        logger.info("Handling request")  # Automatically includes request_id
"""

import json
import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Any, Optional

from utils.time import get_uae_time

# Context variable for request ID tracking
_request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def get_request_id() -> Optional[str]:
    """Get the current request ID from context."""
    return _request_id_ctx.get()


def set_request_id(request_id: Optional[str] = None) -> str:
    """
    Set the request ID in context.

    Args:
        request_id: Optional request ID. If not provided, generates a new UUID.

    Returns:
        The request ID that was set.
    """
    if request_id is None:
        request_id = str(uuid.uuid4())[:8]
    _request_id_ctx.set(request_id)
    return request_id


def clear_request_id() -> None:
    """Clear the request ID from context."""
    _request_id_ctx.set(None)


class RequestContextManager:
    """Context manager for request ID tracking."""

    def __init__(self, request_id: Optional[str] = None):
        self.request_id = request_id
        self.token = None

    def __enter__(self) -> str:
        self.request_id = set_request_id(self.request_id)
        return self.request_id

    def __exit__(self, *args):
        clear_request_id()


def request_context(request_id: Optional[str] = None) -> RequestContextManager:
    """
    Create a context manager for request ID tracking.

    Usage:
        with request_context() as request_id:
            logger.info("Processing")  # Includes request_id automatically
    """
    return RequestContextManager(request_id)


class JSONFormatter(logging.Formatter):
    """
    JSON log formatter for production environments.

    Outputs logs in a structured JSON format suitable for log aggregation
    systems like ELK, Datadog, or CloudWatch.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": get_uae_time().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add request ID if available
        request_id = get_request_id()
        if request_id:
            log_data["request_id"] = request_id

        # Add location info
        log_data["location"] = {
            "file": record.filename,
            "line": record.lineno,
            "function": record.funcName,
        }

        # Add any extra fields
        if hasattr(record, "__dict__"):
            for key, value in record.__dict__.items():
                if key not in (
                    "name", "msg", "args", "created", "filename", "funcName",
                    "levelname", "levelno", "lineno", "module", "msecs",
                    "pathname", "process", "processName", "relativeCreated",
                    "stack_info", "exc_info", "exc_text", "thread", "threadName",
                    "message", "taskName",
                ):
                    log_data[key] = value

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


class ConsoleFormatter(logging.Formatter):
    """
    Human-readable console formatter for development.

    Includes colors for different log levels.
    """

    COLORS = {
        "DEBUG": "\033[36m",    # Cyan
        "INFO": "\033[32m",     # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",    # Red
        "CRITICAL": "\033[35m", # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        # Color the level name
        color = self.COLORS.get(record.levelname, "")
        level = f"{color}{record.levelname:8}{self.RESET}"

        # Get request ID
        request_id = get_request_id()
        req_str = f"[{request_id}] " if request_id else ""

        # Format timestamp
        timestamp = get_uae_time().strftime("%H:%M:%S")

        # Build message
        msg = f"{timestamp} {level} {req_str}{record.name}: {record.getMessage()}"

        # Add exception if present
        if record.exc_info:
            msg += f"\n{self.formatException(record.exc_info)}"

        return msg


class RequestIDFilter(logging.Filter):
    """Filter that adds request_id to log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        return True


def setup_logging(
    level: str = "INFO",
    json_format: bool = False,
    module_levels: Optional[dict[str, str]] = None,
) -> None:
    """
    Configure application logging.

    Args:
        level: Default log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Use JSON format (True for production, False for development)
        module_levels: Optional dict of module names to log levels
            Example: {"httpx": "WARNING", "uvicorn": "INFO"}
    """
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, level.upper()))

    # Add request ID filter
    handler.addFilter(RequestIDFilter())

    # Set formatter based on environment
    if json_format:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(ConsoleFormatter())

    root_logger.addHandler(handler)

    # Configure per-module levels
    if module_levels:
        for module, mod_level in module_levels.items():
            logging.getLogger(module).setLevel(getattr(logging, mod_level.upper()))

    # Quiet down noisy third-party loggers by default
    default_quiet = {
        "httpx": "WARNING",
        "httpcore": "WARNING",
        "urllib3": "WARNING",
        "asyncio": "WARNING",
        "hpack": "WARNING",  # HTTP/2 header encoding spam
        "hpack.hpack": "WARNING",
        "hpack.table": "WARNING",
        "multipart": "WARNING",  # Multipart form parsing spam
        "multipart.multipart": "WARNING",
        "PIL": "WARNING",  # Pillow image plugin loading spam
        "PIL.Image": "WARNING",
    }
    for module, mod_level in default_quiet.items():
        if module_levels is None or module not in module_levels:
            logging.getLogger(module).setLevel(getattr(logging, mod_level.upper()))


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a module.

    Args:
        name: Logger name, typically __name__

    Returns:
        Logger instance
    """
    return logging.getLogger(name)


# Paths to skip logging at DEBUG level (health checks flood the terminal)
_SKIP_LOG_PATHS_DEBUG = {"/health", "/health/ready", "/health/auth"}


# Middleware helper for FastAPI
async def logging_middleware_helper(request, call_next):
    """
    Helper for creating FastAPI logging middleware.

    Usage in api/server.py:
        from utils.logging import logging_middleware_helper

        @app.middleware("http")
        async def logging_middleware(request, call_next):
            return await logging_middleware_helper(request, call_next)
    """
    # Generate or extract request ID
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:8]

    with request_context(request_id):
        logger = get_logger("api.request")
        path = request.url.path

        # Skip health check logging only at DEBUG level (they flood terminal)
        # In production (INFO+), health checks are logged normally
        is_debug = logging.getLogger().level <= logging.DEBUG
        skip_logging = is_debug and path in _SKIP_LOG_PATHS_DEBUG

        if not skip_logging:
            # Log request
            logger.info(
                f"{request.method} {path}",
                extra={
                    "method": request.method,
                    "path": path,
                    "query": str(request.query_params),
                }
            )

        # Process request
        import time
        start_time = time.time()
        response = await call_next(request)
        duration_ms = (time.time() - start_time) * 1000

        if not skip_logging:
            # Log response
            logger.info(
                f"{request.method} {path} -> {response.status_code} ({duration_ms:.0f}ms)",
                extra={
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                }
            )

        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id

        return response
