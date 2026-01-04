"""
Slack Router for Video Critique.

Handles Slack webhook endpoints for events, interactive components,
and slash commands.
"""

import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import parse_qs

from fastapi import APIRouter, Request, Response, HTTPException, BackgroundTasks

import config
from handlers.slack_handler import SlackEventHandler
from core.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/slack", tags=["slack"])

# Lazy-initialized handler
_handler: SlackEventHandler | None = None

# Event deduplication TTL in seconds
EVENT_DEDUP_TTL = 600  # 10 minutes


def get_handler() -> SlackEventHandler:
    """Get or create the Slack event handler."""
    global _handler
    if _handler is None:
        from integrations.channels import get_channel
        channel = get_channel("slack")
        _handler = SlackEventHandler(channel=channel)
    return _handler


async def is_duplicate_event(event_id: str) -> bool:
    """
    Check if an event has already been processed.

    Uses crm-cache for deduplication with fallback to memory cache.

    Args:
        event_id: Unique event identifier from Slack

    Returns:
        True if event was already processed (duplicate)
    """
    if not event_id:
        return False

    try:
        from crm_cache import get_cache

        cache = get_cache()
        cache_key = f"slack:event:{event_id}"

        # Check if event already processed
        if await cache.exists(cache_key):
            logger.debug(f"[Slack] Duplicate event detected: {event_id}")
            return True

        # Mark event as processed
        await cache.set(cache_key, "1", ttl=EVENT_DEDUP_TTL)
        return False

    except Exception as e:
        # Log but don't fail - better to process duplicate than miss event
        logger.warning(f"[Slack] Event deduplication error: {e}")
        return False


# ============================================================================
# SIGNATURE VERIFICATION
# ============================================================================

def verify_slack_signature(
    body: bytes,
    timestamp: str,
    signature: str,
) -> bool:
    """
    Verify Slack request signature.

    Args:
        body: Raw request body
        timestamp: X-Slack-Request-Timestamp header
        signature: X-Slack-Signature header

    Returns:
        True if signature is valid
    """
    signing_secret = getattr(config, "SLACK_SIGNING_SECRET", "")
    if not signing_secret:
        logger.warning("[Slack] No signing secret configured")
        return True  # Allow in development

    # Check timestamp is not too old (5 minutes)
    try:
        request_time = int(timestamp)
        if abs(time.time() - request_time) > 300:
            logger.warning("[Slack] Request timestamp too old")
            return False
    except (ValueError, TypeError):
        return False

    # Compute signature
    sig_basestring = f"v0:{timestamp}:{body.decode()}"
    computed_sig = "v0=" + hmac.new(
        signing_secret.encode(),
        sig_basestring.encode(),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(computed_sig, signature)


# ============================================================================
# EVENT ENDPOINTS
# ============================================================================

@router.post("/events")
async def slack_events(request: Request, background_tasks: BackgroundTasks):
    """
    Handle Slack Events API webhooks.

    Processes message events, file shares, app mentions, etc.
    """
    body = await request.body()

    # Verify signature
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    if not verify_slack_signature(body, timestamp, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Parse body
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Handle URL verification challenge
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge")}

    # Handle event callback
    if payload.get("type") == "event_callback":
        event = payload.get("event", {})

        # Get event ID for deduplication
        # Slack provides event_id in the outer payload, or we can use client_msg_id/event_ts
        event_id = payload.get("event_id") or event.get("client_msg_id") or event.get("event_ts")

        # Check for duplicate event
        if event_id and await is_duplicate_event(event_id):
            logger.info(f"[Slack] Skipping duplicate event: {event_id}")
            return Response(status_code=200)

        # Process event in background to respond quickly
        background_tasks.add_task(process_event, event)

        # Respond immediately
        return Response(status_code=200)

    return {"status": "ok"}


async def process_event(event: dict[str, Any]):
    """Process a Slack event in the background."""
    try:
        handler = get_handler()
        await handler.handle_event(event)
    except Exception as e:
        logger.error(f"[Slack] Error processing event: {e}")


# ============================================================================
# INTERACTIVE ENDPOINTS
# ============================================================================

@router.post("/interactive")
async def slack_interactive(request: Request, background_tasks: BackgroundTasks):
    """
    Handle Slack interactive component callbacks.

    Processes button clicks, modal submissions, etc.
    """
    body = await request.body()

    # Verify signature
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    if not verify_slack_signature(body, timestamp, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Parse form data
    try:
        form_data = parse_qs(body.decode())
        payload_str = form_data.get("payload", [""])[0]
        payload = json.loads(payload_str)
    except (json.JSONDecodeError, KeyError, IndexError):
        raise HTTPException(status_code=400, detail="Invalid payload")

    payload_type = payload.get("type")

    # Deduplicate interactive payloads using action_ts or trigger_id
    action_id = payload.get("trigger_id") or payload.get("actions", [{}])[0].get("action_ts")
    if action_id and await is_duplicate_event(f"interactive:{action_id}"):
        logger.info(f"[Slack] Skipping duplicate interactive: {action_id}")
        return Response(status_code=200)

    # Handle different payload types
    if payload_type == "block_actions":
        # Process button clicks in background
        background_tasks.add_task(process_interactive, payload)
        return Response(status_code=200)

    elif payload_type == "view_submission":
        # Modal submissions need immediate response
        handler = get_handler()
        result = await handler.handle_interactive(payload)

        # Return response action if any
        if result.get("response_action"):
            return result

        return Response(status_code=200)

    elif payload_type == "shortcut":
        background_tasks.add_task(process_interactive, payload)
        return Response(status_code=200)

    return Response(status_code=200)


async def process_interactive(payload: dict[str, Any]):
    """Process an interactive payload in the background."""
    try:
        handler = get_handler()
        await handler.handle_interactive(payload)
    except Exception as e:
        logger.error(f"[Slack] Error processing interactive: {e}")


# ============================================================================
# COMMAND ENDPOINTS
# ============================================================================

@router.post("/commands")
async def slack_commands(request: Request, background_tasks: BackgroundTasks):
    """
    Handle Slack slash commands.

    Processes /log, /edit, /delete, etc.
    """
    body = await request.body()

    # Verify signature
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    if not verify_slack_signature(body, timestamp, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Parse form data
    form_data = parse_qs(body.decode())

    command = form_data.get("command", [""])[0]
    text = form_data.get("text", [""])[0]
    user_id = form_data.get("user_id", [""])[0]
    channel_id = form_data.get("channel_id", [""])[0]
    response_url = form_data.get("response_url", [""])[0]

    # Process command in background
    background_tasks.add_task(
        process_command,
        command,
        text,
        user_id,
        channel_id,
        response_url,
    )

    # Return immediate acknowledgment
    return {
        "response_type": "ephemeral",
        "text": "Processing your request...",
    }


async def process_command(
    command: str,
    text: str,
    user_id: str,
    channel_id: str,
    response_url: str,
):
    """Process a slash command in the background."""
    import aiohttp

    try:
        handler = get_handler()
        result = await handler.handle_command(
            command=command,
            text=text,
            user_id=user_id,
            channel_id=channel_id,
            response_url=response_url,
        )

        # Send response via response_url
        if response_url and result:
            async with aiohttp.ClientSession() as session:
                await session.post(
                    response_url,
                    json={
                        "response_type": result.get("response_type", "ephemeral"),
                        "text": result.get("text", result.get("response", "")),
                    },
                )

    except Exception as e:
        logger.error(f"[Slack] Error processing command: {e}")

        # Try to send error response
        if response_url:
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    await session.post(
                        response_url,
                        json={
                            "response_type": "ephemeral",
                            "text": f"Error: {str(e)}",
                        },
                    )
            except Exception:
                pass
