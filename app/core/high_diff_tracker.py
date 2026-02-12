"""
High difficulty share tracking for leaderboard
"""
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
from typing import Optional
import logging
import aiohttp

from core.database import HighDiffShare, BlockFound, Miner, AsyncSessionLocal, AlertConfig, PoolBlockEffort

logger = logging.getLogger(__name__)

# Cache network difficulties (TTL: 10 minutes)
_network_diff_cache = {}
_cache_ttl = 600  # seconds


async def _send_block_found_notification(
    miner_name: str,
    coin: str,
    pool_name: str,
    difficulty: float,
    network_difficulty: float
):
    """Send notification when a block is found"""
    try:
        from core.notifications import NotificationService
        
        # Check if block_found alert is enabled
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(AlertConfig).where(
                    AlertConfig.alert_type == "block_found",
                    AlertConfig.enabled == True
                )
            )
            alert_config = result.scalar_one_or_none()
            
            if not alert_config:
                return  # Alert not enabled
        
        # Format message (note: says POTENTIAL until confirmed)
        message = (
            f"🎉 <b>POTENTIAL BLOCK!</b> 🎉\n\n"
            f"Miner: {miner_name}\n"
            f"Coin: {coin}\n"
            f"Pool: {pool_name}\n"
            f"Difficulty: {difficulty:,.0f}\n"
            f"Network: {network_difficulty:,.0f}\n"
            f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n"
            f"⏳ <i>Awaiting Solopool confirmation...</i>"
        )
        
        # Send to all enabled channels
        service = NotificationService()
        await service.send_notification("telegram", message, "block_found")
        await service.send_notification("discord", message.replace("<b>", "**").replace("</b>", "**").replace("<i>", "*").replace("</i>", "*"), "block_found")
        
    except Exception as e:
        logger.error(f"Failed to send block found notification: {e}")


async def get_network_difficulty(coin: str, force_fresh: bool = False) -> Optional[float]:
    """
    Fetch current network difficulty from blockchain APIs
    
    Args:
        coin: BTC, BCH, or DGB
    
    Returns:
        Network difficulty or None if unavailable
    """
    coin = coin.upper()
    
    # Check cache first (unless force_fresh)
    now = datetime.utcnow().timestamp()
    if not force_fresh and coin in _network_diff_cache:
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
            
            elif coin == "BC2":
                # Use Solopool.org BC2 API
                async with session.get("https://bc2.solopool.org/api/stats", timeout=5) as resp:
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
    Examples: "Solopool BTC" → "BTC", "Solopool BCH" → "BCH", "Braiins Pool BTC" → "BTC"
    """
    pool_upper = pool_name.upper()
    
    if "BTC" in pool_upper or "BITCOIN" in pool_upper or "SHA256" in pool_upper:
        return "BTC"
    elif "BCH" in pool_upper or "BITCOIN CASH" in pool_upper:
        return "BCH"
    elif "BC2" in pool_upper or "BITCOIN II" in pool_upper:
        return "BC2"
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
    # Check if this is actually a new personal best
    if previous_best is not None and difficulty <= previous_best:
        return  # Not a new record
    
    # Extract coin from pool name
    coin = extract_coin_from_pool_name(pool_name)
    
    # For high difficulty shares (>80% of cached network diff), always fetch fresh data
    # This prevents false negatives when network difficulty drops
    if network_difficulty and difficulty > (network_difficulty * 0.8):
        fresh_network_diff = await get_network_difficulty(coin, force_fresh=True)
        if fresh_network_diff:
            logger.info(f"High diff share detected - using fresh network diff: {fresh_network_diff:,.0f} (cached was {network_difficulty:,.0f})")
            network_difficulty = fresh_network_diff
    elif not network_difficulty:
        # Fetch if not provided at all
        network_difficulty = await get_network_difficulty(coin)
    
    # Check if this solves a block (share_diff >= network_diff)
    was_block_solve = False
    if network_difficulty and difficulty >= network_difficulty:
        was_block_solve = True
        logger.info(f"🏆 POTENTIAL BLOCK! Miner {miner_name} found block-level share with diff {difficulty:,.0f} (network: {network_difficulty:,.0f})")
        
        # Record block in blocks_found table with PENDING status
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
            status="pending",  # Pending until Solopool confirms
            timestamp=datetime.utcnow()
        )
        db.add(block)
        
        # Reset pool effort counter on block found
        await reset_pool_block_effort(db, pool_name)
        
        # Trigger block found notification (note: says POTENTIAL)
        await _send_block_found_notification(
            miner_name=miner_name,
            coin=coin,
            pool_name=pool_name,
            difficulty=difficulty,
            network_difficulty=network_difficulty
        )
        
        # Log system event
        from core.database import Event
        event = Event(
            event_type="info",
            source="mining",
            message=f"🏆 Potential block found! {miner_name} - {coin} (diff: {difficulty:,.0f}) - Awaiting confirmation"
        )
        db.add(event)
    
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
    
    # Log high diff share event (only if not a block - blocks already logged)
    if not was_block_solve:
        from core.database import Event
        percentage = (difficulty / network_difficulty * 100) if network_difficulty else 0
        event = Event(
            event_type="info",
            source="mining",
            message=f"⭐ High diff share: {miner_name} - {coin} ({percentage:.2f}% of network diff)"
        )
        db.add(event)
    
    # Keep only top 30 shares per miner (prevent infinite growth)
    # Delete older shares beyond the top 30
    with db.no_autoflush:
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
                
                # Mark as block solve if share difficulty >= network difficulty
                # This handles shares that were found before we tracked network difficulty
                if share.difficulty >= network_diff and not share.was_block_solve:
                    share.was_block_solve = True
                    logger.info(f"🏆 Marked share as block solve: {share.miner_name} ({share.coin}) - {share.difficulty:,.0f}")
                
                updated_count += 1
        except Exception as e:
            logger.warning(f"Failed to backfill network difficulty for share {share.id}: {e}")
    
    await db.commit()
    logger.info(f"✅ Backfilled network difficulty for {updated_count}/{len(shares_to_update)} shares")
    
    # Sync block solves to blocks_found table
    await sync_block_solves_to_blocks_found(db)


async def sync_block_solves_to_blocks_found(db: AsyncSession):
    """
    Sync shares marked as block solves to the blocks_found table
    Ensures Coin Hunter leaderboard includes all found blocks
    """
    # Get all shares marked as block solves
    result = await db.execute(
        select(HighDiffShare).where(HighDiffShare.was_block_solve == True)
    )
    block_shares = result.scalars().all()
    
    if not block_shares:
        logger.info("✅ No block solves to sync")
        return
    
    synced_count = 0
    for share in block_shares:
        # Check if block already exists in blocks_found
        existing = await db.execute(
            select(BlockFound).where(
                BlockFound.miner_id == share.miner_id,
                BlockFound.timestamp == share.timestamp,
                BlockFound.difficulty == share.difficulty
            )
        )
        
        if existing.scalar_one_or_none():
            continue  # Already exists
        
        # Create BlockFound entry
        block = BlockFound(
            miner_id=share.miner_id,
            miner_name=share.miner_name,
            miner_type=share.miner_type,
            coin=share.coin,
            pool_name=share.pool_name,
            difficulty=share.difficulty,
            network_difficulty=share.network_difficulty,
            block_height=None,
            block_reward=None,
            hashrate=share.hashrate,
            hashrate_unit=share.hashrate_unit,
            miner_mode=share.miner_mode,
            timestamp=share.timestamp
        )
        db.add(block)
        synced_count += 1
        logger.info(f"🏆 Synced block solve to Coin Hunter: {share.miner_name} ({share.coin}) - {share.difficulty:,.0f}")
    
    await db.commit()
    logger.info(f"✅ Synced {synced_count} block solves to Coin Hunter leaderboard")


async def update_pool_block_effort(
    db: AsyncSession,
    pool_name: str,
    coin: str,
    new_shares: int,
    pool_difficulty: float,
    network_difficulty: Optional[float] = None
):
    """
    Update cumulative block effort for a pool (all miners combined)
    
    Args:
        db: Database session
        pool_name: Pool name (e.g., "MMSP DGB Local Solo Pool")
        coin: Coin being mined (BTC, BCH, DGB, BC2)
        new_shares: Number of new shares accepted this telemetry cycle
        pool_difficulty: Pool share difficulty
        network_difficulty: Current network difficulty (fetched if not provided)
    """
    if new_shares <= 0:
        return  # No new shares to add
    
    # Fetch or create pool effort record
    result = await db.execute(
        select(PoolBlockEffort).where(PoolBlockEffort.pool_name == pool_name)
    )
    effort = result.scalar_one_or_none()
    
    if not effort:
        # Create new effort tracking for this pool
        effort = PoolBlockEffort(
            pool_name=pool_name,
            coin=coin,
            effort_start=datetime.utcnow(),
            total_shares_accepted=0,
            total_hashes="0",
            blocks_equivalent=0.0,
            last_updated=datetime.utcnow()
        )
        db.add(effort)
    
    # Calculate new hashes: shares × pool_difficulty × 2^32
    new_hashes = int(new_shares * pool_difficulty * (2 ** 32))
    
    # Update totals
    effort.total_shares_accepted += new_shares
    effort.total_hashes = str(int(effort.total_hashes) + new_hashes)
    effort.last_updated = datetime.utcnow()
    
    # Fetch fresh network difficulty if not provided
    if not network_difficulty:
        network_difficulty = await get_network_difficulty(coin)
    
    if network_difficulty:
        effort.current_network_difficulty = network_difficulty
        
        # Calculate blocks equivalent: total_hashes / (net_diff × 2^32)
        network_hashes = network_difficulty * (2 ** 32)
        effort.blocks_equivalent = int(effort.total_hashes) / network_hashes
    
    logger.debug(f"Updated pool effort: {pool_name} - {effort.blocks_equivalent:.2f}× blocks ({effort.total_shares_accepted:,} shares)")


async def reset_pool_block_effort(
    db: AsyncSession,
    pool_name: str
):
    """
    Reset pool effort counter when a block is found
    
    Args:
        db: Database session
        pool_name: Pool name to reset
    """
    result = await db.execute(
        select(PoolBlockEffort).where(PoolBlockEffort.pool_name == pool_name)
    )
    effort = result.scalar_one_or_none()
    
    if effort:
        logger.info(f"🔄 Resetting pool effort for {pool_name} (was {effort.blocks_equivalent:.2f}× blocks)")
        
        effort.last_reset = datetime.utcnow()
        effort.effort_start = datetime.utcnow()
        effort.total_shares_accepted = 0
        effort.total_hashes = "0"
        effort.blocks_equivalent = 0.0
        effort.last_updated = datetime.utcnow()
