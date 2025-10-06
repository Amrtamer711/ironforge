import asyncio
from datetime import datetime
import subprocess
import shutil
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

import config
from llm import main_llm_loop
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
    subfolder: str = Form("all"),
    frames_data: str = Form(...),
    photo: UploadFile = File(...)
):
    """Save a billboard photo with multiple frame coordinates"""
    import json
    import db
    import mockup_generator

    try:
        # Parse frames data (list of frames, each frame is list of 4 points)
        frames = json.loads(frames_data)
        if not isinstance(frames, list) or len(frames) == 0:
            raise HTTPException(status_code=400, detail="frames_data must be a non-empty list of frames")

        # Validate each frame has 4 points
        for i, frame in enumerate(frames):
            if not isinstance(frame, list) or len(frame) != 4:
                raise HTTPException(status_code=400, detail=f"Frame {i} must have exactly 4 corner points")

        # Validate location
        if location_key not in config.LOCATION_METADATA:
            raise HTTPException(status_code=400, detail=f"Invalid location: {location_key}")

        # Read photo data
        photo_data = await photo.read()

        # Save photo to disk in subfolder
        photo_path = mockup_generator.save_location_photo(location_key, photo.filename, photo_data, subfolder)

        # Save all frames to database
        db.save_mockup_frame(location_key, photo.filename, frames, subfolder=subfolder)

        logger.info(f"[MOCKUP API] Saved {len(frames)} frame(s) for {location_key}/{subfolder}/{photo.filename}")

        return {"success": True, "photo": photo.filename, "subfolder": subfolder, "frames_count": len(frames)}

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid frames_data JSON")
    except Exception as e:
        logger.error(f"[MOCKUP API] Error saving frames: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/mockup/photos/{location_key}")
async def list_mockup_photos(location_key: str):
    """List all photos for a location"""
    import db

    try:
        photos = db.list_mockup_photos(location_key)
        return {"photos": photos}
    except Exception as e:
        logger.error(f"[MOCKUP API] Error listing photos: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/mockup/photo/{location_key}/{photo_filename}")
async def get_mockup_photo(location_key: str, photo_filename: str):
    """Get a specific photo file"""
    import mockup_generator

    photo_path = mockup_generator.get_location_photos_dir(location_key) / photo_filename
    if not photo_path.exists():
        raise HTTPException(status_code=404, detail="Photo not found")

    return FileResponse(photo_path)


@app.delete("/api/mockup/photo/{location_key}/{photo_filename}")
async def delete_mockup_photo(location_key: str, photo_filename: str):
    """Delete a photo and its frame"""
    import mockup_generator

    try:
        success = mockup_generator.delete_location_photo(location_key, photo_filename)
        if success:
            return {"success": True}
        else:
            raise HTTPException(status_code=500, detail="Failed to delete photo")
    except Exception as e:
        logger.error(f"[MOCKUP API] Error deleting photo: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/mockup/generate")
async def generate_mockup_api(
    location_key: str = Form(...),
    subfolder: str = Form("all"),
    creative: UploadFile = File(...)
):
    """Generate a mockup by warping creative onto billboard"""
    import tempfile
    import mockup_generator
    from pathlib import Path

    try:
        # Validate location
        if location_key not in config.LOCATION_METADATA:
            raise HTTPException(status_code=400, detail=f"Invalid location: {location_key}")

        # Save creative to temp file
        creative_data = await creative.read()
        creative_temp = tempfile.NamedTemporaryFile(delete=False, suffix=Path(creative.filename).suffix)
        creative_temp.write(creative_data)
        creative_temp.close()
        creative_path = Path(creative_temp.name)

        # Generate mockup (pass as list) with subfolder
        result_path = mockup_generator.generate_mockup(location_key, [creative_path], subfolder=subfolder)

        if not result_path:
            raise HTTPException(status_code=500, detail="Failed to generate mockup")

        # Return the image
        return FileResponse(
            result_path,
            media_type="image/jpeg",
            filename=f"mockup_{location_key}_{subfolder}.jpg"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[MOCKUP API] Error generating mockup: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Cleanup temp creative file
        try:
            if creative_path and creative_path.exists():
                creative_path.unlink()
        except:
            pass 