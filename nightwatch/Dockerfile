# ============================================================================
# Nightwatch — Cloud-Agnostic AI Monitoring Platform
# Single image supports all adapters (AWS, ForexTrader, custom)
# ============================================================================

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for boto3, kubernetes client, httpx,
# and kubectl (used by remediation/log collection helpers).
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && ARCH="$(dpkg --print-architecture)" \
    && case "$ARCH" in \
        amd64) K8S_ARCH="amd64" ;; \
        arm64) K8S_ARCH="arm64" ;; \
        *) echo "Unsupported architecture: $ARCH" && exit 1 ;; \
       esac \
    && KUBECTL_VERSION="$(curl -fsSL https://dl.k8s.io/release/stable.txt)" \
    && curl -fsSLo /usr/local/bin/kubectl "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${K8S_ARCH}/kubectl" \
    && chmod +x /usr/local/bin/kubectl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY src/ ./src/
COPY config/ ./config/

# Nightwatch is a Python package
ENV PYTHONPATH=/app

# Non-root user for security
RUN useradd -m -u 1000 nightwatch && chown -R nightwatch:nightwatch /app
USER nightwatch

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8080}/health || exit 1

# Default port
EXPOSE 8080

# Default: start the FastAPI server
# Override CMD to run different modes:
#   docker run nightwatch python -m pytest        # Run tests
#   docker run nightwatch python -c "..."          # One-off scripts
CMD ["python", "-m", "src.api.main"]
