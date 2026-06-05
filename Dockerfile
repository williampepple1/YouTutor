FROM python:3.12-slim

WORKDIR /app

# Install runtime deps (yt-dlp needs ffmpeg for some features)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY . .

# Expose the port
EXPOSE 8080

# Run with uvicorn directly (no venv needed in Docker)
CMD ["uvicorn", "backend:app", "--host", "0.0.0.0", "--port", "8080"]
