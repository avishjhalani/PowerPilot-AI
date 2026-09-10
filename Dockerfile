# Multi-stage Docker build for PowerPilot AI
# Stage 1: Build React 19 + Tailwind Frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# Stage 2: Production Python 3.11 Runtime
FROM python:3.11-slim

# Install system fonts for Unicode PDF report generation
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu-core \
    fonts-dejavu-extra \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Hugging Face Spaces runs as user 1000 by default
RUN useradd -m -u 1000 user
WORKDIR /app

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend, data, and server entrypoint
COPY backend/ ./backend/
COPY data/ ./data/
COPY server.py ./

# Copy compiled frontend static bundle
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Ensure runtime directories exist and grant permissions to UID 1000
RUN mkdir -p data/raw data/cleaned output/pbip output/reports && \
    chown -R user:user /app && \
    chmod -R 777 /app

USER user

# 7860 is the default port for Hugging Face Spaces
ENV PORT=7860
ENV HOST=0.0.0.0
EXPOSE 7860

CMD ["python", "server.py"]
