"""
Dashboard and analytics API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta, timezone

from core.database import get_db, Miner, Telemetry, EnergyPrice, Event


router = APIRouter()


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
    result = await db.execute(select(Miner).where(Miner.enabled == True))
    miners = result.scalars().all()
    
    cutoff = datetime.utcnow() - timedelta(minutes=5)
    for miner in miners:
        result = await db.execute(
            select(Telemetry.hashrate)
            .where(Telemetry.miner_id == miner.id)
            .where(Telemetry.timestamp > cutoff)
            .order_by(Telemetry.timestamp.desc())
            .limit(1)
        )
        latest_hashrate = result.scalar()
        if latest_hashrate:
            total_hashrate += latest_hashrate
    
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
    
    # Calculate 24h earnings (from Braiins Pool + Solopool blocks found)
    earnings_pounds_24h = 0.0
    try:
        from core.braiins import get_braiins_stats
        from core.config import app_config, crypto_price_cache
        
        # Get crypto prices for earnings calculation
        btc_price_gbp = crypto_price_cache.get("bitcoin", 0)
        bch_price_gbp = crypto_price_cache.get("bitcoin-cash", 0)
        dgb_price_gbp = crypto_price_cache.get("digibyte", 0)
        xmr_price_gbp = crypto_price_cache.get("monero", 0)
        
        # 1. Braiins Pool earnings
        braiins_enabled = app_config.get("braiins_pool.enabled", False)
        if braiins_enabled and btc_price_gbp > 0:
            braiins_stats = await get_braiins_stats(db)
            if braiins_stats and "today_reward" in braiins_stats:
                # today_reward is in satoshis
                btc_earned_24h = braiins_stats["today_reward"] / 100000000
                earnings_pounds_24h += btc_earned_24h * btc_price_gbp
        
        # 2. Solopool earnings (blocks found in last 24h)
        # Check if any miners are using Solopool and fetch their stats
        from core.solopool import SolopoolService
        from core.database import Pool
        
        # Get all pools to check for Solopool configurations
        result = await db.execute(select(Pool))
        pools = result.scalars().all()
        
        # Track unique Solopool usernames to avoid double-counting
        solopool_users_checked = set()
        
        for pool in pools:
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
            
            # Fetch stats for this user
            stats = None
            coin_price = 0
            block_reward = 0
            
            if is_bch and bch_price_gbp > 0:
                stats = await SolopoolService.get_bch_account_stats(username)
                coin_price = bch_price_gbp
                block_reward = 6.25  # BCH block reward
            elif is_dgb and dgb_price_gbp > 0:
                stats = await SolopoolService.get_dgb_account_stats(username)
                coin_price = dgb_price_gbp
                block_reward = 665  # DGB block reward (approximate)
            elif is_btc and btc_price_gbp > 0:
                stats = await SolopoolService.get_btc_account_stats(username)
                coin_price = btc_price_gbp
                block_reward = 3.125  # BTC block reward (post-2024 halving)
            elif is_xmr and xmr_price_gbp > 0:
                stats = await SolopoolService.get_xmr_account_stats(username)
                coin_price = xmr_price_gbp
                block_reward = 0.6  # XMR block reward (approximate)
            
            if stats and "blocks_24h" in stats:
                blocks_found = stats["blocks_24h"]
                if blocks_found > 0:
                    earnings_pounds_24h += blocks_found * block_reward * coin_price
        
    except Exception as e:
        import logging
        logging.error(f"Error calculating 24h earnings: {e}")
    
    # Calculate P/L (earnings - cost)
    pl_pounds_24h = earnings_pounds_24h - (total_cost_pence / 100)
    
    # Calculate average miner health
    from core.database import HealthScore
    avg_miner_health = None
    result = await db.execute(
        select(func.avg(HealthScore.health_score))
        .where(HealthScore.timestamp > cutoff_24h)
    )
    avg_health_value = result.scalar()
    if avg_health_value is not None:
        avg_miner_health = float(avg_health_value)
    
    # Calculate average pool health
    from core.database import PoolHealth
    avg_pool_health = None
    result = await db.execute(
        select(func.avg(PoolHealth.health_score))
        .where(PoolHealth.timestamp > cutoff_24h)
    )
    avg_pool_value = result.scalar()
    if avg_pool_value is not None:
        avg_pool_health = float(avg_pool_value)
    
    return {
        "total_miners": total_miners,
        "active_miners": active_miners,
        "total_hashrate_ghs": round(total_hashrate, 2),
        "current_energy_price_pence": current_price,
        "recent_events_24h": recent_events,
        "total_cost_24h_pence": round(total_cost_pence, 2),
        "total_cost_24h_pounds": round(total_cost_pence / 100, 2),
        "earnings_24h_pounds": round(earnings_pounds_24h, 2),
        "pl_24h_pounds": round(pl_pounds_24h, 2),
        "avg_miner_health": round(avg_miner_health, 1) if avg_miner_health is not None else None,
        "avg_pool_health": round(avg_pool_health, 1) if avg_pool_health is not None else None
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
async def get_dashboard_all(db: AsyncSession = Depends(get_db)):
    """
    Optimized bulk endpoint - returns all dashboard data in one call
    Uses cached telemetry from database instead of live polling
    """
    from core.database import Pool
    
    # Get all miners
    result = await db.execute(select(Miner))
    miners = result.scalars().all()
    
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
    total_cost_24h_pence = 0.0
    
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
        power = 0.0
        pool_display = '--'
        
        if latest_telemetry:
            hashrate = latest_telemetry.hashrate or 0.0
            power = latest_telemetry.power_watts or 0.0
            
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
            
            if miner.enabled:
                total_hashrate += hashrate
        
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
            if tel_power is None or tel_power <= 0:
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
            else:
                duration_hours = 30.0 / 3600.0
            
            # Calculate cost for this period
            kwh = (tel_power / 1000.0) * duration_hours
            cost = kwh * price_pence
            miner_cost_24h += cost
        
        if miner.enabled:
            total_cost_24h_pence += miner_cost_24h
        
        miners_data.append({
            "id": miner.id,
            "name": miner.name,
            "miner_type": miner.miner_type,
            "enabled": miner.enabled,
            "current_mode": miner.current_mode,
            "firmware_version": miner.firmware_version,
            "hashrate": hashrate,
            "power": power,
            "pool": pool_display,
            "cost_24h": round(miner_cost_24h / 100, 2)  # Convert to pounds
        })
    
    # Calculate 24h earnings (from Braiins Pool + Solopool blocks found)
    earnings_pounds_24h = 0.0
    try:
        from core.braiins import get_braiins_stats
        from core.config import app_config, crypto_price_cache
        
        # Get crypto prices for earnings calculation
        btc_price_gbp = crypto_price_cache.get("bitcoin", 0)
        bch_price_gbp = crypto_price_cache.get("bitcoin-cash", 0)
        dgb_price_gbp = crypto_price_cache.get("digibyte", 0)
        xmr_price_gbp = crypto_price_cache.get("monero", 0)
        
        # 1. Braiins Pool earnings
        braiins_enabled = app_config.get("braiins_pool.enabled", False)
        if braiins_enabled and btc_price_gbp > 0:
            braiins_stats = await get_braiins_stats(db)
            if braiins_stats and "today_reward" in braiins_stats:
                # today_reward is in satoshis
                btc_earned_24h = braiins_stats["today_reward"] / 100000000
                earnings_pounds_24h += btc_earned_24h * btc_price_gbp
        
        # 2. Solopool earnings (blocks found in last 24h)
        # Check if any miners are using Solopool and fetch their stats
        from core.solopool import SolopoolService
        
        # Track unique Solopool usernames to avoid double-counting
        solopool_users_checked = set()
        
        for pool in pools:
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
            
            # Fetch stats for this user
            stats = None
            coin_price = 0
            block_reward = 0
            
            if is_bch and bch_price_gbp > 0:
                stats = await SolopoolService.get_bch_account_stats(username)
                coin_price = bch_price_gbp
                block_reward = 6.25  # BCH block reward
            elif is_dgb and dgb_price_gbp > 0:
                stats = await SolopoolService.get_dgb_account_stats(username)
                coin_price = dgb_price_gbp
                block_reward = 665  # DGB block reward (approximate)
            elif is_btc and btc_price_gbp > 0:
                stats = await SolopoolService.get_btc_account_stats(username)
                coin_price = btc_price_gbp
                block_reward = 3.125  # BTC block reward (post-2024 halving)
            elif is_xmr and xmr_price_gbp > 0:
                stats = await SolopoolService.get_xmr_account_stats(username)
                coin_price = xmr_price_gbp
                block_reward = 0.6  # XMR block reward (approximate)
            
            if stats and "blocks_24h" in stats:
                blocks_found = stats["blocks_24h"]
                if blocks_found > 0:
                    earnings_pounds_24h += blocks_found * block_reward * coin_price
        
    except Exception as e:
        import logging
        logging.error(f"Error calculating 24h earnings in /api/dashboard/all: {e}")
    
    # Calculate P/L (earnings - cost)
    pl_pounds_24h = earnings_pounds_24h - (total_cost_24h_pence / 100)
    
    # Calculate average miner health
    from core.database import HealthScore
    avg_miner_health = None
    result = await db.execute(
        select(func.avg(HealthScore.health_score))
        .where(HealthScore.timestamp > cutoff_24h)
    )
    avg_health_value = result.scalar()
    if avg_health_value is not None:
        avg_miner_health = float(avg_health_value)
    
    # Calculate average pool health
    from core.database import PoolHealth
    avg_pool_health = None
    result = await db.execute(
        select(func.avg(PoolHealth.health_score))
        .where(PoolHealth.timestamp > cutoff_24h)
    )
    avg_pool_value = result.scalar()
    if avg_pool_value is not None:
        avg_pool_health = float(avg_pool_value)
    
    return {
        "stats": {
            "total_miners": len(miners),
            "active_miners": sum(1 for m in miners if m.enabled),
            "total_hashrate_ghs": round(total_hashrate, 2),
            "current_energy_price_pence": current_energy_price,
            "total_cost_24h_pence": round(total_cost_24h_pence, 2),
            "total_cost_24h_pounds": round(total_cost_24h_pence / 100, 2),
            "earnings_24h_pounds": round(earnings_pounds_24h, 2),
            "pl_24h_pounds": round(pl_pounds_24h, 2),
            "avg_miner_health": round(avg_miner_health, 1) if avg_miner_health is not None else None,
            "avg_pool_health": round(avg_pool_health, 1) if avg_pool_health is not None else None
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
