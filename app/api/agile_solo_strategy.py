"""
Agile Solo Mining Strategy API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from core.database import get_db, AgileStrategy, MinerStrategy, Miner

router = APIRouter()


class AgileStrategySettings(BaseModel):
    enabled: bool
    miner_ids: List[int]


class AgileStrategyStatus(BaseModel):
    enabled: bool
    current_price_band: Optional[str]
    last_action_time: Optional[datetime]
    last_price_checked: Optional[float]
    enrolled_miners: List[dict]  # List of {id, name, type}


@router.get("/agile-solo-strategy")
async def get_agile_strategy_settings(db: AsyncSession = Depends(get_db)):
    """Get current Agile Solo Strategy settings"""
    # Get strategy config
    result = await db.execute(select(AgileStrategy))
    strategy = result.scalar_one_or_none()
    
    if not strategy:
        # Create default strategy config
        strategy = AgileStrategy(
            enabled=False,
            current_price_band=None,
            hysteresis_counter=0
        )
        db.add(strategy)
        await db.commit()
        await db.refresh(strategy)
    
    # Get enrolled miners
    miner_strategy_result = await db.execute(
        select(MinerStrategy, Miner)
        .join(Miner, MinerStrategy.miner_id == Miner.id)
        .where(MinerStrategy.strategy_enabled == True)
    )
    enrolled = miner_strategy_result.all()
    
    enrolled_miners = [
        {
            "id": miner.id,
            "name": miner.name,
            "type": miner.miner_type
        }
        for _, miner in enrolled
    ]
    
    # Get all miners for selection
    all_miners_result = await db.execute(
        select(Miner)
        .where(Miner.enabled == True)
        .order_by(Miner.miner_type, Miner.name)
    )
    all_miners = all_miners_result.scalars().all()
    
    miners_by_type = {
        "bitaxe": [],
        "nerdqaxe": [],
        "avalon_nano": []
    }
    
    for miner in all_miners:
        miner_dict = {
            "id": miner.id,
            "name": miner.name,
            "type": miner.miner_type,
            "enrolled": miner.id in [m["id"] for m in enrolled_miners]
        }
        
        if miner.miner_type == "bitaxe":
            miners_by_type["bitaxe"].append(miner_dict)
        elif miner.miner_type == "nerdqaxe":
            miners_by_type["nerdqaxe"].append(miner_dict)
        elif miner.miner_type == "avalon_nano":
            miners_by_type["avalon_nano"].append(miner_dict)
    
    return {
        "enabled": strategy.enabled,
        "current_price_band": strategy.current_price_band,
        "last_action_time": strategy.last_action_time.isoformat() if strategy.last_action_time else None,
        "last_price_checked": strategy.last_price_checked,
        "hysteresis_counter": strategy.hysteresis_counter,
        "enrolled_miners": enrolled_miners,
        "miners_by_type": miners_by_type
    }


@router.post("/agile-solo-strategy")
async def save_agile_strategy_settings(
    settings: AgileStrategySettings,
    db: AsyncSession = Depends(get_db)
):
    """Save Agile Solo Strategy settings"""
    # Get or create strategy
    result = await db.execute(select(AgileStrategy))
    strategy = result.scalar_one_or_none()
    
    if not strategy:
        strategy = AgileStrategy(enabled=settings.enabled)
        db.add(strategy)
    else:
        strategy.enabled = settings.enabled
    
    strategy.updated_at = datetime.utcnow()
    
    # Clear existing miner strategy entries
    existing_result = await db.execute(select(MinerStrategy))
    existing = existing_result.scalars().all()
    
    for ms in existing:
        await db.delete(ms)
    
    await db.flush()  # Ensure deletions are processed
    
    # Add new miner strategy entries
    for miner_id in settings.miner_ids:
        ms = MinerStrategy(
            miner_id=miner_id,
            strategy_enabled=True
        )
        db.add(ms)
    
    await db.commit()
    
    return {
        "message": "Agile Solo Strategy settings saved successfully",
        "enabled": settings.enabled,
        "enrolled_count": len(settings.miner_ids)
    }


@router.post("/agile-solo-strategy/execute")
async def execute_agile_strategy_manual(db: AsyncSession = Depends(get_db)):
    """Manually trigger Agile Solo Strategy execution"""
    from core.agile_solo_strategy import AgileSoloStrategy
    
    try:
        report = await AgileSoloStrategy.execute_strategy(db)
        return report
    except Exception as e:
        import traceback
        return {
            "error": str(e),
            "traceback": traceback.format_exc()
        }
