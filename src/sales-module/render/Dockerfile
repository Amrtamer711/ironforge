# =============================================================================
# RENDER DEPLOYMENT DOCKERFILE
# =============================================================================
# This Dockerfile is ONLY used for Render deployments.
# Do NOT modify for other pipelines (AWS, etc.) - use Dockerfile instead.
# =============================================================================

FROM python:3.11-slim

# Install system dependencies including LibreOffice and git
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
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

# Copy requirements first for better caching
# Use requirements.render.txt for production (git-based SDK install)
COPY requirements.render.txt .
RUN pip install --no-cache-dir -r requirements.render.txt

# Copy application code
COPY . .

# Create directory for fonts
RUN mkdir -p /usr/share/fonts/truetype/custom

# Copy and install custom fonts if they exist in the data volume
# This will be done at runtime since /data is a mounted volume

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONPATH=/app

# Create a startup script
RUN echo '#!/bin/bash\n\
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