# Dockerfile for Wallex Grid Bot
# Multi-stage build for smaller image

# Build stage
FROM python:3.12-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy and install dependencies
COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY config/ ./config/

RUN pip install --no-cache-dir -e ".[ui]"

# Runtime stage
FROM python:3.12-slim

WORKDIR /app

# Create non-root user
RUN groupadd -r wallexbot && useradd -r -g wallexbot wallexbot

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --from=builder /app/src ./src
COPY --from=builder /app/config ./config

# Create data directory
RUN mkdir -p /app/data && chown -R wallexbot:wallexbot /app

USER wallexbot

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8080/api/health', timeout=5)"

# Run command
CMD ["wallexbot", "ui", "--host", "0.0.0.0", "--port", "8080"]