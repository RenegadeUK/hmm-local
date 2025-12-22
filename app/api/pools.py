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


# Pool Strategy Endpoints

class PoolStrategyCreate(BaseModel):
    name: str
    strategy_type: str  # round_robin, load_balance, pro_mode
    pool_ids: List[int]
    miner_ids: List[int] = []  # Empty list means all miners
    config: dict = {}
    enabled: bool = False


class PoolStrategyUpdate(BaseModel):
    name: str | None = None
    strategy_type: str | None = None
    pool_ids: List[int] | None = None
    miner_ids: List[int] | None = None
    config: dict | None = None
    enabled: bool | None = None


class PoolStrategyResponse(BaseModel):
    id: int
    name: str
    strategy_type: str
    enabled: bool
    pool_ids: List[int]
    miner_ids: List[int]
    config: dict
    current_pool_index: int
    last_switch: str | None
    
    class Config:
        from_attributes = True


@router.get("/strategies", response_model=List[PoolStrategyResponse])
async def list_strategies(db: AsyncSession = Depends(get_db)):
    """List all pool strategies"""
    from core.database import PoolStrategy
    
    result = await db.execute(select(PoolStrategy).order_by(PoolStrategy.id))
    strategies = result.scalars().all()
    
    return [
        {
            "id": s.id,
            "name": s.name,
            "strategy_type": s.strategy_type,
            "enabled": s.enabled,
            "pool_ids": s.pool_ids,
            "miner_ids": s.miner_ids if s.miner_ids else [],
            "config": s.config,
            "current_pool_index": s.current_pool_index,
            "last_switch": s.last_switch.isoformat() if s.last_switch else None
        }
        for s in strategies
    ]


@router.post("/strategies", response_model=PoolStrategyResponse)
async def create_strategy(strategy: PoolStrategyCreate, db: AsyncSession = Depends(get_db)):
    """Create a new pool strategy"""
    from core.database import PoolStrategy
    from core.config import app_config
    
    # Validate strategy type
    valid_types = ["round_robin", "load_balance", "pro_mode"]
    if strategy.strategy_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid strategy type. Must be one of: {', '.join(valid_types)}")
    
    # Pro Mode specific validations
    if strategy.strategy_type == "pro_mode":
        # Check if energy optimization is enabled
        energy_enabled = app_config.get("energy_optimization.enabled", False)
        if not energy_enabled:
            raise HTTPException(
                status_code=400, 
                detail="Pro Mode requires Energy Optimization to be enabled. Please enable it in Settings > Energy > Optimization."
            )
        
        # Validate Pro Mode config
        if not strategy.config:
            raise HTTPException(status_code=400, detail="Pro Mode requires configuration")
        
        low_mode_pool_id = strategy.config.get("low_mode_pool_id")
        high_mode_pool_id = strategy.config.get("high_mode_pool_id")
        
        if not low_mode_pool_id or not high_mode_pool_id:
            raise HTTPException(
                status_code=400, 
                detail="Pro Mode requires both low_mode_pool_id and high_mode_pool_id in config"
            )
        
        # Validate both pools exist
        result = await db.execute(select(Pool).where(Pool.id.in_([low_mode_pool_id, high_mode_pool_id])))
        pools = result.scalars().all()
        if len(pools) != 2:
            raise HTTPException(status_code=400, detail="One or both Pro Mode pool IDs not found")
        
        # For Pro Mode, pool_ids should contain both pools
        if set(strategy.pool_ids) != {low_mode_pool_id, high_mode_pool_id}:
            raise HTTPException(
                status_code=400, 
                detail="pool_ids must contain both low_mode_pool_id and high_mode_pool_id"
            )
    else:
        # Validate pool IDs exist for other strategy types
        result = await db.execute(select(Pool).where(Pool.id.in_(strategy.pool_ids)))
        pools = result.scalars().all()
        
        if len(pools) != len(strategy.pool_ids):
            raise HTTPException(status_code=400, detail="One or more pool IDs not found")
    
    # Validate miner IDs exist if specified
    if strategy.miner_ids:
        from core.database import Miner
        result = await db.execute(select(Miner).where(Miner.id.in_(strategy.miner_ids)))
        miners = result.scalars().all()
        if len(miners) != len(strategy.miner_ids):
            raise HTTPException(status_code=400, detail="One or more miner IDs not found")
    
    # Check for miner conflicts with other enabled strategies
    if strategy.enabled and strategy.miner_ids:
        result = await db.execute(select(PoolStrategy).where(PoolStrategy.enabled == True))
        existing_strategies = result.scalars().all()
        for existing in existing_strategies:
            # Check if any miners overlap
            existing_miner_ids = existing.miner_ids if existing.miner_ids else []
            if existing_miner_ids:
                overlap = set(strategy.miner_ids) & set(existing_miner_ids)
                if overlap:
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Miners {list(overlap)} are already assigned to strategy '{existing.name}'"
                    )
    
    new_strategy = PoolStrategy(
        name=strategy.name,
        strategy_type=strategy.strategy_type,
        pool_ids=strategy.pool_ids,
        miner_ids=strategy.miner_ids,
        config=strategy.config,
        enabled=strategy.enabled,
        current_pool_index=0
    )
    
    db.add(new_strategy)
    await db.commit()
    await db.refresh(new_strategy)
    
    return {
        "id": new_strategy.id,
        "name": new_strategy.name,
        "strategy_type": new_strategy.strategy_type,
        "enabled": new_strategy.enabled,
        "pool_ids": new_strategy.pool_ids,
        "miner_ids": new_strategy.miner_ids if new_strategy.miner_ids else [],
        "config": new_strategy.config,
        "current_pool_index": new_strategy.current_pool_index,
        "last_switch": new_strategy.last_switch.isoformat() if new_strategy.last_switch else None
    }


@router.get("/strategies/{strategy_id}", response_model=PoolStrategyResponse)
async def get_strategy(strategy_id: int, db: AsyncSession = Depends(get_db)):
    """Get strategy details"""
    from core.database import PoolStrategy
    
    result = await db.execute(select(PoolStrategy).where(PoolStrategy.id == strategy_id))
    strategy = result.scalar_one_or_none()
    
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    
    return {
        "id": strategy.id,
        "name": strategy.name,
        "strategy_type": strategy.strategy_type,
        "enabled": strategy.enabled,
        "pool_ids": strategy.pool_ids,
        "miner_ids": strategy.miner_ids if strategy.miner_ids else [],
        "config": strategy.config,
        "current_pool_index": strategy.current_pool_index,
        "last_switch": strategy.last_switch.isoformat() if strategy.last_switch else None
    }


@router.put("/strategies/{strategy_id}", response_model=PoolStrategyResponse)
async def update_strategy(
    strategy_id: int,
    strategy_update: PoolStrategyUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update strategy"""
    from core.database import PoolStrategy
    
    result = await db.execute(select(PoolStrategy).where(PoolStrategy.id == strategy_id))
    strategy = result.scalar_one_or_none()
    
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    
    # Update miner_ids if specified
    updated_miner_ids = strategy_update.miner_ids if strategy_update.miner_ids is not None else strategy.miner_ids
    
    # Validate miner IDs if updating
    if strategy_update.miner_ids is not None and strategy_update.miner_ids:
        from core.database import Miner
        result = await db.execute(select(Miner).where(Miner.id.in_(strategy_update.miner_ids)))
        miners = result.scalars().all()
        if len(miners) != len(strategy_update.miner_ids):
            raise HTTPException(status_code=400, detail="One or more miner IDs not found")
    
    # Check for miner conflicts if enabling or updating miner_ids
    is_enabling = strategy_update.enabled is not None and strategy_update.enabled
    if (is_enabling or strategy_update.miner_ids is not None) and updated_miner_ids:
        result = await db.execute(select(PoolStrategy).where(PoolStrategy.enabled == True))
        existing_strategies = result.scalars().all()
        for existing in existing_strategies:
            if existing.id != strategy_id:
                existing_miner_ids = existing.miner_ids if existing.miner_ids else []
                if existing_miner_ids:
                    overlap = set(updated_miner_ids) & set(existing_miner_ids)
                    if overlap:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Miners {list(overlap)} are already assigned to strategy '{existing.name}'"
                        )
    
    if strategy_update.name is not None:
        strategy.name = strategy_update.name
    if strategy_update.strategy_type is not None:
        strategy.strategy_type = strategy_update.strategy_type
    if strategy_update.pool_ids is not None:
        # Validate pool IDs
        result = await db.execute(select(Pool).where(Pool.id.in_(strategy_update.pool_ids)))
        pools = result.scalars().all()
        if len(pools) != len(strategy_update.pool_ids):
            raise HTTPException(status_code=400, detail="One or more pool IDs not found")
        strategy.pool_ids = strategy_update.pool_ids
    if strategy_update.miner_ids is not None:
        strategy.miner_ids = strategy_update.miner_ids
        strategy.current_pool_index = 0  # Reset index when pools change
    if strategy_update.config is not None:
        strategy.config = strategy_update.config
    if strategy_update.enabled is not None:
        strategy.enabled = strategy_update.enabled
    
    await db.commit()
    await db.refresh(strategy)
    
    return {
        "id": strategy.id,
        "name": strategy.name,
        "strategy_type": strategy.strategy_type,
        "enabled": strategy.enabled,
        "pool_ids": strategy.pool_ids,
        "miner_ids": strategy.miner_ids if strategy.miner_ids else [],
        "config": strategy.config,
        "current_pool_index": strategy.current_pool_index,
        "last_switch": strategy.last_switch.isoformat() if strategy.last_switch else None
    }


@router.delete("/strategies/{strategy_id}")
async def delete_strategy(strategy_id: int, db: AsyncSession = Depends(get_db)):
    """Delete strategy"""
    from core.database import PoolStrategy
    
    result = await db.execute(select(PoolStrategy).where(PoolStrategy.id == strategy_id))
    strategy = result.scalar_one_or_none()
    
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    
    await db.delete(strategy)
    await db.commit()
    
    return {"status": "deleted"}


@router.post("/strategies/{strategy_id}/execute")
async def execute_strategy(strategy_id: int, db: AsyncSession = Depends(get_db)):
    """Manually execute a strategy (immediate switch/rebalance)"""
    from core.database import PoolStrategy
    from core.pool_strategy import PoolStrategyService
    
    result = await db.execute(select(PoolStrategy).where(PoolStrategy.id == strategy_id))
    strategy = result.scalar_one_or_none()
    
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    
    service = PoolStrategyService(db)
    
    if strategy.strategy_type == "round_robin":
        result = await service.execute_round_robin(strategy, force=True)
    elif strategy.strategy_type == "load_balance":
        result = await service.execute_load_balance(strategy, force=True)
    else:
        raise HTTPException(status_code=400, detail="Unknown strategy type")
    
    return result
