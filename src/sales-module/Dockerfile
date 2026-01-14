# =============================================================================
# BASE DOCKERFILE (Reference/Template)
# =============================================================================
# This is the base Dockerfile template. Use environment-specific versions:
# - Dockerfile.render = Render deployments
# - Dockerfile.aws = AWS deployments (ECS, Fargate)
# - Dockerfile.local = Local development
# =============================================================================

FROM python:3.11-slim

# Install system dependencies including LibreOffice and git
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice \
    libreoffice-writer \
    libreoffice-impress \
    fonts-liberation \
    fonts-liberation2 \
    fonts-dejavu \
    fonts-dejavu-core \
    fonts-dejavu-extra \
    fontconfig \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Verify LibreOffice installation
RUN which libreoffice && libreoffice --version

# Set working directory
WORKDIR /app

# Shared libs (for local installs in requirements.render.txt)
COPY src/shared/crm-security /app/shared/crm-security
COPY src/shared/crm-cache /app/shared/crm-cache
COPY src/shared/crm-llm /app/shared/crm-llm
COPY src/shared/crm-channels /app/shared/crm-channels

# Copy requirements first for better caching
COPY src/sales-module/requirements.aws.txt /app/requirements.aws.txt
RUN pip install --no-cache-dir -r /app/requirements.aws.txt

# Copy application code
COPY src/sales-module/ /app/

# Create directory for fonts
RUN mkdir -p /usr/share/fonts/truetype/custom

# Copy and install custom fonts if they exist in the data volume
# This will be done at runtime since /data is a mounted volume

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONPATH=/app

# Create a startup script (use /bin/sh; bash is not guaranteed to exist in slim images)
RUN echo '#!/bin/sh\n\
export PYTHONPATH=/app\n\
if [ -d "/data/Sofia-Pro Font" ]; then\n\
    echo "Installing custom fonts..."\n\
    cp "/data/Sofia-Pro Font"/*.ttf /usr/share/fonts/truetype/custom/ 2>/dev/null || true\n\
    cp "/data/Sofia-Pro Font"/*.otf /usr/share/fonts/truetype/custom/ 2>/dev/null || true\n\
    fc-cache -f -v\n\
fi\n\
exec uvicorn api.server:app --host 0.0.0.0 --port $PORT' > /app/start.sh && \
    chmod +x /app/start.sh

# Run the startup script
CMD ["/app/start.sh"]
