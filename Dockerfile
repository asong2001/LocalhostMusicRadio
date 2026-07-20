FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /radio

LABEL org.opencontainers.image.title="MusicRadio" \
      org.opencontainers.image.description="Local music radio service with HLS, MP3, M3U playlist, and web management." \
      org.opencontainers.image.source="https://github.com/asong2001/LocalhostMusicRadio" \
      org.opencontainers.image.licenses="MIT"

COPY app ./app
COPY requirements.txt ./

RUN mkdir -p /radio/audio /radio/public/hls /radio/config \
    && if [ -s requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi

ENV RADIO_BASE_DIR=/radio \
    RADIO_AUDIO_DIR=/radio/audio \
    RADIO_PUBLIC_DIR=/radio/public \
    RADIO_HLS_DIR=/radio/public/hls \
    RADIO_CONFIG_PATH=/radio/config/radio.json \
    RADIO_HOST=0.0.0.0 \
    RADIO_PORT=8000 \
    RADIO_WEB_PORT=8001 \
    PYTHONUNBUFFERED=1

EXPOSE 8000 8001

VOLUME ["/radio/audio", "/radio/public", "/radio/config"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/status' % os.getenv('RADIO_PORT', '8000'), timeout=3).read()" || exit 1

CMD ["python", "-m", "app.main"]
