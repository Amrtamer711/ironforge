"""
Authentication API endpoints.

Handles token validation and service token generation.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies import require_service_auth, get_client_ip, get_request_id
from core import auth_service, audit_service
from models import (
    TokenValidationRequest,
    TokenValidationResponse,
    ServiceTokenRequest,
    ServiceTokenResponse,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/validate-token", response_model=TokenValidationResponse)
async def validate_token(
    request: TokenValidationRequest,
    service: str = Depends(require_service_auth),
):
    """
    Validate a JWT token and return user info with RBAC context.

    This is the main endpoint used by unified-ui gateway to validate
    user tokens and get the full RBAC context for header injection.

    Returns:
        TokenValidationResponse with:
        - valid: Whether the token is valid
        - user: Basic user info (id, email, name, profile)
        - rbac_context: Full 5-level RBAC context
        - expires_at: Token expiration time
        - error: Error message if invalid
    """
    result = auth_service.validate_token(request.token)

    if not result.get("valid"):
        audit_service.log_login_failed(
            reason=result.get("error", "Unknown error"),
        )

    return TokenValidationResponse(
        valid=result.get("valid", False),
        user=result.get("user"),
        rbac_context=result.get("rbac_context"),
        expires_at=result.get("expires_at"),
        error=result.get("error"),
    )


@router.post("/service-token", response_model=ServiceTokenResponse)
async def generate_service_token(
    request: ServiceTokenRequest,
    calling_service: str = Depends(require_service_auth),
):
    """
    Generate a short-lived JWT for service-to-service communication.

    Used when one backend service needs to call another backend service.
    The token is valid for a short time (default 60 seconds).

    Returns:
        ServiceTokenResponse with:
        - token: JWT token string
        - expires_at: Expiration timestamp
    """
    try:
        result = auth_service.generate_service_token(request.service_name)

        return ServiceTokenResponse(
            token=result["token"],
            expires_at=result["expires_at"],
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post("/validate-service-token")
async def validate_service_token(
    request: TokenValidationRequest,
    calling_service: str = Depends(require_service_auth),
):
    """
    Validate a service-to-service token.

    Returns:
        {
            "valid": bool,
            "service": Service name if valid,
            "error": Error message if invalid
        }
    """
    result = auth_service.validate_service_token(request.token)

    return {
        "valid": result.get("valid", False),
        "service": result.get("service"),
        "error": result.get("error"),
    }
