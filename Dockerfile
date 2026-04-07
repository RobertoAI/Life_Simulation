# ---- Stage 1: Build ----
FROM python:3.12-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- Stage 2: Runtime ----
FROM python:3.12-slim

LABEL maintainer="Roberto Pagano <robertopagano2011@gmail.com>"
LABEL description="AI Life Simulator - Real-time agent simulation with GPU monitoring"

WORKDIR /app

# Copy installed dependencies from builder
COPY --from=builder /install /usr/local

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

# Copy application code
COPY --chown=appuser:appuser . .

# Create data directory for persistent storage
RUN mkdir -p /app/data && chown appuser:appuser /app/data

# Health check
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/simulation/status')" || exit 1

EXPOSE 8000

USER appuser

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
