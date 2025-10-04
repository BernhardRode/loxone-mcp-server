# Loxone MCP Server Dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:$PATH"

# Copy project files
COPY pyproject.toml uv.lock ./
COPY src/ ./src/
COPY README.md ./

# Install Python dependencies
RUN uv venv /opt/venv
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN uv pip install -e .

# Create directory for token persistence
RUN mkdir -p /app/tokens
ENV LOXONE_TOKEN_PATH=/app/tokens/loxone_token.json

# Create non-root user
RUN useradd --create-home --shell /bin/bash loxone
RUN chown -R loxone:loxone /app
USER loxone

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Expose port (if running HTTP server mode)
EXPOSE 3000

# Set default environment variables
ENV LOG_LEVEL=INFO
ENV PYTHONUNBUFFERED=1

# Run the server
CMD ["loxone-mcp-server"]