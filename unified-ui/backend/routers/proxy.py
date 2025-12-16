"""
Proxy router for unified-ui.

[VERIFIED] Mirrors server.js lines 624-717:
- Auth middleware for proxy (proxyAuthMiddleware - lines 548-621)
- Proxy middleware (lines 630-717)
- Trusted header injection (lines 649-696)

This router proxies authenticated requests to proposal-bot with trusted
user headers, enabling proposal-bot to trust the user context without
re-validating tokens.

5-Level RBAC context is injected as headers:
1. User identity & profile
2. Combined permissions (profile + permission sets)
3. Teams and hierarchy
4. Sharing rules & record shares
5. Company access
"""

import json
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from backend.config import get_settings
from backend.middleware.auth import TrustedUser, get_trusted_user

logger = logging.getLogger("unified-ui")

router = APIRouter(tags=["proxy"])


def _build_trusted_headers(user: TrustedUser, proxy_secret: str | None) -> dict[str, str]:
    """
    Build trusted headers to inject into proxy request.

    Mirrors server.js:649-696 (proxyReq handler)

    Args:
        user: TrustedUser with full RBAC context
        proxy_secret: Shared secret to prove request is from unified-ui

    Returns:
        Dictionary of headers to inject
    """
    headers: dict[str, str] = {}

    # server.js:652-655 - Send proxy secret
    if proxy_secret:
        headers["X-Proxy-Secret"] = proxy_secret

    # Level 1: User identity & profile - server.js:657-661
    headers["X-Trusted-User-Id"] = user.id
    headers["X-Trusted-User-Email"] = user.email
    headers["X-Trusted-User-Name"] = user.name
    headers["X-Trusted-User-Profile"] = user.profile

    # Level 1 + 2: Combined permissions - server.js:663-664
    headers["X-Trusted-User-Permissions"] = json.dumps(user.permissions)

    # Level 2: Active permission sets - server.js:666-667
    headers["X-Trusted-User-Permission-Sets"] = json.dumps(user.permission_sets)

    # Level 3: Teams - server.js:669-671
    headers["X-Trusted-User-Teams"] = json.dumps(user.teams)
    headers["X-Trusted-User-Team-Ids"] = json.dumps(user.team_ids)

    # Level 3: Hierarchy - server.js:673-677
    if user.manager_id:
        headers["X-Trusted-User-Manager-Id"] = user.manager_id
    headers["X-Trusted-User-Subordinate-Ids"] = json.dumps(user.subordinate_ids)

    # Level 4: Sharing Rules & Record Shares - server.js:679-682
    headers["X-Trusted-User-Sharing-Rules"] = json.dumps(user.sharing_rules)
    headers["X-Trusted-User-Shared-Records"] = json.dumps(user.shared_records)
    headers["X-Trusted-User-Shared-From-User-Ids"] = json.dumps(user.shared_from_user_ids)

    # Level 5: Company access - server.js:684-685
    headers["X-Trusted-User-Companies"] = json.dumps(user.companies)

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
    Proxy requests to proposal-bot (sales module) with trusted headers.

    Mirrors server.js:630-717

    Path transformation (server.js:633-639):
    /api/sales/chat/history -> /api/chat/history on proposal-bot
    """
    settings = get_settings()

    # Build target URL - server.js:633-639
    # When mounted at /api/sales, path comes in ALREADY STRIPPED
    # We want to forward to /api/{path} on the target
    target_url = f"{settings.SALES_BOT_URL}/api/{path}"
    if request.query_params:
        target_url += f"?{request.query_params}"

    logger.info(f"[PROXY] {request.method} /api/sales/{path} -> {target_url}")
    logger.info(f"[PROXY] User: {user.email} | Profile: {user.profile}")

    # Build trusted headers - server.js:649-696
    trusted_headers = _build_trusted_headers(user, settings.PROXY_SECRET)

    # Forward original authorization header (backward compat) - server.js:688-691
    auth_header = request.headers.get("authorization")
    if auth_header:
        trusted_headers["Authorization"] = auth_header

    # Forward IP - server.js:693-695
    ip = request.headers.get("x-forwarded-for") or (
        request.client.host if request.client else None
    )
    if ip:
        trusted_headers["X-Forwarded-For"] = ip

    # Forward content type if present
    content_type = request.headers.get("content-type")
    if content_type:
        trusted_headers["Content-Type"] = content_type

    # Check if this is a streaming request - server.js:700-704
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
    """
    Proxy a streaming (SSE) request.

    Mirrors server.js:700-704 SSE handling.
    """

    async def stream_generator():
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream(
                method=method,
                url=url,
                headers=headers,
                content=body,
            ) as response:
                logger.info(f"[PROXY] Streaming response: {response.status_code}")
                async for chunk in response.aiter_bytes():
                    yield chunk

    # server.js:700-704 - SSE headers
    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
