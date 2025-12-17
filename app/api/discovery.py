"""
Network Discovery API Endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from pydantic import BaseModel
import logging

from core.database import get_db, Miner, Event
from core.discovery import MinerDiscoveryService
from core.config import app_config

logger = logging.getLogger(__name__)

router = APIRouter()


class NetworkRange(BaseModel):
    """Model for a network range"""
    cidr: str
    name: Optional[str] = None


class DiscoveryConfig(BaseModel):
    """Model for discovery configuration"""
    enabled: bool
    auto_add: bool
    networks: List[NetworkRange]
    scan_interval_hours: int = 24


class DiscoveryRequest(BaseModel):
    """Request model for discovery scan"""
    network_cidr: Optional[str] = None
    timeout: float = 2.0


class DiscoveredMiner(BaseModel):
    """Model for discovered miner"""
    ip: str
    port: int
    type: str
    name: str
    details: dict
    already_added: bool = False


class DiscoveryResponse(BaseModel):
    """Response model for discovery scan"""
    total_found: int
    new_miners: int
    existing_miners: int
    miners: List[DiscoveredMiner]


@router.post("/discovery/scan", response_model=DiscoveryResponse)
async def scan_network(
    request: DiscoveryRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Scan the local network for mining hardware
    
    Returns list of discovered miners with indication of which are already added
    """
    # Perform discovery scan
    discovered = await MinerDiscoveryService.discover_miners(
        network_cidr=request.network_cidr,
        timeout=request.timeout
    )
    
    # Get existing miners from database
    result = await db.execute(select(Miner))
    existing_miners = result.scalars().all()
    
    # Create a set of IP addresses for existing miners (ignore port for matching)
    # Some miners may have null ports, and port can vary (80, 8080, 4028)
    existing_ips = {
        m.ip_address for m in existing_miners if m.ip_address
    }
    
    # Mark which miners are already added
    response_miners = []
    new_count = 0
    existing_count = 0
    
    for miner in discovered:
        # Check if this IP is already in the database (ignore port)
        is_existing = miner['ip'] in existing_ips
        
        response_miners.append(DiscoveredMiner(
            ip=miner['ip'],
            port=miner['port'],
            type=miner['type'],
            name=miner['name'],
            details=miner['details'],
            already_added=is_existing
        ))
        
        if is_existing:
            existing_count += 1
        else:
            new_count += 1
    
    return DiscoveryResponse(
        total_found=len(discovered),
        new_miners=new_count,
        existing_miners=existing_count,
        miners=response_miners
    )


@router.post("/discovery/verify/{miner_id}")
async def verify_miner(
    miner_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Verify that a miner is still reachable at its configured address
    """
    result = await db.execute(select(Miner).where(Miner.id == miner_id))
    miner = result.scalar_one_or_none()
    
    if not miner:
        raise HTTPException(status_code=404, detail="Miner not found")
    
    if not miner.ip_address:
        raise HTTPException(status_code=400, detail="Miner has no IP address configured")
    
    is_reachable = await MinerDiscoveryService.verify_miner_connection(
        miner_type=miner.type,
        ip=miner.ip_address,
        port=miner.port
    )
    
    return {
        "miner_id": miner_id,
        "miner_name": miner.name,
        "ip_address": miner.ip_address,
        "port": miner.port,
        "is_reachable": is_reachable
    }


@router.get("/discovery/network-info")
async def get_network_info():
    """
    Get auto-detected network information
    """
    network_cidr = MinerDiscoveryService._get_local_network()
    
    if not network_cidr:
        raise HTTPException(status_code=500, detail="Could not determine local network")
    
    return {
        "network_cidr": network_cidr,
        "description": "Auto-detected local network range"
    }


@router.get("/discovery/config", response_model=DiscoveryConfig)
async def get_discovery_config():
    """Get current discovery configuration"""
    config = app_config.get("network_discovery", {})
    
    networks = config.get("networks", [])
    # Convert to NetworkRange objects
    network_ranges = [
        NetworkRange(cidr=n["cidr"], name=n.get("name"))
        if isinstance(n, dict) else NetworkRange(cidr=n)
        for n in networks
    ]
    
    return DiscoveryConfig(
        enabled=config.get("enabled", False),
        auto_add=config.get("auto_add", False),
        networks=network_ranges,
        scan_interval_hours=config.get("scan_interval_hours", 24)
    )


@router.post("/discovery/config")
async def update_discovery_config(config: DiscoveryConfig):
    """Update discovery configuration"""
    from core.scheduler import scheduler
    
    # Convert NetworkRange objects to dicts
    networks_data = [
        {"cidr": n.cidr, "name": n.name}
        for n in config.networks
    ]
    
    app_config.set("network_discovery.enabled", config.enabled)
    app_config.set("network_discovery.auto_add", config.auto_add)
    app_config.set("network_discovery.networks", networks_data)
    app_config.set("network_discovery.scan_interval_hours", config.scan_interval_hours)
    
    # Update scheduler interval
    if scheduler:
        scheduler._update_discovery_schedule()
    
    logger.info(f"Discovery config updated: enabled={config.enabled}, auto_add={config.auto_add}, networks={len(config.networks)}, interval={config.scan_interval_hours}h")
    
    return {"message": "Configuration updated successfully"}


@router.post("/discovery/scan-network")
async def scan_specific_network(
    network_cidr: str = Query(..., description="Network CIDR to scan (e.g., 192.168.1.0/24)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Scan a specific network range
    
    This is for manual one-off scans
    """
    logger.info(f"Manual scan requested for network: {network_cidr}")
    
    # Perform discovery scan
    discovered = await MinerDiscoveryService.discover_miners(
        network_cidr=network_cidr,
        timeout=2.0
    )
    
    # Get existing miners from database
    result = await db.execute(select(Miner))
    existing_miners = result.scalars().all()
    
    # Create a set of (ip, port) tuples for existing miners
    existing_connections = {
        (m.ip_address, m.port) for m in existing_miners if m.ip_address
    }
    
    # Mark which miners are already added
    response_miners = []
    new_count = 0
    existing_count = 0
    
    for miner in discovered:
        is_existing = (miner['ip'], miner['port']) in existing_connections
        
        response_miners.append(DiscoveredMiner(
            ip=miner['ip'],
            port=miner['port'],
            type=miner['type'],
            name=miner['name'],
            details=miner['details'],
            already_added=is_existing
        ))
        
        if is_existing:
            existing_count += 1
        else:
            new_count += 1
    
    # Log event
    event = Event(
        event_type="info",
        source="network_discovery",
        message=f"Manual scan of {network_cidr}: found {len(discovered)} miners ({new_count} new)"
    )
    db.add(event)
    await db.commit()
    
    return DiscoveryResponse(
        total_found=len(discovered),
        new_miners=new_count,
        existing_miners=existing_count,
        miners=response_miners
    )


@router.post("/discovery/auto-scan")
async def trigger_auto_scan(db: AsyncSession = Depends(get_db)):
    """
    Trigger an immediate auto-discovery scan of all configured networks
    
    This respects auto_add setting
    """
    config = app_config.get("network_discovery", {})
    
    if not config.get("enabled", False):
        raise HTTPException(status_code=400, detail="Network discovery is not enabled")
    
    networks = config.get("networks", [])
    if not networks:
        raise HTTPException(status_code=400, detail="No networks configured for scanning")
    
    auto_add = config.get("auto_add", False)
    total_found = 0
    total_added = 0
    
    for network_config in networks:
        network_cidr = network_config["cidr"] if isinstance(network_config, dict) else network_config
        
        logger.info(f"Auto-scanning network: {network_cidr}")
        
        try:
            discovered = await MinerDiscoveryService.discover_miners(
                network_cidr=network_cidr,
                timeout=2.0
            )
            
            total_found += len(discovered)
            
            if auto_add:
                # Get existing miners
                result = await db.execute(select(Miner))
                existing_miners = result.scalars().all()
                existing_connections = {
                    (m.ip_address, m.port) for m in existing_miners if m.ip_address
                }
                
                # Add new miners
                for miner_data in discovered:
                    if (miner_data['ip'], miner_data['port']) not in existing_connections:
                        new_miner = Miner(
                            name=miner_data['name'],
                            type=miner_data['type'],
                            ip_address=miner_data['ip'],
                            port=miner_data['port'],
                            enabled=True
                        )
                        db.add(new_miner)
                        total_added += 1
                        logger.info(f"Auto-added miner: {miner_data['name']} at {miner_data['ip']}:{miner_data['port']}")
                
                await db.commit()
        
        except Exception as e:
            logger.error(f"Error scanning network {network_cidr}: {e}")
    
    # Log event
    event = Event(
        event_type="success" if total_found > 0 else "info",
        source="network_discovery",
        message=f"Auto-discovery scan complete: {total_found} miners found" + (f", {total_added} auto-added" if auto_add else "")
    )
    db.add(event)
    await db.commit()
    
    return {
        "total_found": total_found,
        "total_added": total_added if auto_add else 0,
        "auto_add_enabled": auto_add,
        "networks_scanned": len(networks)
    }
