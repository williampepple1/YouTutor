FROM python:3.12-slim

WORKDIR /app

# Fix SSL issues: upgrade OpenSSL and CA certificates
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssl \
    ca-certificates \
    curl \
    ffmpeg \
    && update-ca-certificates --fresh \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY . .

# Expose the port (HF Spaces expects 7860)
EXPOSE 7860

# Use $PORT env var (set by HF Spaces to 7860, or override with docker-compose)
CMD uvicorn backend:app --host 0.0.0.0 --port ${PORT:-7860}
