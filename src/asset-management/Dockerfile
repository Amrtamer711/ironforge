# =============================================================================
# BASE DOCKERFILE (Reference/Template)
# =============================================================================
# This is the base Dockerfile template. Use environment-specific versions:
# - Dockerfile.render = Render deployments
# - Dockerfile.aws = AWS deployments (ECS, Fargate)
# - Dockerfile.local = Local development
# =============================================================================

FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Shared libs (for local installs in requirements.render.txt)
COPY src/shared/crm-security /app/shared/crm-security
COPY src/shared/crm-cache /app/shared/crm-cache

# Copy requirements first for better caching
COPY src/asset-management/requirements.aws.txt /app/requirements.aws.txt
RUN pip install --no-cache-dir -r /app/requirements.aws.txt

# Copy application code
COPY src/asset-management/ /app/

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
