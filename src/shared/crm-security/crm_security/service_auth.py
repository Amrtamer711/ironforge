"""
Inter-service authentication using short-lived JWT tokens.

This is NEW functionality - not copied from sales-module.

Usage (caller):
    from shared.security import ServiceAuthClient

    client = ServiceAuthClient("sales-module")
    headers = client.get_auth_headers()
    response = httpx.get("http://asset-management:8001/api/v1/locations", headers=headers)

Usage (receiver):
    from shared.security import verify_service_token

    @router.get("/internal/data")
    async def internal_endpoint(service: str = Depends(verify_service_token)):
        return {"called_by": service}
"""

import logging
from datetime import datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, Request, status

from .config import security_config

logger = logging.getLogger(__name__)


class ServiceAuthClient:
    """
    Client for making authenticated inter-service requests.

    Generates short-lived JWT tokens for service-to-service communication.
    """

    def __init__(self, service_name: str | None = None):
        """
        Initialize service auth client.

        Args:
            service_name: Override service name (defaults to config)
        """
        self.service_name = service_name or security_config.service_name
        self.secret = security_config.inter_service_secret
        self.expiry = security_config.service_token_expiry_seconds

    def generate_token(self) -> str:
        """
        Generate a short-lived JWT for this service.

        Returns:
            JWT token string

        Raises:
            ValueError: If inter_service_secret not configured
        """
        if not self.secret:
            raise ValueError(
                "INTER_SERVICE_SECRET not configured. "
                "Set this environment variable for service-to-service auth."
            )

        now = datetime.utcnow()
        payload = {
            "service": self.service_name,
            "iat": now,
            "exp": now + timedelta(seconds=self.expiry),
            "type": "service",
        }

        return jwt.encode(payload, self.secret, algorithm="HS256")

    def get_auth_headers(self) -> dict[str, str]:
        """
        Get headers for authenticated inter-service request.

        Returns:
            Dict with Authorization and X-Service-Name headers
        """
        return {
            "Authorization": f"Bearer {self.generate_token()}",
            "X-Service-Name": self.service_name,
        }


def verify_service_token(request: Request) -> str:
    """
    Verify inter-service JWT token from request.

    Use as FastAPI dependency for internal endpoints:

        @router.get("/internal/data")
        async def internal_data(service: str = Depends(verify_service_token)):
            return {"caller": service}

    Returns:
        Service name from token (e.g., "sales-module")

    Raises:
        HTTPException: If token is missing, invalid, or expired
    """
    auth_header = request.headers.get("Authorization", "")

    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )

    token = auth_header[7:]  # Remove "Bearer " prefix

    if not security_config.inter_service_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Inter-service auth not configured",
        )

    try:
        payload = jwt.decode(
            token,
            security_config.inter_service_secret,
            algorithms=["HS256"],
        )

        # Verify this is a service token
        if payload.get("type") != "service":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )

        service_name = payload.get("service")
        if not service_name:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing service name in token",
            )

        logger.debug(f"[SERVICE AUTH] Verified token from: {service_name}")
        return service_name

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Service token expired",
        )
    except jwt.InvalidTokenError as e:
        logger.warning(f"[SERVICE AUTH] Invalid token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid service token",
        )


async def require_service_auth(
    service: str = Depends(verify_service_token),
) -> str:
    """
    Alias for verify_service_token for clearer intent.
    """
    return service


def require_service(allowed_services: list[str]):
    """
    Factory for requiring specific services.

    Usage:
        @router.get("/internal/sensitive")
        async def sensitive_data(
            service: str = Depends(require_service(["sales-module"]))
        ):
            ...
    """
    async def _require_service(
        service: str = Depends(verify_service_token),
    ) -> str:
        if service not in allowed_services:
            logger.warning(
                f"[SERVICE AUTH] Service {service} not allowed to access this endpoint"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Service {service} not authorized for this endpoint",
            )
        return service

    return _require_service
