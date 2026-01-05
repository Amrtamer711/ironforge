"""
Main entry point for the Video Critique Service.
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("api.server:app", host="0.0.0.0", port=8003, reload=True)
