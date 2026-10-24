# PAM Rate Board — API / worker image.
#
# One image serves both roles; docker-compose overrides the command for the
# worker. Build context is the repository root so .dockerignore applies:
#   docker build -f backend/Dockerfile -t pam-rate-board .

FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# libgl1 + libglib2.0-0: OpenCV. ffmpeg: MP4 encoding (imageio-ffmpeg ships a
# binary, but the system one is used when present and is smaller overall).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        ffmpeg \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY backend/ /app/

# Storage is a volume in compose; create it so a bare `docker run` still works.
RUN mkdir -p /data/storage
ENV STORAGE_DIR=/data/storage

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# Entry point moved from the old flat main:app to the application package.
# Production runs without --reload.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
