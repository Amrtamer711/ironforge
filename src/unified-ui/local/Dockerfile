# =============================================================================
# LOCAL DEVELOPMENT DOCKERFILE
# =============================================================================
# This Dockerfile is for local development and testing.
# Do NOT modify for other pipelines - use the appropriate Dockerfile instead.
# - Dockerfile.render = Render
# - Dockerfile.aws = AWS (ECS, Fargate)
# =============================================================================
#
# unified-ui FastAPI Backend + React Frontend
# Multi-stage build: Node.js for frontend, Python for backend

# =============================================================================
# Stage 1: Build React Frontend
# =============================================================================
FROM node:20-slim AS frontend-builder

WORKDIR /frontend

# Copy package files first for better caching
COPY src/unified-ui/frontend/package*.json ./

# Install dependencies
RUN npm ci --only=production=false

# Copy frontend source
COPY src/unified-ui/frontend/ ./

# Build the React app
RUN npm run build

# =============================================================================
# Stage 2: Python Backend + Built Frontend
# =============================================================================
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends curl git \
  && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY src/shared/crm-security /app/shared/crm-security
COPY src/shared/crm-cache /app/shared/crm-cache
COPY src/unified-ui/requirements.render.txt /app/requirements.render.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r /app/requirements.render.txt

# Copy backend
COPY src/unified-ui/backend /app/backend
COPY src/unified-ui/db /app/db

# Copy built frontend from Stage 1
COPY --from=frontend-builder /frontend/dist /app/public

# Create directories
RUN mkdir -p uploads data

# Environment defaults
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV ENVIRONMENT=production
ENV PORT=3005

# Expose the port
EXPOSE 3005

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:3005/health || exit 1

# Run uvicorn
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "3005"]
