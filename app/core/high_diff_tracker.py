"""
High difficulty share tracking for leaderboard
"""
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
from typing import Optional
import logging
import aiohttp

from core.database import HighDiffShare, BlockFound, Miner

logger = logging.getLogger(__name__)

# Cache network difficulties (TTL: 10 minutes)
_network_diff_cache = {}
_cache_ttl = 600  # seconds


async def get_network_difficulty(coin: str) -> Optional[float]:
    """
    Fetch current network difficulty from blockchain APIs
    
    Args:
        coin: BTC, BCH, or DGB
    
    Returns:
        Network difficulty or None if unavailable
    """
    coin = coin.upper()
    
    # Check cache first
    now = datetime.utcnow().timestamp()
    if coin in _network_diff_cache:
        cached_diff, cache_time = _network_diff_cache[coin]
        if now - cache_time < _cache_ttl:
            return cached_diff
    
    try:
        async with aiohttp.ClientSession() as session:
            if coin == "BTC":
                # Use Solopool.org BTC API
                async with session.get("https://btc.solopool.org/api/stats", timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        diff = float(data.get("stats", {}).get("difficulty", 0))
                        if diff > 0:
                            _network_diff_cache[coin] = (diff, now)
                            return diff
            
            elif coin == "BCH":
                # Use Solopool.org BCH API
                async with session.get("https://bch.solopool.org/api/stats", timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        diff = float(data.get("stats", {}).get("difficulty", 0))
                        if diff > 0:
                            _network_diff_cache[coin] = (diff, now)
                            return diff
            
            elif coin == "DGB":
                # Use Solopool.org DGB API
                async with session.get("https://dgb-sha.solopool.org/api/stats", timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        diff = float(data.get("stats", {}).get("difficulty", 0))
                        if diff > 0:
                            _network_diff_cache[coin] = (diff, now)
                            return diff
    
    except Exception as e:
        logger.warning(f"Failed to fetch network difficulty for {coin}: {e}")
    
    return None


def extract_coin_from_pool_name(pool_name: str) -> str:
    """
    Extract coin symbol from pool name
    Examples: "Solopool BTC" → "BTC", "CKPool SHA256" → "BTC", "Solopool BCH" → "BCH"
    """
    pool_upper = pool_name.upper()
    
    if "BTC" in pool_upper or "BITCOIN" in pool_upper or "SHA256" in pool_upper:
        return "BTC"
    elif "BCH" in pool_upper or "BITCOIN CASH" in pool_upper:
        return "BCH"
    elif "DGB" in pool_upper or "DIGIBYTE" in pool_upper:
        return "DGB"
    else:
        return "BTC"  # Default fallback


async def track_high_diff_share(
    db: AsyncSession,
    miner_id: int,
    miner_name: str,
    miner_type: str,
    pool_name: str,
    difficulty: float,
    network_difficulty: Optional[float],
    hashrate: Optional[float],
    hashrate_unit: str,
    miner_mode: Optional[str],
    previous_best: Optional[float] = None
):
    """
    Track a new high difficulty share if it's better than the miner's previous best
    
    Args:
        db: Database session
        miner_id: Miner ID
        miner_name: Miner name (snapshot)
        miner_type: avalon_nano, bitaxe, nerdqaxe
        pool_name: Pool name to extract coin from
        difficulty: Share difficulty
        network_difficulty: Network difficulty at time (if available)
        hashrate: Miner hashrate at time
        hashrate_unit: GH/s, TH/s, etc
        miner_mode: eco/std/turbo/oc/low/med/high
        previous_best: Previous best diff (to check if this is actually new)
    """
    # Only track ASIC miners (not XMRig)
    if miner_type == "xmrig":
        return
    
    # Check if this is actually a new personal best
    if previous_best is not None and difficulty <= previous_best:
        return  # Not a new record
    
    # Extract coin from pool name
    coin = extract_coin_from_pool_name(pool_name)
    
    # Fetch current network difficulty from blockchain API if not provided
    if not network_difficulty:
        network_difficulty = await get_network_difficulty(coin)
    
    # Check if this solves a block (share_diff >= network_diff)
    was_block_solve = False
    if network_difficulty and difficulty >= network_difficulty:
        was_block_solve = True
        logger.info(f"🏆 BLOCK SOLVE! Miner {miner_name} found block with diff {difficulty:,.0f} (network: {network_difficulty:,.0f})")
        
        # Record block in blocks_found table
        block = BlockFound(
            miner_id=miner_id,
            miner_name=miner_name,
            miner_type=miner_type,
            coin=coin,
            pool_name=pool_name,
            difficulty=difficulty,
            network_difficulty=network_difficulty,
            block_height=None,  # Could be populated from pool API later
            block_reward=None,  # Could be populated from pool API later
            hashrate=hashrate,
            hashrate_unit=hashrate_unit,
            miner_mode=miner_mode,
            timestamp=datetime.utcnow()
        )
        db.add(block)
    
    # Create new high diff share entry
    new_share = HighDiffShare(
        miner_id=miner_id,
        miner_name=miner_name,
        miner_type=miner_type,
        coin=coin,
        pool_name=pool_name,
        difficulty=difficulty,
        network_difficulty=network_difficulty,
        was_block_solve=was_block_solve,
        hashrate=hashrate,
        hashrate_unit=hashrate_unit,
        miner_mode=miner_mode,
        timestamp=datetime.utcnow()
    )
    
    db.add(new_share)
    
    # Keep only top 30 shares per miner (prevent infinite growth)
    # Delete older shares beyond the top 30
    result = await db.execute(
        select(HighDiffShare)
        .where(HighDiffShare.miner_id == miner_id)
        .order_by(HighDiffShare.difficulty.desc())
    )
    all_shares = result.scalars().all()
    
    if len(all_shares) > 30:
        # Keep top 30, delete the rest
        shares_to_delete = all_shares[30:]
        for share in shares_to_delete:
            await db.delete(share)
    
    await db.commit()
    
    logger.info(f"📊 New high diff share: {miner_name} ({coin}) - {difficulty:,.0f}")


async def get_leaderboard(
    db: AsyncSession,
    days: int = 90,
    coin: Optional[str] = None,
    limit: int = 10
):
    """
    Get top high diff shares from last X days
    
    Args:
        db: Database session
        days: Number of days to look back (default 90)
        coin: Filter by coin (BTC/BCH/DGB) or None for all
        limit: Number of entries to return (default 10)
    
    Returns:
        List of high diff shares ordered by difficulty descending
    """
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    query = select(HighDiffShare).where(HighDiffShare.timestamp >= cutoff_date)
    
    if coin:
        query = query.where(HighDiffShare.coin == coin.upper())
    
    query = query.order_by(HighDiffShare.difficulty.desc()).limit(limit)
    
    result = await db.execute(query)
    return result.scalars().all()


async def cleanup_old_shares(db: AsyncSession, days: int = 180):
    """
    Delete shares older than X days to prevent unbounded growth
    Run this periodically (e.g., daily)
    
    Args:
        db: Database session
        days: Delete shares older than this (default 180 days)
    """
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    await db.execute(
        delete(HighDiffShare).where(HighDiffShare.timestamp < cutoff_date)
    )
    await db.commit()
    
    logger.info(f"🧹 Cleaned up high diff shares older than {days} days")


async def backfill_network_difficulty(db: AsyncSession):
    """
    Backfill network difficulty for existing shares that don't have it
    This allows % of Block calculation for historical shares
    """
    # Get all shares without network_difficulty
    result = await db.execute(
        select(HighDiffShare).where(HighDiffShare.network_difficulty.is_(None))
    )
    shares_to_update = result.scalars().all()
    
    if not shares_to_update:
        logger.info("✅ All shares already have network difficulty")
        return
    
    logger.info(f"🔄 Backfilling network difficulty for {len(shares_to_update)} shares...")
    
    updated_count = 0
    for share in shares_to_update:
        try:
            # Fetch current network difficulty for this coin
            network_diff = await get_network_difficulty(share.coin)
            
            if network_diff:
                share.network_difficulty = network_diff
                # NOTE: Do NOT retroactively mark as block solve - difficulty changes over time
                # The was_block_solve flag should only be set when the share is initially tracked
                
                updated_count += 1
        except Exception as e:
            logger.warning(f"Failed to backfill network difficulty for share {share.id}: {e}")
    
    await db.commit()
    logger.info(f"✅ Backfilled network difficulty for {updated_count}/{len(shares_to_update)} shares")
