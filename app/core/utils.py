"""
Utility functions for Home Miner Manager
"""
from datetime import datetime
from typing import Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.sql import func


def format_time_elapsed(start_time: datetime, compact: bool = True) -> str:
    """
    Format elapsed time since start_time in compact P2Pool-style format.
    
    Args:
        start_time: The starting datetime (UTC)
        compact: If True, uses compact format (1m 35s, 1h 10m, 1d 10h 32m)
                 If False, uses format with "ago" suffix
    
    Returns:
        Formatted time string (e.g., "1m 35s", "1h 10m", "1d 10h 32m")
        Returns None if start_time is None
    
    Examples:
        - 45 seconds: "45s"
        - 5 minutes 30 seconds: "5m 30s"
        - 2 hours 15 minutes: "2h 15m"
        - 1 day 10 hours 32 minutes: "1d 10h 32m"
        - 3 days 0 hours 0 minutes: "3d"
    """
    if not start_time:
        return None
    
    elapsed = datetime.utcnow() - start_time
    total_seconds = int(elapsed.total_seconds())
    
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    
    if days > 0:
        if hours > 0 and minutes > 0:
            return f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            return f"{days}d {hours}h"
        else:
            return f"{days}d"
    elif hours > 0:
        if minutes > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{hours}h"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"


async def get_latest_telemetry_batch(
    db: AsyncSession, 
    miner_ids: List[int],
    cutoff: Optional[datetime] = None
) -> Dict[int, 'Telemetry']:
    """
    Get latest telemetry for multiple miners in a single query.
    
    This function eliminates N+1 query problems by fetching all telemetry
    records in a single batch query using a subquery + join pattern.
    
    Args:
        db: Database session
        miner_ids: List of miner IDs to fetch telemetry for
        cutoff: Optional timestamp cutoff (only return if newer than this)
    
    Returns:
        Dict mapping miner_id to latest Telemetry record
        
    Example:
        >>> telemetry_map = await get_latest_telemetry_batch(db, [1, 2, 3])
        >>> miner_1_telemetry = telemetry_map.get(1)  # Fast O(1) lookup
    
    Performance:
        - Before: N queries (one per miner)
        - After: 1 query (batch fetch)
        - Improvement: 10-50x faster for typical workloads
    """
    from core.database import Telemetry
    
    if not miner_ids:
        return {}
    
    # Subquery to get max timestamp per miner
    subq = (
        select(
            Telemetry.miner_id,
            func.max(Telemetry.timestamp).label('max_timestamp')
        )
        .where(Telemetry.miner_id.in_(miner_ids))
    )
    
    if cutoff:
        subq = subq.where(Telemetry.timestamp >= cutoff)
    
    subq = subq.group_by(Telemetry.miner_id).subquery()
    
    # Join to get full telemetry records
    query = (
        select(Telemetry)
        .join(
            subq,
            and_(
                Telemetry.miner_id == subq.c.miner_id,
                Telemetry.timestamp == subq.c.max_timestamp
            )
        )
    )
    
    result = await db.execute(query)
    telemetry_list = result.scalars().all()
    
    # Return as dict for easy O(1) lookup
    return {t.miner_id: t for t in telemetry_list}


async def get_latest_telemetry(
    db: AsyncSession, 
    miner_id: int,
    cutoff: Optional[datetime] = None
) -> Optional['Telemetry']:
    """
    Get most recent telemetry record for a single miner.
    
    Args:
        db: Database session
        miner_id: Miner ID
        cutoff: Optional timestamp cutoff (only return if newer than this)
    
    Returns:
        Latest Telemetry record or None
        
    Note:
        For multiple miners, use get_latest_telemetry_batch() instead
        to avoid N+1 query problems.
    """
    from core.database import Telemetry
    
    query = (
        select(Telemetry)
        .where(Telemetry.miner_id == miner_id)
    )
    
    if cutoff:
        query = query.where(Telemetry.timestamp >= cutoff)
    
    query = query.order_by(Telemetry.timestamp.desc()).limit(1)
    
    result = await db.execute(query)
    return result.scalar_one_or_none()


def format_hashrate(hashrate: float, unit: str = "GH/s") -> str:
    """
    Format hashrate with appropriate unit (GH/s or TH/s).
    
    Args:
        hashrate: Hashrate value
        unit: Base unit (default: GH/s)
    
    Returns:
        Formatted string (e.g., "1.5 TH/s", "500.00 GH/s")
    
    Examples:
        >>> format_hashrate(1500, "GH/s")
        "1.50 TH/s"
        >>> format_hashrate(500, "GH/s")
        "500.00 GH/s"
        >>> format_hashrate(500000, "KH/s")
        "500.00 MH/s"
    """
    if not hashrate:
        return f"0.00 {unit}"
    
    if unit == "GH/s" and hashrate >= 1000:
        return f"{hashrate / 1000:.2f} TH/s"
    elif unit == "KH/s" and hashrate >= 1000:
        return f"{hashrate / 1000:.2f} MH/s"
    elif unit == "MH/s" and hashrate >= 1000:
        return f"{hashrate / 1000:.2f} GH/s"
    
    return f"{hashrate:.2f} {unit}"


def get_recent_cutoff(minutes: int = 5) -> datetime:
    """
    Get cutoff timestamp for recent data (default: 5 minutes ago).
    
    Args:
        minutes: Number of minutes to go back
    
    Returns:
        Datetime representing N minutes ago (UTC)
    
    Example:
        >>> cutoff = get_recent_cutoff()  # 5 minutes ago
        >>> cutoff = get_recent_cutoff(10)  # 10 minutes ago
    """
    from datetime import timedelta
    return datetime.utcnow() - timedelta(minutes=minutes)


def get_daily_cutoff() -> datetime:
    """
    Get cutoff timestamp for daily data (24 hours ago).
    
    Returns:
        Datetime representing 24 hours ago (UTC)
    """
    from datetime import timedelta
    return datetime.utcnow() - timedelta(hours=24)


def get_weekly_cutoff() -> datetime:
    """
    Get cutoff timestamp for weekly data (7 days ago).
    
    Returns:
        Datetime representing 7 days ago (UTC)
    """
    from datetime import timedelta
    return datetime.utcnow() - timedelta(days=7)


async def get_cached_crypto_price(db: AsyncSession, coin_id: str) -> float:
    """
    Get cached cryptocurrency price from database.
    
    Args:
        db: Database session
        coin_id: Coin ID (bitcoin, bitcoin-cash, digibyte, monero)
    
    Returns:
        Price in GBP, or 0 if not found/cached
    
    Note:
        Prices are updated every 10 minutes by the scheduler.
        This avoids hitting CoinGecko rate limits.
    """
    from core.database import CryptoPrice
    
    result = await db.execute(
        select(CryptoPrice).where(CryptoPrice.coin_id == coin_id)
    )
    cached_price = result.scalar_one_or_none()
    
    if cached_price:
        return cached_price.price_gbp
    
    return 0.0
