FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

ENV APP_ENV=production
ENV DEMO_MODE=false
ENV APP_HOST=0.0.0.0
ENV APP_PORT=8620
ENV MAX_FILE_SIZE_MB=25
ENV ALLOWED_FILE_EXTENSIONS=.uff
ENV STALE_PROCESSING_MINUTES=30
ENV APP_VERSION=1.0.0

WORKDIR /app

RUN groupadd --system appgroup \
    && useradd \
        --system \
        --gid appgroup \
        --create-home \
        appuser

COPY requirements.txt /app/requirements.txt

RUN python -m pip install \
        --no-cache-dir \
        --requirement /app/requirements.txt

COPY . /app

RUN mkdir -p /app/data \
    && chown -R appuser:appgroup /app

USER appuser

EXPOSE 8620

VOLUME ["/app/data"]

HEALTHCHECK \
    --interval=30s \
    --timeout=5s \
    --start-period=20s \
    --retries=3 \
    CMD python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8620/health/ready', timeout=4)"

CMD ["python", "start_server.py"]