"""
Monero Solo Mining API Endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from core.database import get_db, MoneroSoloSettings
from core.monero_solo import MoneroSoloService
from core.monero_node import MoneroNodeRPC
from core.monero_wallet import MoneroWalletRPC

router = APIRouter()


class MoneroSoloSettingsUpdate(BaseModel):
    """Request model for updating Monero solo settings"""
    enabled: bool
    node_ip: Optional[str] = None
    node_port: int = 18081
    wallet_rpc_ip: Optional[str] = None
    wallet_rpc_port: int = 18083
    wallet_rpc_user: Optional[str] = None
    wallet_rpc_pass: Optional[str] = None


class MoneroSoloSettingsResponse(BaseModel):
    """Response model for Monero solo settings"""
    id: int
    enabled: bool
    pool_id: Optional[int]
    node_ip: Optional[str] = None
    node_port: Optional[int] = None
    wallet_rpc_ip: Optional[str]
    wallet_rpc_port: int
    wallet_rpc_user: Optional[str]
    wallet_rpc_pass: Optional[str]
    wallet_address: Optional[str]
    last_sync: Optional[datetime]
    
    class Config:
        from_attributes = True


class TestConnectionRequest(BaseModel):
    """Request model for testing RPC connections"""
    ip: str
    port: int


class TestNodeRequest(BaseModel):
    """Request model for testing node connections"""
    ip: str
    port: int


class TestWalletRequest(BaseModel):
    """Request model for testing wallet RPC connections"""
    ip: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None


class TestConnectionResponse(BaseModel):
    """Response model for connection tests"""
    success: bool
    message: str
    address: Optional[str] = None


@router.get("/settings/monero-solo", response_model=MoneroSoloSettingsResponse)
async def get_monero_solo_settings(db: AsyncSession = Depends(get_db)):
    """Get Monero solo mining settings"""
    from sqlalchemy import select
    from core.database import Pool
    
    service = MoneroSoloService(db)
    settings = await service.get_or_create_settings()
    
    # Build response with node info from pool
    response_dict = {
        "id": settings.id,
        "enabled": settings.enabled,
        "pool_id": settings.pool_id,
        "wallet_rpc_ip": settings.wallet_rpc_ip,
        "wallet_rpc_port": settings.wallet_rpc_port,
        "wallet_rpc_user": settings.wallet_rpc_user,
        "wallet_rpc_pass": settings.wallet_rpc_pass,
        "wallet_address": settings.wallet_address,
        "last_sync": settings.last_sync,
        "node_ip": None,
        "node_port": None
    }
    
    # Get node info from linked pool
    if settings.pool_id:
        pool_stmt = select(Pool).where(Pool.id == settings.pool_id)
        result = await db.execute(pool_stmt)
        pool = result.scalar_one_or_none()
        if pool:
            response_dict["node_ip"] = pool.url
            response_dict["node_port"] = pool.port
    
    return response_dict


@router.put("/settings/monero-solo", response_model=MoneroSoloSettingsResponse)
async def update_monero_solo_settings(
    settings_update: MoneroSoloSettingsUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update Monero solo mining settings"""
    from sqlalchemy import select
    from core.database import Pool
    
    service = MoneroSoloService(db)
    settings = await service.get_or_create_settings()
    
    # Update fields
    settings.enabled = settings_update.enabled
    settings.wallet_rpc_ip = settings_update.wallet_rpc_ip
    settings.wallet_rpc_port = settings_update.wallet_rpc_port
    settings.wallet_rpc_user = settings_update.wallet_rpc_user
    settings.wallet_rpc_pass = settings_update.wallet_rpc_pass
    
    # Create or update pool entry for node
    if settings_update.node_ip and settings_update.node_port:
        if settings.pool_id:
            # Update existing pool
            pool_stmt = select(Pool).where(Pool.id == settings.pool_id)
            result = await db.execute(pool_stmt)
            pool = result.scalar_one_or_none()
            if pool:
                pool.url = settings_update.node_ip
                pool.port = settings_update.node_port
                pool.user = settings.wallet_address or "x"
        else:
            # Create new pool
            pool = Pool(
                name="Monero Solo Mining",
                url=settings_update.node_ip,
                port=settings_update.node_port,
                user=settings.wallet_address or "x",
                password="x",
                enabled=True
            )
            db.add(pool)
            await db.flush()
            settings.pool_id = pool.id
    
    # If enabled and wallet RPC configured, try to fetch wallet address
    if settings.enabled and settings.wallet_rpc_ip:
        try:
            wallet_rpc = MoneroWalletRPC(
                host=settings.wallet_rpc_ip,
                port=settings.wallet_rpc_port,
                username=settings.wallet_rpc_user,
                password=settings.wallet_rpc_pass
            )
            address = await wallet_rpc.get_address()
            if address:
                settings.wallet_address = address
                # Update pool user if we have a pool
                if settings.pool_id:
                    pool_stmt = select(Pool).where(Pool.id == settings.pool_id)
                    result = await db.execute(pool_stmt)
                    pool = result.scalar_one_or_none()
                    if pool:
                        pool.user = address
        except Exception as e:
            # Don't fail the update if we can't fetch the address
            pass
    
    await db.commit()
    await db.refresh(settings)
    
    # Add node info to response
    response_dict = {
        "id": settings.id,
        "enabled": settings.enabled,
        "pool_id": settings.pool_id,
        "wallet_rpc_ip": settings.wallet_rpc_ip,
        "wallet_rpc_port": settings.wallet_rpc_port,
        "wallet_rpc_user": settings.wallet_rpc_user,
        "wallet_rpc_pass": settings.wallet_rpc_pass,
        "wallet_address": settings.wallet_address,
        "last_sync": settings.last_sync,
        "node_ip": None,
        "node_port": None
    }
    
    # Get node info from pool
    if settings.pool_id:
        pool_stmt = select(Pool).where(Pool.id == settings.pool_id)
        result = await db.execute(pool_stmt)
        pool = result.scalar_one_or_none()
        if pool:
            response_dict["node_ip"] = pool.url
            response_dict["node_port"] = pool.port
    
    return response_dict


@router.post("/settings/monero-solo/test-wallet", response_model=TestConnectionResponse)
async def test_wallet_connection(request: TestWalletRequest):
    """Test connection to Monero wallet RPC"""
    try:
        wallet_rpc = MoneroWalletRPC(
            host=request.ip,
            port=request.port,
            username=request.username,
            password=request.password
        )
        
        # Test connection by getting wallet address
        address = await wallet_rpc.get_address()
        
        if address:
            return TestConnectionResponse(
                success=True,
                message="Successfully connected to wallet RPC",
                address=address
            )
        else:
            return TestConnectionResponse(
                success=False,
                message="Failed to retrieve wallet address"
            )
            
    except Exception as e:
        return TestConnectionResponse(
            success=False,
            message=f"Connection failed: {str(e)}"
        )


@router.post("/settings/monero-solo/test-node", response_model=TestConnectionResponse)
async def test_node_connection(request: TestNodeRequest):
    """Test connection to Monero node RPC"""
    try:
        node_rpc = MoneroNodeRPC(
            host=request.ip,
            port=request.port
        )
        
        # Test connection by getting node info
        info = await node_rpc.get_info()
        
        if info:
            height = info.get("height", 0)
            return TestConnectionResponse(
                success=True,
                message=f"Successfully connected to node RPC (height: {height})"
            )
        else:
            return TestConnectionResponse(
                success=False,
                message="Failed to retrieve node information"
            )
            
    except Exception as e:
        return TestConnectionResponse(
            success=False,
            message=f"Connection failed: {str(e)}"
        )


@router.get("/settings/monero-solo/stats")
async def get_monero_solo_stats(db: AsyncSession = Depends(get_db)):
    """Get Monero solo mining statistics for dashboard"""
    from sqlalchemy import select, func
    from core.database import MoneroBlock, MoneroWalletTransaction
    from datetime import datetime, timedelta
    
    service = MoneroSoloService(db)
    settings = await service.get_or_create_settings()
    
    # Check if wallet RPC is configured
    wallet_connected = bool(
        settings.wallet_rpc_ip and 
        settings.wallet_address
    )
    
    if not settings.enabled:
        return {
            "enabled": False,
            "wallet_connected": False,
            "xmrig_workers": 0,
            "total_hashrate_formatted": "0 H/s",
            "current_effort_percent": 0.0,
            "blocks_found": 0,
            "earnings_24h_xmr": 0.0,
            "total_earned_xmr": 0.0
        }
    
    # Get hashrate data from XMRig miners
    hashrate_data = await service.aggregate_hashrate()
    
    # TODO: Calculate effort from total_hashes and network difficulty
    # For now, return 0.0 as effort calculation is not yet implemented
    current_effort = 0.0
    
    # Count blocks found
    blocks_stmt = select(func.count(MoneroBlock.id))
    result = await db.execute(blocks_stmt)
    blocks_count = result.scalar() or 0
    
    # Calculate 24h earnings
    yesterday = datetime.utcnow() - timedelta(days=1)
    earnings_stmt = select(func.sum(MoneroWalletTransaction.amount_xmr)).where(
        MoneroWalletTransaction.timestamp >= yesterday
    )
    result = await db.execute(earnings_stmt)
    earnings_24h = result.scalar() or 0.0
    
    # Calculate all-time earnings
    total_stmt = select(func.sum(MoneroWalletTransaction.amount_xmr))
    result = await db.execute(total_stmt)
    total_earned = result.scalar() or 0.0
    
    # Format hashrate for display
    total_hashrate = hashrate_data["total_hashrate"]
    if total_hashrate >= 1_000_000_000:
        hashrate_formatted = f"{total_hashrate / 1_000_000_000:.2f} GH/s"
    elif total_hashrate >= 1_000_000:
        hashrate_formatted = f"{total_hashrate / 1_000_000:.2f} MH/s"
    elif total_hashrate >= 1_000:
        hashrate_formatted = f"{total_hashrate / 1_000:.2f} KH/s"
    else:
        hashrate_formatted = f"{total_hashrate:.2f} H/s"
    
    return {
        "enabled": True,
        "wallet_connected": wallet_connected,
        "xmrig_workers": hashrate_data["worker_count"],
        "total_hashrate_formatted": hashrate_formatted,
        "current_effort_percent": current_effort,
        "blocks_found": blocks_count,
        "earnings_24h_xmr": float(earnings_24h),
        "total_earned_xmr": float(total_earned)
    }

