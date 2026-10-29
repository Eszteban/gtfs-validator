# ==========================================
# Stage 1: Builder
# ==========================================
FROM python:3.12-slim AS builder

WORKDIR /build

# Avoid writing .pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Create virtual environment to isolate installed dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install application dependencies into the virtual environment
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt


# ==========================================
# Stage 2: Runner (Minimal & Hardened)
# ==========================================
FROM python:3.12-slim AS runner

# Security & environment hardening
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    UPLOAD_DIR="/app/uploads" \
    DATABASE_URL="sqlite:////app/data/gtfs_validator.db"

# Create unprivileged system group and user (appuser: UID/GID 10001)
RUN groupadd --system --gid 10001 appuser && \
    useradd --system --uid 10001 --gid 10001 --no-create-home --home-dir /app appuser

WORKDIR /app

# Prepare writable directories for SQLite database and uploaded GTFS archives
RUN mkdir -p /app/data /app/uploads && \
    chown -R appuser:appuser /app

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv

# Copy application source code with non-root ownership
COPY --chown=appuser:appuser app/ ./app/

# Switch to unprivileged user (UID: 10001)
USER 10001:10001

EXPOSE 8000

# Health check using Python's standard library to avoid installing curl and introducing CVEs
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').getcode() == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

