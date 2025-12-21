FROM python:3.11-slim

WORKDIR /app

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
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
