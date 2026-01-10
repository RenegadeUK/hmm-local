FROM python:3.11-slim

# Build argument for git commit hash
ARG GIT_COMMIT=unknown

# Set working directory
WORKDIR /app

# Install system dependencies including mosquitto
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    git \
    nano \
    librsvg2-bin \
    mosquitto \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ /app/

# Write git commit to file (use first 7 chars for short hash)
RUN echo "${GIT_COMMIT}" | cut -c1-7 > /app/.git_commit

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create config directory
RUN mkdir -p /config

# Environment variables with defaults
ENV WEB_PORT=8080 \
    TZ=UTC \
    PUID=1000 \
    PGID=1000

# Expose web port
EXPOSE ${WEB_PORT}

# Use entrypoint script
CMD ["/entrypoint.sh"]
