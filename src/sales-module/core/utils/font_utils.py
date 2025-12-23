"""
Font utilities for proposal generation.

Downloads custom fonts from Supabase Storage and installs them for PDF/PPTX rendering.
"""

import asyncio
import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger("proposal-bot")

# Local font cache directory
FONT_CACHE_DIR = Path("/data/fonts")


async def download_fonts_from_storage() -> bool:
    """
    Download fonts from Supabase Storage to local cache.

    Fonts are stored in Sales-Module Supabase Storage in the 'fonts' bucket.
    Downloads to /data/fonts for local use by PDF/PPTX generators.

    Returns:
        True if fonts were downloaded successfully
    """
    try:
        from integrations.storage.providers.supabase import SupabaseStorageProvider

        storage = SupabaseStorageProvider()

        # Ensure local font directory exists
        FONT_CACHE_DIR.mkdir(parents=True, exist_ok=True)

        # List all fonts in storage
        result = await storage.list_files("fonts", prefix="Sofia-Pro")

        if not result.success:
            logger.warning(f"[FONTS] Failed to list fonts: {result.error}")
            return False

        if not result.files:
            logger.info("[FONTS] No fonts found in storage")
            return False

        # Download each font file
        downloaded = 0
        for font_file in result.files:
            local_path = FONT_CACHE_DIR / font_file.name

            # Skip if already cached
            if local_path.exists():
                logger.debug(f"[FONTS] Already cached: {font_file.name}")
                continue

            # Download from storage
            download_result = await storage.download("fonts", font_file.key)
            if download_result.success and download_result.data:
                local_path.write_bytes(download_result.data)
                logger.info(f"[FONTS] Downloaded: {font_file.name}")
                downloaded += 1
            else:
                logger.warning(f"[FONTS] Failed to download: {font_file.name}")

        logger.info(f"[FONTS] Downloaded {downloaded} new fonts, {len(result.files)} total in storage")
        return True

    except Exception as e:
        logger.error(f"[FONTS] Failed to download fonts from storage: {e}")
        return False


def install_custom_fonts():
    """
    Install fonts from local cache to system font directories.

    This makes fonts available to libraries like python-pptx and reportlab
    for PDF/PPTX generation.
    """
    # Try multiple font source directories
    font_source_dirs = [
        FONT_CACHE_DIR,  # New: downloaded from Supabase
        Path("/data/Sofia-Pro Font"),  # Legacy: mounted volume
    ]

    font_files = []
    source_dir = None

    for dir_path in font_source_dirs:
        if dir_path.exists():
            font_files = list(dir_path.glob("*.ttf")) + list(dir_path.glob("*.otf"))
            if font_files:
                source_dir = dir_path
                break

    if not font_files:
        logger.info("[FONTS] No font files found to install")
        return

    # Target font directories (in order of preference)
    font_dirs = [
        Path.home() / ".fonts",
        Path.home() / ".local/share/fonts",
        Path("/usr/share/fonts/truetype/custom"),
    ]

    # Copy fonts to system directories
    for font_dir in font_dirs:
        try:
            font_dir.mkdir(parents=True, exist_ok=True)
            for font_file in font_files:
                dest = font_dir / font_file.name
                if not dest.exists():
                    shutil.copy2(font_file, dest)
                    logger.info(f"[FONTS] Installed {font_file.name} to {font_dir}")
            break  # Success, don't try other directories
        except Exception as e:
            logger.debug(f"[FONTS] Could not install to {font_dir}: {e}")
            continue

    # Set environment variable for fontconfig
    if source_dir:
        os.environ["FONTCONFIG_PATH"] = str(source_dir)

    logger.info(f"[FONTS] Installed {len(font_files)} fonts from {source_dir}")


async def ensure_fonts_available():
    """
    Ensure fonts are available for document generation.

    Downloads from Supabase Storage if needed, then installs to system.
    Call this during application startup.
    """
    # First, try to download from Supabase Storage
    await download_fonts_from_storage()

    # Then install to system font directories
    install_custom_fonts()


def sync_ensure_fonts_available():
    """
    Synchronous wrapper for ensure_fonts_available.

    Use this in non-async contexts like startup scripts.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Already in async context, schedule as task
            asyncio.create_task(ensure_fonts_available())
        else:
            loop.run_until_complete(ensure_fonts_available())
    except RuntimeError:
        # No event loop, create new one
        asyncio.run(ensure_fonts_available())
