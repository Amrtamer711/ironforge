"""
Proxy router for unified-ui.

This router proxies authenticated requests to the backend API service with
trusted user headers, enabling the backend to trust the user context without
re-validating tokens.

5-Level RBAC context is injected as headers:
1. User identity & profile
2. Combined permissions (profile + permission sets)
3. Teams and hierarchy
4. Sharing rules & record shares
5. Company access

See backend/contracts/trusted_headers.py for the header contract.
"""

import json
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from backend.config import get_settings
from backend.contracts.trusted_headers import (
    HEADER_PROXY_SECRET,
    HEADER_USER_COMPANIES,
    HEADER_USER_EMAIL,
    HEADER_USER_ID,
    HEADER_USER_MANAGER_ID,
    HEADER_USER_NAME,
    HEADER_USER_PERMISSION_SETS,
    HEADER_USER_PERMISSIONS,
    HEADER_USER_PROFILE,
    HEADER_USER_SHARED_FROM_USER_IDS,
    HEADER_USER_SHARED_RECORDS,
    HEADER_USER_SHARING_RULES,
    HEADER_USER_SUBORDINATE_IDS,
    HEADER_USER_TEAM_IDS,
    HEADER_USER_TEAMS,
)
from backend.middleware.auth import TrustedUser, get_trusted_user

logger = logging.getLogger("unified-ui")

router = APIRouter(tags=["proxy"])


def _build_trusted_headers(user: TrustedUser, proxy_secret: str | None) -> dict[str, str]:
    """
    Build trusted headers to inject into proxy request.

    Uses header names from backend/contracts/trusted_headers.py to ensure
    consistency with downstream consumers.

    Args:
        user: TrustedUser with full RBAC context
        proxy_secret: Shared secret to prove request origin

    Returns:
        Dictionary of headers to inject
    """
    headers: dict[str, str] = {}

    # Proxy secret for authentication
    if proxy_secret:
        headers[HEADER_PROXY_SECRET] = proxy_secret

    # Level 1: User identity & profile
    headers[HEADER_USER_ID] = user.id
    headers[HEADER_USER_EMAIL] = user.email
    headers[HEADER_USER_NAME] = user.name
    headers[HEADER_USER_PROFILE] = user.profile

    # Level 2: Combined permissions (profile + permission sets)
    headers[HEADER_USER_PERMISSIONS] = json.dumps(user.permissions)
    headers[HEADER_USER_PERMISSION_SETS] = json.dumps(user.permission_sets)

    # Level 3: Teams & hierarchy
    headers[HEADER_USER_TEAMS] = json.dumps(user.teams)
    headers[HEADER_USER_TEAM_IDS] = json.dumps(user.team_ids)
    if user.manager_id:
        headers[HEADER_USER_MANAGER_ID] = user.manager_id
    headers[HEADER_USER_SUBORDINATE_IDS] = json.dumps(user.subordinate_ids)

    # Level 4: Sharing rules & record shares
    headers[HEADER_USER_SHARING_RULES] = json.dumps(user.sharing_rules)
    headers[HEADER_USER_SHARED_RECORDS] = json.dumps(user.shared_records)
    headers[HEADER_USER_SHARED_FROM_USER_IDS] = json.dumps(user.shared_from_user_ids)

    # Level 5: Company access
    headers[HEADER_USER_COMPANIES] = json.dumps(user.companies)

    return headers


@router.api_route(
    "/api/sales/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
async def proxy_to_sales_bot(
    path: str,
    request: Request,
    user: TrustedUser = Depends(get_trusted_user),
) -> Response:
    """
    Proxy requests to the backend API service with trusted headers.

    Path transformation:
    /api/sales/chat/history -> /api/chat/history on backend
    """
    settings = get_settings()

    # Build target URL
    # When mounted at /api/sales, path comes in already stripped
    # Forward to /api/{path} on the backend
    target_url = f"{settings.SALES_BOT_URL}/api/{path}"
    if request.query_params:
        target_url += f"?{request.query_params}"

    logger.info(f"[PROXY] {request.method} /api/sales/{path} -> {target_url}")
    logger.info(f"[PROXY] User: {user.email} | Profile: {user.profile}")

    # Build trusted headers using contract
    trusted_headers = _build_trusted_headers(user, settings.PROXY_SECRET)

    # Forward original authorization header (backward compat)
    auth_header = request.headers.get("authorization")
    if auth_header:
        trusted_headers["Authorization"] = auth_header

    # Forward client IP
    ip = request.headers.get("x-forwarded-for") or (
        request.client.host if request.client else None
    )
    if ip:
        trusted_headers["X-Forwarded-For"] = ip

    # Forward content type if present
    content_type = request.headers.get("content-type")
    if content_type:
        trusted_headers["Content-Type"] = content_type

    # Check if this is a streaming request (SSE)
    is_streaming = (
        "stream" in path or
        request.headers.get("accept") == "text/event-stream"
    )

    try:
        body = await request.body()

        if is_streaming:
            # SSE streaming response
            return await _proxy_streaming(
                method=request.method,
                url=target_url,
                headers=trusted_headers,
                body=body,
            )
        else:
            # Regular response
            return await _proxy_regular(
                method=request.method,
                url=target_url,
                headers=trusted_headers,
                body=body,
            )

    except httpx.TimeoutException:
        logger.error(f"[PROXY] Timeout for {request.method} {target_url}")
        raise HTTPException(
            status_code=504,
            detail="Request timed out",
        )
    except httpx.ConnectError as e:
        logger.error(f"[PROXY] Connection error for {request.method} {target_url}: {e}")
        settings = get_settings()
        if settings.is_production:
            raise HTTPException(
                status_code=502,
                detail="Service temporarily unavailable",
            )
        else:
            raise HTTPException(
                status_code=502,
                detail={
                    "error": "Service unavailable",
                    "details": str(e),
                    "target": settings.SALES_BOT_URL,
                },
            )
    except Exception as e:
        logger.error(f"[PROXY] Error: {e}")
        raise HTTPException(status_code=502, detail="Proxy error")


async def _proxy_regular(
    method: str,
    url: str,
    headers: dict[str, str],
    body: bytes,
) -> Response:
    """
    Proxy a regular (non-streaming) request.
    """
    async with httpx.AsyncClient(timeout=300.0) as client:
        response = await client.request(
            method=method,
            url=url,
            headers=headers,
            content=body,
        )

        logger.info(f"[PROXY] Response: {response.status_code}")

        # Forward response headers, filtering out hop-by-hop headers
        # Also skip content-encoding since httpx auto-decompresses
        response_headers = {}
        skip_headers = {
            "transfer-encoding",
            "content-encoding",  # httpx already decompresses, don't confuse browser
            "content-length",    # length changed after decompression
            "connection",
            "keep-alive",
            "proxy-authenticate",
            "proxy-authorization",
            "te",
            "trailers",
            "upgrade",
        }
        for key, value in response.headers.items():
            if key.lower() not in skip_headers:
                response_headers[key] = value

        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=response_headers,
        )


async def _proxy_streaming(
    method: str,
    url: str,
    headers: dict[str, str],
    body: bytes,
) -> StreamingResponse:
    """Proxy a streaming (SSE) request."""

    async def stream_generator():
        async with httpx.AsyncClient(timeout=300.0) as client, client.stream(
            method=method,
            url=url,
            headers=headers,
            content=body,
        ) as response:
            logger.info(f"[PROXY] Streaming response: {response.status_code}")
            async for chunk in response.aiter_bytes():
                yield chunk

    # SSE headers
    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
