FROM python:3.13.17-slim

WORKDIR /fts

# Dependencies are installed before the application source so edits to
# the app do not rebuild the package layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 1000 appuser

COPY . .

# The process writes the local database and exports under /fts/data.
# Secrets are not copied into the image; pass them at runtime:
#   docker run --env-file .env -p 8501:8501 -v "$PWD/data:/fts/data" <image>
# The process runs as uid 1000. A bind-mounted data directory must be
# writable by that user (chown 1000:1000 on the host). A Docker-managed
# volume is created root-owned and is not writable until it is chowned.
RUN mkdir -p /fts/data \
    && chown -R appuser:appuser /fts

VOLUME ["/fts/data"]

USER appuser

EXPOSE 8501

# Headless: the container must not try to open a browser.
ENV STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=3)"]

CMD ["streamlit", "run", "./fTrees.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
