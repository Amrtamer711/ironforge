"""
Slack event and interactive component handlers.
"""

import asyncio
import json
import time
from collections import defaultdict
from urllib.parse import unquote_plus

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

import config
from utils.time import get_uae_time

logger = config.logger

router = APIRouter(prefix="/slack", tags=["slack"])


@router.post("/events")
async def slack_events(request: Request):
    """Handle Slack Events API webhook."""
    from core.llm import main_llm_loop

    body = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp")
    signature = request.headers.get("X-Slack-Signature")

    if not config.signature_verifier.is_valid(body.decode(), timestamp, signature):
        raise HTTPException(status_code=403, detail="Invalid Slack signature")

    data = await request.json()
    if data.get("type") == "url_verification":
        return JSONResponse({"challenge": data["challenge"]})

    event = data.get("event", {})
    event_type = event.get("type")
    event_subtype = event.get("subtype")

    # Process regular messages and file uploads from users (not bot messages)
    # Allow file_share subtype for file uploads
    if event_type == "message" and not event.get("bot_id") and (not event_subtype or event_subtype == "file_share"):
        # Regular user messages should have user and channel
        user = event.get("user")
        channel = event.get("channel")
        if user and channel:
            asyncio.create_task(main_llm_loop(channel, user, event.get("text", ""), channel_event=event))
        else:
            logger.warning(f"[SLACK_EVENT] Message missing user or channel: {event}")
    # Handle file_shared events where Slack does not send a message subtype
    elif event_type == "file_shared":
        try:
            file_id = event.get("file_id") or (event.get("file", {}).get("id") if isinstance(event.get("file"), dict) else None)
            user = event.get("user_id") or event.get("user")
            channel = event.get("channel_id") or event.get("channel")
            if not file_id:
                logger.warning(f"[SLACK_EVENT] file_shared without file_id: {event}")
            else:
                # Fetch full file info so downstream can detect PPT
                channel_adapter = config.get_channel_adapter()
                file_obj = await channel_adapter.get_file_info(file_id) if channel_adapter else None
                # Fallback channel from file channels list if missing
                if not channel and file_obj:
                    channels = file_obj.get("channels") or []
                    if isinstance(channels, list) and channels:
                        channel = channels[0]
                if user and channel and file_obj:
                    synthetic_event = {"type": "message", "subtype": "file_share", "file": file_obj, "user": user, "channel": channel}
                    asyncio.create_task(main_llm_loop(channel, user, "", channel_event=synthetic_event))
                else:
                    logger.warning(f"[SLACK_EVENT] Cannot route file_shared event, missing user/channel/file: user={user}, channel={channel}, has_file={bool(file_obj)}")
        except Exception as e:
            logger.error(f"[SLACK_EVENT] Error handling file_shared: {e}", exc_info=True)
    elif event_type == "message" and event_subtype:
        # Log subtypes at debug level to reduce noise
        logger.debug(f"[SLACK_EVENT] Skipping message subtype '{event_subtype}'")

    return JSONResponse({"status": "ok"})


# Debounce storage for button clicks
_button_clicks = defaultdict(lambda: defaultdict(float))
DEBOUNCE_WINDOW = 3


@router.post("/interactive")
async def slack_interactive(request: Request):
    """Handle Slack interactive components (buttons, modals, etc.)"""
    from core import bo_messaging
    from integrations.channels import FieldType, Modal, ModalField, to_slack
    from workflows import bo_approval as bo_approval_workflow

    # Verify signature
    body = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp")
    signature = request.headers.get("X-Slack-Signature")

    if not config.signature_verifier.is_valid(body.decode(), timestamp, signature):
        raise HTTPException(status_code=403, detail="Invalid Slack signature")

    # Parse form data
    form_data = {}
    for line in body.decode().split('&'):
        if '=' in line:
            key, value = line.split('=', 1)
            form_data[key] = unquote_plus(value)

    payload = json.loads(form_data.get("payload", "{}"))
    interaction_type = payload.get("type")

    if interaction_type == "block_actions":
        # Button click
        user_id = payload["user"]["id"]
        actions = payload.get("actions", [])
        response_url = payload.get("response_url")
        channel = payload.get("container", {}).get("channel_id") or payload.get("channel", {}).get("id")
        message_ts = payload.get("container", {}).get("message_ts")

        if not actions:
            return JSONResponse({"status": "ok"})

        action = actions[0]
        action_id = action.get("action_id")
        workflow_id = action.get("value")

        # Debounce spam clicks (3 second window)
        current_time = time.time()
        action_key = f"{action_id}:{workflow_id}"
        last_click = _button_clicks[user_id][action_key]

        if current_time - last_click < DEBOUNCE_WINDOW:
            logger.warning(f"[BO APPROVAL] Spam click detected from {user_id}")
            return JSONResponse({"status": "ok"})

        _button_clicks[user_id][action_key] = current_time

        # Route to appropriate handler
        if action_id == "approve_bo_coordinator":
            logger.info(f"[BO APPROVAL] Coordinator {user_id} clicked APPROVE for workflow {workflow_id}")
            # Send wait message
            await bo_messaging.post_response_url(response_url, {
                "replace_original": True,
                "text": "⏳ Please wait... Processing coordinator approval..."
            })
            # Process asynchronously
            asyncio.create_task(bo_approval_workflow.handle_coordinator_approval(workflow_id, user_id, response_url))

        elif action_id == "reject_bo_coordinator":
            logger.info(f"[BO APPROVAL] Coordinator {user_id} clicked REJECT for workflow {workflow_id}, starting thread for edits")

            # Get workflow to find thread_ts
            workflow = await bo_approval_workflow.get_workflow_with_cache(workflow_id)
            thread_ts = workflow.get("coordinator_thread_ts") if workflow else message_ts

            # Edit the button message to ask what needs to be changed
            rejecter_name = await bo_messaging.get_user_real_name(user_id)
            await bo_messaging.post_response_url(response_url, {
                "replace_original": True,
                "text": to_slack(
                    f"❌ *Rejected by {rejecter_name}*\n\n"
                    "What would you like to change? You can:\n"
                    "• Describe changes in natural language\n"
                    "• Make multiple edits\n"
                    "• When ready, say *'execute'* to regenerate the Excel and create new approval buttons\n\n"
                    "Please describe the changes needed:"
                )
            })

            # Update workflow to track rejection
            await bo_approval_workflow.update_workflow(workflow_id, {
                "status": "coordinator_rejected",
                "coordinator_rejected_by": user_id,
                "coordinator_rejected_at": get_uae_time().isoformat()
            })

            logger.info(f"[BO APPROVAL] Started edit conversation in thread {thread_ts} for {workflow_id}")

        elif action_id == "cancel_bo_coordinator":
            logger.info(f"[BO APPROVAL] Coordinator {user_id} clicked CANCEL for workflow {workflow_id}, opening modal")
            # Open modal for cancellation reason
            channel_adapter = config.get_channel_adapter()
            modal = Modal(
                modal_id=f"cancel_bo_coordinator_modal:{workflow_id}",
                title="Cancel BO",
                submit_text="Confirm Cancel",
                cancel_text="Go Back",
                fields=[
                    ModalField(
                        field_id="reason_input",
                        label="Cancellation Reason",
                        field_type=FieldType.TEXTAREA,
                        placeholder="Explain why you're cancelling this booking order...",
                        block_id="cancellation_reason"
                    )
                ]
            )
            await channel_adapter.open_modal(trigger_id=payload.get("trigger_id"), modal=modal)

        elif action_id == "approve_bo_hos":
            logger.info(f"[BO APPROVAL] Head of Sales {user_id} clicked APPROVE for workflow {workflow_id}")
            # Send wait message
            await bo_messaging.post_response_url(response_url, {
                "replace_original": True,
                "text": "⏳ Please wait... Processing HoS approval and saving to database..."
            })
            # Process asynchronously
            asyncio.create_task(bo_approval_workflow.handle_hos_approval(workflow_id, user_id, response_url))

        elif action_id == "reject_bo_hos":
            logger.info(f"[BO APPROVAL] Head of Sales {user_id} clicked REJECT for workflow {workflow_id}, opening modal")
            # Open modal for rejection reason
            channel_adapter = config.get_channel_adapter()
            modal = Modal(
                modal_id=f"reject_bo_hos_modal:{workflow_id}",
                title="Reject BO",
                submit_text="Submit",
                cancel_text="Cancel",
                fields=[
                    ModalField(
                        field_id="reason_input",
                        label="Rejection Reason",
                        field_type=FieldType.TEXTAREA,
                        placeholder="Explain why you're rejecting this booking order...",
                        block_id="rejection_reason"
                    )
                ]
            )
            await channel_adapter.open_modal(trigger_id=payload.get("trigger_id"), modal=modal)

        elif action_id == "cancel_bo_hos":
            logger.info(f"[BO APPROVAL] Head of Sales {user_id} clicked CANCEL for workflow {workflow_id}, opening modal")
            # Open modal for cancellation reason
            channel_adapter = config.get_channel_adapter()
            modal = Modal(
                modal_id=f"cancel_bo_hos_modal:{workflow_id}",
                title="Cancel BO",
                submit_text="Confirm Cancel",
                cancel_text="Go Back",
                fields=[
                    ModalField(
                        field_id="reason_input",
                        label="Cancellation Reason",
                        field_type=FieldType.TEXTAREA,
                        placeholder="Explain why you're cancelling this booking order...",
                        block_id="cancellation_reason"
                    )
                ]
            )
            await channel_adapter.open_modal(trigger_id=payload.get("trigger_id"), modal=modal)

    elif interaction_type == "view_submission":
        # Modal submission
        callback_id = payload.get("view", {}).get("callback_id", "")
        user_id = payload["user"]["id"]

        # Handle coordinator rejection modal
        if callback_id.startswith("reject_bo_coordinator_modal:"):
            parts = callback_id.split(":")
            workflow_id = parts[1]
            channel = parts[2]
            message_ts = parts[3]

            # Extract rejection reason from modal
            values = payload.get("view", {}).get("state", {}).get("values", {})
            rejection_reason = values.get("rejection_reason", {}).get("reason_input", {}).get("value", "No reason provided")

            logger.info(f"[BO APPROVAL] Coordinator {user_id} submitted rejection modal for {workflow_id}: {rejection_reason[:50]}...")

            # Process rejection asynchronously
            asyncio.create_task(bo_approval_workflow.handle_coordinator_rejection(
                workflow_id, user_id, None, rejection_reason, channel, message_ts
            ))

            # Return empty response to close modal
            return JSONResponse({})

        # Handle HoS rejection modal
        elif callback_id.startswith("reject_bo_hos_modal:"):
            parts = callback_id.split(":")
            workflow_id = parts[1]

            # Extract rejection reason from modal
            values = payload.get("view", {}).get("state", {}).get("values", {})
            rejection_reason = values.get("rejection_reason", {}).get("reason_input", {}).get("value", "No reason provided")

            logger.info(f"[BO APPROVAL] Head of Sales {user_id} submitted rejection modal for {workflow_id}: {rejection_reason[:50]}...")

            # Process rejection asynchronously
            asyncio.create_task(bo_approval_workflow.handle_hos_rejection(
                workflow_id, user_id, None, rejection_reason
            ))

            # Return empty response to close modal
            return JSONResponse({})

        # Handle coordinator cancellation modal
        elif callback_id.startswith("cancel_bo_coordinator_modal:"):
            workflow_id = callback_id.split(":")[1]

            # Extract cancellation reason from modal
            values = payload.get("view", {}).get("state", {}).get("values", {})
            cancellation_reason = values.get("cancellation_reason", {}).get("reason_input", {}).get("value", "No reason provided")

            logger.info(f"[BO APPROVAL] Coordinator {user_id} submitted cancellation modal for {workflow_id}: {cancellation_reason[:50]}...")

            # Process cancellation asynchronously
            asyncio.create_task(bo_approval_workflow.handle_bo_cancellation(
                workflow_id, user_id, cancellation_reason, "coordinator"
            ))

            # Return empty response to close modal
            return JSONResponse({})

        # Handle HoS cancellation modal
        elif callback_id.startswith("cancel_bo_hos_modal:"):
            workflow_id = callback_id.split(":")[1]

            # Extract cancellation reason from modal
            values = payload.get("view", {}).get("state", {}).get("values", {})
            cancellation_reason = values.get("cancellation_reason", {}).get("reason_input", {}).get("value", "No reason provided")

            logger.info(f"[BO APPROVAL] Head of Sales {user_id} submitted cancellation modal for {workflow_id}: {cancellation_reason[:50]}...")

            # Process cancellation asynchronously
            asyncio.create_task(bo_approval_workflow.handle_bo_cancellation(
                workflow_id, user_id, cancellation_reason, "hos"
            ))

            # Return empty response to close modal
            return JSONResponse({})

    return JSONResponse({"status": "ok"})
