# Nightwatch AWS Pipeline Collector
# Multi-stage build for a minimal production image

FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# ─────────────────────────────────────────────────────────────────────────────
# Runtime stage — minimal image
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

LABEL maintainer="Nova ⚡ <nova@strategybase.io>"
LABEL description="Nightwatch AWS Pipeline Collector — Prometheus exporter for Bayer ModelN.io"
LABEL version="1.0.0"

# Create non-root user
RUN groupadd -g 10001 nightwatch && \
    useradd -u 10001 -g nightwatch -s /sbin/nologin -r nightwatch

WORKDIR /app

# Copy Python packages from builder
COPY --from=builder /root/.local /home/nightwatch/.local
ENV PATH=/home/nightwatch/.local/bin:$PATH
ENV PYTHONPATH=/home/nightwatch/.local/lib/python3.11/site-packages:$PYTHONPATH

# Copy application
COPY aws_pipeline_collector.py .

# Non-root user
USER nightwatch

# Expose metrics port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

# Environment defaults (override in Kubernetes)
ENV AWS_REGION=us-east-1 \
    PORT=8080 \
    SCRAPE_INTERVAL_SECONDS=30 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

CMD ["python", "-u", "aws_pipeline_collector.py"]
