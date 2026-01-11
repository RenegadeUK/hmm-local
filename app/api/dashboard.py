"""
Dashboard and analytics API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta, timezone
import logging

from core.database import get_db, Miner, Telemetry, EnergyPrice, Event, HighDiffShare, AgileStrategy


router = APIRouter()


def parse_coin_from_pool(pool_url: str) -> str:
    """Extract coin symbol from pool URL"""
    if not pool_url:
        return None
    
    pool_url = pool_url.lower()
    
    # Braiins Pool patterns
    if "braiins" in pool_url or "slushpool" in pool_url:
        return "BTC"
    
    # Solopool.org patterns
    if "dgb" in pool_url:
        return "DGB"
    elif "bch" in pool_url or "eu2.solopool.org" in pool_url:
        return "BCH"
    elif "btc" in pool_url:
        return "BTC"
    elif "eu1.solopool.org" in pool_url or "us1.solopool.org" in pool_url:
        # Default to DGB for shared pools
        return "DGB"
    
    return None


async def get_best_share_24h(db: AsyncSession) -> dict:
    """
    Get best difficulty share in last 24 hours for ASIC dashboard
    Uses HighDiffShare table which tracks when shares were actually found
    """
    from core.high_diff_tracker import get_network_difficulty
    
    # Query HighDiffShare table for actual share finds in last 24h
    cutoff_24h = datetime.utcnow() - timedelta(hours=24)
    
    result = await db.execute(
        select(HighDiffShare)
        .where(HighDiffShare.timestamp > cutoff_24h)
        .order_by(HighDiffShare.difficulty.desc())
        .limit(1)
    )
    best_share = result.scalar_one_or_none()
    
    if not best_share:
        return {
            "difficulty": 0,
            "coin": None,
            "network_difficulty": None,
            "percentage": 0.0,
            "timestamp": None,
            "time_ago_seconds": None
        }
    
    # Get current network difficulty for the coin (use cached value if recent)
    network_diff = best_share.network_difficulty
    if not network_diff or network_diff == 0:
        network_diff = await get_network_difficulty(best_share.coin)
    
    # Calculate percentage
    percentage = 0.0
    if network_diff and network_diff > 0:
        percentage = (best_share.difficulty / network_diff) * 100
    
    # Calculate time ago
    time_ago_seconds = int((datetime.utcnow() - best_share.timestamp).total_seconds())
    
    return {
        "difficulty": best_share.difficulty,
        "coin": best_share.coin,
        "network_difficulty": network_diff,
        "percentage": round(percentage, 2),
        "timestamp": best_share.timestamp.isoformat(),
        "time_ago_seconds": time_ago_seconds
    }


@router.get("/stats")
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)):
    """Get overall dashboard statistics"""
    # Count miners
    result = await db.execute(select(func.count(Miner.id)))
    total_miners = result.scalar()
    
    result = await db.execute(select(func.count(Miner.id)).where(Miner.enabled == True))
    active_miners = result.scalar()
    
    # Get latest telemetry for each miner for total hashrate
    # Use a subquery to get the latest timestamp per miner, then sum their hashrates
    from sqlalchemy import and_
    
    # Get latest telemetry for each enabled miner
    total_hashrate = 0.0
    total_power_watts = 0.0
    online_miners = 0
    result = await db.execute(select(Miner).where(Miner.enabled == True))
    miners = result.scalars().all()
    
    cutoff = datetime.utcnow() - timedelta(minutes=5)
    for miner in miners:
        result = await db.execute(
            select(Telemetry.hashrate, Telemetry.power_watts)
            .where(Telemetry.miner_id == miner.id)
            .where(Telemetry.timestamp > cutoff)
            .order_by(Telemetry.timestamp.desc())
            .limit(1)
        )
        latest_data = result.first()
        if latest_data and latest_data[0]:  # If hashrate exists
            latest_hashrate, latest_power = latest_data
            total_hashrate += latest_hashrate
            # Only count power for ASIC miners (exclude xmrig)
            if miner.miner_type != 'xmrig' and latest_power:
                total_power_watts += latest_power
            online_miners += 1
    
    # Calculate average efficiency (W/TH) for ASIC miners
    # Efficiency = Watts / Hashrate_TH = Watts per Terahash
    avg_efficiency_wth = None
    if total_hashrate > 0 and total_power_watts > 0:
        hashrate_ths = total_hashrate / 1000.0  # Convert GH/s to TH/s
        avg_efficiency_wth = total_power_watts / hashrate_ths
    
    # Get current energy price
    now = datetime.utcnow()
    result = await db.execute(
        select(EnergyPrice.price_pence)
        .where(EnergyPrice.valid_from <= now)
        .where(EnergyPrice.valid_to > now)
        .limit(1)
    )
    current_price = result.scalar()
    
    # Count recent events
    cutoff_24h = datetime.utcnow() - timedelta(hours=24)
    result = await db.execute(
        select(func.count(Event.id))
        .where(Event.timestamp > cutoff_24h)
    )
    recent_events = result.scalar()
    
    # Pre-fetch all energy prices for the last 24 hours (avoid N queries per telemetry record)
    result = await db.execute(
        select(EnergyPrice)
        .where(EnergyPrice.valid_from >= cutoff_24h)
        .order_by(EnergyPrice.valid_from)
    )
    energy_prices = result.scalars().all()
    
    # Create a lookup function for energy prices
    def get_price_for_timestamp(ts):
        for price in energy_prices:
            if price.valid_from <= ts < price.valid_to:
                return price.price_pence
        return None
    
    # Calculate total 24h cost across all miners using actual telemetry + energy prices
    total_cost_pence = 0.0
    total_kwh_consumed_24h = 0.0
    for miner in miners:
        # Get telemetry for last 24 hours
        result = await db.execute(
            select(Telemetry.power_watts, Telemetry.timestamp)
            .where(Telemetry.miner_id == miner.id)
            .where(Telemetry.timestamp > cutoff_24h)
            .order_by(Telemetry.timestamp)
        )
        telemetry_records = result.all()
        
        if not telemetry_records:
            continue
        
        # Calculate cost by matching each telemetry reading with the energy price that was active at that time
        for i, (power, timestamp) in enumerate(telemetry_records):
            if power is None or power <= 0:
                continue
            
            # Find the energy price that was active when this telemetry was recorded
            price_pence = get_price_for_timestamp(timestamp)
            
            if price_pence is None:
                # No price data for this timestamp, skip
                continue
            
            # Calculate duration until next telemetry reading (or assume 30s if it's the last one)
            if i < len(telemetry_records) - 1:
                next_timestamp = telemetry_records[i + 1][1]
                duration_seconds = (next_timestamp - timestamp).total_seconds()
                duration_hours = duration_seconds / 3600.0
            else:
                # Last reading, assume 30 second interval
                duration_hours = 30.0 / 3600.0
            
            # Calculate cost: (power_watts / 1000) * duration_hours * price_pence_per_kwh
            kwh = (power / 1000.0) * duration_hours
            cost = kwh * price_pence
            total_cost_pence += cost
            total_kwh_consumed_24h += kwh
    
    # Calculate 24h earnings (from Braiins Pool + Solopool blocks found)
    # ASIC dashboard: only count earnings from pools used by ASIC miners (exclude XMRig)
    earnings_pounds_24h = 0.0
    try:
        from core.braiins import get_braiins_stats
        from core.config import app_config
        from core.database import CryptoPrice
        
        # Get pool IDs that ASIC miners are actually using
        from core.database import MinerPoolSlot
        result = await db.execute(
            select(MinerPoolSlot.pool_id).distinct()
            .join(Miner)
            .where(Miner.enabled == True)
            .where(Miner.miner_type != 'xmrig')  # Exclude XMRig from ASIC dashboard
        )
        asic_pool_ids = {pool_id for (pool_id,) in result.all()}
        
        # Get crypto prices for earnings calculation from database
        btc_price_gbp = 0
        bch_price_gbp = 0
        dgb_price_gbp = 0
        xmr_price_gbp = 0
        
        # Fetch from database
        result = await db.execute(select(CryptoPrice).where(CryptoPrice.coin_id == "bitcoin"))
        btc_cached = result.scalar_one_or_none()
        if btc_cached:
            btc_price_gbp = btc_cached.price_gbp
        
        result = await db.execute(select(CryptoPrice).where(CryptoPrice.coin_id == "bitcoin-cash"))
        bch_cached = result.scalar_one_or_none()
        if bch_cached:
            bch_price_gbp = bch_cached.price_gbp
        
        result = await db.execute(select(CryptoPrice).where(CryptoPrice.coin_id == "digibyte"))
        dgb_cached = result.scalar_one_or_none()
        if dgb_cached:
            dgb_price_gbp = dgb_cached.price_gbp
        
        result = await db.execute(select(CryptoPrice).where(CryptoPrice.coin_id == "monero"))
        xmr_cached = result.scalar_one_or_none()
        if xmr_cached:
            xmr_price_gbp = xmr_cached.price_gbp
        
        # 1. Braiins Pool earnings (only if ASIC miners use it)
        braiins_enabled = app_config.get("braiins_enabled", False)
        if braiins_enabled and btc_price_gbp > 0:
            braiins_stats = await get_braiins_stats(db)
            if braiins_stats and "today_reward" in braiins_stats:
                # today_reward is in satoshis
                btc_earned_24h = braiins_stats["today_reward"] / 100000000
                earnings_pounds_24h += btc_earned_24h * btc_price_gbp
        
        # 2. SupportXMR Pool earnings (skip - only for XMRig/CPU miners)
        # ASIC dashboard shouldn't show XMR earnings
        
        # 3. Solopool earnings (only from pools ASIC miners are using)
        result = await db.execute(select(Pool).where(Pool.id.in_(asic_pool_ids)) if asic_pool_ids else select(Pool).where(False))
        asic_pools = result.scalars().all()
        
        # Check if any miners are using Solopool and fetch their stats
        from core.solopool import SolopoolService
        from core.database import Pool
        
        # Track unique Solopool usernames to avoid double-counting
        solopool_users_checked = set()
        
        for pool in asic_pools:
            # Check which Solopool coin this is
            is_bch = SolopoolService.is_solopool_bch_pool(pool.url, pool.port)
            is_dgb = SolopoolService.is_solopool_dgb_pool(pool.url, pool.port)
            is_btc = SolopoolService.is_solopool_btc_pool(pool.url, pool.port)
            is_xmr = SolopoolService.is_solopool_xmr_pool(pool.url, pool.port)
            
            if not (is_bch or is_dgb or is_btc or is_xmr):
                continue
            
            # Extract username from pool.user
            username = SolopoolService.extract_username(pool.user)
            if not username or username in solopool_users_checked:
                continue
            
            solopool_users_checked.add(username)
            
            # Fetch account stats and calculate earnings from blocks found in last 24h only
            if is_bch and bch_price_gbp > 0:
                raw_stats = await SolopoolService.get_bch_account_stats(username)
                if raw_stats:
                    stats = SolopoolService.format_stats_summary(raw_stats)
                    blocks_24h = stats.get("blocks_24h", 0)
                    # BCH block reward: 3.125 BCH (post-2024 halving)
                    earned_24h_bch = blocks_24h * 3.125
                    earnings_pounds_24h += earned_24h_bch * bch_price_gbp
            elif is_dgb and dgb_price_gbp > 0:
                raw_stats = await SolopoolService.get_dgb_account_stats(username)
                if raw_stats:
                    stats = SolopoolService.format_stats_summary(raw_stats)
                    blocks_24h = stats.get("blocks_24h", 0)
                    # DGB block reward: 277.376 DGB (current as of January 2025, post-halving)
                    earned_24h_dgb = blocks_24h * 277.376
                    earnings_pounds_24h += earned_24h_dgb * dgb_price_gbp
            elif is_btc and btc_price_gbp > 0:
                raw_stats = await SolopoolService.get_btc_account_stats(username)
                if raw_stats:
                    stats = SolopoolService.format_stats_summary(raw_stats)
                    blocks_24h = stats.get("blocks_24h", 0)
                    # BTC block reward: 3.125 BTC (post-2024 halving)
                    earned_24h_btc = blocks_24h * 3.125
                    earnings_pounds_24h += earned_24h_btc * btc_price_gbp
            elif is_xmr and xmr_price_gbp > 0:
                raw_stats = await SolopoolService.get_xmr_account_stats(username)
                if raw_stats:
                    stats = SolopoolService.format_stats_summary(raw_stats)
                    blocks_24h = stats.get("blocks_24h", 0)
                    # XMR block reward: ~0.6 XMR (emission curve, approximate)
                    earned_24h_xmr = blocks_24h * 0.6
                    earnings_pounds_24h += earned_24h_xmr * xmr_price_gbp
        
    except Exception as e:
        logging.error(f"Error calculating 24h earnings: {e}")
    
    # Calculate P/L (earnings - cost)
    pl_pounds_24h = earnings_pounds_24h - (total_cost_pence / 100)
    
    # Calculate average price per kWh (weighted by consumption)
    avg_price_per_kwh = None
    if total_kwh_consumed_24h > 0:
        avg_price_per_kwh = total_cost_pence / total_kwh_consumed_24h
    
    # Calculate P/L (earnings - cost)
    pl_pounds_24h = earnings_pounds_24h - (total_cost_pence / 100)
    
    # Calculate average miner health (using latest health score for each ASIC miner)
    # Exclude XMRig miners for now - they use different scoring weights
    from core.database import HealthScore
    avg_miner_health = None
    
    # Get all ASIC miners (exclude XMRig)
    result = await db.execute(select(Miner).where(Miner.miner_type != 'xmrig'))
    asic_miners = result.scalars().all()
    
    # Get latest health score for each ASIC miner
    miner_health_scores = []
    for miner in asic_miners:
        result = await db.execute(
            select(HealthScore.overall_score)
            .where(HealthScore.miner_id == miner.id)
            .order_by(HealthScore.timestamp.desc())
            .limit(1)
        )
        latest_score = result.scalar()
        if latest_score is not None:
            miner_health_scores.append(latest_score)
    
    # Calculate average of latest scores
    if miner_health_scores:
        avg_miner_health = sum(miner_health_scores) / len(miner_health_scores)
    
    # Calculate average pool health (using latest health score for each pool)
    from core.database import PoolHealth, Pool
    avg_pool_health = None
    
    # Get all pools
    result = await db.execute(select(Pool))
    all_pools = result.scalars().all()
    
    # Get latest health score for each pool
    pool_health_scores = []
    for pool in all_pools:
        result = await db.execute(
            select(PoolHealth.health_score)
            .where(PoolHealth.pool_id == pool.id)
            .order_by(PoolHealth.timestamp.desc())
            .limit(1)
        )
        latest_score = result.scalar()
        if latest_score is not None:
            pool_health_scores.append(latest_score)
    
    # Calculate average of latest scores
    if pool_health_scores:
        avg_pool_health = sum(pool_health_scores) / len(pool_health_scores)
    
    # Get best share in last 24h (ASIC only)
    best_share_24h = await get_best_share_24h(db)
    
    return {
        "total_miners": total_miners,
        "active_miners": active_miners,
        "online_miners": online_miners,
        "total_hashrate_ghs": round(total_hashrate, 2),
        "total_power_watts": round(total_power_watts, 1),
        "avg_efficiency_wth": round(avg_efficiency_wth, 1) if avg_efficiency_wth is not None else None,
        "current_energy_price_pence": current_price,
        "avg_price_per_kwh_pence": round(avg_price_per_kwh, 2) if avg_price_per_kwh is not None else None,
        "recent_events_24h": recent_events,
        "total_cost_24h_pence": round(total_cost_pence, 2),
        "total_cost_24h_pounds": round(total_cost_pence / 100, 2),
        "earnings_24h_pounds": round(earnings_pounds_24h, 2),
        "pl_24h_pounds": round(pl_pounds_24h, 2),
        "avg_miner_health": round(avg_miner_health, 1) if avg_miner_health is not None else None,
        "avg_pool_health": round(avg_pool_health, 1) if avg_pool_health is not None else None,
        "best_share_24h": best_share_24h
    }


@router.get("/energy/current")
async def get_current_energy_price(db: AsyncSession = Depends(get_db)):
    """Get current energy price slot"""
    from core.config import app_config
    
    region = app_config.get("octopus_agile.region", "H")
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(EnergyPrice)
        .where(EnergyPrice.region == region)
        .where(EnergyPrice.valid_from <= now)
        .where(EnergyPrice.valid_to > now)
        .limit(1)
    )
    price = result.scalar_one_or_none()
    
    if not price:
        return {"price_pence": None, "valid_from": None, "valid_to": None}
    
    return {
        "price_pence": price.price_pence,
        "valid_from": price.valid_from.isoformat(),
        "valid_to": price.valid_to.isoformat()
    }


@router.get("/energy/next")
async def get_next_energy_price(db: AsyncSession = Depends(get_db)):
    """Get next energy price slot"""
    from core.config import app_config
    
    region = app_config.get("octopus_agile.region", "H")
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(EnergyPrice)
        .where(EnergyPrice.region == region)
        .where(EnergyPrice.valid_from > now)
        .order_by(EnergyPrice.valid_from)
        .limit(1)
    )
    price = result.scalar_one_or_none()
    
    if not price:
        return {"price_pence": None, "valid_from": None, "valid_to": None}
    
    return {
        "price_pence": price.price_pence,
        "valid_from": price.valid_from.isoformat(),
        "valid_to": price.valid_to.isoformat()
    }


@router.get("/energy/timeline")
async def get_energy_timeline(db: AsyncSession = Depends(get_db)):
    """Get energy price timeline grouped by today and tomorrow"""
    from core.config import app_config
    import logging
    logger = logging.getLogger(__name__)
    
    region = app_config.get("octopus_agile.region", "H")
    now = datetime.now(timezone.utc)
    
    # Calculate day boundaries (timezone-aware)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + timedelta(days=1)
    day_after_start = today_start + timedelta(days=2)
    
    logger.info(f"Energy timeline query - Region: {region}, Tomorrow: {tomorrow_start} to {day_after_start}")
    
    # Get today's prices
    result = await db.execute(
        select(EnergyPrice)
        .where(EnergyPrice.region == region)
        .where(EnergyPrice.valid_from >= today_start)
        .where(EnergyPrice.valid_from < tomorrow_start)
        .order_by(EnergyPrice.valid_from)
    )
    today_prices = result.scalars().all()
    
    # Get tomorrow's prices
    result = await db.execute(
        select(EnergyPrice)
        .where(EnergyPrice.region == region)
        .where(EnergyPrice.valid_from >= tomorrow_start)
        .where(EnergyPrice.valid_from < day_after_start)
        .order_by(EnergyPrice.valid_from)
    )
    tomorrow_prices = result.scalars().all()
    
    # Debug: check total count in DB
    debug_result = await db.execute(
        select(func.count()).select_from(EnergyPrice).where(EnergyPrice.region == region)
    )
    total_count = debug_result.scalar()
    logger.info(f"Total prices in DB for region {region}: {total_count}")
    logger.info(f"Found {len(today_prices)} today prices, {len(tomorrow_prices)} tomorrow prices")
    
    return {
        "today": {
            "date": today_start.strftime("%A, %d %B %Y"),
            "prices": [
                {
                    "valid_from": p.valid_from.isoformat(),
                    "valid_to": p.valid_to.isoformat(),
                    "price_pence": p.price_pence
                }
                for p in today_prices
            ]
        },
        "tomorrow": {
            "date": tomorrow_start.strftime("%A, %d %B %Y"),
            "prices": [
                {
                    "valid_from": p.valid_from.isoformat(),
                    "valid_to": p.valid_to.isoformat(),
                    "price_pence": p.price_pence
                }
                for p in tomorrow_prices
            ]
        }
    }


@router.get("/energy/config")
async def get_energy_config():
    """Get current Octopus Agile configuration"""
    from core.config import app_config
    
    return {
        "enabled": app_config.get("octopus_agile.enabled", False),
        "region": app_config.get("octopus_agile.region", "H")
    }


@router.post("/energy/region")
async def set_energy_region(region: str):
    """Set Octopus Agile region"""
    from core.config import app_config, save_config
    from core.scheduler import scheduler
    
    # Validate region
    valid_regions = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'J', 'K', 'L', 'M', 'N', 'P']
    if region not in valid_regions:
        raise HTTPException(status_code=400, detail=f"Invalid region: {region}")
    
    # Update config using the app_config methods
    save_config("octopus_agile.region", region)
    save_config("octopus_agile.enabled", True)
    
    # Trigger immediate energy price fetch for the new region
    scheduler.scheduler.add_job(
        scheduler._update_energy_prices,
        id=f"update_energy_prices_region_change_{region}",
        name=f"Fetch prices for region {region}",
        replace_existing=True
    )
    
    return {"status": "success", "region": region}


@router.post("/energy/toggle")
async def toggle_energy_pricing(enabled: bool):
    """Enable or disable Octopus Agile energy pricing"""
    from core.config import save_config
    
    save_config("octopus_agile.enabled", enabled)
    
    return {"status": "success", "enabled": enabled}


@router.get("/events/recent")
async def get_recent_events(limit: int = 50, db: AsyncSession = Depends(get_db)):
    """Get recent events"""
    result = await db.execute(
        select(Event)
        .order_by(Event.timestamp.desc())
        .limit(limit)
    )
    events = result.scalars().all()
    
    return {
        "events": [
            {
                "id": e.id,
                "timestamp": e.timestamp.isoformat(),
                "event_type": e.event_type,
                "source": e.source,
                "message": e.message,
                "data": e.data
            }
            for e in events
        ]
    }


@router.get("/all")
async def get_dashboard_all(dashboard_type: str = "all", db: AsyncSession = Depends(get_db)):
    """
    Optimized bulk endpoint - returns all dashboard data in one call
    Uses cached telemetry from database instead of live polling
    
    Args:
        dashboard_type: Filter by miner type - "asic", "cpu", or "all"
    """
    from core.database import Pool
    
    # Define miner type filters
    ASIC_TYPES = ["avalon_nano", "bitaxe", "nerdqaxe", "nmminer"]
    CPU_TYPES = ["xmrig"]
    
    # Get all miners
    result = await db.execute(select(Miner))
    all_miners = result.scalars().all()
    
    # Filter miners based on dashboard type
    if dashboard_type == "asic":
        miners = [m for m in all_miners if m.miner_type in ASIC_TYPES]
    elif dashboard_type == "cpu":
        miners = [m for m in all_miners if m.miner_type in CPU_TYPES]
    else:
        miners = all_miners
    
    # Get all pools for name mapping
    result = await db.execute(select(Pool))
    pools = result.scalars().all()
    pools_dict = {(p.url, p.port): p.name for p in pools}
    
    # Get current energy price
    now = datetime.utcnow()
    result = await db.execute(
        select(EnergyPrice.price_pence)
        .where(EnergyPrice.valid_from <= now)
        .where(EnergyPrice.valid_to > now)
        .limit(1)
    )
    current_energy_price = result.scalar()
    
    # Get recent events (limit 200 for pagination - 50 per page x 4 pages)
    result = await db.execute(
        select(Event)
        .order_by(Event.timestamp.desc())
        .limit(200)
    )
    events = result.scalars().all()
    
    # Get latest telemetry and calculate costs for each miner
    cutoff_5min = datetime.utcnow() - timedelta(minutes=5)
    cutoff_24h = datetime.utcnow() - timedelta(hours=24)
    
    # Pre-fetch all energy prices for the last 24 hours (optimization)
    result = await db.execute(
        select(EnergyPrice)
        .where(EnergyPrice.valid_from >= cutoff_24h)
        .order_by(EnergyPrice.valid_from)
    )
    energy_prices = result.scalars().all()
    
    # Create a lookup function for energy prices
    def get_price_for_timestamp(ts):
        for price in energy_prices:
            if price.valid_from <= ts < price.valid_to:
                return price.price_pence
        return None
    
    miners_data = []
    total_hashrate = 0.0
    total_power_watts = 0.0
    total_cost_24h_pence = 0.0
    total_kwh_consumed_24h = 0.0
    
    for miner in miners:
        # Get latest telemetry (last 5 minutes)
        result = await db.execute(
            select(Telemetry)
            .where(Telemetry.miner_id == miner.id)
            .where(Telemetry.timestamp > cutoff_5min)
            .order_by(Telemetry.timestamp.desc())
            .limit(1)
        )
        latest_telemetry = result.scalar_one_or_none()
        
        hashrate = 0.0
        hashrate_unit = "GH/s"  # Default for ASIC miners
        power = 0.0
        pool_display = '--'
        
        if latest_telemetry:
            hashrate = latest_telemetry.hashrate or 0.0
            hashrate_unit = latest_telemetry.hashrate_unit or "GH/s"
            power = latest_telemetry.power_watts or 0.0
            
            # Fallback to manual power if telemetry has no power
            if not power and miner.manual_power_watts:
                power = miner.manual_power_watts
            
            # Map pool URL to name
            if latest_telemetry.pool_in_use:
                pool_str = latest_telemetry.pool_in_use
                # Remove protocol
                if '://' in pool_str:
                    pool_str = pool_str.split('://')[1]
                # Extract host and port
                if ':' in pool_str:
                    parts = pool_str.split(':')
                    host = parts[0]
                    port = int(parts[1])
                    pool_display = pools_dict.get((host, port), latest_telemetry.pool_in_use)
                else:
                    pool_display = latest_telemetry.pool_in_use
            
            # Only add to total if it's in GH/s (ASIC miners)
            # CPU miners (KH/s) are summed separately
            if miner.enabled:
                if hashrate_unit == "GH/s":
                    total_hashrate += hashrate
                    # Only count power for ASIC miners
                    if miner.miner_type in ASIC_TYPES and power:
                        total_power_watts += power
                elif hashrate_unit == "KH/s":
                    # Convert KH/s to GH/s for consistent storage
                    total_hashrate += hashrate / 1000000
                    # Count power for CPU miners too
                    if miner.miner_type in CPU_TYPES and power:
                        total_power_watts += power
        
        # Calculate accurate 24h cost using historical telemetry + energy prices (using cached prices)
        miner_cost_24h = 0.0
        result = await db.execute(
            select(Telemetry.power_watts, Telemetry.timestamp)
            .where(Telemetry.miner_id == miner.id)
            .where(Telemetry.timestamp > cutoff_24h)
            .order_by(Telemetry.timestamp)
        )
        telemetry_records = result.all()
        
        for i, (tel_power, tel_timestamp) in enumerate(telemetry_records):
            power = tel_power
            
            # Fallback to manual power if no auto-detected power
            if not power or power <= 0:
                if miner.manual_power_watts:
                    power = miner.manual_power_watts
                else:
                    continue
            
            # Find the energy price that was active at this telemetry timestamp (from cached prices)
            price_pence = get_price_for_timestamp(tel_timestamp)
            
            if price_pence is None:
                continue
            
            # Calculate duration until next reading
            if i < len(telemetry_records) - 1:
                next_timestamp = telemetry_records[i + 1][1]
                duration_seconds = (next_timestamp - tel_timestamp).total_seconds()
                duration_hours = duration_seconds / 3600.0
                
                # Cap duration at 10 minutes to prevent counting offline gaps
                # Telemetry is recorded every 30s, so >10min gap = miner was offline
                max_duration_hours = 10.0 / 60.0  # 10 minutes in hours
                if duration_hours > max_duration_hours:
                    duration_hours = max_duration_hours
            else:
                duration_hours = 30.0 / 3600.0
            
            # Calculate cost for this period
            kwh = (power / 1000.0) * duration_hours
            cost = kwh * price_pence
            miner_cost_24h += cost
        
        if miner.enabled:
            total_cost_24h_pence += miner_cost_24h
            # Track total kWh from telemetry records
            for i, (tel_power, tel_timestamp) in enumerate(telemetry_records):
                power = tel_power
                if not power or power <= 0:
                    if miner.manual_power_watts:
                        power = miner.manual_power_watts
                    else:
                        continue
                
                if i < len(telemetry_records) - 1:
                    next_timestamp = telemetry_records[i + 1][1]
                    duration_seconds = (next_timestamp - tel_timestamp).total_seconds()
                    duration_hours = duration_seconds / 3600.0
                    max_duration_hours = 10.0 / 60.0
                    if duration_hours > max_duration_hours:
                        duration_hours = max_duration_hours
                else:
                    duration_hours = 30.0 / 3600.0
                
                kwh = (power / 1000.0) * duration_hours
                total_kwh_consumed_24h += kwh
        
        # Get latest health score for this miner
        health_score = None
        try:
            result = await db.execute(
                select(HealthScore.overall_score)
                .where(HealthScore.miner_id == miner.id)
                .order_by(HealthScore.timestamp.desc())
                .limit(1)
            )
            health_score = result.scalar()
        except Exception:
            pass
        
        # Determine if miner is offline (no telemetry in last 5 minutes)
        is_offline = latest_telemetry is None
        
        # Get best session diff/share for tile display
        best_diff = None
        if latest_telemetry and latest_telemetry.data:
            if miner.miner_type in ["bitaxe", "nerdqaxe"]:
                best_diff = latest_telemetry.data.get("best_session_diff")
            elif miner.miner_type in ["avalon_nano"]:
                best_diff = latest_telemetry.data.get("best_share")
            elif miner.miner_type == "nmminer":
                best_diff = latest_telemetry.data.get("best_share_diff")
        
        miners_data.append({
            "id": miner.id,
            "name": miner.name,
            "miner_type": miner.miner_type,
            "enabled": miner.enabled,
            "current_mode": miner.current_mode,
            "firmware_version": miner.firmware_version,
            "best_diff": best_diff,
            "hashrate": hashrate,
            "hashrate_unit": hashrate_unit,
            "power": power,
            "pool": pool_display,
            "cost_24h": round(miner_cost_24h / 100, 2),  # Convert to pounds
            "health_score": health_score,
            "is_offline": is_offline
        })
    
    # Calculate 24h earnings (from Braiins Pool + Solopool blocks found)
    # Filter by dashboard_type: only count earnings from pools used by filtered miners
    earnings_pounds_24h = 0.0
    try:
        from core.braiins import get_braiins_stats
        from core.config import app_config
        from core.database import CryptoPrice, MinerPoolSlot
        
        # Get pool IDs that filtered miners are actually using
        filtered_miner_ids = {m.id for m in miners}
        result = await db.execute(
            select(MinerPoolSlot.pool_id).distinct()
            .where(MinerPoolSlot.miner_id.in_(filtered_miner_ids))
        )
        dashboard_pool_ids = {pool_id for (pool_id,) in result.all()}
        
        # Get crypto prices for earnings calculation from database
        btc_price_gbp = 0
        bch_price_gbp = 0
        dgb_price_gbp = 0
        xmr_price_gbp = 0
        
        # Fetch from database
        result = await db.execute(select(CryptoPrice).where(CryptoPrice.coin_id == "bitcoin"))
        btc_cached = result.scalar_one_or_none()
        if btc_cached:
            btc_price_gbp = btc_cached.price_gbp
        
        result = await db.execute(select(CryptoPrice).where(CryptoPrice.coin_id == "bitcoin-cash"))
        bch_cached = result.scalar_one_or_none()
        if bch_cached:
            bch_price_gbp = bch_cached.price_gbp
        
        result = await db.execute(select(CryptoPrice).where(CryptoPrice.coin_id == "digibyte"))
        dgb_cached = result.scalar_one_or_none()
        if dgb_cached:
            dgb_price_gbp = dgb_cached.price_gbp
        
        result = await db.execute(select(CryptoPrice).where(CryptoPrice.coin_id == "monero"))
        xmr_cached = result.scalar_one_or_none()
        if xmr_cached:
            xmr_price_gbp = xmr_cached.price_gbp
        
        # 1. Braiins Pool earnings (only if filtered miners use it)
        braiins_enabled = app_config.get("braiins_enabled", False)
        if braiins_enabled and btc_price_gbp > 0 and dashboard_type != "cpu":
            # Braiins is BTC-only, skip for CPU dashboard
            braiins_stats = await get_braiins_stats(db)
            if braiins_stats and "today_reward" in braiins_stats:
                # today_reward is in satoshis
                btc_earned_24h = braiins_stats["today_reward"] / 100000000
                earnings_pounds_24h += btc_earned_24h * btc_price_gbp
        
        # 2. SupportXMR Pool earnings (24h delta from snapshots) - only for CPU/XMRig miners
        supportxmr_enabled = app_config.get("supportxmr_enabled", False)
        logging.info(f"🔍 SupportXMR check: enabled={supportxmr_enabled}, xmr_price_gbp={xmr_price_gbp}, dashboard_type={dashboard_type}")
        if supportxmr_enabled and xmr_price_gbp > 0 and dashboard_type != "asic":
            # Only count SupportXMR for CPU dashboard (skip for ASIC dashboard)
            from core.supportxmr import SupportXMRService
            from core.database import SupportXMRSnapshot
            
            # Get all SupportXMR pools (CPU miners don't use MinerPoolSlot table)
            result = await db.execute(select(Pool))
            all_pools_check = result.scalars().all()
            supportxmr_pools = [p for p in all_pools_check if SupportXMRService.is_supportxmr_pool(p.url, p.port)]
            
            logging.info(f"💰 SupportXMR: found {len(supportxmr_pools)} pools")
            
            for pool in supportxmr_pools:
                wallet_address = SupportXMRService.extract_address(pool.user)
                if not wallet_address:
                    continue
                
                logging.info(f"💰 Processing wallet: ...{wallet_address[-8:]}")
                
                # Get 24h earnings from snapshots
                twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
                snapshot_result = await db.execute(
                    select(SupportXMRSnapshot)
                    .where(SupportXMRSnapshot.wallet_address == wallet_address)
                    .where(SupportXMRSnapshot.timestamp >= twenty_four_hours_ago)
                    .order_by(SupportXMRSnapshot.timestamp.asc())
                    .limit(1)
                )
                old_snapshot = snapshot_result.scalar_one_or_none()
                
                # Get most recent snapshot
                recent_result = await db.execute(
                    select(SupportXMRSnapshot)
                    .where(SupportXMRSnapshot.wallet_address == wallet_address)
                    .order_by(SupportXMRSnapshot.timestamp.desc())
                    .limit(1)
                )
                recent_snapshot = recent_result.scalar_one_or_none()
                
                logging.info(f"💰 Snapshots: old={old_snapshot is not None}, recent={recent_snapshot is not None}")
                
                if old_snapshot and recent_snapshot:
                    # Calculate 24h XMR earnings
                    current_total = recent_snapshot.amount_due + recent_snapshot.amount_paid
                    old_total = old_snapshot.amount_due + old_snapshot.amount_paid
                    xmr_earned_24h = max(0, current_total - old_total)
                    xmr_earned_gbp = xmr_earned_24h * xmr_price_gbp
                    logging.info(f"💰 Wallet ...{wallet_address[-8:]}: {xmr_earned_24h:.6f} XMR = £{xmr_earned_gbp:.4f}")
                    logging.info(f"💰 Before add: earnings_pounds_24h = £{earnings_pounds_24h:.4f}")
                    earnings_pounds_24h += xmr_earned_gbp
                    logging.info(f"💰 After add: earnings_pounds_24h = £{earnings_pounds_24h:.4f}")
        
        # 3. Solopool earnings (blocks found in last 24h) - only from pools filtered miners use
        from core.solopool import SolopoolService
        
        # Get pools used by filtered miners only
        result = await db.execute(select(Pool).where(Pool.id.in_(dashboard_pool_ids)) if dashboard_pool_ids else select(Pool).where(False))
        pools_list = result.scalars().all()
        
        # Track unique Solopool usernames to avoid double-counting
        solopool_users_checked = set()
        
        for pool in pools_list:
            # Check which Solopool coin this is
            is_bch = SolopoolService.is_solopool_bch_pool(pool.url, pool.port)
            is_dgb = SolopoolService.is_solopool_dgb_pool(pool.url, pool.port)
            is_btc = SolopoolService.is_solopool_btc_pool(pool.url, pool.port)
            is_xmr = SolopoolService.is_solopool_xmr_pool(pool.url, pool.port)
            
            if not (is_bch or is_dgb or is_btc or is_xmr):
                continue
            
            # Extract username from pool.user
            username = SolopoolService.extract_username(pool.user)
            if not username or username in solopool_users_checked:
                continue
            
            solopool_users_checked.add(username)
            
            # Fetch account stats and calculate earnings from blocks found in last 24h only
            if is_bch and bch_price_gbp > 0:
                raw_stats = await SolopoolService.get_bch_account_stats(username)
                if raw_stats:
                    stats = SolopoolService.format_stats_summary(raw_stats)
                    blocks_24h = stats.get("blocks_24h", 0)
                    # BCH block reward: 3.125 BCH (post-2024 halving)
                    earned_24h_bch = blocks_24h * 3.125
                    earnings_pounds_24h += earned_24h_bch * bch_price_gbp
            elif is_dgb and dgb_price_gbp > 0:
                raw_stats = await SolopoolService.get_dgb_account_stats(username)
                if raw_stats:
                    stats = SolopoolService.format_stats_summary(raw_stats)
                    blocks_24h = stats.get("blocks_24h", 0)
                    # DGB block reward: 277.376 DGB (current as of January 2025, post-halving)
                    earned_24h_dgb = blocks_24h * 277.376
                    earnings_pounds_24h += earned_24h_dgb * dgb_price_gbp
            elif is_btc and btc_price_gbp > 0:
                raw_stats = await SolopoolService.get_btc_account_stats(username)
                if raw_stats:
                    stats = SolopoolService.format_stats_summary(raw_stats)
                    blocks_24h = stats.get("blocks_24h", 0)
                    # BTC block reward: 3.125 BTC (post-2024 halving)
                    earned_24h_btc = blocks_24h * 3.125
                    earnings_pounds_24h += earned_24h_btc * btc_price_gbp
            elif is_xmr and xmr_price_gbp > 0:
                raw_stats = await SolopoolService.get_xmr_account_stats(username)
                if raw_stats:
                    stats = SolopoolService.format_stats_summary(raw_stats)
                    blocks_24h = stats.get("blocks_24h", 0)
                    # XMR block reward: ~0.6 XMR (emission curve, approximate)
                    earned_24h_xmr = blocks_24h * 0.6
                    earnings_pounds_24h += earned_24h_xmr * xmr_price_gbp
        
    except Exception as e:
        logging.error(f"Error calculating 24h earnings in /all: {e}")
    
    # Calculate P/L
    pl_pounds_24h = earnings_pounds_24h - (total_cost_24h_pence / 100)
    
    # Calculate average price per kWh (weighted by consumption)
    avg_price_per_kwh = None
    if total_kwh_consumed_24h > 0:
        avg_price_per_kwh = total_cost_24h_pence / total_kwh_consumed_24h
    
    # Count offline/online miners
    offline_miners_count = sum(1 for m in miners_data if m["is_offline"])
    online_miners_count = sum(1 for m in miners_data if not m["is_offline"])
    
    # Calculate average efficiency (W/TH) for ASIC miners
    # Efficiency = Watts / Hashrate_TH = Watts per Terahash
    avg_efficiency_wth = None
    if total_hashrate > 0 and total_power_watts > 0:
        hashrate_ths = total_hashrate / 1000.0  # Convert GH/s to TH/s
        avg_efficiency_wth = total_power_watts / hashrate_ths
    
    # Calculate average pool health
    avg_pool_health = None
    
    try:
        from core.database import HealthScore, PoolHealth
        
        # Calculate average pool health (using latest health score for each pool)
        # Get all pools
        result = await db.execute(select(Pool))
        all_pools = result.scalars().all()
        
        # Get latest health score for each pool
        pool_health_scores = []
        for pool in all_pools:
            result = await db.execute(
                select(PoolHealth.health_score)
                .where(PoolHealth.pool_id == pool.id)
                .order_by(PoolHealth.timestamp.desc())
                .limit(1)
            )
            latest_score = result.scalar()
            if latest_score is not None:
                pool_health_scores.append(latest_score)
        
        # Calculate average of latest scores
        if pool_health_scores:
            avg_pool_health = round(sum(pool_health_scores) / len(pool_health_scores), 1)
    except Exception as e:
        logging.error(f"Error calculating health scores in /all: {e}")
    
    # Get best share in last 24h (ASIC only)
    best_share_24h = await get_best_share_24h(db)
    
    return {
        "stats": {
            "total_miners": len(miners),
            "active_miners": sum(1 for m in miners if m.enabled),
            "online_miners": online_miners_count,
            "offline_miners": offline_miners_count,
            "total_hashrate_ghs": total_hashrate,  # Don't round - preserve precision for KH/s miners
            "total_power_watts": round(total_power_watts, 1),
            "avg_efficiency_wth": round(avg_efficiency_wth, 1) if avg_efficiency_wth is not None else None,
            "current_energy_price_pence": current_energy_price,
            "avg_price_per_kwh_pence": round(avg_price_per_kwh, 2) if avg_price_per_kwh is not None else None,
            "total_cost_24h_pence": round(total_cost_24h_pence, 2),
            "total_cost_24h_pounds": round(total_cost_24h_pence / 100, 2),
            "earnings_24h_pounds": round(earnings_pounds_24h, 2),
            "pl_24h_pounds": round(pl_pounds_24h, 2),
            "avg_pool_health": avg_pool_health,
            "best_share_24h": best_share_24h
        },
        "miners": miners_data,
        "events": [
            {
                "id": e.id,
                "timestamp": e.timestamp.isoformat(),
                "event_type": e.event_type,
                "source": e.source,
                "message": e.message
            }
            for e in events
        ]
    }


@router.delete("/events")
async def clear_events(db: AsyncSession = Depends(get_db)):
    """Clear all events"""
    from sqlalchemy import delete
    
    await db.execute(delete(Event))
    await db.commit()
    
    return {"message": "All events cleared"}
