"""
Security Headers Middleware.

Adds standard security headers to all HTTP responses for protection
against common web vulnerabilities (XSS, clickjacking, MIME sniffing, etc.)
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app_settings import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds security headers to all responses.

    Headers added:
    - X-Content-Type-Options: nosniff (prevents MIME-type sniffing)
    - X-Frame-Options: DENY (prevents clickjacking)
    - X-XSS-Protection: 1; mode=block (legacy XSS protection)
    - Referrer-Policy: strict-origin-when-cross-origin
    - Permissions-Policy: restricts browser features
    - Strict-Transport-Security: HSTS (production only)
    - X-Request-ID: echoes request ID for client correlation
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Core security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions Policy (formerly Feature-Policy)
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), "
            "camera=(), "
            "geolocation=(), "
            "gyroscope=(), "
            "magnetometer=(), "
            "microphone=(), "
            "payment=(), "
            "usb=()"
        )

        # HSTS - only in production with HTTPS
        if settings.environment == "production":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        # Echo request ID for client-side correlation with server logs
        request_id = getattr(request.state, "request_id", None)
        if request_id:
            response.headers["X-Request-ID"] = request_id

        return response
