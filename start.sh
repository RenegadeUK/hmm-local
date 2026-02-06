#!/bin/bash
# v0 Miner Controller - Quick Start Script

set -e

echo "🚀 v0 Miner Controller - Quick Start"
echo "===================================="
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Create .env if it doesn't exist
if [ ! -f .env ]; then
    echo "📝 Creating .env file from .env.example..."
    cp .env.example .env
    echo "✅ .env file created"
fi

# Create config directory if it doesn't exist
if [ ! -d config ]; then
    echo "📁 Creating config directory..."
    mkdir -p config
    echo "✅ Config directory created"
fi

# Build and start containers
echo ""
echo "🐳 Building Docker container..."
# Get current git commit and branch for version info
export GIT_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
export GIT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")
docker-compose build

echo ""
echo "🚀 Starting v0 Miner Controller..."
docker-compose up -d

# Wait for container to be ready
echo ""
echo "⏳ Waiting for service to start..."
sleep 5

# Check if service is running
if docker-compose ps | grep -q "Up"; then
    echo ""
    echo "✅ v0 Miner Controller is running!"
    echo ""
    echo "📊 Dashboard: http://localhost:8080"
    echo "📚 API Docs:  http://localhost:8080/docs"
    echo ""
    echo "To view logs:    docker-compose logs -f"
    echo "To stop:         docker-compose down"
    echo "To restart:      docker-compose restart"
else
    echo ""
    echo "❌ Failed to start service. Check logs with:"
    echo "   docker-compose logs"
fi
