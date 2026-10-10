FROM python:3.12-slim

# ffmpeg is required for audio extraction / rendering
# fonts-noto-core ships Noto Sans Myanmar so Burmese subtitles render correctly
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY frontend ./frontend

ENV HOST=0.0.0.0 \
    DATA_DIR=/app/data \
    PORT=7860

EXPOSE 7860

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
