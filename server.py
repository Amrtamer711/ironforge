import asyncio
from datetime import datetime
import subprocess
import shutil
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

import config
import db
from llm import main_llm_loop, _generate_mockup_queued
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
            from llm import user_history, pending_location_additions
            from datetime import timedelta
            
            # Clean user histories older than 1 hour
            cutoff = datetime.now() - timedelta(hours=1)
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
            location_cutoff = datetime.now() - timedelta(minutes=10)
            expired_locations = [
                uid for uid, data in pending_location_additions.items()
                if data.get("timestamp", datetime.now()) < location_cutoff
            ]
            for uid in expired_locations:
                del pending_location_additions[uid]
                
            if expired_locations:
                logger.info(f"[CLEANUP] Removed {len(expired_locations)} pending locations")

            # Clean mockup history (30-minute expiry for creative files)
            from llm import cleanup_expired_mockups
            cleanup_expired_mockups()

            # Clean up old temporary files
            import tempfile
            import time
            import os
            temp_dir = tempfile.gettempdir()
            now = time.time()
            
            cleaned_files = 0
            for filename in os.listdir(temp_dir):
                filepath = os.path.join(temp_dir, filename)
                # Clean files older than 1 hour that match our patterns (including images for mockups)
                if (filename.endswith(('.pptx', '.pdf', '.bin', '.jpg', '.jpeg', '.png', '.gif')) and 
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
    
    yield
    
    # Shutdown
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        logger.info("[SHUTDOWN] Background cleanup task cancelled")


app = FastAPI(title="Proposal Bot API", lifespan=lifespan)


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
                info = await config.slack_client.files_info(file=file_id)
                file_obj = info.get("file", {}) if isinstance(info, dict) else getattr(info, "data", {}).get("file", {})
                # Fallback channel from file channels list if missing
                if not channel:
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


@app.get("/health")
async def health():
    import os
    environment = os.getenv("ENVIRONMENT", "development")
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "environment": environment
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
    from pdf_utils import _CONVERT_SEMAPHORE
    pdf_conversions_active = _CONVERT_SEMAPHORE._initial_value - _CONVERT_SEMAPHORE._value
    
    # Get user history size
    from llm import user_history, pending_location_additions

    # Get mockup queue status
    from task_queue import mockup_queue
    queue_status = mockup_queue.get_queue_status()

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
        "mockup_queue": queue_status,
        "cache_sizes": {
            "user_histories": len(user_history),
            "pending_locations": len(pending_location_additions),
            "templates_cached": len(config.get_location_mapping()),
        },
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/queue/status")
async def queue_status():
    """Get current mockup generation queue status"""
    from task_queue import mockup_queue

    status = mockup_queue.get_queue_status()

    return {
        "queue": status,
        "timestamp": datetime.now().isoformat()
    }


@app.post("/api/queue/update-limit")
async def update_queue_limit(max_concurrent: int):
    """Update the maximum concurrent mockup generation tasks (admin only)"""
    from task_queue import mockup_queue

    if max_concurrent < 1 or max_concurrent > 10:
        raise HTTPException(status_code=400, detail="max_concurrent must be between 1 and 10")

    await mockup_queue.update_max_concurrent(max_concurrent)

    return {
        "success": True,
        "new_max_concurrent": max_concurrent,
        "timestamp": datetime.now().isoformat()
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
    import db
    import mockup_generator

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

        # Immediately delete photo_data to free memory
        del photo_data

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
    import mockup_generator
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
        del billboard_data  # Free memory immediately

        if billboard_img is None:
            raise HTTPException(status_code=400, detail="Invalid billboard photo")

        # Read creative
        creative_data = await creative.read()
        creative_array = np.frombuffer(creative_data, np.uint8)
        creative_img = cv2.imdecode(creative_array, cv2.IMREAD_COLOR)
        del creative_data  # Free memory immediately

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
        # Use individual dels to ensure all cleanup even if one fails
        try: del billboard_data
        except: pass
        try: del billboard_array
        except: pass
        try: del billboard_img
        except: pass
        try: del creative_data
        except: pass
        try: del creative_array
        except: pass
        try: del creative_img
        except: pass
        try: del result
        except: pass
        import gc
        gc.collect()

        if not success:
            raise HTTPException(status_code=500, detail="Failed to encode preview image")

        # Return as image response
        from fastapi.responses import Response
        return Response(content=buffer.tobytes(), media_type="image/jpeg")

    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")
    except Exception as e:
        logger.error(f"[TEST PREVIEW] Error generating preview: {e}", exc_info=True)
        # Cleanup on error path too - individual dels to ensure all cleanup
        try: del billboard_data
        except: pass
        try: del billboard_array
        except: pass
        try: del billboard_img
        except: pass
        try: del creative_data
        except: pass
        try: del creative_array
        except: pass
        try: del creative_img
        except: pass
        try: del result
        except: pass
        import gc
        gc.collect()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/mockup/photos/{location_key}")
async def list_mockup_photos(location_key: str, time_of_day: str = "all", finish: str = "all"):
    """List all photos for a location with specific time_of_day and finish"""
    import db

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
    import db

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
    import mockup_generator
    import db
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
    import mockup_generator
    import db

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
    import mockup_generator
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

            # Extensive system prompt for billboard artwork generation
            enhanced_prompt = f"""Create a professional outdoor advertising billboard creative - IMPORTANT: This is the FLAT 2D ARTWORK FILE that will be printed and placed ON a billboard, NOT a photograph of an existing billboard.

═══════════════════════════════════════════════════════════
CRITICAL DISTINCTIONS:
═══════════════════════════════════════════════════════════

✅ CORRECT OUTPUT (what we want):
- A flat, rectangular advertisement design (like a Photoshop/Illustrator file)
- The actual graphic design artwork that goes ON the billboard surface
- Think: magazine ad, poster design, digital banner creative
- Perfectly rectangular, no perspective, no angle, no depth
- Edge-to-edge design filling the entire rectangular canvas
- Like looking at a computer screen showing the ad design

❌ INCORRECT OUTPUT (what we DON'T want):
- A photograph of a physical billboard in a street scene
- 3D rendering showing billboard from an angle/perspective
- Image with billboard frame, poles, or support structure visible
- Photo showing buildings, sky, roads, or environment around billboard
- Any mockup showing how the billboard looks in real life
- Perspective view, vanishing points, or dimensional representation

═══════════════════════════════════════════════════════════
DETAILED DESIGN REQUIREMENTS:
═══════════════════════════════════════════════════════════

📐 FORMAT & DIMENSIONS:
- Aspect ratio: Wide landscape (roughly 3:2 ratio)
- Orientation: Horizontal/landscape ONLY
- Canvas: Perfectly flat, rectangular, no warping or perspective
- Fill entire frame edge-to-edge with design
- No white borders, frames, or margins around the design

🎨 VISUAL DESIGN PRINCIPLES:
- Bold, high-impact composition that catches attention immediately
- Large hero image or visual focal point (50-70% of design)
- Vibrant, saturated colors that pop in daylight
- High contrast between elements for maximum visibility
- Simple, uncluttered layout (viewer has 5-7 seconds max)
- Professional photo quality or clean vector graphics
- Modern, contemporary advertising aesthetic

✍️ TYPOGRAPHY (if text is needed):
- LARGE, bold, highly readable fonts
- Sans-serif typefaces work best for outdoor viewing
- Maximum 7-10 words total (fewer is better)
- High contrast text-to-background ratio
- Text size: headlines should occupy 15-25% of vertical height
- Clear hierarchy: one main message, optional supporting text
- Avoid script fonts, thin fonts, or decorative typefaces
- Letter spacing optimized for distance reading

🎯 COMPOSITION STRATEGY:
- Rule of thirds or strong visual hierarchy
- One clear focal point (don't scatter attention)
- Negative space used strategically
- Visual flow guides eye to key message/CTA
- Brand logo prominent but not dominating (10-15% of space)
- Clean, professional layout with breathing room

💡 COLOR THEORY FOR OUTDOOR:
- Vibrant, saturated colors (avoid pastels or muted tones)
- High contrast pairings: dark on light or light on dark
- Colors that work in bright sunlight and shadows
- Consistent brand color palette if applicable
- Background should enhance, not compete with message
- Consider: bright blues, bold reds, energetic oranges, fresh greens

🔍 QUALITY STANDARDS:
- Sharp, crisp graphics (no blur, pixelation, or artifacts)
- Professional commercial photography or illustration
- Consistent lighting across all design elements
- No watermarks, stock photo markers, or placeholder text
- Print-ready quality at large scale
- Polished, agency-level execution

═══════════════════════════════════════════════════════════
CREATIVE BRIEF:
═══════════════════════════════════════════════════════════

{ai_prompt}

═══════════════════════════════════════════════════════════
FINAL REMINDER:
═══════════════════════════════════════════════════════════

You are creating the ARTWORK FILE - the actual advertisement design.
Imagine you're a graphic designer creating this in Adobe Illustrator or Photoshop.
The output should be the flat design that will be PLACED onto a billboard structure later.
DO NOT show the billboard itself, the street, or any environmental context.
Just deliver the pure, flat, rectangular advertisement graphic.

Example analogy: If asked to create a "movie poster," you'd create the poster ARTWORK, not a photo of someone holding a poster in a cinema."""

            creative_path = await mockup_generator.generate_ai_creative(
                prompt=enhanced_prompt,
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
            del creative_data  # Free memory immediately

        else:
            raise HTTPException(status_code=400, detail="Either ai_prompt or creative file must be provided")

        # Generate mockup (pass as list) with time_of_day, finish, specific_photo, and config override (queued)
        result_path, photo_used = await _generate_mockup_queued(
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
            """Delete temp files after response is sent and force garbage collection"""
            import gc

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

            # Force garbage collection to free memory from numpy arrays
            gc.collect()
            logger.debug(f"[CLEANUP] Forced garbage collection")

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
        import gc

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

        # Force garbage collection
        gc.collect()

        raise http_exc

    except Exception as e:
        logger.error(f"[MOCKUP API] Error generating mockup: {e}", exc_info=True)
        import gc

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

        # Force garbage collection
        gc.collect()

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