FROM python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/HimanM/DropForge" \
      org.opencontainers.image.title="DropForge" \
      org.opencontainers.image.description="Self-hosted Twitch drops miner with an authenticated web UI"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TDMINER_DATA_DIR=/data \
    TDMINER_BROWSER=/usr/bin/chromium \
    TDMINER_HOST=0.0.0.0 \
    TDMINER_PORT=17473

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium xvfb ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-web.txt ./
RUN pip install --no-cache-dir -r requirements-web.txt

COPY . .
RUN chmod +x docker/entrypoint.sh && mkdir -p /data

VOLUME ["/data"]
EXPOSE 17473

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:17473/healthz', timeout=3)"

ENTRYPOINT ["/app/docker/entrypoint.sh"]
