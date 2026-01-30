"""
WebSocket endpoints for real-time updates
Uses PostgreSQL NOTIFY/LISTEN for push notifications
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Set
import asyncio
import json
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections and broadcasts"""
    
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.listener_task = None
    
    async def connect(self, websocket: WebSocket):
        """Accept new WebSocket connection"""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")
        
        # Start PostgreSQL listener if not already running
        if not self.listener_task and len(self.active_connections) == 1:
            self.listener_task = asyncio.create_task(self._listen_postgres_notifications())
    
    def disconnect(self, websocket: WebSocket):
        """Remove WebSocket connection"""
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")
        
        # Stop listener if no more connections
        if len(self.active_connections) == 0 and self.listener_task:
            self.listener_task.cancel()
            self.listener_task = None
    
    async def broadcast(self, message: dict):
        """Send message to all connected clients"""
        if not self.active_connections:
            return
        
        message_json = json.dumps(message)
        disconnected = set()
        
        for connection in self.active_connections:
            try:
                await connection.send_text(message_json)
            except Exception as e:
                logger.error(f"Error sending to WebSocket: {e}")
                disconnected.add(connection)
        
        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)
    
    async def _listen_postgres_notifications(self):
        """
        Listen to PostgreSQL NOTIFY events and broadcast to WebSocket clients.
        Only runs when using PostgreSQL.
        """
        from core.database import engine
        
        # Check if PostgreSQL
        if 'postgresql' not in str(engine.url):
            logger.info("SQLite detected - WebSocket notifications disabled")
            return
        
        try:
            import asyncpg
            
            # Extract connection details from SQLAlchemy engine
            url = engine.url
            
            # Create asyncpg connection for LISTEN
            conn = await asyncpg.connect(
                host=url.host,
                port=url.port or 5432,
                user=url.username,
                password=url.password,
                database=url.database
            )
            
            logger.info("🔔 PostgreSQL LISTEN started for real-time notifications")
            
            # Set up listeners for different channels
            await conn.add_listener('telemetry_update', self._handle_telemetry_notification)
            await conn.add_listener('miner_update', self._handle_miner_notification)
            
            # Keep connection alive
            while self.active_connections:
                await asyncio.sleep(1)
            
            # Cleanup
            await conn.remove_listener('telemetry_update', self._handle_telemetry_notification)
            await conn.remove_listener('miner_update', self._handle_miner_notification)
            await conn.close()
            
            logger.info("🔕 PostgreSQL LISTEN stopped")
            
        except ImportError:
            logger.warning("asyncpg not installed - PostgreSQL NOTIFY/LISTEN unavailable")
        except Exception as e:
            logger.error(f"PostgreSQL LISTEN error: {e}")
    
    def _handle_telemetry_notification(self, connection, pid, channel, payload):
        """Handle telemetry_update notifications"""
        try:
            data = json.loads(payload)
            asyncio.create_task(self.broadcast({
                "type": "telemetry_update",
                "data": data
            }))
        except Exception as e:
            logger.error(f"Error handling telemetry notification: {e}")
    
    def _handle_miner_notification(self, connection, pid, channel, payload):
        """Handle miner_update notifications"""
        try:
            data = json.loads(payload)
            asyncio.create_task(self.broadcast({
                "type": "miner_update",
                "data": data
            }))
        except Exception as e:
            logger.error(f"Error handling miner notification: {e}")


# Global connection manager
manager = ConnectionManager()


@router.websocket("/ws/updates")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time dashboard updates.
    
    Receives push notifications from PostgreSQL NOTIFY triggers:
    - telemetry_update: New telemetry data inserted
    - miner_update: Miner state/mode changed
    
    Message format:
    {
        "type": "telemetry_update" | "miner_update",
        "data": {...}
    }
    """
    await manager.connect(websocket)
    
    try:
        # Keep connection alive and handle client messages
        while True:
            # Wait for client messages (ping/pong for keepalive)
            data = await websocket.receive_text()
            
            # Handle ping
            if data == "ping":
                await websocket.send_text("pong")
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)
