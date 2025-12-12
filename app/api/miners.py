"""
Miner management API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from pydantic import BaseModel

from core.database import get_db, Miner
from adapters import create_adapter, get_supported_types


router = APIRouter()


class MinerCreate(BaseModel):
    name: str
    miner_type: str
    ip_address: str
    port: int | None = None
    config: dict | None = None


class MinerUpdate(BaseModel):
    name: str | None = None
    ip_address: str | None = None
    port: int | None = None
    current_mode: str | None = None
    enabled: bool | None = None
    config: dict | None = None


class MinerResponse(BaseModel):
    id: int
    name: str
    miner_type: str
    ip_address: str
    port: int | None
    current_mode: str | None
    enabled: bool
    config: dict | None
    
    class Config:
        from_attributes = True


@router.get("/types")
async def get_miner_types():
    """Get supported miner types"""
    return {"types": get_supported_types()}


@router.get("/", response_model=List[MinerResponse])
async def list_miners(db: AsyncSession = Depends(get_db)):
    """List all miners"""
    result = await db.execute(select(Miner))
    miners = result.scalars().all()
    return miners


@router.get("/{miner_id}", response_model=MinerResponse)
async def get_miner(miner_id: int, db: AsyncSession = Depends(get_db)):
    """Get miner by ID"""
    result = await db.execute(select(Miner).where(Miner.id == miner_id))
    miner = result.scalar_one_or_none()
    
    if not miner:
        raise HTTPException(status_code=404, detail="Miner not found")
    
    return miner


@router.post("/", response_model=MinerResponse)
async def create_miner(miner: MinerCreate, db: AsyncSession = Depends(get_db)):
    """Create new miner"""
    # Validate miner type
    if miner.miner_type not in get_supported_types():
        raise HTTPException(status_code=400, detail=f"Invalid miner type: {miner.miner_type}")
    
    db_miner = Miner(
        name=miner.name,
        miner_type=miner.miner_type,
        ip_address=miner.ip_address,
        port=miner.port,
        config=miner.config
    )
    
    db.add(db_miner)
    await db.commit()
    await db.refresh(db_miner)
    
    return db_miner


@router.put("/{miner_id}", response_model=MinerResponse)
async def update_miner(miner_id: int, miner_update: MinerUpdate, db: AsyncSession = Depends(get_db)):
    """Update miner configuration"""
    result = await db.execute(select(Miner).where(Miner.id == miner_id))
    miner = result.scalar_one_or_none()
    
    if not miner:
        raise HTTPException(status_code=404, detail="Miner not found")
    
    # Update fields
    if miner_update.name is not None:
        miner.name = miner_update.name
    if miner_update.ip_address is not None:
        miner.ip_address = miner_update.ip_address
    if miner_update.port is not None:
        miner.port = miner_update.port
    if miner_update.current_mode is not None:
        miner.current_mode = miner_update.current_mode
    if miner_update.enabled is not None:
        miner.enabled = miner_update.enabled
    if miner_update.config is not None:
        miner.config = miner_update.config
    
    await db.commit()
    await db.refresh(miner)
    
    return miner


@router.delete("/{miner_id}")
async def delete_miner(miner_id: int, db: AsyncSession = Depends(get_db)):
    """Delete miner"""
    result = await db.execute(select(Miner).where(Miner.id == miner_id))
    miner = result.scalar_one_or_none()
    
    if not miner:
        raise HTTPException(status_code=404, detail="Miner not found")
    
    await db.delete(miner)
    await db.commit()
    
    return {"status": "deleted"}


@router.get("/{miner_id}/telemetry")
async def get_miner_telemetry(miner_id: int, db: AsyncSession = Depends(get_db)):
    """Get current telemetry from miner"""
    result = await db.execute(select(Miner).where(Miner.id == miner_id))
    miner = result.scalar_one_or_none()
    
    if not miner:
        raise HTTPException(status_code=404, detail="Miner not found")
    
    adapter = create_adapter(miner.miner_type, miner.id, miner.ip_address, miner.port, miner.config)
    if not adapter:
        raise HTTPException(status_code=500, detail="Failed to create miner adapter")
    
    telemetry = await adapter.get_telemetry()
    if not telemetry:
        raise HTTPException(status_code=503, detail="Failed to get telemetry from miner")
    
    return telemetry.to_dict()


@router.post("/{miner_id}/mode")
async def set_miner_mode(miner_id: int, mode: str, db: AsyncSession = Depends(get_db)):
    """Set miner operating mode"""
    result = await db.execute(select(Miner).where(Miner.id == miner_id))
    miner = result.scalar_one_or_none()
    
    if not miner:
        raise HTTPException(status_code=404, detail="Miner not found")
    
    adapter = create_adapter(miner.miner_type, miner.id, miner.ip_address, miner.port, miner.config)
    if not adapter:
        raise HTTPException(status_code=500, detail="Failed to create miner adapter")
    
    success = await adapter.set_mode(mode)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to set mode")
    
    # Update database
    miner.current_mode = mode
    await db.commit()
    
    return {"status": "success", "mode": mode}


@router.post("/{miner_id}/restart")
async def restart_miner(miner_id: int, db: AsyncSession = Depends(get_db)):
    """Restart miner"""
    result = await db.execute(select(Miner).where(Miner.id == miner_id))
    miner = result.scalar_one_or_none()
    
    if not miner:
        raise HTTPException(status_code=404, detail="Miner not found")
    
    adapter = create_adapter(miner.miner_type, miner.id, miner.ip_address, miner.port, miner.config)
    if not adapter:
        raise HTTPException(status_code=500, detail="Failed to create miner adapter")
    
    success = await adapter.restart()
    if not success:
        raise HTTPException(status_code=500, detail="Failed to restart miner")
    
    return {"status": "restarting"}


@router.get("/{miner_id}/modes")
async def get_miner_modes(miner_id: int, db: AsyncSession = Depends(get_db)):
    """Get available modes for miner"""
    result = await db.execute(select(Miner).where(Miner.id == miner_id))
    miner = result.scalar_one_or_none()
    
    if not miner:
        raise HTTPException(status_code=404, detail="Miner not found")
    
    adapter = create_adapter(miner.miner_type, miner.id, miner.ip_address, miner.port, miner.config)
    if not adapter:
        raise HTTPException(status_code=500, detail="Failed to create miner adapter")
    
    modes = await adapter.get_available_modes()
    
    return {"modes": modes}


@router.get("/{miner_id}/cost/24h")
async def get_miner_24h_cost(miner_id: int, db: AsyncSession = Depends(get_db)):
    """Calculate rolling 24-hour cost for a miner based on power consumption and Octopus Agile prices"""
    from datetime import datetime, timedelta
    from core.database import Telemetry, EnergyPrice
    from core.config import app_config
    
    # Get miner
    result = await db.execute(select(Miner).where(Miner.id == miner_id))
    miner = result.scalar_one_or_none()
    
    if not miner:
        raise HTTPException(status_code=404, detail="Miner not found")
    
    # Get region
    region = app_config.get("octopus_agile.region", "H")
    
    # Get time range (last 24 hours)
    now = datetime.utcnow()
    start_time = now - timedelta(hours=24)
    
    # Get all telemetry records for this miner in the last 24 hours
    result = await db.execute(
        select(Telemetry)
        .where(Telemetry.miner_id == miner_id)
        .where(Telemetry.timestamp >= start_time)
        .where(Telemetry.timestamp <= now)
        .order_by(Telemetry.timestamp)
    )
    telemetry_records = result.scalars().all()
    
    if not telemetry_records:
        return {
            "miner_id": miner_id,
            "miner_name": miner.name,
            "period_hours": 24,
            "cost_pence": 0,
            "cost_pounds": 0,
            "avg_power_watts": 0,
            "total_kwh": 0,
            "message": "No telemetry data available"
        }
    
    # Calculate total cost by matching telemetry records with energy prices
    total_cost_pence = 0
    total_power_readings = 0
    total_power_sum = 0
    
    for telem in telemetry_records:
        if telem.power_watts is None or telem.power_watts <= 0:
            continue
        
        # Find the energy price for this timestamp
        result = await db.execute(
            select(EnergyPrice)
            .where(EnergyPrice.region == region)
            .where(EnergyPrice.valid_from <= telem.timestamp)
            .where(EnergyPrice.valid_to > telem.timestamp)
            .limit(1)
        )
        price = result.scalar_one_or_none()
        
        if price:
            # Calculate energy consumed since last reading (or assume 30 seconds interval)
            interval_hours = 30 / 3600  # 30 seconds in hours (typical telemetry interval)
            energy_kwh = (telem.power_watts / 1000) * interval_hours
            cost_pence = energy_kwh * price.price_pence
            total_cost_pence += cost_pence
        
        total_power_sum += telem.power_watts
        total_power_readings += 1
    
    # Calculate averages
    avg_power_watts = total_power_sum / total_power_readings if total_power_readings > 0 else 0
    
    # Calculate total kWh (average power over 24 hours)
    total_kwh = (avg_power_watts / 1000) * 24
    
    return {
        "miner_id": miner_id,
        "miner_name": miner.name,
        "period_hours": 24,
        "cost_pence": round(total_cost_pence, 2),
        "cost_pounds": round(total_cost_pence / 100, 2),
        "avg_power_watts": round(avg_power_watts, 2),
        "total_kwh": round(total_kwh, 3),
        "data_points": total_power_readings
    }
