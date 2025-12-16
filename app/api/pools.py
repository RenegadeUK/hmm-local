"""
Pool management API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from pydantic import BaseModel

from core.database import get_db, Pool


router = APIRouter()


class PoolCreate(BaseModel):
    name: str
    url: str
    port: int
    user: str
    password: str
    enabled: bool = True


class PoolUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    port: int | None = None
    user: str | None = None
    password: str | None = None
    enabled: bool | None = None


class PoolResponse(BaseModel):
    id: int
    name: str
    url: str
    port: int
    user: str
    password: str
    enabled: bool
    
    class Config:
        from_attributes = True


@router.get("/", response_model=List[PoolResponse])
async def list_pools(db: AsyncSession = Depends(get_db)):
    """List all pools"""
    from sqlalchemy import func
    result = await db.execute(select(Pool).order_by(func.lower(Pool.name)))
    pools = result.scalars().all()
    return pools


@router.get("/performance")
async def get_pool_performance(range: str = "24h", db: AsyncSession = Depends(get_db)):
    """Get pool performance comparison data"""
    from datetime import datetime, timedelta
    from sqlalchemy import func
    from core.database import PoolHealth
    
    # Parse time range
    range_hours = {
        "24h": 24,
        "3d": 72,
        "7d": 168,
        "30d": 720
    }.get(range, 24)
    
    cutoff_time = datetime.utcnow() - timedelta(hours=range_hours)
    
    # Get all enabled pools
    result = await db.execute(select(Pool).where(Pool.enabled == True))
    pools = result.scalars().all()
    
    pool_data = []
    
    for pool in pools:
        # Get health history for this pool
        history_result = await db.execute(
            select(PoolHealth)
            .where(PoolHealth.pool_id == pool.id)
            .where(PoolHealth.timestamp >= cutoff_time)
            .order_by(PoolHealth.timestamp)
        )
        history = history_result.scalars().all()
        
        # Calculate averages
        if history:
            avg_luck = sum(h.luck_percentage for h in history if h.luck_percentage is not None) / len([h for h in history if h.luck_percentage is not None]) if any(h.luck_percentage is not None for h in history) else None
            avg_latency = sum(h.response_time_ms for h in history if h.response_time_ms is not None) / len([h for h in history if h.response_time_ms is not None]) if any(h.response_time_ms is not None for h in history) else None
            avg_health = sum(h.health_score for h in history if h.health_score is not None) / len([h for h in history if h.health_score is not None]) if any(h.health_score is not None for h in history) else None
            avg_reject = sum(h.reject_rate for h in history if h.reject_rate is not None) / len([h for h in history if h.reject_rate is not None]) if any(h.reject_rate is not None for h in history) else None
        else:
            avg_luck = avg_latency = avg_health = avg_reject = None
        
        pool_data.append({
            "id": pool.id,
            "name": pool.name,
            "avg_luck": avg_luck,
            "avg_latency": avg_latency,
            "avg_health": avg_health,
            "avg_reject": avg_reject,
            "history": [
                {
                    "timestamp": h.timestamp.isoformat(),
                    "luck": h.luck_percentage or 0,
                    "latency": h.response_time_ms or 0,
                    "health": h.health_score or 0,
                    "reject_rate": h.reject_rate or 0
                }
                for h in history
            ]
        })
    
    return {"pools": pool_data, "range": range}


@router.get("/{pool_id}", response_model=PoolResponse)
async def get_pool(pool_id: int, db: AsyncSession = Depends(get_db)):
    """Get pool by ID"""
    result = await db.execute(select(Pool).where(Pool.id == pool_id))
    pool = result.scalar_one_or_none()
    
    if not pool:
        raise HTTPException(status_code=404, detail="Pool not found")
    
    return pool


@router.post("/", response_model=PoolResponse)
async def create_pool(pool: PoolCreate, db: AsyncSession = Depends(get_db)):
    """Create new pool"""
    db_pool = Pool(
        name=pool.name,
        url=pool.url,
        port=pool.port,
        user=pool.user,
        password=pool.password,
        enabled=pool.enabled
    )
    
    db.add(db_pool)
    await db.commit()
    await db.refresh(db_pool)
    
    return db_pool


@router.put("/{pool_id}", response_model=PoolResponse)
async def update_pool(pool_id: int, pool_update: PoolUpdate, db: AsyncSession = Depends(get_db)):
    """Update pool configuration"""
    result = await db.execute(select(Pool).where(Pool.id == pool_id))
    pool = result.scalar_one_or_none()
    
    if not pool:
        raise HTTPException(status_code=404, detail="Pool not found")
    
    # Update fields
    if pool_update.name is not None:
        pool.name = pool_update.name
    if pool_update.url is not None:
        pool.url = pool_update.url
    if pool_update.port is not None:
        pool.port = pool_update.port
    if pool_update.user is not None:
        pool.user = pool_update.user
    if pool_update.password is not None:
        pool.password = pool_update.password
    if pool_update.enabled is not None:
        pool.enabled = pool_update.enabled
    
    await db.commit()
    await db.refresh(pool)
    
    return pool


@router.delete("/{pool_id}")
async def delete_pool(pool_id: int, db: AsyncSession = Depends(get_db)):
    """Delete pool"""
    result = await db.execute(select(Pool).where(Pool.id == pool_id))
    pool = result.scalar_one_or_none()
    
    if not pool:
        raise HTTPException(status_code=404, detail="Pool not found")
    
    await db.delete(pool)
    await db.commit()
    
    return {"status": "deleted"}
