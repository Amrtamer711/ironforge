# =============================================================================
# RENDER DEPLOYMENT DOCKERFILE - Video Critique
# =============================================================================
# This Dockerfile is ONLY used for Render deployments.
# Do NOT modify for other pipelines - use the appropriate Dockerfile instead:
# - Dockerfile (root) = AWS/ECS/Production
# - local/Dockerfile = Local development
# =============================================================================

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (git required for pip to clone SDK repos)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
# Use requirements.render.txt for production (git-based SDK install)
COPY requirements.render.txt .
RUN pip install --no-cache-dir -r requirements.render.txt

# Copy application code
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app

# Default port
ENV PORT=8003

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Run the application
CMD ["sh", "-c", "uvicorn api.server:app --host 0.0.0.0 --port ${PORT}"]
