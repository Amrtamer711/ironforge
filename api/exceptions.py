"""
Centralized exception handling for the API.

Provides custom exception classes and exception handlers that
return consistent JSON error responses.
"""

import logging
import traceback
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from utils.time import get_uae_time

logger = logging.getLogger("proposal-bot")


# =============================================================================
# CUSTOM EXCEPTION CLASSES
# =============================================================================


class APIError(Exception):
    """
    Base exception for API errors.

    All custom API exceptions should inherit from this class.
    """

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code or "INTERNAL_ERROR"
        self.details = details or {}
        super().__init__(message)


class NotFoundError(APIError):
    """Resource not found error."""

    def __init__(
        self,
        message: str = "Resource not found",
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
    ):
        details = {}
        if resource_type:
            details["resource_type"] = resource_type
        if resource_id:
            details["resource_id"] = resource_id

        super().__init__(
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="NOT_FOUND",
            details=details,
        )


class ValidationFailedError(APIError):
    """Request validation error."""

    def __init__(
        self,
        message: str = "Validation failed",
        field: Optional[str] = None,
        errors: Optional[list] = None,
    ):
        details = {}
        if field:
            details["field"] = field
        if errors:
            details["errors"] = errors

        super().__init__(
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="VALIDATION_ERROR",
            details=details,
        )


class AuthenticationError(APIError):
    """Authentication failed error."""

    def __init__(self, message: str = "Authentication required"):
        super().__init__(
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="AUTHENTICATION_REQUIRED",
        )


class AuthorizationError(APIError):
    """Authorization failed error."""

    def __init__(
        self,
        message: str = "Permission denied",
        required_permission: Optional[str] = None,
        required_role: Optional[str] = None,
    ):
        details = {}
        if required_permission:
            details["required_permission"] = required_permission
        if required_role:
            details["required_role"] = required_role

        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="PERMISSION_DENIED",
            details=details,
        )


class RateLimitError(APIError):
    """Rate limit exceeded error."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: Optional[int] = None,
    ):
        details = {}
        if retry_after:
            details["retry_after_seconds"] = retry_after

        super().__init__(
            message=message,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            error_code="RATE_LIMIT_EXCEEDED",
            details=details,
        )


class ExternalServiceError(APIError):
    """External service error (Slack, Supabase, etc.)."""

    def __init__(
        self,
        message: str = "External service error",
        service: Optional[str] = None,
    ):
        details = {}
        if service:
            details["service"] = service

        super().__init__(
            message=message,
            status_code=status.HTTP_502_BAD_GATEWAY,
            error_code="EXTERNAL_SERVICE_ERROR",
            details=details,
        )


# =============================================================================
# ERROR RESPONSE BUILDER
# =============================================================================


def build_error_response(
    message: str,
    status_code: int,
    error_code: str,
    details: Optional[Dict[str, Any]] = None,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build a standardized error response dictionary.

    All API errors return this structure for consistent client handling.
    """
    response = {
        "error": {
            "message": message,
            "code": error_code,
            "status_code": status_code,
            "timestamp": get_uae_time().isoformat(),
        }
    }

    if details:
        response["error"]["details"] = details

    if request_id:
        response["error"]["request_id"] = request_id

    return response


# =============================================================================
# EXCEPTION HANDLERS
# =============================================================================


async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    """Handle custom APIError exceptions."""
    logger.warning(
        f"[API ERROR] {exc.error_code}: {exc.message}",
        extra={"status_code": exc.status_code, "details": exc.details},
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=build_error_response(
            message=exc.message,
            status_code=exc.status_code,
            error_code=exc.error_code,
            details=exc.details,
        ),
    )


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle Pydantic/FastAPI validation errors."""
    errors = []
    for error in exc.errors():
        loc = " -> ".join(str(x) for x in error["loc"])
        errors.append({
            "location": loc,
            "message": error["msg"],
            "type": error["type"],
        })

    logger.warning(f"[VALIDATION ERROR] {len(errors)} validation errors")

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=build_error_response(
            message="Request validation failed",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="VALIDATION_ERROR",
            details={"errors": errors},
        ),
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handle unexpected exceptions.

    Logs the full traceback but returns a generic error to the client
    to avoid leaking internal details.
    """
    # Log the full error for debugging
    logger.error(
        f"[UNHANDLED ERROR] {type(exc).__name__}: {exc}",
        exc_info=True,
    )

    # Return generic error to client
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=build_error_response(
            message="An internal error occurred",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="INTERNAL_ERROR",
        ),
    )


# =============================================================================
# SETUP FUNCTION
# =============================================================================


def setup_exception_handlers(app: FastAPI) -> None:
    """
    Register all exception handlers with the FastAPI app.

    Call this during app initialization:
        from api.exceptions import setup_exception_handlers
        setup_exception_handlers(app)
    """
    # Custom API errors
    app.add_exception_handler(APIError, api_error_handler)

    # Pydantic validation errors
    app.add_exception_handler(RequestValidationError, validation_error_handler)

    # Catch-all for unhandled exceptions (only in production)
    # Uncomment to enable:
    # app.add_exception_handler(Exception, generic_exception_handler)

    logger.info("[EXCEPTIONS] Registered custom exception handlers")
