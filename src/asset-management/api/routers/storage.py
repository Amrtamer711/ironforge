"""
Storage API Router - Templates and Mockup Files.

Provides access to templates and mockup files stored in Supabase Storage.
"""

import asyncio
import base64
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

import config
from db.database import db

logger = logging.getLogger("asset-management")

router = APIRouter(
    prefix="/api/storage",
    tags=["storage"],
)


class FileResponse(BaseModel):
    """Response containing base64-encoded file data."""
    data: str
    content_type: str
    filename: str


class TemplateInfo(BaseModel):
    """Template info response."""
    location_key: str
    storage_key: str
    filename: str


class UrlResponse(BaseModel):
    """Response containing a signed URL."""
    url: str
    expires_in: int


class ExistsResponse(BaseModel):
    """Response for existence check."""
    exists: bool


def _get_storage_client():
    """Get Supabase storage client."""
    try:
        from supabase import create_client
        from supabase.lib.client_options import ClientOptions

        # Use longer timeouts (seconds) to handle slow network conditions
        options = ClientOptions(
            postgrest_client_timeout=30,
            storage_client_timeout=60,  # Storage operations can be slower
        )
        supabase = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY, options=options)
        return supabase.storage
    except Exception as e:
        logger.error(f"[STORAGE] Failed to create storage client: {e}")
        raise HTTPException(status_code=500, detail="Storage service unavailable")


# =============================================================================
# TEMPLATES
# =============================================================================


@router.get("/templates/{company}", response_model=list[TemplateInfo])
async def list_templates(company: str) -> list[dict[str, Any]]:
    """
    List all templates for a company.

    Templates are stored in: templates/{company}/{location_key}/{location_key}.pptx

    Args:
        company: Company schema (e.g., "backlite_dubai")

    Returns:
        List of template info dicts
    """
    logger.info(f"[STORAGE] Listing templates for {company}")

    try:
        storage = _get_storage_client()
        bucket = storage.from_("templates")

        # List all location folders under the company folder
        response = bucket.list(company)
        templates = []

        for item in response:
            if item.get("name") and not item["name"].startswith("."):
                location_key = item["name"]

                # List files in this location folder
                folder_contents = bucket.list(f"{company}/{location_key}")
                for file_item in folder_contents:
                    filename = file_item.get("name", "")
                    if filename.endswith((".pptx", ".ppt")):
                        templates.append({
                            "location_key": location_key,
                            "storage_key": f"{company}/{location_key}/{filename}",
                            "filename": filename,
                        })

        logger.info(f"[STORAGE] Found {len(templates)} templates for {company}")
        return templates

    except Exception as e:
        logger.error(f"[STORAGE] Failed to list templates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates/{company}/{location_key}", response_model=FileResponse)
async def get_template(company: str, location_key: str) -> dict[str, Any]:
    """
    Download template file as base64.

    Args:
        company: Company schema
        location_key: Location identifier

    Returns:
        Base64-encoded file data
    """
    logger.info(f"[STORAGE] Getting template for {company}/{location_key}")

    try:
        storage = _get_storage_client()
        bucket = storage.from_("templates")

        # Look for template file: {company}/{location_key}/{location_key}.pptx
        storage_key = f"{company}/{location_key}/{location_key}.pptx"

        # Run blocking Supabase download in thread pool for concurrent execution
        data = await asyncio.to_thread(bucket.download, storage_key)
        if not data:
            raise HTTPException(status_code=404, detail="Template not found")

        return {
            "data": base64.b64encode(data).decode("utf-8"),
            "content_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "filename": f"{location_key}.pptx",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[STORAGE] Failed to get template: {e}")
        raise HTTPException(status_code=404, detail="Template not found")


@router.get("/templates/{company}/{location_key}/exists", response_model=ExistsResponse)
async def template_exists(company: str, location_key: str) -> dict[str, bool]:
    """
    Check if template exists for a location.

    Args:
        company: Company schema
        location_key: Location identifier

    Returns:
        Exists flag
    """
    try:
        storage = _get_storage_client()
        bucket = storage.from_("templates")

        storage_key = f"{company}/{location_key}/{location_key}.pptx"

        # Try to get file info (run in thread pool)
        try:
            await asyncio.to_thread(bucket.download, storage_key)
            return {"exists": True}
        except Exception:
            return {"exists": False}

    except Exception as e:
        logger.error(f"[STORAGE] Failed to check template existence: {e}")
        return {"exists": False}


@router.get("/templates/{company}/{location_key}/url", response_model=UrlResponse)
async def get_template_url(
    company: str,
    location_key: str,
    expires_in: int = Query(default=3600, ge=60, le=86400),
) -> dict[str, Any]:
    """
    Get signed URL for template download.

    Args:
        company: Company schema
        location_key: Location identifier
        expires_in: URL expiry in seconds (default 1 hour)

    Returns:
        Signed URL
    """
    try:
        storage = _get_storage_client()
        bucket = storage.from_("templates")

        storage_key = f"{company}/{location_key}/{location_key}.pptx"
        result = bucket.create_signed_url(storage_key, expires_in)

        if result and "signedURL" in result:
            return {"url": result["signedURL"], "expires_in": expires_in}

        raise HTTPException(status_code=404, detail="Template not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[STORAGE] Failed to create signed URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class UploadTemplateRequest(BaseModel):
    """Request for uploading a template."""
    location_key: str
    data: str  # Base64-encoded file data
    filename: str = None  # Optional, defaults to {location_key}.pptx


class UploadResponse(BaseModel):
    """Response for upload operations."""
    success: bool
    storage_key: str
    message: str


@router.post("/templates/{company}", response_model=UploadResponse)
async def upload_template(company: str, request: UploadTemplateRequest) -> dict[str, Any]:
    """
    Upload a template file for a location.

    Templates are stored in: templates/{company}/{location_key}/{location_key}.pptx

    Args:
        company: Company schema (e.g., "backlite_dubai")
        request: Upload request with location_key and base64 data

    Returns:
        Upload result with storage key
    """
    location_key = request.location_key.lower().strip()
    logger.info(f"[STORAGE] Uploading template for {company}/{location_key}")

    try:
        storage = _get_storage_client()
        bucket = storage.from_("templates")

        # Decode base64 data
        import base64 as b64
        file_data = b64.b64decode(request.data)

        # Determine filename
        filename = request.filename or f"{location_key}.pptx"
        storage_key = f"{company}/{location_key}/{filename}"

        # Upload file
        result = bucket.upload(
            storage_key,
            file_data,
            {
                "content-type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                "upsert": "true",  # Overwrite if exists
            },
        )

        logger.info(f"[STORAGE] Template uploaded: {storage_key}")
        return {
            "success": True,
            "storage_key": storage_key,
            "message": f"Template uploaded for {company}/{location_key}",
        }

    except Exception as e:
        logger.error(f"[STORAGE] Failed to upload template: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/templates/{company}/{location_key}", response_model=UploadResponse)
async def delete_template(company: str, location_key: str) -> dict[str, Any]:
    """
    Delete a template file for a location.

    Args:
        company: Company schema
        location_key: Location identifier

    Returns:
        Delete result
    """
    location_key = location_key.lower().strip()
    logger.info(f"[STORAGE] Deleting template for {company}/{location_key}")

    try:
        storage = _get_storage_client()
        bucket = storage.from_("templates")

        storage_key = f"{company}/{location_key}/{location_key}.pptx"

        # Delete file
        bucket.remove([storage_key])

        # Also try to remove the location folder if empty
        try:
            bucket.remove([f"{company}/{location_key}"])
        except Exception:
            pass  # Folder may not be empty or may not exist

        logger.info(f"[STORAGE] Template deleted: {storage_key}")
        return {
            "success": True,
            "storage_key": storage_key,
            "message": f"Template deleted for {company}/{location_key}",
        }

    except Exception as e:
        logger.error(f"[STORAGE] Failed to delete template: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# INTRO/OUTRO PDFs
# =============================================================================


@router.get("/intro-outro/{company}/{pdf_name}", response_model=FileResponse)
async def get_intro_outro_pdf(company: str, pdf_name: str) -> dict[str, Any]:
    """
    Download intro/outro PDF.

    Storage structure: templates/{company}/intro_outro/{pdf_name}.pdf

    Args:
        company: Company schema
        pdf_name: PDF name (e.g., "landmark_series", "rest")

    Returns:
        Base64-encoded PDF data
    """
    logger.info(f"[STORAGE] Getting intro/outro PDF: {company}/{pdf_name}")

    try:
        storage = _get_storage_client()
        bucket = storage.from_("templates")

        # Look for PDF in company's intro_outro folder
        storage_key = f"{company}/intro_outro/{pdf_name}.pdf"

        # Run blocking Supabase download in thread pool for concurrent execution
        data = await asyncio.to_thread(bucket.download, storage_key)
        if not data:
            raise HTTPException(status_code=404, detail="PDF not found")

        return {
            "data": base64.b64encode(data).decode("utf-8"),
            "content_type": "application/pdf",
            "filename": f"{pdf_name}.pdf",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.debug(f"[STORAGE] Intro/outro PDF not found: {company}/{pdf_name} - {e}")
        raise HTTPException(status_code=404, detail="PDF not found")


# =============================================================================
# MOCKUP PHOTOS
# =============================================================================


def _build_mockup_storage_key(
    company: str,
    location_key: str,
    environment: str,
    time_of_day: str | None,
    side: str | None,
    photo_filename: str,
) -> str:
    """
    Build mockup storage key based on environment.

    Args:
        company: Company schema (e.g., "backlite_dubai")
        location_key: Location identifier. Can be:
            - Standalone network: just network_key (e.g., "dubai_gateway")
            - Traditional network: "{network_key}/{type_key}/{asset_key}" (e.g., "dubai_mall/digital_screens/mall_screen_a")
        environment: "indoor" or "outdoor"
        time_of_day: "day" or "night" (ignored for indoor)
        side: "gold", "silver", or "single_side" (ignored for indoor)
        photo_filename: The photo filename

    Structure:
    - Standalone outdoor: {company}/{network_key}/outdoor/{time_of_day}/{side}/{filename}
    - Standalone indoor:  {company}/{network_key}/indoor/{filename}
    - Traditional outdoor: {company}/{network_key}/{type_key}/{asset_key}/outdoor/{time_of_day}/{side}/{filename}
    - Traditional indoor:  {company}/{network_key}/{type_key}/{asset_key}/indoor/{filename}
    """
    if environment == "indoor":
        # Indoor: simplified structure, no time_of_day/side
        return f"{company}/{location_key}/indoor/{photo_filename}"
    else:
        # Outdoor: full structure with time_of_day and side
        return f"{company}/{location_key}/outdoor/{time_of_day}/{side}/{photo_filename}"


@router.get(
    "/mockups/{company}/{location_key}/{environment}/{time_of_day}/{side}/{photo_filename}",
    response_model=FileResponse,
)
async def get_mockup_photo(
    company: str,
    location_key: str,
    environment: str,
    time_of_day: str,
    side: str,
    photo_filename: str,
) -> dict[str, Any]:
    """
    Download mockup background photo.

    Storage structure:
    - Outdoor: mockups/{company}/{location_key}/outdoor/{time_of_day}/{side}/{photo_filename}
    - Indoor: mockups/{company}/{location_key}/indoor/{photo_filename}

    Args:
        company: Company schema
        location_key: Location identifier
        environment: "indoor" or "outdoor"
        time_of_day: "day" or "night" (ignored for indoor)
        side: "gold", "silver", or "single_side" (ignored for indoor)
        photo_filename: Photo filename

    Returns:
        Base64-encoded photo data
    """
    logger.info(f"[STORAGE] Getting mockup photo: {company}/{location_key}/{environment}/{time_of_day}/{side}/{photo_filename}")

    try:
        storage = _get_storage_client()
        bucket = storage.from_("mockups")

        storage_key = _build_mockup_storage_key(
            company, location_key, environment, time_of_day, side, photo_filename
        )

        # Run blocking Supabase download in thread pool for concurrent execution
        data = await asyncio.to_thread(bucket.download, storage_key)
        if not data:
            raise HTTPException(status_code=404, detail="Photo not found")

        # Determine content type from extension
        ext = photo_filename.lower().split(".")[-1] if "." in photo_filename else "jpg"
        content_types = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
        }
        content_type = content_types.get(ext, "image/jpeg")

        return {
            "data": base64.b64encode(data).decode("utf-8"),
            "content_type": content_type,
            "filename": photo_filename,
        }

    except HTTPException:
        raise
    except Exception as e:
        # Log at debug level since 404s are expected during multi-company searches
        logger.debug(f"[STORAGE] Mockup photo not found: {storage_key} - {e}")
        raise HTTPException(status_code=404, detail="Photo not found")


# Simplified route for indoor (no time_of_day/finish needed)
@router.get(
    "/mockups/{company}/{location_key}/indoor/{photo_filename}",
    response_model=FileResponse,
)
async def get_mockup_photo_indoor(
    company: str,
    location_key: str,
    photo_filename: str,
) -> dict[str, Any]:
    """
    Download indoor mockup background photo (simplified path).

    Storage structure: mockups/{company}/{location_key}/indoor/{photo_filename}

    Args:
        company: Company schema
        location_key: Location identifier
        photo_filename: Photo filename

    Returns:
        Base64-encoded photo data
    """
    logger.info(f"[STORAGE] Getting indoor mockup photo: {company}/{location_key}/indoor/{photo_filename}")

    try:
        storage = _get_storage_client()
        bucket = storage.from_("mockups")

        storage_key = f"{company}/{location_key}/indoor/{photo_filename}"

        # Run blocking Supabase download in thread pool for concurrent execution
        data = await asyncio.to_thread(bucket.download, storage_key)
        if not data:
            raise HTTPException(status_code=404, detail="Photo not found")

        # Determine content type from extension
        ext = photo_filename.lower().split(".")[-1] if "." in photo_filename else "jpg"
        content_types = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
        }
        content_type = content_types.get(ext, "image/jpeg")

        return {
            "data": base64.b64encode(data).decode("utf-8"),
            "content_type": content_type,
            "filename": photo_filename,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.debug(f"[STORAGE] Indoor mockup photo not found: {company}/{location_key}/indoor/{photo_filename} - {e}")
        raise HTTPException(status_code=404, detail="Photo not found")


@router.get(
    "/mockups/{company}/{location_key}/{environment}/{time_of_day}/{side}/{photo_filename}/url",
    response_model=UrlResponse,
)
async def get_mockup_photo_url(
    company: str,
    location_key: str,
    environment: str,
    time_of_day: str,
    side: str,
    photo_filename: str,
    expires_in: int = Query(default=3600, ge=60, le=86400),
) -> dict[str, Any]:
    """
    Get signed URL for mockup photo download.

    Args:
        company: Company schema
        location_key: Location identifier
        environment: "indoor" or "outdoor"
        time_of_day: "day" or "night" (ignored for indoor)
        side: "gold", "silver", or "single_side" (ignored for indoor)
        photo_filename: Photo filename
        expires_in: URL expiry in seconds

    Returns:
        Signed URL
    """
    try:
        storage = _get_storage_client()
        bucket = storage.from_("mockups")

        storage_key = _build_mockup_storage_key(
            company, location_key, environment, time_of_day, side, photo_filename
        )
        result = bucket.create_signed_url(storage_key, expires_in)

        if result and "signedURL" in result:
            return {"url": result["signedURL"], "expires_in": expires_in}

        raise HTTPException(status_code=404, detail="Photo not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[STORAGE] Failed to create signed URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Simplified URL route for indoor
@router.get(
    "/mockups/{company}/{location_key}/indoor/{photo_filename}/url",
    response_model=UrlResponse,
)
async def get_mockup_photo_url_indoor(
    company: str,
    location_key: str,
    photo_filename: str,
    expires_in: int = Query(default=3600, ge=60, le=86400),
) -> dict[str, Any]:
    """
    Get signed URL for indoor mockup photo download.

    Args:
        company: Company schema
        location_key: Location identifier
        photo_filename: Photo filename
        expires_in: URL expiry in seconds

    Returns:
        Signed URL
    """
    try:
        storage = _get_storage_client()
        bucket = storage.from_("mockups")

        storage_key = f"{company}/{location_key}/indoor/{photo_filename}"
        result = bucket.create_signed_url(storage_key, expires_in)

        if result and "signedURL" in result:
            return {"url": result["signedURL"], "expires_in": expires_in}

        raise HTTPException(status_code=404, detail="Photo not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[STORAGE] Failed to create signed URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))
