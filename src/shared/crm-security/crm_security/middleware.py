"""
Security Middleware.

Adds standard security headers to all HTTP responses for protection
against common web vulnerabilities (XSS, clickjacking, MIME sniffing, etc.)

Also includes request ID injection and timing headers.

Adapted from sales-module/api/middleware/security_headers.py for shared use.

Usage:
    from shared.security import SecurityHeadersMiddleware

    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)
"""

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .config import security_config

logger = logging.getLogger(__name__)


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
    - X-Response-Time: request processing time
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
        if security_config.is_production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        # Request/Response correlation
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration_ms}ms"

        # Add rate limit headers if present
        rate_limit_info = getattr(request.state, "rate_limit_info", None)
        if rate_limit_info:
            response.headers["X-RateLimit-Limit"] = str(rate_limit_info.limit)
            response.headers["X-RateLimit-Remaining"] = str(rate_limit_info.remaining)
            response.headers["X-RateLimit-Reset"] = str(int(rate_limit_info.reset_at))

        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for logging requests and responses.

    Logs:
    - Request method and path
    - Response status code
    - Processing time
    - User ID (if authenticated)
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.time()
        request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)

        # Get user ID if present
        user_id = request.headers.get("X-Trusted-User-Id", "-")

        # Log request
        logger.info(
            f"[HTTP] {request.method} {request.url.path} "
            f"-> {response.status_code} ({duration_ms}ms) "
            f"user={user_id} request_id={request_id}"
        )

        return response


class TrustedUserMiddleware(BaseHTTPMiddleware):
    """
    Comprehensive authentication middleware.

    Handles:
    - Dev auth for API testing via /docs (non-production only)
    - Proxy secret validation (X-Proxy-Secret)
    - Trusted header parsing (X-Trusted-User-*)
    - User context setting for access anywhere in code

    Usage:
        from security import TrustedUserMiddleware

        app = FastAPI()
        app.add_middleware(TrustedUserMiddleware, exempt_paths={"/health", "/slack"})
    """

    def __init__(self, app, exempt_paths: set[str] | None = None, exempt_prefixes: list[str] | None = None):
        """
        Initialize the middleware.

        Args:
            app: FastAPI application
            exempt_paths: Paths that don't require proxy secret (exact match)
            exempt_prefixes: Path prefixes that don't require proxy secret
        """
        super().__init__(app)
        self.exempt_paths = exempt_paths or {"/health"}
        self.exempt_prefixes = exempt_prefixes or []

    def _is_exempt(self, path: str) -> bool:
        """Check if path is exempt from proxy secret validation."""
        if path in self.exempt_paths:
            return True
        for prefix in self.exempt_prefixes:
            if path.startswith(prefix):
                return True
        return False

    async def dispatch(self, request: Request, call_next) -> Response:
        import json
        from starlette.responses import JSONResponse
        from .context import set_user_context, clear_user_context, set_dev_auth_context

        path = request.url.path

        # =====================================================================
        # DEV AUTH: Allow testing via /docs with static token (non-production)
        # =====================================================================
        dev_auth_active = False
        if (
            security_config.dev_auth_enabled
            and not security_config.is_production
            and not self._is_exempt(path)
        ):
            dev_token = request.headers.get("x-dev-token")
            if dev_token == security_config.dev_auth_token:
                dev_auth_active = True
                logger.debug(f"[DEV-AUTH] Dev auth active for {path}")

        # =====================================================================
        # PROXY SECRET VALIDATION
        # =====================================================================
        if not self._is_exempt(path) and not dev_auth_active:
            expected_secret = security_config.proxy_secret
            if expected_secret:
                provided_secret = request.headers.get("x-proxy-secret")
                if provided_secret != expected_secret:
                    # If trusted user headers are present without valid secret, reject
                    if request.headers.get("x-trusted-user-id"):
                        logger.warning(f"[SECURITY] Blocked spoofed trusted headers on {path}")
                        return JSONResponse(
                            status_code=403,
                            content={"error": "Invalid proxy secret"}
                        )

        # =====================================================================
        # SET USER CONTEXT
        # =====================================================================
        if dev_auth_active:
            # Use dev auth context
            set_dev_auth_context()
        else:
            # Parse from trusted headers
            user_id = request.headers.get("x-trusted-user-id")

            if user_id:
                expected_secret = security_config.proxy_secret
                provided_secret = request.headers.get("x-proxy-secret")

                # Only set context if proxy secret is valid (or not configured)
                if not expected_secret or provided_secret == expected_secret:
                    # Parse all RBAC levels from headers
                    def safe_json_parse(value: str | None, default):
                        if not value:
                            return default
                        try:
                            return json.loads(value)
                        except json.JSONDecodeError:
                            return default

                    set_user_context(
                        user_id=user_id,
                        email=request.headers.get("x-trusted-user-email", ""),
                        name=request.headers.get("x-trusted-user-name", ""),
                        profile=request.headers.get("x-trusted-user-profile", ""),
                        # Level 1+2: Permissions
                        permissions=safe_json_parse(
                            request.headers.get("x-trusted-user-permissions"), []
                        ),
                        permission_sets=safe_json_parse(
                            request.headers.get("x-trusted-user-permission-sets"), []
                        ),
                        # Level 3: Teams & Hierarchy
                        teams=safe_json_parse(
                            request.headers.get("x-trusted-user-teams"), []
                        ),
                        team_ids=safe_json_parse(
                            request.headers.get("x-trusted-user-team-ids"), []
                        ),
                        manager_id=request.headers.get("x-trusted-user-manager-id"),
                        subordinate_ids=safe_json_parse(
                            request.headers.get("x-trusted-user-subordinate-ids"), []
                        ),
                        # Level 4: Sharing
                        sharing_rules=safe_json_parse(
                            request.headers.get("x-trusted-user-sharing-rules"), []
                        ),
                        shared_records=safe_json_parse(
                            request.headers.get("x-trusted-user-shared-records"), {}
                        ),
                        shared_from_user_ids=safe_json_parse(
                            request.headers.get("x-trusted-user-shared-from-user-ids"), []
                        ),
                        # Level 5: Companies
                        companies=safe_json_parse(
                            request.headers.get("x-trusted-user-companies"), []
                        ),
                    )

        try:
            response = await call_next(request)
            return response
        finally:
            clear_user_context()
