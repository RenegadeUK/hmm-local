#!/bin/bash
# Start MQTT broker in background
if [ -f /config/mosquitto/mosquitto.conf ]; then
    echo "🚀 Starting Mosquitto MQTT broker..."
    mosquitto -c /config/mosquitto/mosquitto.conf -d
    echo "✅ Mosquitto started"
else
    echo "⚠️ No mosquitto config found, MQTT broker not started"
fi

# Start the main application
echo "🚀 Starting Home Miner Manager..."
uvicorn main:app --host 0.0.0.0 --port ${WEB_PORT}
