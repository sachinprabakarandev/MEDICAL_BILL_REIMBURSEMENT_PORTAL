FROM python:3.12-slim

# pdfplumber/Pillow need these; the Swift OCR helper is macOS-only and is not
# used in this image (extraction falls back to pdfplumber + regex).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libjpeg62-turbo \
        zlib1g \
        libfreetype6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY frontend/ frontend/
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# main.py resolves templates/static as ../../frontend from app/, so the working
# directory must be backend/ and the tree layout must be preserved.
WORKDIR /app/backend

# Mount a persistent volume here in production — the SQLite DB and uploaded
# bills live in this directory and are otherwise lost on every redeploy.
VOLUME ["/app/backend/app/data"]

ENV PYTHONUNBUFFERED=1 \
    PORT=8000

EXPOSE 8000

CMD ["docker-entrypoint.sh"]
