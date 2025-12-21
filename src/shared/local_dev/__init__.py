"""
MMG Local Development Tools

Tools for fully offline development:
- sync_from_supabase.py: Sync Dev Supabase → local SQLite
- setup_local_env.py: Set up local development environment

Usage:
    # Set up local environment
    python -m shared.local_dev.setup_local_env

    # Sync from Dev Supabase
    python -m shared.local_dev.sync_from_supabase

    # Check setup
    python -m shared.local_dev.setup_local_env --check
"""
