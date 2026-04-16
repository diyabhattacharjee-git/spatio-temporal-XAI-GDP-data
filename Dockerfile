# =============================================================================
# EconXAI Dashboard — Dockerfile
# Works with: Render, Railway, Fly.io, Google Cloud Run, any Docker host
# =============================================================================

FROM python:3.11-slim

# System deps needed by some Python packages (scipy, shap, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer-cached)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app files
COPY . .

# Streamlit uses port 8501 by default
EXPOSE 8501

# Health-check so Render/Railway know the container is ready
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Run the app
ENTRYPOINT ["streamlit", "run", "app.py", \
    "--server.port=8501", \
    "--server.address=0.0.0.0", \
    "--server.headless=true", \
    "--browser.gatherUsageStats=false"]
