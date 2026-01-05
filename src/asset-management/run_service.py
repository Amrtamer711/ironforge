#!/usr/bin/env python3
"""
Standalone uvicorn runner for asset-management service.

Usage:
    python run_service.py

Environment Variables:
    PORT: Server port (default: 8001)
    ENVIRONMENT: 'development' or 'production' (default: development)

In development mode, auto-reload is enabled.
"""
import os
import sys
from pathlib import Path

# Add shared modules to path for local development
# This allows importing crm_security, crm_cache, crm_channels, crm_llm without pip install
_shared_base = Path(__file__).parent.parent / "shared"
for _module in ["crm-security", "crm-cache", "crm-channels", "crm-llm"]:
    _shared_path = _shared_base / _module
    if _shared_path.exists() and str(_shared_path) not in sys.path:
        sys.path.insert(0, str(_shared_path))

import uvicorn


def main():
    """Run the asset-management FastAPI server."""
    port = int(os.getenv("PORT", "8001"))
    environment = os.getenv("ENVIRONMENT", "development")
    reload = environment != "production"

    print(f"Starting asset-management service on port {port}")
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
