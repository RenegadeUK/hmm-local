"""
MQTT client for telemetry export
"""
import json
import asyncio
from typing import Optional
import paho.mqtt.client as mqtt_lib
from core.config import app_config


class MQTTClient:
    """MQTT client wrapper"""
    
    def __init__(self):
        self.client: Optional[mqtt_lib.Client] = None
        self.connected = False
        self.enabled = False
    
    async def start(self):
        """Start MQTT client if enabled"""
        self.enabled = app_config.get("mqtt.enabled", False)
        
        if not self.enabled:
            print("📡 MQTT disabled in config")
            return
        
        broker = app_config.get("mqtt.broker", "localhost")
        port = app_config.get("mqtt.port", 1883)
        username = app_config.get("mqtt.username", "")
        password = app_config.get("mqtt.password", "")
        
        self.client = mqtt_lib.Client()
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        
        # Set username/password if provided
        if username:
            self.client.username_pw_set(username, password)
        
        try:
            self.client.connect(broker, port, 60)
            self.client.loop_start()
            print(f"📡 MQTT client connected to {broker}:{port}")
        except Exception as e:
            print(f"❌ Failed to connect to MQTT broker: {e}")
            self.enabled = False
    
    async def stop(self):
        """Stop MQTT client"""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
    
    def _on_connect(self, client, userdata, flags, rc):
        """MQTT connection callback"""
        if rc == 0:
            self.connected = True
            print("📡 MQTT connected")
        else:
            print(f"❌ MQTT connection failed with code {rc}")
    
    def _on_disconnect(self, client, userdata, rc):
        """MQTT disconnection callback"""
        self.connected = False
        print("📡 MQTT disconnected")
    
    def publish(self, topic: str, payload: dict):
        """Publish message to MQTT topic"""
        if not self.enabled or not self.connected:
            return
        
        topic_prefix = app_config.get("mqtt.topic_prefix", "miner")
        full_topic = f"{topic_prefix}/{topic}"
        
        try:
            self.client.publish(full_topic, json.dumps(payload))
        except Exception as e:
            print(f"❌ Failed to publish to MQTT: {e}")


mqtt_client = MQTTClient()
