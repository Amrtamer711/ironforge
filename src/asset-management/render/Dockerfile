# =============================================================================
# RENDER DEPLOYMENT DOCKERFILE
# =============================================================================
# This Dockerfile is ONLY used for Render deployments.
# Do NOT modify for other pipelines (AWS, etc.) - use Dockerfile instead.
# =============================================================================

FROM python:3.11-slim

WORKDIR /app

# Install git for pip to clone dependencies from GitHub
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
# Use requirements.render.txt for production (git-based SDK install)
COPY requirements.render.txt .
RUN pip install --no-cache-dir -r requirements.render.txt

# Copy application code
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Default port
ENV PORT=8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/health')"

# Run the application
CMD ["sh", "-c", "uvicorn api.server:app --host 0.0.0.0 --port ${PORT}"]
