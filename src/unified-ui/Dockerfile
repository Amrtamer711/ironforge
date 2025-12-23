# unified-ui FastAPI Backend
# Replaces Node.js server.js with Python FastAPI
# Maintains same port and API contract

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
  && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
# Use requirements.render.txt for production (git-based SDK install)
COPY requirements.render.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.render.txt

# Copy backend code
COPY backend/ ./backend/

# Copy frontend static files
COPY public/ ./public/

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
