import asyncio
from datetime import datetime, timezone, timedelta
import subprocess
import shutil
from contextlib import asynccontextmanager
from typing import Optional

# UAE timezone (GMT+4)
UAE_TZ = timezone(timedelta(hours=4))

def get_uae_time():
    """Get current time in UAE timezone (GMT+4)"""
    return datetime.now(UAE_TZ)

from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List

import config
from db.database import db
from core.llm import main_llm_loop
from font_utils import install_custom_fonts

# Install custom fonts on startup
install_custom_fonts()

# Load location templates
config.refresh_templates()

# Check LibreOffice installation
logger = config.logger
logger.info("[STARTUP] Checking LibreOffice installation...")
libreoffice_found = False
for cmd in ['libreoffice', 'soffice', '/usr/bin/libreoffice']:
    if shutil.which(cmd) or subprocess.run(['which', cmd], capture_output=True).returncode == 0:
        try:
            result = subprocess.run([cmd, '--version'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                logger.info(f"[STARTUP] LibreOffice found at '{cmd}': {result.stdout.strip()}")
                libreoffice_found = True
                break
        except Exception as e:
            logger.debug(f"[STARTUP] Error checking {cmd}: {e}")

if not libreoffice_found:
    logger.warning("[STARTUP] LibreOffice not found! PDF conversion will use fallback method.")
else:
    logger.info("[STARTUP] LibreOffice is ready for PDF conversion.")


async def periodic_cleanup():
    """Background task to clean up old data periodically"""
    while True:
        await asyncio.sleep(300)  # Every 5 minutes
        try:
            # Clean up old user histories
            from db.cache import user_history, pending_location_additions
            from datetime import timedelta
            
            # Clean user histories older than 1 hour
            cutoff = get_uae_time() - timedelta(hours=1)
            expired_users = []
            for uid, history in user_history.items():
                if history and hasattr(history[-1], 'get'):
                    timestamp_str = history[-1].get('timestamp')
                    if timestamp_str:
                        try:
                            last_time = datetime.fromisoformat(timestamp_str)
                            if last_time < cutoff:
                                expired_users.append(uid)
                        except:
                            pass
            
            for uid in expired_users:
                del user_history[uid]
            
            if expired_users:
                logger.info(f"[CLEANUP] Removed {len(expired_users)} old user histories")
                
            # Clean pending locations older than 10 minutes
            location_cutoff = get_uae_time() - timedelta(minutes=10)
            expired_locations = [
                uid for uid, data in pending_location_additions.items()
                if data.get("timestamp", get_uae_time()) < location_cutoff
            ]
            for uid in expired_locations:
                del pending_location_additions[uid]
                
            if expired_locations:
                logger.info(f"[CLEANUP] Removed {len(expired_locations)} pending locations")
            
            # Clean up old temporary files
            import tempfile
            import time
            import os
            temp_dir = tempfile.gettempdir()
            now = time.time()
            
            cleaned_files = 0
            for filename in os.listdir(temp_dir):
                filepath = os.path.join(temp_dir, filename)
                # Clean files older than 1 hour that match our patterns
                if (filename.endswith(('.pptx', '.pdf', '.bin')) and 
                    os.path.isfile(filepath) and 
                    os.stat(filepath).st_mtime < now - 3600):
                    try:
                        os.unlink(filepath)
                        cleaned_files += 1
                    except:
                        pass
                        
            if cleaned_files > 0:
                logger.info(f"[CLEANUP] Removed {cleaned_files} old temporary files")
                
        except Exception as e:
            logger.error(f"[CLEANUP] Error in periodic cleanup: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown events"""
    # Startup
    cleanup_task = asyncio.create_task(periodic_cleanup())
    logger.info("[STARTUP] Started background cleanup task")

    # Load active workflows from database to restore state after restart
    from workflows import bo_approval
    await bo_approval.load_workflows_from_db()

    yield

    # Shutdown
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        logger.info("[SHUTDOWN] Background cleanup task cancelled")


app = FastAPI(title="Proposal Bot API", lifespan=lifespan)

# Add CORS middleware for unified UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3005", "http://localhost:3000", "http://127.0.0.1:3005"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/slack/events")
async def slack_events(request: Request):
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
            asyncio.create_task(main_llm_loop(channel, user, event.get("text", ""), event))
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
                    asyncio.create_task(main_llm_loop(channel, user, "", synthetic_event))
                else:
                    logger.warning(f"[SLACK_EVENT] Cannot route file_shared event, missing user/channel/file: user={user}, channel={channel}, has_file={bool(file_obj)}")
        except Exception as e:
            logger.error(f"[SLACK_EVENT] Error handling file_shared: {e}", exc_info=True)
    elif event_type == "message" and event_subtype:
        # Log subtypes at debug level to reduce noise
        logger.debug(f"[SLACK_EVENT] Skipping message subtype '{event_subtype}'")

    return JSONResponse({"status": "ok"})


@app.post("/slack/interactive")
async def slack_interactive(request: Request):
    """Handle Slack interactive components (buttons, modals, etc.)"""
    import json
    import time
    from collections import defaultdict
    from workflows import bo_approval as bo_approval_workflow
    from core import bo_messaging
    from integrations.channels import to_slack

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
            from urllib.parse import unquote_plus
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
        _button_clicks = defaultdict(lambda: defaultdict(float))
        DEBOUNCE_WINDOW = 3
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
            # This replaces the buttons with the rejection prompt
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

            # Update workflow to track rejection (thread_ts already set during upload)
            await bo_approval_workflow.update_workflow(workflow_id, {
                "status": "coordinator_rejected",
                "coordinator_rejected_by": user_id,
                "coordinator_rejected_at": get_uae_time().isoformat()
            })

            logger.info(f"[BO APPROVAL] Started edit conversation in thread {thread_ts} for {workflow_id}")

        elif action_id == "cancel_bo_coordinator":
            logger.info(f"[BO APPROVAL] Coordinator {user_id} clicked CANCEL for workflow {workflow_id}, opening modal")
            # Open modal for cancellation reason
            from integrations.channels import Modal, ModalField, FieldType
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
            from integrations.channels import Modal, ModalField, FieldType
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
            from integrations.channels import Modal, ModalField, FieldType
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


@app.get("/health")
async def health():
    import os
    environment = os.getenv("ENVIRONMENT", "development")
    return {
        "status": "healthy",
        "timestamp": get_uae_time().isoformat(),
        "environment": environment,
        "timezone": "UAE (GMT+4)"
    }


@app.get("/metrics")
async def metrics():
    """Performance metrics endpoint for monitoring"""
    import psutil
    import os
    
    process = psutil.Process(os.getpid())
    memory_info = process.memory_info()
    
    # Get CPU count
    cpu_count = psutil.cpu_count()
    
    # Get current PDF conversion semaphore status
    from generators.pdf import _CONVERT_SEMAPHORE
    pdf_conversions_active = _CONVERT_SEMAPHORE._initial_value - _CONVERT_SEMAPHORE._value

    # Get user history size
    from db.cache import user_history, pending_location_additions
    
    return {
        "memory": {
            "rss_mb": round(memory_info.rss / 1024 / 1024, 2),
            "vms_mb": round(memory_info.vms / 1024 / 1024, 2),
        },
        "cpu": {
            "percent": process.cpu_percent(interval=0.1),
            "count": cpu_count,
        },
        "pdf_conversions": {
            "active": pdf_conversions_active,
            "max_concurrent": _CONVERT_SEMAPHORE._initial_value,
        },
        "cache_sizes": {
            "user_histories": len(user_history),
            "pending_locations": len(pending_location_additions),
            "templates_cached": len(config.get_location_mapping()),
        },
        "timestamp": get_uae_time().isoformat()
    }


@app.get("/costs")
async def get_costs(
    start_date: str = None,
    end_date: str = None,
    call_type: str = None,
    workflow: str = None,
    user_id: str = None
):
    """
    Get AI costs summary with optional filters

    Query parameters:
        - start_date: Filter by start date (ISO format)
        - end_date: Filter by end date (ISO format)
        - call_type: Filter by call type (classification, parsing, coordinator_thread, main_llm, etc.)
        - workflow: Filter by workflow (mockup_upload, mockup_ai, bo_parsing, bo_editing, bo_revision, proposal_generation, general_chat, location_management)
        - user_id: Filter by Slack user ID
    """
    summary = db.get_ai_costs_summary(
        start_date=start_date,
        end_date=end_date,
        call_type=call_type,
        workflow=workflow,
        user_id=user_id
    )

    return {
        "summary": summary,
        "filters": {
            "start_date": start_date,
            "end_date": end_date,
            "call_type": call_type,
            "workflow": workflow,
            "user_id": user_id
        },
        "timestamp": get_uae_time().isoformat()
    }


@app.delete("/costs/clear")
async def clear_costs(auth_code: str = None):
    """
    Clear all AI cost tracking data (useful for testing/resetting)
    WARNING: This will delete all cost history!

    Requires authentication code in query parameter:
    DELETE /costs/clear?auth_code=YOUR_CODE
    """
    import os
    from fastapi import HTTPException

    # Check authentication code
    required_code = os.getenv("COSTS_CLEAR_AUTH_CODE", "nour2024")
    if not auth_code or auth_code != required_code:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Invalid or missing authentication code"
        )

    db.clear_ai_costs()
    return {
        "status": "success",
        "message": "All AI cost data cleared",
        "timestamp": get_uae_time().isoformat()
    }


# Mockup Generator Routes
@app.get("/mockup")
async def mockup_setup_page():
    """Serve the mockup setup/generate interface"""
    from pathlib import Path
    html_path = Path(__file__).parent / "templates" / "mockup_setup.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Mockup setup page not found")
    return HTMLResponse(content=html_path.read_text())


@app.get("/api/mockup/locations")
async def get_mockup_locations():
    """Get list of available locations for mockup"""
    locations = []
    for key, meta in config.LOCATION_METADATA.items():
        locations.append({
            "key": key,
            "name": meta.get("display_name", key.title())
        })
    return {"locations": sorted(locations, key=lambda x: x["name"])}


@app.post("/api/mockup/save-frame")
async def save_mockup_frame(
    location_key: str = Form(...),
    time_of_day: str = Form("day"),
    finish: str = Form("gold"),
    frames_data: str = Form(...),
    photo: UploadFile = File(...),
    config_json: Optional[str] = Form(None)
):
    """Save a billboard photo with multiple frame coordinates and optional config"""
    import json
    from db.database import db
    from generators import mockup as mockup_generator

    # Log EXACTLY what was received from the form
    logger.info(f"[MOCKUP API] ====== SAVE FRAME REQUEST ======")
    logger.info(f"[MOCKUP API] RECEIVED location_key: '{location_key}'")
    logger.info(f"[MOCKUP API] RECEIVED time_of_day: '{time_of_day}'")
    logger.info(f"[MOCKUP API] RECEIVED finish: '{finish}'")
    logger.info(f"[MOCKUP API] RECEIVED photo filename: '{photo.filename}'")
    logger.info(f"[MOCKUP API] ====================================")

    try:
        # Parse frames data (list of frames, each frame has points and config)
        frames = json.loads(frames_data)
        if not isinstance(frames, list) or len(frames) == 0:
            raise HTTPException(status_code=400, detail="frames_data must be a non-empty list of frames")

        # Validate each frame has points array with 4 points and optional config
        for i, frame in enumerate(frames):
            if not isinstance(frame, dict):
                raise HTTPException(status_code=400, detail=f"Frame {i} must be an object with 'points' and 'config'")
            if 'points' not in frame:
                raise HTTPException(status_code=400, detail=f"Frame {i} missing 'points' field")
            if not isinstance(frame['points'], list) or len(frame['points']) != 4:
                raise HTTPException(status_code=400, detail=f"Frame {i} must have exactly 4 corner points")

        # Parse config if provided
        config_dict = None
        if config_json:
            try:
                config_dict = json.loads(config_json)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid config JSON")

        # Validate location
        if location_key not in config.LOCATION_METADATA:
            raise HTTPException(status_code=400, detail=f"Invalid location: {location_key}")

        # Read photo data
        logger.info(f"[MOCKUP API] Reading photo data from upload: {photo.filename}")
        photo_data = await photo.read()
        logger.info(f"[MOCKUP API] ✓ Read {len(photo_data)} bytes from upload")

        # Save all frames to database with per-frame configs - this returns the auto-numbered filename
        logger.info(f"[MOCKUP API] Saving {len(frames)} frame(s) to database for {location_key}/{time_of_day}/{finish}")
        final_filename = db.save_mockup_frame(location_key, photo.filename, frames, created_by=None, time_of_day=time_of_day, finish=finish, config=config_dict)
        logger.info(f"[MOCKUP API] ✓ Database save complete, filename: {final_filename}")

        # Save photo to disk with the final auto-numbered filename
        logger.info(f"[MOCKUP API] Saving photo to disk: {final_filename}")
        photo_path = mockup_generator.save_location_photo(location_key, final_filename, photo_data, time_of_day, finish)
        logger.info(f"[MOCKUP API] ✓ Photo saved to disk at: {photo_path}")

        # Verify the file exists immediately after saving
        import os
        if os.path.exists(photo_path):
            file_size = os.path.getsize(photo_path)
            logger.info(f"[MOCKUP API] ✓ VERIFICATION: File exists on disk, size: {file_size} bytes")
        else:
            logger.error(f"[MOCKUP API] ✗ VERIFICATION FAILED: File does not exist at {photo_path}")

        logger.info(f"[MOCKUP API] ✓ Complete: Saved {len(frames)} frame(s) for {location_key}/{time_of_day}/{finish}/{final_filename}")

        return {"success": True, "photo": final_filename, "time_of_day": time_of_day, "finish": finish, "frames_count": len(frames)}

    except json.JSONDecodeError as e:
        logger.error(f"[MOCKUP API] JSON decode error: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail="Invalid frames_data JSON")
    except Exception as e:
        logger.error(f"[MOCKUP API] Error saving frames: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/mockup/test-preview")
async def test_preview_mockup(
    billboard_photo: UploadFile = File(...),
    creative: UploadFile = File(...),
    frame_points: str = Form(...),
    config: str = Form("{}"),
    time_of_day: str = Form("day")
):
    """Generate a test preview of how the creative will look on the billboard with current config"""
    import json
    import tempfile
    from generators import mockup as mockup_generator
    import cv2
    import numpy as np
    from pathlib import Path

    try:
        # Parse frame points (list of 4 [x, y] coordinates)
        points = json.loads(frame_points)
        if not isinstance(points, list) or len(points) != 4:
            raise HTTPException(status_code=400, detail="frame_points must be a list of 4 [x, y] coordinates")

        # Parse config
        config_dict = json.loads(config)

        # Read billboard photo
        billboard_data = await billboard_photo.read()
        billboard_array = np.frombuffer(billboard_data, np.uint8)
        billboard_img = cv2.imdecode(billboard_array, cv2.IMREAD_COLOR)

        if billboard_img is None:
            raise HTTPException(status_code=400, detail="Invalid billboard photo")

        # Read creative
        creative_data = await creative.read()
        creative_array = np.frombuffer(creative_data, np.uint8)
        creative_img = cv2.imdecode(creative_array, cv2.IMREAD_COLOR)

        if creative_img is None:
            raise HTTPException(status_code=400, detail="Invalid creative image")

        # Apply the warp using the same function as real mockup generation
        result = mockup_generator.warp_creative_to_billboard(
            billboard_img,
            creative_img,
            points,
            config=config_dict,
            time_of_day=time_of_day
        )

        # Encode result as JPEG
        success, buffer = cv2.imencode('.jpg', result, [cv2.IMWRITE_JPEG_QUALITY, 85])

        # CRITICAL: Explicitly delete large numpy arrays to free memory immediately
        # Preview endpoint is called repeatedly during setup, causing memory buildup
        del billboard_data, billboard_array, billboard_img
        del creative_data, creative_array, creative_img
        del result
        from utils.memory import cleanup_memory
        cleanup_memory(context="mockup_preview", aggressive=False, log_stats=False)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to encode preview image")

        # Return as image response
        from fastapi.responses import Response
        return Response(content=buffer.tobytes(), media_type="image/jpeg")

    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")
    except Exception as e:
        logger.error(f"[TEST PREVIEW] Error generating preview: {e}", exc_info=True)
        # Cleanup on error path too
        try:
            del billboard_data, billboard_array, billboard_img
            del creative_data, creative_array, creative_img
            del result
            from utils.memory import cleanup_memory
            cleanup_memory(context="mockup_preview_error", aggressive=False, log_stats=False)
        except:
            pass
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/mockup/photos/{location_key}")
async def list_mockup_photos(location_key: str, time_of_day: str = "all", finish: str = "all"):
    """List all photos for a location with specific time_of_day and finish"""
    from db.database import db

    try:
        # If "all" is specified, we need to aggregate from all variations
        if time_of_day == "all" or finish == "all":
            variations = db.list_mockup_variations(location_key)
            all_photos = set()
            for tod in variations:
                for fin in variations[tod]:
                    photos = db.list_mockup_photos(location_key, tod, fin)
                    all_photos.update(photos)
            return {"photos": sorted(list(all_photos))}
        else:
            photos = db.list_mockup_photos(location_key, time_of_day, finish)
            return {"photos": photos}
    except Exception as e:
        logger.error(f"[MOCKUP API] Error listing photos: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/mockup/templates/{location_key}")
async def list_mockup_templates(location_key: str, time_of_day: str = "all", finish: str = "all"):
    """List all templates (photos with frame configs) for a location"""
    from db.database import db

    try:
        templates = []

        # If "all" is specified, aggregate from all variations
        if time_of_day == "all" or finish == "all":
            variations = db.list_mockup_variations(location_key)
            for tod in variations:
                for fin in variations[tod]:
                    photos = db.list_mockup_photos(location_key, tod, fin)
                    for photo in photos:
                        # Get frame count and config
                        frames_data = db.get_mockup_frames(location_key, photo, tod, fin)
                        if frames_data:
                            # Get first frame's config (all frames typically share same config in UI)
                            frame_config = frames_data[0].get("config", {}) if frames_data else {}
                            templates.append({
                                "photo": photo,
                                "time_of_day": tod,
                                "finish": fin,
                                "frame_count": len(frames_data),
                                "config": frame_config
                            })
        else:
            photos = db.list_mockup_photos(location_key, time_of_day, finish)
            for photo in photos:
                # Get frame count and config
                frames_data = db.get_mockup_frames(location_key, photo, time_of_day, finish)
                if frames_data:
                    frame_config = frames_data[0].get("config", {}) if frames_data else {}
                    templates.append({
                        "photo": photo,
                        "time_of_day": time_of_day,
                        "finish": finish,
                        "frame_count": len(frames_data),
                        "config": frame_config
                    })

        return {"templates": templates}
    except Exception as e:
        logger.error(f"[MOCKUP API] Error listing templates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/mockup/photo/{location_key}/{photo_filename}")
async def get_mockup_photo(location_key: str, photo_filename: str, time_of_day: str = "all", finish: str = "all"):
    """Get a specific photo file"""
    from generators import mockup as mockup_generator
    from db.database import db
    import os

    logger.info(f"[PHOTO GET] Request for photo: {location_key}/{photo_filename} (time_of_day={time_of_day}, finish={finish})")

    # If "all" is specified, find the photo in any variation
    if time_of_day == "all" or finish == "all":
        logger.info(f"[PHOTO GET] Searching across variations (all mode)")
        variations = db.list_mockup_variations(location_key)
        logger.info(f"[PHOTO GET] Available variations: {variations}")

        all_checked_paths = []
        for tod in variations:
            for fin in variations[tod]:
                photo_path = mockup_generator.get_location_photos_dir(location_key, tod, fin) / photo_filename
                all_checked_paths.append(str(photo_path))
                logger.info(f"[PHOTO GET] Checking: {photo_path}")

                if photo_path.exists():
                    file_size = os.path.getsize(photo_path)
                    logger.info(f"[PHOTO GET] ✓ FOUND: {photo_path} ({file_size} bytes)")
                    return FileResponse(photo_path)
                else:
                    logger.info(f"[PHOTO GET] ✗ NOT FOUND: {photo_path}")

        logger.error(f"[PHOTO GET] ✗ Photo not found in any variation. Checked paths: {all_checked_paths}")

        # Check if directory exists at all
        mockups_base = mockup_generator.MOCKUPS_DIR / location_key
        if mockups_base.exists():
            logger.info(f"[PHOTO GET] Base directory exists: {mockups_base}")
            logger.info(f"[PHOTO GET] Contents: {list(os.walk(mockups_base))}")
        else:
            logger.error(f"[PHOTO GET] Base directory doesn't exist: {mockups_base}")

        raise HTTPException(status_code=404, detail=f"Photo not found: {photo_filename}")
    else:
        photo_path = mockup_generator.get_location_photos_dir(location_key, time_of_day, finish) / photo_filename
        logger.info(f"[PHOTO GET] Direct path request: {photo_path}")

        if not photo_path.exists():
            logger.error(f"[PHOTO GET] ✗ Photo not found: {photo_path}")

            # Check parent directories
            parent_dir = photo_path.parent
            if parent_dir.exists():
                logger.info(f"[PHOTO GET] Parent directory exists: {parent_dir}")
                logger.info(f"[PHOTO GET] Contents: {list(parent_dir.iterdir())}")
            else:
                logger.error(f"[PHOTO GET] Parent directory doesn't exist: {parent_dir}")

            raise HTTPException(status_code=404, detail=f"Photo not found: {photo_filename}")

        file_size = os.path.getsize(photo_path)
        logger.info(f"[PHOTO GET] ✓ Found photo: {photo_path} ({file_size} bytes)")
        return FileResponse(photo_path)


@app.delete("/api/mockup/photo/{location_key}/{photo_filename}")
async def delete_mockup_photo(location_key: str, photo_filename: str, time_of_day: str = "all", finish: str = "all"):
    """Delete a photo and its frame"""
    from generators import mockup as mockup_generator
    from db.database import db

    try:
        # If "all" is specified, find and delete the photo from whichever variation it's in
        if time_of_day == "all" or finish == "all":
            variations = db.list_mockup_variations(location_key)
            for tod in variations:
                for fin in variations[tod]:
                    photos = db.list_mockup_photos(location_key, tod, fin)
                    if photo_filename in photos:
                        success = mockup_generator.delete_location_photo(location_key, photo_filename, tod, fin)
                        if success:
                            return {"success": True}
                        else:
                            raise HTTPException(status_code=500, detail="Failed to delete photo")
            raise HTTPException(status_code=404, detail="Photo not found")
        else:
            success = mockup_generator.delete_location_photo(location_key, photo_filename, time_of_day, finish)
            if success:
                return {"success": True}
            else:
                raise HTTPException(status_code=500, detail="Failed to delete photo")
    except Exception as e:
        logger.error(f"[MOCKUP API] Error deleting photo: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/mockup/generate")
async def generate_mockup_api(
    request: Request,
    location_key: str = Form(...),
    time_of_day: str = Form("all"),
    finish: str = Form("all"),
    ai_prompt: Optional[str] = Form(None),
    creative: Optional[UploadFile] = File(None),
    specific_photo: Optional[str] = Form(None),
    frame_config: Optional[str] = Form(None)
):
    """Generate a mockup by warping creative onto billboard (upload or AI-generated)"""
    import tempfile
    from generators import mockup as mockup_generator
    from pathlib import Path
    import json

    creative_path = None
    photo_used = None
    creative_type = None
    template_selected = specific_photo is not None

    # Get client IP for analytics
    client_ip = request.client.host if request.client else None

    try:
        # Parse frame config if provided
        config_dict = None
        if frame_config:
            try:
                config_dict = json.loads(frame_config)
                logger.info(f"[MOCKUP API] Using custom frame config: {config_dict}")
            except json.JSONDecodeError:
                logger.warning(f"[MOCKUP API] Invalid frame config JSON, ignoring")

        # Validate location
        if location_key not in config.LOCATION_METADATA:
            raise HTTPException(status_code=400, detail=f"Invalid location: {location_key}")

        # Determine mode: AI generation or upload
        if ai_prompt:
            # AI MODE: Generate creative using AI
            creative_type = "ai_generated"
            logger.info(f"[MOCKUP API] Generating AI creative with prompt: {ai_prompt[:100]}...")

            
            creative_path = await mockup_generator.generate_ai_creative(
                prompt=ai_prompt,
                size="1536x1024"  # Landscape format for billboards
            )

            if not creative_path:
                raise HTTPException(status_code=500, detail="Failed to generate AI creative")

        elif creative:
            # UPLOAD MODE: Use uploaded creative
            creative_type = "uploaded"
            logger.info(f"[MOCKUP API] Using uploaded creative: {creative.filename}")

            creative_data = await creative.read()
            creative_temp = tempfile.NamedTemporaryFile(delete=False, suffix=Path(creative.filename).suffix)
            creative_temp.write(creative_data)
            creative_temp.close()
            creative_path = Path(creative_temp.name)

        else:
            raise HTTPException(status_code=400, detail="Either ai_prompt or creative file must be provided")

        # Generate mockup (pass as list) with time_of_day, finish, specific_photo, and config override
        result_path, photo_used = mockup_generator.generate_mockup(
            location_key,
            [creative_path],
            time_of_day=time_of_day,
            finish=finish,
            specific_photo=specific_photo,
            config_override=config_dict
        )

        if not result_path or not photo_used:
            # Log failed attempt
            db.log_mockup_usage(
                location_key=location_key,
                time_of_day=time_of_day,
                finish=finish,
                photo_used=specific_photo or "random",
                creative_type=creative_type or "unknown",
                ai_prompt=ai_prompt if ai_prompt else None,
                template_selected=template_selected,
                success=False,
                user_ip=client_ip
            )
            raise HTTPException(status_code=500, detail="Failed to generate mockup")

        # Log successful generation
        db.log_mockup_usage(
            location_key=location_key,
            time_of_day=time_of_day,
            finish=finish,
            photo_used=photo_used,
            creative_type=creative_type,
            ai_prompt=ai_prompt if ai_prompt else None,
            template_selected=template_selected,
            success=True,
            user_ip=client_ip
        )

        # Return the image with background_tasks to delete after serving
        from fastapi import BackgroundTasks

        def cleanup_files():
            """Delete temp files after response is sent"""
            try:
                if creative_path and creative_path.exists():
                    creative_path.unlink()
                    logger.debug(f"[CLEANUP] Deleted temp creative: {creative_path}")
            except Exception as e:
                logger.debug(f"[CLEANUP] Error deleting creative: {e}")

            try:
                if result_path and result_path.exists():
                    result_path.unlink()
                    logger.debug(f"[CLEANUP] Deleted temp mockup: {result_path}")
            except Exception as e:
                logger.debug(f"[CLEANUP] Error deleting mockup: {e}")

        # Schedule cleanup after response is sent
        background_tasks = BackgroundTasks()
        background_tasks.add_task(cleanup_files)

        return FileResponse(
            result_path,
            media_type="image/jpeg",
            filename=f"mockup_{location_key}_{time_of_day}_{finish}.jpg",
            background=background_tasks
        )

    except HTTPException as http_exc:
        # Cleanup temp files on HTTP exceptions (validation errors, etc.)
        try:
            if 'creative_path' in locals() and creative_path and creative_path.exists():
                creative_path.unlink()
                logger.debug(f"[CLEANUP] Deleted temp creative after error: {creative_path}")
        except Exception as cleanup_error:
            logger.debug(f"[CLEANUP] Error deleting creative after error: {cleanup_error}")

        try:
            if 'result_path' in locals() and result_path and result_path.exists():
                result_path.unlink()
                logger.debug(f"[CLEANUP] Deleted temp mockup after error: {result_path}")
        except Exception as cleanup_error:
            logger.debug(f"[CLEANUP] Error deleting mockup after error: {cleanup_error}")

        raise http_exc

    except Exception as e:
        logger.error(f"[MOCKUP API] Error generating mockup: {e}", exc_info=True)

        # Cleanup temp files on unexpected errors
        try:
            if 'creative_path' in locals() and creative_path and creative_path.exists():
                creative_path.unlink()
                logger.debug(f"[CLEANUP] Deleted temp creative after error: {creative_path}")
        except Exception as cleanup_error:
            logger.debug(f"[CLEANUP] Error deleting creative after error: {cleanup_error}")

        try:
            if 'result_path' in locals() and result_path and result_path.exists():
                result_path.unlink()
                logger.debug(f"[CLEANUP] Deleted temp mockup after error: {result_path}")
        except Exception as cleanup_error:
            logger.debug(f"[CLEANUP] Error deleting mockup after error: {cleanup_error}")

        # Log failed attempt
        try:
            db.log_mockup_usage(
                location_key=location_key,
                time_of_day=time_of_day,
                finish=finish,
                photo_used=specific_photo or "random",
                creative_type=creative_type or "unknown",
                ai_prompt=ai_prompt if ai_prompt else None,
                template_selected=template_selected,
                success=False,
                user_ip=client_ip
            )
        except Exception as log_error:
            logger.error(f"[MOCKUP API] Error logging usage: {log_error}")

        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# UNIFIED UI CHAT ENDPOINTS
# ============================================

class ChatMessageRequest(BaseModel):
    """Request model for chat messages."""
    message: str
    conversation_id: Optional[str] = None
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    roles: Optional[List[str]] = None


class ChatMessageResponse(BaseModel):
    """Response model for chat messages."""
    content: Optional[str] = None
    tool_call: Optional[dict] = None
    files: Optional[List[dict]] = None
    error: Optional[str] = None
    conversation_id: Optional[str] = None


@app.post("/api/chat/message", response_model=ChatMessageResponse)
async def chat_message(request: ChatMessageRequest):
    """
    Send a chat message and receive a response.

    This endpoint connects the Unified UI to the same LLM infrastructure
    used by the Slack bot.
    """
    from core.chat_api import process_chat_message

    try:
        # Use provided user info or defaults for local dev
        user_id = request.user_id or "web-user-default"
        user_name = request.user_name or "Web User"
        roles = request.roles or ["sales_person"]

        result = await process_chat_message(
            user_id=user_id,
            user_name=user_name,
            message=request.message,
            roles=roles
        )

        return ChatMessageResponse(
            content=result.get("content"),
            tool_call=result.get("tool_call"),
            files=result.get("files"),
            error=result.get("error"),
            conversation_id=request.conversation_id
        )

    except Exception as e:
        logger.error(f"[CHAT API] Error processing message: {e}", exc_info=True)
        return ChatMessageResponse(
            error=str(e),
            conversation_id=request.conversation_id
        )


@app.post("/api/chat/stream")
async def chat_stream(request: ChatMessageRequest):
    """
    Stream a chat response using Server-Sent Events.

    Returns real-time chunks as the LLM generates the response.
    """
    from core.chat_api import stream_chat_message

    user_id = request.user_id or "web-user-default"
    user_name = request.user_name or "Web User"
    roles = request.roles or ["sales_person"]

    async def event_generator():
        async for chunk in stream_chat_message(
            user_id=user_id,
            user_name=user_name,
            message=request.message,
            roles=roles
        ):
            yield chunk

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.get("/api/chat/conversations")
async def get_conversations(user_id: Optional[str] = None):
    """Get conversation history for a user."""
    from core.chat_api import get_conversation_history

    user_id = user_id or "web-user-default"
    history = get_conversation_history(user_id)

    return {"conversations": [{"id": user_id, "messages": history}]}


@app.post("/api/chat/conversation")
async def create_conversation(user_id: Optional[str] = None, user_name: Optional[str] = None):
    """Create a new conversation (clears existing history)."""
    from core.chat_api import clear_conversation, get_web_adapter
    import uuid

    user_id = user_id or "web-user-default"
    user_name = user_name or "Web User"

    # Clear existing conversation
    clear_conversation(user_id)

    # Create new session
    web_adapter = get_web_adapter()
    session = web_adapter.create_session(user_id, user_name)

    return {
        "conversation_id": session.conversation_id,
        "user_id": user_id
    }


@app.delete("/api/chat/conversation/{conversation_id}")
async def delete_conversation(conversation_id: str, user_id: Optional[str] = None):
    """Delete a conversation."""
    from core.chat_api import clear_conversation

    user_id = user_id or "web-user-default"
    clear_conversation(user_id)

    return {"success": True, "conversation_id": conversation_id}


# ============================================
# UNIFIED UI AUTH ENDPOINTS (Local Dev)
# ============================================

class LoginRequest(BaseModel):
    """Login request model."""
    email: str
    password: str


# Dev users for local testing (mirrors auth.js)
DEV_USERS = {
    'admin@mmg.com': {
        'password': 'admin123',
        'id': 'dev-admin-1',
        'name': 'Sales Admin',
        'email': 'admin@mmg.com',
        'roles': ['admin', 'hos', 'sales_person']
    },
    'hos@mmg.com': {
        'password': 'hos123',
        'id': 'dev-hos-1',
        'name': 'Head of Sales',
        'email': 'hos@mmg.com',
        'roles': ['hos', 'sales_person']
    },
    'sales@mmg.com': {
        'password': 'sales123',
        'id': 'dev-sales-1',
        'name': 'Sales Person',
        'email': 'sales@mmg.com',
        'roles': ['sales_person']
    }
}


@app.post("/api/auth/login")
async def auth_login(request: LoginRequest):
    """
    Authenticate a user (local dev mode).

    In production, this would validate against Supabase.
    """
    email = request.email.lower()
    user = DEV_USERS.get(email)

    if not user or user['password'] != request.password:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Generate a simple token for local dev
    import hashlib
    import time
    token = hashlib.sha256(f"{email}-{time.time()}".encode()).hexdigest()[:32]

    return {
        "token": f"dev-{token}",
        "user": {
            "id": user['id'],
            "name": user['name'],
            "email": user['email'],
            "roles": user['roles']
        }
    }


@app.post("/api/auth/logout")
async def auth_logout():
    """Logout endpoint (no-op for local dev)."""
    return {"success": True}


@app.get("/api/auth/me")
async def auth_me(request: Request):
    """Get current user info from token."""
    auth_header = request.headers.get("Authorization", "")

    if not auth_header.startswith("Bearer dev-"):
        raise HTTPException(status_code=401, detail="Not authenticated")

    # For local dev, just return a default user
    # In production, validate the token
    return {
        "id": "dev-admin-1",
        "name": "Sales Admin",
        "email": "admin@mmg.com",
        "roles": ["admin", "hos", "sales_person"]
    }


# ============================================
# UNIFIED UI PROPOSALS ENDPOINTS
# ============================================

@app.get("/api/proposals/history")
async def get_proposals_history(user_id: Optional[str] = None):
    """Get proposal generation history."""
    try:
        # Get recent proposals from database
        proposals = db.get_recent_proposals(limit=20, user_id=user_id)
        return proposals
    except Exception as e:
        logger.error(f"[PROPOSALS API] Error getting history: {e}")
        return []


# ============================================
# STATIC FILE SERVING FOR UNIFIED UI
# ============================================

@app.get("/api/files/{file_id}/{filename}")
async def serve_uploaded_file(file_id: str, filename: str):
    """Serve files uploaded through the chat interface."""
    from core.chat_api import get_web_adapter

    web_adapter = get_web_adapter()
    file_path = web_adapter.get_file_path(file_id)

    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(file_path, filename=filename)