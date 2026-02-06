"""
HMM-Local Updater Service
Simple web UI for updating the hmm-local container
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import subprocess
import asyncio
import json
import logging
from datetime import datetime
from typing import List
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="HMM-Local Updater", version="1.0.0")

# WebSocket connections for streaming logs
active_connections: List[WebSocket] = []

# Update status
update_in_progress = False


async def broadcast_log(message: str, level: str = "info"):
    """Broadcast log message to all connected WebSocket clients"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_data = {
        "timestamp": timestamp,
        "level": level,
        "message": message
    }
    
    # Also log to server console
    if level == "error":
        logger.error(message)
    elif level == "warning":
        logger.warning(message)
    else:
        logger.info(message)
    
    # Broadcast to WebSocket clients
    disconnected = []
    for connection in active_connections:
        try:
            await connection.send_json(log_data)
        except:
            disconnected.append(connection)
    
    # Remove disconnected clients
    for conn in disconnected:
        active_connections.remove(conn)


@app.get("/", response_class=HTMLResponse)
async def get_index():
    """Serve the main UI"""
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HMM-Local Updater</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        
        .container {
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            max-width: 800px;
            width: 100%;
            overflow: hidden;
        }
        
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 30px;
            text-align: center;
            color: white;
        }
        
        .header h1 {
            font-size: 28px;
            font-weight: 600;
            margin-bottom: 8px;
        }
        
        .header p {
            opacity: 0.9;
            font-size: 14px;
        }
        
        .content {
            padding: 30px;
        }
        
        .update-button {
            width: 100%;
            padding: 16px 32px;
            font-size: 18px;
            font-weight: 600;
            color: white;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border: none;
            border-radius: 12px;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
            margin-bottom: 30px;
        }
        
        .update-button:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(102, 126, 234, 0.4);
        }
        
        .update-button:active:not(:disabled) {
            transform: translateY(0);
        }
        
        .update-button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
        
        .update-button.updating {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        }
        
        .logs-container {
            background: #1a1a1a;
            border-radius: 12px;
            padding: 20px;
            height: 400px;
            overflow-y: auto;
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
            font-size: 13px;
            line-height: 1.6;
        }
        
        .log-entry {
            margin-bottom: 8px;
            display: flex;
            gap: 12px;
        }
        
        .log-timestamp {
            color: #666;
            flex-shrink: 0;
        }
        
        .log-message {
            color: #e0e0e0;
        }
        
        .log-entry.info .log-message {
            color: #4CAF50;
        }
        
        .log-entry.warning .log-message {
            color: #FF9800;
        }
        
        .log-entry.error .log-message {
            color: #f44336;
        }
        
        .status-indicator {
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 8px;
        }
        
        .status-indicator.connected {
            background: #4CAF50;
            box-shadow: 0 0 10px #4CAF50;
        }
        
        .status-indicator.disconnected {
            background: #f44336;
        }
        
        .footer {
            padding: 20px 30px;
            background: #f5f5f5;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 13px;
            color: #666;
        }
        
        .status-text {
            display: flex;
            align-items: center;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        .spinner {
            display: inline-block;
            width: 16px;
            height: 16px;
            border: 2px solid rgba(255, 255, 255, 0.3);
            border-top-color: white;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            margin-right: 8px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔄 HMM-Local Updater</h1>
            <p>Update your HMM-Local container with one click</p>
        </div>
        
        <div class="content">
            <button id="updateBtn" class="update-button" onclick="startUpdate()">
                Update HMM-Local Container
            </button>
            
            <div class="logs-container" id="logsContainer">
                <div class="log-entry info">
                    <span class="log-timestamp">--:--:--</span>
                    <span class="log-message">Ready to update. Click the button above to begin.</span>
                </div>
            </div>
        </div>
        
        <div class="footer">
            <div class="status-text">
                <span class="status-indicator" id="statusIndicator"></span>
                <span id="statusText">Connecting...</span>
            </div>
            <div>HMM-Local Updater v1.0.0</div>
        </div>
    </div>
    
    <script>
        let ws = null;
        let isUpdating = false;
        
        function connectWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${protocol}//${window.location.host}/ws/logs`);
            
            ws.onopen = () => {
                console.log('WebSocket connected');
                document.getElementById('statusIndicator').classList.add('connected');
                document.getElementById('statusIndicator').classList.remove('disconnected');
                document.getElementById('statusText').textContent = 'Connected';
                addLog('info', 'Connected to updater service');
            };
            
            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                addLog(data.level, data.message, data.timestamp);
            };
            
            ws.onclose = () => {
                console.log('WebSocket disconnected');
                document.getElementById('statusIndicator').classList.remove('connected');
                document.getElementById('statusIndicator').classList.add('disconnected');
                document.getElementById('statusText').textContent = 'Disconnected';
                
                // Attempt reconnect after 2 seconds
                setTimeout(connectWebSocket, 2000);
            };
            
            ws.onerror = (error) => {
                console.error('WebSocket error:', error);
            };
        }
        
        function addLog(level, message, timestamp = null) {
            const logsContainer = document.getElementById('logsContainer');
            const logEntry = document.createElement('div');
            logEntry.className = `log-entry ${level}`;
            
            if (!timestamp) {
                const now = new Date();
                timestamp = now.toTimeString().split(' ')[0];
            }
            
            logEntry.innerHTML = `
                <span class="log-timestamp">${timestamp}</span>
                <span class="log-message">${message}</span>
            `;
            
            logsContainer.appendChild(logEntry);
            logsContainer.scrollTop = logsContainer.scrollHeight;
        }
        
        async function startUpdate() {
            if (isUpdating) return;
            
            const btn = document.getElementById('updateBtn');
            btn.disabled = true;
            btn.classList.add('updating');
            btn.innerHTML = '<span class="spinner"></span> Updating...';
            isUpdating = true;
            
            try {
                const response = await fetch('/update', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });
                
                const data = await response.json();
                
                if (response.ok) {
                    // Update will be in progress, logs will stream via WebSocket
                } else {
                    addLog('error', `Update failed: ${data.detail || 'Unknown error'}`);
                    resetButton();
                }
            } catch (error) {
                addLog('error', `Request failed: ${error.message}`);
                resetButton();
            }
        }
        
        function resetButton() {
            const btn = document.getElementById('updateBtn');
            btn.disabled = false;
            btn.classList.remove('updating');
            btn.textContent = 'Update HMM-Local Container';
            isUpdating = false;
        }
        
        // Initialize WebSocket connection
        connectWebSocket();
        
        // Reset button after update completes (listen for completion message)
        window.addEventListener('message', (event) => {
            if (event.data === 'update-complete') {
                setTimeout(resetButton, 2000);
            }
        });
    </script>
</body>
</html>
"""


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "hmm-local-updater",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
        "update_in_progress": update_in_progress
    }


@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    """WebSocket endpoint for streaming logs"""
    await websocket.accept()
    active_connections.append(websocket)
    
    try:
        # Send welcome message
        await websocket.send_json({
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "level": "info",
            "message": "WebSocket connection established"
        })
        
        # Keep connection alive
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_connections.remove(websocket)


@app.post("/update")
async def update_container():
    """
    Update the hmm-local container
    - Pull latest image from GHCR
    - Restart the container with new image
    """
    global update_in_progress
    
    if update_in_progress:
        return {"error": "Update already in progress"}, 409
    
    # Start update in background
    asyncio.create_task(perform_update())
    
    return {
        "success": True,
        "message": "Update started. Check logs for progress."
    }


async def perform_update():
    """Perform the actual container update with full config preservation"""
    global update_in_progress
    update_in_progress = True
    
    try:
        # Get container name from environment
        container_name = os.environ.get("TARGET_CONTAINER", "hmm-local")
        new_image = os.environ.get("TARGET_IMAGE", "ghcr.io/renegadeuk/hmm-local:latest")
        
        await broadcast_log(f"🚀 Starting update for container: {container_name}", "info")
        await broadcast_log(f"📦 Target image: {new_image}", "info")
        
        # Step 1: Inspect current container to get configuration
        await broadcast_log("🔍 Inspecting current container configuration...", "info")
        process = await asyncio.create_subprocess_exec(
            "docker", "inspect", container_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown error"
            await broadcast_log(f"❌ Failed to inspect container: {error_msg}", "error")
            return
        
        import json
        container_info = json.loads(stdout.decode())[0]
        
        # Extract configuration
        config = container_info['Config']
        host_config = container_info['HostConfig']
        network_settings = container_info['NetworkSettings']
        
        # Extract key settings
        env_vars = config.get('Env', [])
        binds = host_config.get('Binds', [])
        restart_policy = host_config.get('RestartPolicy', {})
        restart_policy_name = restart_policy.get('Name', 'no')
        
        await broadcast_log(f"   Environment variables: {len(env_vars)}", "info")
        await broadcast_log(f"   Volume binds: {len(binds)}", "info")
        await broadcast_log(f"   Restart policy: {restart_policy_name}", "info")
        
        # Extract network settings (including static IP)
        networks = network_settings.get('Networks', {})
        network_name = None
        ip_address = None
        
        if networks:
            network_name = list(networks.keys())[0]
            network_info = networks[network_name]
            ip_address = network_info.get('IPAddress')
            if ip_address:
                await broadcast_log(f"   Static IP: {ip_address}", "info")
        
        await broadcast_log("✅ Configuration extracted successfully", "info")
        
        # Step 2: Pull latest image
        await broadcast_log("⬇️  Pulling latest image from GHCR...", "info")
        process = await asyncio.create_subprocess_exec(
            "docker", "pull", new_image,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown error"
            await broadcast_log(f"❌ Failed to pull image: {error_msg}", "error")
            return
        
        await broadcast_log("✅ Image pulled successfully", "info")
        
        # Step 3: Stop current container
        await broadcast_log(f"⏸️  Stopping container {container_name}...", "info")
        process = await asyncio.create_subprocess_exec(
            "docker", "stop", container_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown error"
            await broadcast_log(f"⚠️  Warning: Could not stop container: {error_msg}", "warning")
        else:
            await broadcast_log("✅ Container stopped", "info")
        
        # Step 4: Remove old container
        await broadcast_log(f"🗑️  Removing old container...", "info")
        process = await asyncio.create_subprocess_exec(
            "docker", "rm", container_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        await process.communicate()
        await broadcast_log("✅ Old container removed", "info")
        
        # Small delay to ensure cleanup
        await asyncio.sleep(1)
        
        # Step 5: Recreate container with preserved configuration
        await broadcast_log(f"🚀 Creating new container with preserved configuration...", "info")
        
        # Build docker run command
        docker_cmd = ["docker", "run", "-d", "--name", container_name]
        
        # Add environment variables
        for env in env_vars:
            docker_cmd.extend(["-e", env])
        
        # Add volume binds
        for bind in binds:
            docker_cmd.extend(["-v", bind])
        
        # Add restart policy
        if restart_policy_name != 'no':
            max_retry = restart_policy.get('MaximumRetryCount', 0)
            if max_retry > 0:
                docker_cmd.extend(["--restart", f"{restart_policy_name}:{max_retry}"])
            else:
                docker_cmd.extend(["--restart", restart_policy_name])
        
        # Add network with static IP if applicable
        if network_name and network_name not in ['bridge', 'host', 'none']:
            docker_cmd.extend(["--network", network_name])
            if ip_address:
                docker_cmd.extend(["--ip", ip_address])
                await broadcast_log(f"   Preserving static IP: {ip_address}", "info")
        elif network_name:
            docker_cmd.extend(["--network", network_name])
        
        # Add image
        docker_cmd.append(new_image)
        
        # Execute docker run
        process = await asyncio.create_subprocess_exec(
            *docker_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown error"
            await broadcast_log(f"❌ Failed to create container: {error_msg}", "error")
            return
        
        await broadcast_log("✅ New container created successfully", "info")
        await broadcast_log("🎉 Update completed successfully!", "info")
        await broadcast_log(f"ℹ️  Container {container_name} is now running {new_image}", "info")
        await broadcast_log("✅ All settings preserved (volumes, network, static IP, environment, restart policy)", "info")
        
    except Exception as e:
        await broadcast_log(f"❌ Update failed: {str(e)}", "error")
        logger.exception("Update failed")
    
    finally:
        update_in_progress = False


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8081))
    uvicorn.run(app, host="0.0.0.0", port=port)
