"""
API Key Management endpoints.

Handles API key creation, validation, and lifecycle management.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.dependencies import require_service_auth
from core import api_key_service, audit_service
from models import (
    APIKeyCreateRequest,
    APIKeyCreateResponse,
    APIKeyResponse,
    APIKeyUpdateRequest,
    APIKeyValidateRequest,
    APIKeyValidateResponse,
    APIKeyListResponse,
    APIKeyUsageResponse,
)

router = APIRouter(prefix="/api/api-keys", tags=["api-keys"])


@router.post("/validate", response_model=APIKeyValidateResponse)
async def validate_api_key(
    request: APIKeyValidateRequest,
    service: str = Depends(require_service_auth),
):
    """
    Validate an API key.

    Called by services to validate incoming API key authentication.

    Returns:
        APIKeyValidateResponse with:
        - valid: Whether the key is valid
        - key_info: Key details if valid (id, name, scopes, limits)
        - error: Error message if invalid
    """
    result = api_key_service.validate_key(
        raw_key=request.api_key,
        required_scope=request.required_scope,
        service=request.service,
        client_ip=request.client_ip,
    )

    if result.get("valid"):
        key_info = result.get("key_info")
        return APIKeyValidateResponse(
            valid=True,
            key_info={
                "id": key_info.id,
                "name": key_info.name,
                "scopes": [s.value for s in key_info.scopes],
                "rate_limit_per_minute": key_info.rate_limit_per_minute,
                "rate_limit_per_day": key_info.rate_limit_per_day,
            },
        )

    return APIKeyValidateResponse(
        valid=False,
        error=result.get("error"),
    )


@router.post("", response_model=APIKeyCreateResponse)
async def create_api_key(
    request: APIKeyCreateRequest,
    service: str = Depends(require_service_auth),
):
    """
    Create a new API key.

    The raw key is returned ONCE in the response. It cannot be retrieved
    again after creation - only a hash is stored.

    Returns:
        APIKeyCreateResponse with:
        - key: The raw API key (SAVE THIS!)
        - key_id: Database ID of the key
        - key_prefix: First 12 chars for identification
        - name: Key name
        - scopes: Key scopes
    """
    try:
        result = api_key_service.generate_key(
            name=request.name,
            scopes=request.scopes,
            created_by=request.created_by,
            description=request.description,
            allowed_services=request.allowed_services,
            allowed_ips=request.allowed_ips,
            rate_limit_per_minute=request.rate_limit_per_minute,
            rate_limit_per_day=request.rate_limit_per_day,
            expires_at=request.expires_at,
            metadata=request.metadata,
        )

        audit_service.log_event(
            actor_type="user" if request.created_by else "service",
            actor_id=request.created_by or service,
            service="security-service",
            action="api_key.create",
            resource_type="api_key",
            resource_id=result["key_id"],
            metadata={"key_name": request.name},
        )

        return APIKeyCreateResponse(
            key=result["key"],
            key_id=result["key_id"],
            key_prefix=result["key_prefix"],
            name=result["name"],
            scopes=result["scopes"],
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create API key: {str(e)}",
        )


@router.get("", response_model=APIKeyListResponse)
async def list_api_keys(
    created_by: str | None = Query(None, description="Filter by creator"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    limit: int = Query(100, le=1000, description="Max results"),
    offset: int = Query(0, ge=0, description="Offset"),
    service: str = Depends(require_service_auth),
):
    """
    List API keys.

    Returns keys without the actual key values (only prefix shown).
    """
    keys, total = api_key_service.list_keys(
        created_by=created_by,
        is_active=is_active,
        limit=limit,
        offset=offset,
    )

    return APIKeyListResponse(
        keys=keys,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{key_id}", response_model=APIKeyResponse)
async def get_api_key(
    key_id: str,
    service: str = Depends(require_service_auth),
):
    """
    Get API key details by ID.

    Does not return the actual key value.
    """
    key = api_key_service.get_key(key_id)

    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )

    return APIKeyResponse(**key)


@router.patch("/{key_id}", response_model=APIKeyResponse)
async def update_api_key(
    key_id: str,
    request: APIKeyUpdateRequest,
    service: str = Depends(require_service_auth),
):
    """
    Update an API key.

    Can update: name, description, scopes, allowed_services,
    allowed_ips, rate_limits, is_active, expires_at, metadata.
    """
    updates = request.model_dump(exclude_unset=True)

    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No updates provided",
        )

    result = api_key_service.update_key(key_id, updates)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )

    audit_service.log_event(
        actor_type="service",
        actor_id=service,
        service="security-service",
        action="api_key.update",
        resource_type="api_key",
        resource_id=key_id,
        metadata={"updated_fields": list(updates.keys())},
    )

    return APIKeyResponse(**result)


@router.delete("/{key_id}")
async def revoke_api_key(
    key_id: str,
    hard_delete: bool = Query(False, description="Permanently delete instead of soft delete"),
    service: str = Depends(require_service_auth),
):
    """
    Revoke (soft delete) or permanently delete an API key.

    Default is soft delete (is_active = false).
    Use hard_delete=true to permanently remove.
    """
    if hard_delete:
        success = api_key_service.delete_key(key_id)
        action = "api_key.delete"
    else:
        success = api_key_service.revoke_key(key_id)
        action = "api_key.revoke"

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )

    audit_service.log_event(
        actor_type="service",
        actor_id=service,
        service="security-service",
        action=action,
        resource_type="api_key",
        resource_id=key_id,
    )

    return {
        "success": True,
        "action": "deleted" if hard_delete else "revoked",
    }


@router.get("/{key_id}/usage", response_model=APIKeyUsageResponse)
async def get_api_key_usage(
    key_id: str,
    start_date: str | None = Query(None, description="Start date (ISO format)"),
    end_date: str | None = Query(None, description="End date (ISO format)"),
    service: str = Depends(require_service_auth),
):
    """
    Get API key usage statistics.

    Returns request counts for different time periods.
    """
    usage = api_key_service.get_usage(key_id, start_date, end_date)

    return APIKeyUsageResponse(
        key_id=key_id,
        total_requests=usage.get("total_requests", 0),
        requests_today=usage.get("requests_today", 0),
        requests_this_hour=usage.get("requests_this_hour", 0),
        last_used_at=usage.get("last_used_at"),
    )
