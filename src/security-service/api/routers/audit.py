"""
Audit Logging API endpoints.

Handles audit event logging and querying.
"""

from fastapi import APIRouter, Depends, Query

from api.dependencies import require_service_auth, get_client_ip, get_request_id
from core import audit_service
from models import (
    AuditLogRequest,
    AuditLogResponse,
    AuditLogQuery,
    AuditLogListResponse,
)

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.post("/log", response_model=AuditLogResponse)
async def log_audit_event(
    request: AuditLogRequest,
    service: str = Depends(require_service_auth),
):
    """
    Log an audit event.

    Called by other services to log security-relevant actions.
    All events are stored in Security Supabase for compliance.

    Returns:
        AuditLogResponse with:
        - logged: Whether the event was successfully logged
        - audit_id: ID of the created audit record
    """
    result = audit_service.log_event(
        actor_type=request.actor_type,
        service=request.service or service,
        action=request.action,
        actor_id=request.actor_id,
        actor_email=request.actor_email,
        actor_ip=request.actor_ip,
        resource_type=request.resource_type,
        resource_id=request.resource_id,
        result=request.result,
        error_message=request.error_message,
        request_id=request.request_id,
        request_method=request.request_method,
        request_path=request.request_path,
        request_body=request.request_body,
        response_status=request.response_status,
        duration_ms=request.duration_ms,
        metadata=request.metadata,
    )

    return AuditLogResponse(
        logged=result is not None,
        audit_id=result.get("id") if result else None,
    )


@router.get("/logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    actor_id: str | None = Query(None, description="Filter by actor ID"),
    actor_type: str | None = Query(None, description="Filter by actor type"),
    service_filter: str | None = Query(None, alias="service", description="Filter by service"),
    action: str | None = Query(None, description="Filter by action"),
    resource_type: str | None = Query(None, description="Filter by resource type"),
    resource_id: str | None = Query(None, description="Filter by resource ID"),
    result: str | None = Query(None, description="Filter by result"),
    start_date: str | None = Query(None, description="Start date (ISO format)"),
    end_date: str | None = Query(None, description="End date (ISO format)"),
    limit: int = Query(100, le=1000, description="Max results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    service: str = Depends(require_service_auth),
):
    """
    Query audit logs with filters.

    Requires service authentication. Used for:
    - Admin dashboards
    - Compliance reporting
    - Security investigations

    Returns:
        AuditLogListResponse with:
        - logs: List of audit log records
        - total: Total count matching filters
        - limit: Applied limit
        - offset: Applied offset
    """
    logs, total = audit_service.list_events(
        actor_id=actor_id,
        actor_type=actor_type,
        service=service_filter,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        result=result,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )

    return AuditLogListResponse(
        logs=logs,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/logs/{log_id}")
async def get_audit_log(
    log_id: str,
    service: str = Depends(require_service_auth),
):
    """
    Get a single audit log by ID.

    Returns:
        Audit log record or 404
    """
    log = audit_service.get_event(log_id)

    if not log:
        return {"error": "Audit log not found"}

    return log


@router.get("/logs/by-request/{request_id}")
async def get_logs_by_request(
    request_id: str,
    service: str = Depends(require_service_auth),
):
    """
    Get all audit logs for a specific request ID.

    Useful for tracing a request across services.

    Returns:
        List of audit log records
    """
    logs, _ = audit_service.list_events(
        request_id=request_id,
        limit=100,
    )

    return {
        "request_id": request_id,
        "logs": logs,
    }
