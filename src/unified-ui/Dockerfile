# unified-ui FastAPI Backend
# Replaces Node.js server.js with Python FastAPI
# Maintains same port and API contract

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends curl git \
  && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
# Use requirements.render.txt for production (git-based SDK install)

COPY src/shared/crm-security /app/shared/crm-security
COPY src/unified-ui/requirements.render.txt /app/requirements.render.txt
# Install Python dependencies
RUN pip install --no-cache-dir "/app/shared/crm-security[fastapi]" \
 && pip install --no-cache-dir -r /app/requirements.render.txt

COPY src/unified-ui /app


# Create directories
RUN mkdir -p uploads data

# Environment defaults
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV ENVIRONMENT=production
ENV PORT=3005

# Expose the port (same as Node.js version)
EXPOSE 3005

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:3005/health || exit 1

# Run uvicorn
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "3005"]
