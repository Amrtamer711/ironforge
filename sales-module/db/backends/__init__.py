"""
Database backends package.

Available backends:
- SQLiteBackend: Local SQLite database (default)
- SupabaseBackend: Cloud-hosted Supabase PostgreSQL
"""

from db.backends.sqlite import SQLiteBackend

# Supabase is optional - only import if available
try:
    from db.backends.supabase import SupabaseBackend
    __all__ = ["SQLiteBackend", "SupabaseBackend"]
except ImportError:
    __all__ = ["SQLiteBackend"]
