FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /radio

COPY app ./app
COPY requirements.txt ./

ENV RADIO_BASE_DIR=/radio \
    RADIO_AUDIO_DIR=/radio/audio \
    RADIO_PUBLIC_DIR=/radio/public \
    RADIO_HLS_DIR=/radio/public/hls \
    RADIO_HOST=0.0.0.0 \
    RADIO_PORT=8000 \
    RADIO_WEB_PORT=8001

EXPOSE 8000 8001

CMD ["python", "-m", "app.main"]
