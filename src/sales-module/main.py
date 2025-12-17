"""
Main entry point for the Sales Proposals application.
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("api.server:app", host="0.0.0.0", port=3000, reload=True)
