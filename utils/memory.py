"""
Centralized memory management utilities.

Provides a single point of control for memory cleanup operations,
preventing scattered gc.collect() calls throughout the codebase.
"""

import gc
import logging
import os

import psutil

logger = logging.getLogger(__name__)


def get_memory_usage() -> dict:
    """
    Get current process memory usage.

    Returns:
        Dict with rss_mb (resident set size) and vms_mb (virtual memory size)
    """
    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()
    return {
        "rss_mb": round(mem_info.rss / 1024 / 1024, 2),
        "vms_mb": round(mem_info.vms / 1024 / 1024, 2),
    }


def cleanup_memory(
    context: str | None = None,
    aggressive: bool = False,
    log_stats: bool = True,
) -> dict:
    """
    Perform memory cleanup with optional aggressive mode.

    This is the ONLY place gc.collect() should be called in the codebase.
    All other modules should import and use this function.

    Args:
        context: Optional string describing what triggered the cleanup (for logging)
        aggressive: If True, perform full 3-generation GC + malloc_trim
        log_stats: If True, log memory stats before/after cleanup

    Returns:
        Dict with memory stats (before, after, freed_mb)
    """
    prefix = f"[MEMORY:{context}]" if context else "[MEMORY]"

    before = get_memory_usage() if log_stats else None

    if aggressive:
        # Full 3-generation garbage collection
        gc.collect(0)  # Generation 0 (recent objects)
        gc.collect(1)  # Generation 1
        gc.collect(2)  # Generation 2 (full collection)

        # Try to return freed memory to OS (Linux only)
        _try_malloc_trim(prefix)
    else:
        # Single full collection (default gc.collect() behavior)
        gc.collect()

    after = get_memory_usage() if log_stats else None

    result = {
        "before": before,
        "after": after,
        "freed_mb": round(before["rss_mb"] - after["rss_mb"], 2) if before and after else None,
    }

    if log_stats and before and after:
        freed = result["freed_mb"]
        logger.info(
            f"{prefix} Cleanup complete "
            f"(RAM: {before['rss_mb']}MB → {after['rss_mb']}MB, "
            f"freed: {freed:+.2f}MB)"
        )

    return result


def _try_malloc_trim(log_prefix: str = "[MEMORY]") -> bool:
    """
    Attempt to return freed memory to OS using malloc_trim (Linux only).

    Returns:
        True if malloc_trim was called successfully, False otherwise
    """
    try:
        import ctypes
        libc = ctypes.CDLL("libc.so.6")
        libc.malloc_trim(0)
        logger.debug(f"{log_prefix} malloc_trim() called successfully")
        return True
    except Exception:
        # Not on Linux or malloc_trim unavailable - that's okay
        return False


def check_memory_threshold(
    threshold_mb: float = 1000.0,
    auto_cleanup: bool = True,
    context: str | None = None,
) -> dict:
    """
    Check if memory usage exceeds threshold and optionally trigger cleanup.

    Args:
        threshold_mb: Memory threshold in MB
        auto_cleanup: If True and threshold exceeded, automatically run cleanup
        context: Context string for logging

    Returns:
        Dict with current_mb, threshold_mb, exceeded, and cleaned_up
    """
    current = get_memory_usage()
    exceeded = current["rss_mb"] > threshold_mb
    cleaned_up = False

    if exceeded and auto_cleanup:
        prefix = f"[MEMORY:{context}]" if context else "[MEMORY]"
        logger.warning(
            f"{prefix} Memory threshold exceeded "
            f"({current['rss_mb']}MB > {threshold_mb}MB), triggering cleanup"
        )
        cleanup_memory(context=context, aggressive=True, log_stats=True)
        cleaned_up = True

    return {
        "current_mb": current["rss_mb"],
        "threshold_mb": threshold_mb,
        "exceeded": exceeded,
        "cleaned_up": cleaned_up,
    }
