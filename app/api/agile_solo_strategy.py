"""
Agile Solo Mining Strategy API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from core.database import get_db, AgileStrategy, MinerStrategy, Miner

router = APIRouter()

# Large offset used when re-indexing bands to avoid transient UNIQUE collisions
SHIFT_OFFSET = 1000


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
    """Get current Agile Strategy settings"""
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
        "avalon_nano": [],
        "nmminer": []
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
        elif miner.miner_type == "nmminer":
            miners_by_type["nmminer"].append(miner_dict)
    
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
    """Save Agile Strategy settings"""
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
        "message": "Agile Strategy settings saved successfully",
        "enabled": settings.enabled,
        "enrolled_count": len(settings.miner_ids)
    }


@router.post("/agile-solo-strategy/execute")
async def execute_agile_strategy_manual(db: AsyncSession = Depends(get_db)):
    """Manually trigger Agile Strategy execution"""
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


@router.post("/agile-solo-strategy/reconcile")
async def reconcile_agile_strategy_manual(db: AsyncSession = Depends(get_db)):
    """Manually trigger Agile Strategy reconciliation"""
    from core.agile_solo_strategy import AgileSoloStrategy
    
    try:
        report = await AgileSoloStrategy.reconcile_strategy(db)
        return report
    except Exception as e:
        import traceback
        return {
            "error": str(e),
            "traceback": traceback.format_exc()
        }


class BandUpdate(BaseModel):
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    target_coin: Optional[str] = None
    bitaxe_mode: Optional[str] = None
    nerdqaxe_mode: Optional[str] = None
    avalon_nano_mode: Optional[str] = None


class BandInsertRequest(BaseModel):
    insert_after_band_id: Optional[int] = None


def validate_band_update(update: BandUpdate) -> Optional[str]:
    """
    Validate band update values
    
    Returns:
        Error message if validation fails, None if valid
    """
    from core.agile_bands import VALID_COINS, VALID_MODES
    
    # Validate price thresholds
    if update.min_price is not None and update.min_price < 0:
        return "Minimum price cannot be negative"
    
    if update.max_price is not None and update.max_price < 0:
        return "Maximum price cannot be negative"
    
    if update.min_price is not None and update.max_price is not None:
        if update.min_price >= update.max_price:
            return "Minimum price must be less than maximum price"
    
    # Validate coin
    if update.target_coin is not None:
        if update.target_coin not in VALID_COINS:
            return f"Invalid coin '{update.target_coin}'. Must be one of: {', '.join(VALID_COINS)}"
    
    # Validate modes
    if update.bitaxe_mode is not None:
        if update.bitaxe_mode not in VALID_MODES["bitaxe"]:
            return f"Invalid Bitaxe mode '{update.bitaxe_mode}'. Must be one of: {', '.join(VALID_MODES['bitaxe'])}"
    
    if update.nerdqaxe_mode is not None:
        if update.nerdqaxe_mode not in VALID_MODES["nerdqaxe"]:
            return f"Invalid NerdQaxe mode '{update.nerdqaxe_mode}'. Must be one of: {', '.join(VALID_MODES['nerdqaxe'])}"
    
    if update.avalon_nano_mode is not None:
        if update.avalon_nano_mode not in VALID_MODES["avalon_nano"]:
            return f"Invalid Avalon Nano mode '{update.avalon_nano_mode}'. Must be one of: {', '.join(VALID_MODES['avalon_nano'])}"
    
    return None


@router.get("/agile-solo-strategy/bands")
async def get_strategy_bands_api(db: AsyncSession = Depends(get_db)):
    """Get configured price bands for strategy"""
    from core.database import AgileStrategyBand
    from core.agile_bands import ensure_strategy_bands
    
    # Get strategy
    result = await db.execute(select(AgileStrategy))
    strategy = result.scalar_one_or_none()
    
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    
    # Ensure bands exist
    await ensure_strategy_bands(db, strategy.id)
    
    # Get bands
    bands_result = await db.execute(
        select(AgileStrategyBand)
        .where(AgileStrategyBand.strategy_id == strategy.id)
        .order_by(AgileStrategyBand.sort_order)
    )
    bands = bands_result.scalars().all()
    
    return {
        "bands": [
            {
                "id": band.id,
                "sort_order": band.sort_order,
                "min_price": band.min_price,
                "max_price": band.max_price,
                "target_coin": band.target_coin,
                "bitaxe_mode": band.bitaxe_mode,
                "nerdqaxe_mode": band.nerdqaxe_mode,
                "avalon_nano_mode": band.avalon_nano_mode
            }
            for band in bands
        ]
    }


@router.post("/agile-solo-strategy/bands")
async def insert_strategy_band(
    request: BandInsertRequest,
    db: AsyncSession = Depends(get_db)
):
    """Insert a new band at a specific position"""
    from core.database import AgileStrategyBand
    from core.agile_bands import ensure_strategy_bands

    # Get strategy
    result = await db.execute(select(AgileStrategy))
    strategy = result.scalar_one_or_none()

    if not strategy:
        strategy = AgileStrategy(enabled=False)
        db.add(strategy)
        await db.commit()
        await db.refresh(strategy)

    # Ensure bands exist to insert alongside
    bands_ready = await ensure_strategy_bands(db, strategy.id)
    if not bands_ready:
        raise HTTPException(status_code=500, detail="Failed to initialize bands")

    bands_result = await db.execute(
        select(AgileStrategyBand)
        .where(AgileStrategyBand.strategy_id == strategy.id)
        .order_by(AgileStrategyBand.sort_order)
    )
    bands = bands_result.scalars().all()

    if not bands:
        raise HTTPException(status_code=400, detail="Cannot insert band without existing configuration")

    # Determine desired sort position
    if request.insert_after_band_id is None:
        insert_position = 0
    else:
        anchor_band = next((band for band in bands if band.id == request.insert_after_band_id), None)
        if not anchor_band:
            raise HTTPException(status_code=404, detail="Anchor band not found")
        insert_position = (anchor_band.sort_order or 0) + 1

    # Shift existing bands up one position (update highest first to avoid collisions)
    bands_to_shift = await db.execute(
        select(AgileStrategyBand)
        .where(AgileStrategyBand.strategy_id == strategy.id)
        .where(AgileStrategyBand.sort_order >= insert_position)
        .order_by(AgileStrategyBand.sort_order.desc())  # Highest first!
    )
    for band in bands_to_shift.scalars():
        band.sort_order += 1
        band.updated_at = datetime.utcnow()
    await db.flush()

    # Create new band at the insert position
    new_band = AgileStrategyBand(
        strategy_id=strategy.id,
        sort_order=insert_position,
        min_price=None,
        max_price=None,
        target_coin="OFF",
        bitaxe_mode="managed_externally",
        nerdqaxe_mode="managed_externally",
        avalon_nano_mode="managed_externally"
    )
    db.add(new_band)
    await db.flush()
    
    # Re-sequence ALL bands to ensure contiguous sort_order (highest price first)
    all_bands_result = await db.execute(
        select(AgileStrategyBand)
        .where(AgileStrategyBand.strategy_id == strategy.id)
        .order_by(AgileStrategyBand.min_price.desc().nullslast())
    )
    all_bands = all_bands_result.scalars().all()
    
    # Update in descending current sort_order to avoid collisions
    all_bands.sort(key=lambda b: b.sort_order, reverse=True)
    target_positions = {band.id: idx + 1 for idx, band in enumerate(
        sorted(all_bands, key=lambda b: (b.min_price is None, -(b.min_price or 0)))
    )}
    
    for band in all_bands:
        new_pos = target_positions[band.id]
        if band.sort_order != new_pos:
            band.sort_order = new_pos
            band.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(new_band)

    return {
        "id": new_band.id,
        "sort_order": new_band.sort_order,
        "min_price": new_band.min_price,
        "max_price": new_band.max_price,
        "target_coin": new_band.target_coin,
        "bitaxe_mode": new_band.bitaxe_mode,
        "nerdqaxe_mode": new_band.nerdqaxe_mode,
        "avalon_nano_mode": new_band.avalon_nano_mode
    }


@router.patch("/agile-solo-strategy/bands/{band_id}")
async def update_strategy_band(
    band_id: int,
    update: BandUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a specific band's settings"""
    from core.database import AgileStrategyBand
    
    # Validate input
    validation_error = validate_band_update(update)
    if validation_error:
        raise HTTPException(status_code=400, detail=validation_error)
    
    # Get band
    result = await db.execute(
        select(AgileStrategyBand).where(AgileStrategyBand.id == band_id)
    )
    band = result.scalar_one_or_none()
    
    if not band:
        raise HTTPException(status_code=404, detail="Band not found")
    
    # Update fields if provided
    if update.min_price is not None:
        band.min_price = update.min_price
    
    if update.max_price is not None:
        band.max_price = update.max_price
    
    # Validate price range after updates
    if band.min_price is not None and band.max_price is not None:
        if band.min_price >= band.max_price:
            raise HTTPException(
                status_code=400, 
                detail=f"Minimum price ({band.min_price}) must be less than maximum price ({band.max_price})"
            )
    
    if update.target_coin is not None:
        band.target_coin = update.target_coin
        # If setting to OFF, force all modes to managed_externally
        if update.target_coin == "OFF":
            band.bitaxe_mode = "managed_externally"
            band.nerdqaxe_mode = "managed_externally"
            band.avalon_nano_mode = "managed_externally"
    
    if update.bitaxe_mode is not None:
        band.bitaxe_mode = update.bitaxe_mode
    
    if update.nerdqaxe_mode is not None:
        band.nerdqaxe_mode = update.nerdqaxe_mode
    
    if update.avalon_nano_mode is not None:
        band.avalon_nano_mode = update.avalon_nano_mode
    
    await db.commit()
    await db.refresh(band)
    
    return {
        "id": band.id,
        "sort_order": band.sort_order,
        "min_price": band.min_price,
        "max_price": band.max_price,
        "target_coin": band.target_coin,
        "bitaxe_mode": band.bitaxe_mode,
        "nerdqaxe_mode": band.nerdqaxe_mode,
        "avalon_nano_mode": band.avalon_nano_mode
    }


@router.post("/agile-solo-strategy/bands/reset")
async def reset_strategy_bands_api(db: AsyncSession = Depends(get_db)):
    """Reset all bands to default configuration"""
    from core.agile_bands import reset_bands_to_default
    
    # Get strategy
    result = await db.execute(select(AgileStrategy))
    strategy = result.scalar_one_or_none()
    
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    
    success = await reset_bands_to_default(db, strategy.id)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to reset bands")
    
    return {"message": "Bands reset to defaults"}


@router.delete("/agile-solo-strategy/bands/{band_id}")
async def delete_strategy_band(
    band_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Delete a band and compact sort order"""
    from core.database import AgileStrategyBand
    
    target_result = await db.execute(
        select(AgileStrategyBand)
        .where(AgileStrategyBand.id == band_id)
    )
    target_band = target_result.scalar_one_or_none()
    if not target_band:
        raise HTTPException(status_code=404, detail="Band not found")
    
    strategy_id = target_band.strategy_id
    
    remaining_result = await db.execute(
        select(AgileStrategyBand)
        .where(AgileStrategyBand.strategy_id == strategy_id)
        .order_by(AgileStrategyBand.sort_order)
    )
    bands = remaining_result.scalars().all()
    
    if len(bands) <= 1:
        raise HTTPException(status_code=400, detail="Cannot delete the final price band. Use reset instead.")
    
    await db.delete(target_band)
    await db.flush()
    
    # Fetch again after deletion for ordering
    remaining_result = await db.execute(
        select(AgileStrategyBand)
        .where(AgileStrategyBand.strategy_id == strategy_id)
        .order_by(AgileStrategyBand.sort_order)
    )
    remaining = remaining_result.scalars().all()
    
    for idx, band in enumerate(remaining):
        band.sort_order = idx
    
    await db.commit()
    
    return {"message": "Band deleted", "strategy_id": strategy_id, "remaining": len(remaining)}
