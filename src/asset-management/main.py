"""
Main entry point for the Asset Management Service.
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("api.server:app", host="0.0.0.0", port=8001, reload=True)
