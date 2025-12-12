#!/usr/bin/env python3
"""
Cleanup soft-deleted files from storage.

This script:
1. Finds documents marked as is_deleted=True with deleted_at older than N days
2. Deletes the actual files from storage (local/Supabase)
3. Hard-deletes the database records

Usage:
    # Dry run (show what would be deleted)
    python db/scripts/cleanup_deleted_files.py --dry-run

    # Delete files older than 30 days (default)
    python db/scripts/cleanup_deleted_files.py

    # Delete files older than 7 days
    python db/scripts/cleanup_deleted_files.py --days 7

    # Run for specific table only
    python db/scripts/cleanup_deleted_files.py --table documents
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("file_cleanup")


async def cleanup_documents(
    older_than_days: int = 30,
    dry_run: bool = False,
    batch_size: int = 100,
) -> Dict[str, int]:
    """
    Cleanup soft-deleted documents.

    Args:
        older_than_days: Delete files older than this many days
        dry_run: If True, only show what would be deleted
        batch_size: Number of records to process per batch

    Returns:
        Stats dict with counts
    """
    from db.database import db
    from integrations.storage import get_storage_client

    stats = {
        "documents_found": 0,
        "storage_deleted": 0,
        "db_deleted": 0,
        "errors": 0,
    }

    logger.info(f"Looking for soft-deleted documents older than {older_than_days} days...")

    # Get soft-deleted documents
    documents = db.get_soft_deleted_documents(
        older_than_days=older_than_days,
        limit=batch_size,
    )

    stats["documents_found"] = len(documents)

    if not documents:
        logger.info("No documents found for cleanup.")
        return stats

    logger.info(f"Found {len(documents)} documents to cleanup")

    # Get storage client
    storage_client = get_storage_client()

    for doc in documents:
        file_id = doc.get("file_id")
        storage_provider = doc.get("storage_provider")
        storage_bucket = doc.get("storage_bucket")
        storage_key = doc.get("storage_key")
        filename = doc.get("original_filename")
        deleted_at = doc.get("deleted_at")

        if dry_run:
            logger.info(f"[DRY RUN] Would delete: {filename} (id={file_id}, deleted_at={deleted_at})")
            continue

        try:
            # Delete from storage
            if storage_provider == "local":
                # Local file - delete from filesystem
                local_path = Path(storage_key)
                if local_path.exists():
                    local_path.unlink()
                    stats["storage_deleted"] += 1
                    logger.info(f"Deleted local file: {local_path}")
                else:
                    logger.warning(f"Local file not found: {local_path}")
            elif storage_bucket and storage_key:
                # Remote storage (Supabase/S3)
                deleted = await storage_client.delete(storage_bucket, storage_key)
                if deleted:
                    stats["storage_deleted"] += 1
                    logger.info(f"Deleted from storage: {storage_bucket}/{storage_key}")
                else:
                    logger.warning(f"Storage file not found: {storage_bucket}/{storage_key}")

            # Hard delete from database
            if db.hard_delete_document(file_id):
                stats["db_deleted"] += 1
                logger.info(f"Hard-deleted document record: {file_id}")
            else:
                logger.warning(f"Failed to hard-delete document: {file_id}")

        except Exception as e:
            logger.error(f"Error cleaning up {file_id}: {e}")
            stats["errors"] += 1

    return stats


async def cleanup_table(
    table_name: str,
    older_than_days: int = 30,
    dry_run: bool = False,
    batch_size: int = 100,
) -> Dict[str, int]:
    """
    Generic cleanup for any file table (mockup_files, proposal_files).

    Args:
        table_name: Table to cleanup
        older_than_days: Delete files older than this many days
        dry_run: If True, only show what would be deleted
        batch_size: Number of records to process per batch

    Returns:
        Stats dict with counts
    """
    from db.database import db
    from integrations.storage import get_storage_client

    stats = {
        "files_found": 0,
        "storage_deleted": 0,
        "db_deleted": 0,
        "errors": 0,
    }

    logger.info(f"Looking for soft-deleted {table_name} older than {older_than_days} days...")

    try:
        client = db._get_client()
        cutoff_date = (datetime.now() - timedelta(days=older_than_days)).isoformat()

        response = (
            client.table(table_name)
            .select("*")
            .eq("is_deleted", True)
            .lt("deleted_at", cutoff_date)
            .limit(batch_size)
            .execute()
        )

        files = response.data or []
        stats["files_found"] = len(files)

        if not files:
            logger.info(f"No {table_name} found for cleanup.")
            return stats

        logger.info(f"Found {len(files)} {table_name} to cleanup")

        storage_client = get_storage_client()

        for f in files:
            file_id = f.get("file_id")
            storage_provider = f.get("storage_provider", "local")
            storage_bucket = f.get("storage_bucket")
            storage_key = f.get("storage_key")
            deleted_at = f.get("deleted_at")

            if dry_run:
                logger.info(f"[DRY RUN] Would delete {table_name}: {file_id} (deleted_at={deleted_at})")
                continue

            try:
                # Delete from storage
                if storage_provider == "local":
                    local_path = Path(storage_key)
                    if local_path.exists():
                        local_path.unlink()
                        stats["storage_deleted"] += 1
                elif storage_bucket and storage_key:
                    deleted = await storage_client.delete(storage_bucket, storage_key)
                    if deleted:
                        stats["storage_deleted"] += 1

                # Hard delete from database
                client.table(table_name).delete().eq("file_id", file_id).execute()
                stats["db_deleted"] += 1
                logger.info(f"Cleaned up {table_name}: {file_id}")

            except Exception as e:
                logger.error(f"Error cleaning up {table_name} {file_id}: {e}")
                stats["errors"] += 1

    except Exception as e:
        logger.error(f"Error querying {table_name}: {e}")

    return stats


async def run_cleanup(
    older_than_days: int = 30,
    dry_run: bool = False,
    table: Optional[str] = None,
) -> Dict[str, int]:
    """
    Run cleanup for all or specific file tables.

    Args:
        older_than_days: Delete files older than this many days
        dry_run: If True, only show what would be deleted
        table: Specific table to cleanup (None = all)

    Returns:
        Total stats across all tables
    """
    print(f"\n{'='*60}")
    print("FILE CLEANUP SCRIPT")
    print(f"{'='*60}")
    print(f"Dry run: {dry_run}")
    print(f"Delete files older than: {older_than_days} days")
    print(f"Table filter: {table or 'all'}")
    print()

    total_stats = {
        "files_found": 0,
        "storage_deleted": 0,
        "db_deleted": 0,
        "errors": 0,
    }

    # Cleanup each table
    if table is None or table == "documents":
        print("\n--- Documents ---")
        stats = await cleanup_documents(older_than_days, dry_run)
        for k, v in stats.items():
            if k in total_stats:
                total_stats[k] += v
            else:
                total_stats["files_found"] += stats.get("documents_found", 0)

    if table is None or table == "mockup_files":
        print("\n--- Mockup Files ---")
        stats = await cleanup_table("mockup_files", older_than_days, dry_run)
        for k, v in stats.items():
            total_stats[k] = total_stats.get(k, 0) + v

    if table is None or table == "proposal_files":
        print("\n--- Proposal Files ---")
        stats = await cleanup_table("proposal_files", older_than_days, dry_run)
        for k, v in stats.items():
            total_stats[k] = total_stats.get(k, 0) + v

    # Print summary
    print(f"\n{'='*60}")
    print("CLEANUP SUMMARY:")
    print(f"{'='*60}")
    print(f"  Files found: {total_stats['files_found']}")
    if not dry_run:
        print(f"  Storage files deleted: {total_stats['storage_deleted']}")
        print(f"  DB records deleted: {total_stats['db_deleted']}")
        print(f"  Errors: {total_stats['errors']}")
    else:
        print("  (Dry run - no files were deleted)")
    print(f"{'='*60}")

    return total_stats


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Cleanup soft-deleted files from storage')
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be deleted without actually deleting'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=30,
        help='Delete files older than this many days (default: 30)'
    )
    parser.add_argument(
        '--table',
        choices=['documents', 'mockup_files', 'proposal_files'],
        help='Only cleanup specific table (default: all)'
    )
    args = parser.parse_args()

    await run_cleanup(
        older_than_days=args.days,
        dry_run=args.dry_run,
        table=args.table,
    )


if __name__ == '__main__':
    asyncio.run(main())
