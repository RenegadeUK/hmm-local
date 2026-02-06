#!/usr/bin/env python3
"""
HMM-Local Updater Service
Companion container that handles platform updates by recreating the main container
"""
from flask import Flask, request, jsonify
import docker
import logging
import sys
import time
from datetime import datetime

app = Flask(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# Initialize Docker client
try:
    docker_client = docker.from_env()
    logger.info("✅ Connected to Docker daemon")
except Exception as e:
    logger.error(f"❌ Failed to connect to Docker: {e}")
    sys.exit(1)


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "hmm-local-updater",
        "timestamp": datetime.utcnow().isoformat()
    })


@app.route('/update', methods=['POST'])
def update_container():
    """
    Update a container by recreating it with a new image
    
    POST body:
    {
        "container_name": "hmm-local",
        "new_image": "ghcr.io/renegadeuk/hmm-local:main-abc123"
    }
    """
    try:
        data = request.get_json()
        container_name = data.get('container_name')
        new_image = data.get('new_image')
        
        if not container_name or not new_image:
            return jsonify({
                "success": False,
                "error": "Missing container_name or new_image"
            }), 400
        
        logger.info(f"📦 Update request: {container_name} → {new_image}")
        
        # Step 1: Get current container configuration
        logger.info(f"🔍 Getting configuration for {container_name}")
        try:
            container = docker_client.containers.get(container_name)
        except docker.errors.NotFound:
            return jsonify({
                "success": False,
                "error": f"Container '{container_name}' not found"
            }), 404
        
        # Extract configuration
        config = container.attrs['Config']
        host_config = container.attrs['HostConfig']
        network_settings = container.attrs['NetworkSettings']
        
        # Build run parameters
        run_params = {
            'name': container_name,
            'detach': True,
            'environment': config.get('Env', []),
            'volumes': {},
            'network_mode': host_config.get('NetworkMode', 'bridge'),
            'restart_policy': host_config.get('RestartPolicy', {})
        }
        
        # Extract volumes
        binds = host_config.get('Binds', [])
        for bind in binds:
            parts = bind.split(':')
            if len(parts) >= 2:
                run_params['volumes'][parts[0]] = {
                    'bind': parts[1],
                    'mode': parts[2] if len(parts) > 2 else 'rw'
                }
        
        # Extract network settings (for static IP)
        networks = network_settings.get('Networks', {})
        network_name = None
        ip_address = None
        
        if networks:
            # Get first network (usually there's only one)
            network_name = list(networks.keys())[0]
            network_info = networks[network_name]
            ip_address = network_info.get('IPAddress')
        
        # Step 2: Stop container
        logger.info(f"⏹️  Stopping {container_name}")
        container.stop(timeout=30)
        
        # Step 3: Remove container
        logger.info(f"🗑️  Removing {container_name}")
        container.remove()
        
        # Small delay to ensure cleanup
        time.sleep(1)
        
        # Step 4: Pull new image
        logger.info(f"📥 Pulling image: {new_image}")
        docker_client.images.pull(new_image)
        
        # Step 5: Create new container
        logger.info(f"🚀 Starting new container with {new_image}")
        
        # If we have a specific network and IP, handle that
        if network_name and network_name not in ['bridge', 'host', 'none']:
            # Create with network and IP
            networking_config = docker_client.api.create_networking_config({
                network_name: docker_client.api.create_endpoint_config(
                    ipv4_address=ip_address if ip_address else None
                )
            })
            
            new_container = docker_client.api.create_container(
                image=new_image,
                name=container_name,
                environment=run_params['environment'],
                host_config=docker_client.api.create_host_config(
                    binds=binds,
                    restart_policy=run_params['restart_policy'],
                    network_mode=network_name
                ),
                networking_config=networking_config,
                detach=True
            )
            docker_client.api.start(new_container['Id'])
        else:
            # Simple creation (docker-compose style)
            new_container = docker_client.containers.run(
                image=new_image,
                **run_params
            )
        
        logger.info(f"✅ Update completed successfully")
        
        return jsonify({
            "success": True,
            "message": f"Container {container_name} updated to {new_image}",
            "container_id": new_container.id if hasattr(new_container, 'id') else new_container['Id'],
            "timestamp": datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        logger.error(f"❌ Update failed: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


if __name__ == '__main__':
    logger.info("🚀 Starting HMM-Local Updater Service on port 8081")
    app.run(host='0.0.0.0', port=8081)
