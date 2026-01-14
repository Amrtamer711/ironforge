# =============================================================================
# BASE DOCKERFILE - Video Critique (AWS/ECS/Production)
# =============================================================================
# This is the base Dockerfile for production deployments (AWS, ECS, Fargate).
# Do NOT modify for other pipelines - use the appropriate Dockerfile instead:
# - render/Dockerfile = Render deployments
# - local/Dockerfile = Local development
# =============================================================================

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Shared libs (for local installs in requirements.render.txt)
COPY src/shared/crm-security /app/shared/crm-security
COPY src/shared/crm-cache /app/shared/crm-cache
COPY src/shared/crm-llm /app/shared/crm-llm
COPY src/shared/crm-channels /app/shared/crm-channels

# Copy requirements first for better caching
COPY src/video-critique/requirements.aws.txt /app/requirements.aws.txt
RUN pip install --no-cache-dir -r /app/requirements.aws.txt

# Copy application code
COPY src/video-critique/ /app/

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
