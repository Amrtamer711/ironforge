# =============================================================================
# BASE DOCKERFILE (Reference/Template)
# =============================================================================
# This is the base Dockerfile template. Use environment-specific versions:
# - Dockerfile.render = Render deployments
# - Dockerfile.aws = AWS deployments (ECS, Fargate)
# - Dockerfile.local = Local development
# =============================================================================
#
# Security Service Dockerfile
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

# Copy requirements first for better caching
COPY src/security-service/requirements.aws.txt /app/requirements.aws.txt
RUN pip install --no-cache-dir -r /app/requirements.aws.txt

# Copy application code
COPY src/security-service/ /app/

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app

# Default port
ENV PORT=8002

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Run the application
CMD ["sh", "-c", "uvicorn api.server:app --host 0.0.0.0 --port ${PORT}"]
