#!/usr/bin/env python3
"""
Standalone uvicorn runner for sales-module (proposal-bot).

Usage:
    python run_service.py

Environment Variables:
    PORT: Server port (default: 8000)
    ENVIRONMENT: 'development' or 'production' (default: development)

In development mode, auto-reload is enabled.
"""
import os
import sys
from pathlib import Path

# Add shared modules to path for local development
# This allows importing crm_security without pip install
_shared_path = Path(__file__).parent.parent / "shared" / "crm-security"
if _shared_path.exists() and str(_shared_path) not in sys.path:
    sys.path.insert(0, str(_shared_path))

import uvicorn


def main():
    """Run the sales-module FastAPI server."""
    port = int(os.getenv("PORT", "8000"))
    environment = os.getenv("ENVIRONMENT", "development")
    reload = environment != "production"

    print(f"Starting sales-module (proposal-bot) on port {port}")
    print(f"Environment: {environment}")
    print(f"Auto-reload: {reload}")

    uvicorn.run(
        "api.server:app",
        host="0.0.0.0",
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    sys.exit(main() or 0)
