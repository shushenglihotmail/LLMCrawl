FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy package files
COPY pyproject.toml ./
COPY azure_devops_mcp_server ./azure_devops_mcp_server

# Install Python dependencies
RUN pip install --no-cache-dir -e .

# Create directory for token cache
RUN mkdir -p /app/.mcp_cache && chmod 777 /app/.mcp_cache

# Environment variables (override at runtime)
ENV AZURE_DEVOPS_ORG=microsoft
ENV AZURE_DEVOPS_PROJECT=OS
ENV AZURE_DEVOPS_REPO=os.2020
ENV MCP_MODE=http
ENV MCP_PORT=8004
ENV MCP_HOST=0.0.0.0
ENV AZURE_DEVOPS_AUTH_MODE=pat

# Expose HTTP port
EXPOSE 8004

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8004/health')" || exit 1

# Run server
CMD ["python", "-m", "azure_devops_mcp_server"]
