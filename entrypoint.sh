#!/bin/bash
# Start the main application
echo "🚀 Starting Home Miner Manager..."
uvicorn main:app --host 0.0.0.0 --port ${WEB_PORT}
