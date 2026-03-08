# Memory Service Dockerfile
# Uses memsearch library for OpenClaw-style memory
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory
RUN mkdir -p /data/memory/memory

# Environment variables
ENV PYTHONPATH=/app
ENV MEMORY_DATA_PATH=/data/memory
ENV LOG_LEVEL=INFO
ENV HOST=0.0.0.0
ENV PORT=8007

# Expose port
EXPOSE 8007

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8007/health')"

# Run the service
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8007"]
