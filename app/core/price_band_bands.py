"""
Price Band Strategy Band Management
Handles initialization and migration of configurable price bands
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
import logging

from core.database import PriceBandStrategyConfig, PriceBandStrategyBand, StrategyBandModeTarget
from core.miner_capabilities import (
    get_strategy_mode_map,
)

logger = logging.getLogger(__name__)

def get_valid_modes() -> dict:
    """Return valid strategy modes by miner type from capability registry."""
    return get_strategy_mode_map()


# Backward-compatible exported constant for existing imports
VALID_MODES = get_valid_modes()


DEFAULT_BANDS = [
    {
        "sort_order": 1,
        "min_price": None,
        "max_price": 0.0,
        "target_pool_id": None,  # OFF
        "description": "Band 1 - 0 and under (negative pricing)"
    },
    {
        "sort_order": 2,
        "min_price": 0.0,
        "max_price": 5.0,
        "target_pool_id": None,  # OFF
        "description": "Band 2 - 0-5p"
    },
    {
        "sort_order": 3,
        "min_price": 5.0,
        "max_price": 10.0,
        "target_pool_id": None,  # OFF
        "description": "Band 3 - 5-10p"
    },
    {
        "sort_order": 4,
        "min_price": 10.0,
        "max_price": 20.0,
        "target_pool_id": None,  # OFF
        "description": "Band 4 - 10-20p"
    },
    {
        "sort_order": 5,
        "min_price": 20.0,
        "max_price": 30.0,
        "target_pool_id": None,  # OFF
        "description": "Band 5 - 20-30p"
    },
    {
        "sort_order": 6,
        "min_price": 30.0,
        "max_price": 999.0,
        "target_pool_id": None,  # OFF
        "description": "Band 6 - 30p and above"
    }
]


async def _sync_band_mode_targets(db: AsyncSession, bands: List[PriceBandStrategyBand]) -> None:
    """Ensure dynamic mode target rows exist for all strategy-capable miner types."""
    valid_mode_map = get_strategy_mode_map()

    for band in bands:
        for miner_type, allowed in valid_mode_map.items():
            if "managed_externally" in allowed:
                default_mode = "managed_externally"
            elif allowed:
                default_mode = allowed[0]
            else:
                continue

            existing_result = await db.execute(
                select(StrategyBandModeTarget)
                .where(StrategyBandModeTarget.band_id == band.id)
                .where(StrategyBandModeTarget.miner_type == miner_type)
            )
            existing = existing_result.scalar_one_or_none()
            if not existing:
                db.add(
                    StrategyBandModeTarget(
                        band_id=band.id,
                        miner_type=miner_type,
                        mode=default_mode,
                    )
                )


async def ensure_strategy_bands(db: AsyncSession, strategy_id: int) -> bool:
    """
    Ensure strategy has bands configured. Creates default bands if none exist.
    This handles migration from old versions and fresh installs.
    
    Args:
        db: Database session
        strategy_id: PriceBandStrategyConfig ID
        
    Returns:
        True if bands exist or were created, False on error
    """
    try:
        # Check if bands already exist
        result = await db.execute(
            select(PriceBandStrategyBand)
            .where(PriceBandStrategyBand.strategy_id == strategy_id)
        )
        existing_bands = result.scalars().all()
        
        if existing_bands:
            await _sync_band_mode_targets(db, existing_bands)
            await db.commit()
            logger.debug(f"Strategy {strategy_id} already has {len(existing_bands)} bands configured")
            return True
        
        # No bands exist - create defaults
        logger.info(f"Initializing default bands for strategy {strategy_id} (migration or fresh install)")
        
        for band_config in DEFAULT_BANDS:
            band = PriceBandStrategyBand(
                strategy_id=strategy_id,
                sort_order=band_config["sort_order"],
                min_price=band_config["min_price"],
                max_price=band_config["max_price"],
                target_pool_id=band_config["target_pool_id"],
            )
            db.add(band)
        
        await db.flush()

        created_result = await db.execute(
            select(PriceBandStrategyBand)
            .where(PriceBandStrategyBand.strategy_id == strategy_id)
            .order_by(PriceBandStrategyBand.sort_order)
        )
        created_bands = created_result.scalars().all()
        await _sync_band_mode_targets(db, created_bands)

        await db.commit()
        logger.info(f"Created {len(DEFAULT_BANDS)} default bands for strategy {strategy_id}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to ensure strategy bands: {e}")
        await db.rollback()
        return False


async def get_strategy_bands(db: AsyncSession, strategy_id: int) -> List[PriceBandStrategyBand]:
    """
    Get all bands for a strategy, ordered by sort_order
    
    Args:
        db: Database session
        strategy_id: PriceBandStrategyConfig ID
        
    Returns:
        List of PriceBandStrategyBand objects
    """
    result = await db.execute(
        select(PriceBandStrategyBand)
        .where(PriceBandStrategyBand.strategy_id == strategy_id)
        .order_by(PriceBandStrategyBand.sort_order)
    )
    return result.scalars().all()


async def reset_bands_to_default(db: AsyncSession, strategy_id: int) -> bool:
    """
    Reset strategy bands to default configuration
    
    Args:
        db: Database session
        strategy_id: PriceBandStrategyConfig ID
        
    Returns:
        True on success, False on error
    """
    try:
        # Delete existing bands
        result = await db.execute(
            select(PriceBandStrategyBand)
            .where(PriceBandStrategyBand.strategy_id == strategy_id)
        )
        existing_bands = result.scalars().all()
        
        for band in existing_bands:
            await db.delete(band)
        
        # Delete existing dynamic mode targets first
        for band in existing_bands:
            targets_result = await db.execute(
                select(StrategyBandModeTarget).where(StrategyBandModeTarget.band_id == band.id)
            )
            for target in targets_result.scalars().all():
                await db.delete(target)

        # Flush to ensure deletes are committed before inserts
        await db.flush()
        
        # Create default bands
        for band_config in DEFAULT_BANDS:
            band = PriceBandStrategyBand(
                strategy_id=strategy_id,
                sort_order=band_config["sort_order"],
                min_price=band_config["min_price"],
                max_price=band_config["max_price"],
                target_pool_id=band_config["target_pool_id"],
            )
            db.add(band)
        
        await db.flush()

        created_result = await db.execute(
            select(PriceBandStrategyBand)
            .where(PriceBandStrategyBand.strategy_id == strategy_id)
            .order_by(PriceBandStrategyBand.sort_order)
        )
        created_bands = created_result.scalars().all()
        await _sync_band_mode_targets(db, created_bands)

        await db.commit()
        logger.info(f"Reset strategy {strategy_id} to default bands")
        return True
        
    except Exception as e:
        logger.error(f"Failed to reset bands: {e}")
        await db.rollback()
        return False


def get_band_for_price(bands: List[PriceBandStrategyBand], price_p_kwh: float) -> PriceBandStrategyBand:
    """
    Find the appropriate band for a given price
    
    Args:
        bands: List of bands ordered by sort_order
        price_p_kwh: Current energy price in pence per kWh
        
    Returns:
        Matching PriceBandStrategyBand
    """
    for band in bands:
        # Check if price falls within this band
        min_ok = band.min_price is None or price_p_kwh >= band.min_price
        max_ok = band.max_price is None or price_p_kwh < band.max_price
        
        if min_ok and max_ok:
            return band
    
    # Fallback to first band if no match (shouldn't happen with proper config)
    logger.warning(f"No band found for price {price_p_kwh}p/kWh, using first band")
    return bands[0] if bands else None
