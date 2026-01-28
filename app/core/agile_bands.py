"""
Agile Strategy Band Management
Handles initialization and migration of configurable price bands
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
import logging

from core.database import AgileStrategy, AgileStrategyBand

logger = logging.getLogger(__name__)


# Valid coin options for Agile Solo Strategy (all Solopool)
VALID_COINS = ["OFF", "DGB", "BC2", "BCH", "BTC", "BTC_POOLED"]

# Valid modes per miner type
VALID_MODES = {
    "bitaxe": ["managed_externally", "eco", "standard", "turbo", "oc"],
    "nerdqaxe": ["managed_externally", "eco", "standard", "turbo", "oc"],
    "avalon_nano": ["managed_externally", "low", "med", "high"],
    "nmminer": ["fixed"]  # NMMiner has no configurable modes
}


DEFAULT_BANDS = [
    {
        "sort_order": 0,
        "min_price": 20.0,
        "max_price": None,  # No upper limit
        "target_coin": "OFF",
        "bitaxe_mode": "managed_externally",
        "nerdqaxe_mode": "managed_externally",
        "avalon_nano_mode": "managed_externally",
        "description": "Capital preservation (HA/external automation)"
    },
    {
        "sort_order": 1,
        "min_price": 12.0,
        "max_price": 20.0,
        "target_coin": "DGB",
        "bitaxe_mode": "eco",
        "nerdqaxe_mode": "eco",
        "avalon_nano_mode": "low",
        "description": "Frequent wins, low regret"
    },
    {
        "sort_order": 2,
        "min_price": 7.0,
        "max_price": 12.0,
        "target_coin": "DGB",
        "bitaxe_mode": "standard",
        "nerdqaxe_mode": "standard",
        "avalon_nano_mode": "med",
        "description": "Baseline probability"
    },
    {
        "sort_order": 3,
        "min_price": 4.0,
        "max_price": 7.0,
        "target_coin": "BCH",
        "bitaxe_mode": "oc",
        "nerdqaxe_mode": "standard",
        "avalon_nano_mode": "high",
        "description": "Meaningful upside"
    },
    {
        "sort_order": 4,
        "min_price": None,  # No lower limit
        "max_price": 4.0,
        "target_coin": "BTC",
        "bitaxe_mode": "oc",
        "nerdqaxe_mode": "oc",
        "avalon_nano_mode": "high",
        "description": "Jackpot probability"
    }
]


async def migrate_std_to_standard(db: AsyncSession) -> None:
    """
    Migration: Update 'std' mode to 'standard' for consistency with adapter
    """
    try:
        result = await db.execute(select(AgileStrategyBand))
        bands = result.scalars().all()
        
        updated_count = 0
        for band in bands:
            if band.bitaxe_mode == "std":
                band.bitaxe_mode = "standard"
                updated_count += 1
            if band.nerdqaxe_mode == "std":
                band.nerdqaxe_mode = "standard"
                updated_count += 1
        
        if updated_count > 0:
            await db.commit()
            logger.info(f"Migrated {updated_count} band mode(s) from 'std' to 'standard'")
    except Exception as e:
        logger.error(f"Failed to migrate std to standard: {e}")
        await db.rollback()


async def ensure_strategy_bands(db: AsyncSession, strategy_id: int) -> bool:
    """
    Ensure strategy has bands configured. Creates default bands if none exist.
    This handles migration from old versions and fresh installs.
    
    Args:
        db: Database session
        strategy_id: AgileStrategy ID
        
    Returns:
        True if bands exist or were created, False on error
    """
    try:
        # Run migration for existing bands
        await migrate_std_to_standard(db)
        
        # Check if bands already exist
        result = await db.execute(
            select(AgileStrategyBand)
            .where(AgileStrategyBand.strategy_id == strategy_id)
        )
        existing_bands = result.scalars().all()
        
        if existing_bands:
            logger.debug(f"Strategy {strategy_id} already has {len(existing_bands)} bands configured")
            return True
        
        # No bands exist - create defaults
        logger.info(f"Initializing default bands for strategy {strategy_id} (migration or fresh install)")
        
        for band_config in DEFAULT_BANDS:
            band = AgileStrategyBand(
                strategy_id=strategy_id,
                sort_order=band_config["sort_order"],
                min_price=band_config["min_price"],
                max_price=band_config["max_price"],
                target_coin=band_config["target_coin"],
                bitaxe_mode=band_config["bitaxe_mode"],
                nerdqaxe_mode=band_config["nerdqaxe_mode"],
                avalon_nano_mode=band_config["avalon_nano_mode"]
            )
            db.add(band)
        
        await db.commit()
        logger.info(f"Created {len(DEFAULT_BANDS)} default bands for strategy {strategy_id}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to ensure strategy bands: {e}")
        await db.rollback()
        return False


async def get_strategy_bands(db: AsyncSession, strategy_id: int) -> List[AgileStrategyBand]:
    """
    Get all bands for a strategy, ordered by sort_order
    
    Args:
        db: Database session
        strategy_id: AgileStrategy ID
        
    Returns:
        List of AgileStrategyBand objects
    """
    result = await db.execute(
        select(AgileStrategyBand)
        .where(AgileStrategyBand.strategy_id == strategy_id)
        .order_by(AgileStrategyBand.sort_order)
    )
    return result.scalars().all()


async def reset_bands_to_default(db: AsyncSession, strategy_id: int) -> bool:
    """
    Reset strategy bands to default configuration
    
    Args:
        db: Database session
        strategy_id: AgileStrategy ID
        
    Returns:
        True on success, False on error
    """
    try:
        # Delete existing bands
        result = await db.execute(
            select(AgileStrategyBand)
            .where(AgileStrategyBand.strategy_id == strategy_id)
        )
        existing_bands = result.scalars().all()
        
        for band in existing_bands:
            await db.delete(band)
        
        # Flush to ensure deletes are committed before inserts
        await db.flush()
        
        # Create default bands
        for band_config in DEFAULT_BANDS:
            band = AgileStrategyBand(
                strategy_id=strategy_id,
                sort_order=band_config["sort_order"],
                min_price=band_config["min_price"],
                max_price=band_config["max_price"],
                target_coin=band_config["target_coin"],
                bitaxe_mode=band_config["bitaxe_mode"],
                nerdqaxe_mode=band_config["nerdqaxe_mode"],
                avalon_nano_mode=band_config["avalon_nano_mode"]
            )
            db.add(band)
        
        await db.commit()
        logger.info(f"Reset strategy {strategy_id} to default bands")
        return True
        
    except Exception as e:
        logger.error(f"Failed to reset bands: {e}")
        await db.rollback()
        return False


def get_band_for_price(bands: List[AgileStrategyBand], price_p_kwh: float) -> AgileStrategyBand:
    """
    Find the appropriate band for a given price
    
    Args:
        bands: List of bands ordered by sort_order
        price_p_kwh: Current energy price in pence per kWh
        
    Returns:
        Matching AgileStrategyBand
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
