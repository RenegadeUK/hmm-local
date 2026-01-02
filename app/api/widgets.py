"""
Dashboard Widget Data API endpoints
Real-time data providers for dashboard widgets
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional
from datetime import datetime, timedelta

from core.database import get_db, Miner, Telemetry, EnergyPrice, Pool, PoolHealth
from core.config import app_config
from core.utils import format_time_elapsed, get_latest_telemetry_batch

router = APIRouter()


@router.get("/widgets/miner-stats/{miner_id}")
async def get_miner_stats_widget(miner_id: int, db: AsyncSession = Depends(get_db)):
    """Get real-time stats for a specific miner"""
    # Get miner
    result = await db.execute(select(Miner).where(Miner.id == miner_id))
    miner = result.scalar_one_or_none()
    
    if not miner:
        raise HTTPException(status_code=404, detail="Miner not found")
    
    # Get latest telemetry
    result = await db.execute(
        select(Telemetry)
        .where(Telemetry.miner_id == miner_id)
        .order_by(Telemetry.timestamp.desc())
        .limit(1)
    )
    latest = result.scalar_one_or_none()
    
    if not latest:
        return {
            "miner_id": miner_id,
            "miner_name": miner.name,
            "status": "offline",
            "hashrate": 0,
            "temperature": 0,
            "power": 0
        }
    
    # Determine hashrate unit
    hashrate = latest.hashrate or 0
    if hashrate >= 1000:
        hashrate_display = f"{hashrate / 1000:.2f} TH/s"
    else:
        hashrate_display = f"{hashrate:.2f} GH/s"
    
    return {
        "miner_id": miner_id,
        "miner_name": miner.name,
        "miner_type": miner.miner_type,
        "status": "online" if miner.enabled else "offline",
        "hashrate": hashrate,
        "hashrate_display": hashrate_display,
        "temperature": latest.temperature or 0,
        "power": latest.power_watts or 0,
        "pool": latest.pool_in_use or "Unknown",
        "shares_accepted": latest.shares_accepted or 0,
        "shares_rejected": latest.shares_rejected or 0,
        "last_update": latest.timestamp.isoformat() if latest.timestamp else None
    }


@router.get("/widgets/total-hashrate")
async def get_total_hashrate_widget(db: AsyncSession = Depends(get_db)):
    """Get total hashrate across all miners"""
    # Get all enabled miners
    result = await db.execute(
        select(Miner).where(Miner.enabled == True)
    )
    miners = result.scalars().all()
    
    if not miners:
        return {
            "total_hashrate": 0,
            "hashrate_display": "0 GH/s",
            "active_miners": 0,
            "total_miners": 0
        }
    
    # Get latest telemetry for all miners in SINGLE QUERY (batch optimization)
    cutoff = datetime.utcnow() - timedelta(minutes=5)
    telemetry_map = await get_latest_telemetry_batch(db, [m.id for m in miners], cutoff)
    
    # Process in memory (fast)
    total_hashrate = 0
    active_count = 0
    
    for miner in miners:
        latest = telemetry_map.get(miner.id)
        if latest and latest.hashrate:
            total_hashrate += latest.hashrate
            active_count += 1
    
    # Format display
    if total_hashrate >= 1000:
        hashrate_display = f"{total_hashrate / 1000:.2f} TH/s"
    else:
        hashrate_display = f"{total_hashrate:.2f} GH/s"
    
    return {
        "total_hashrate": total_hashrate,
        "hashrate_display": hashrate_display,
        "active_miners": active_count,
        "total_miners": len(miners)
    }


@router.get("/widgets/energy-price")
async def get_energy_price_widget(db: AsyncSession = Depends(get_db)):
    """Get current energy price"""
    region = app_config.get("agile_region", "B")
    
    # Get current price slot
    now = datetime.utcnow()
    result = await db.execute(
        select(EnergyPrice)
        .where(EnergyPrice.region == region)
        .where(EnergyPrice.valid_from <= now)
        .where(EnergyPrice.valid_to > now)
        .limit(1)
    )
    current = result.scalar_one_or_none()
    
    if not current:
        return {
            "price_pence": 0,
            "price_display": "-- p/kWh",
            "status": "No data",
            "valid_from": None,
            "valid_to": None
        }
    
    return {
        "price_pence": current.price_pence,
        "price_display": f"{current.price_pence:.2f} p/kWh",
        "status": "Current",
        "valid_from": current.valid_from.isoformat(),
        "valid_to": current.valid_to.isoformat()
    }


@router.get("/widgets/pool-health/{pool_id}")
async def get_pool_health_widget(pool_id: int, db: AsyncSession = Depends(get_db)):
    """Get pool health stats"""
    # Get pool
    result = await db.execute(select(Pool).where(Pool.id == pool_id))
    pool = result.scalar_one_or_none()
    
    if not pool:
        raise HTTPException(status_code=404, detail="Pool not found")
    
    # Get latest health
    result = await db.execute(
        select(PoolHealth)
        .where(PoolHealth.pool_id == pool_id)
        .order_by(PoolHealth.timestamp.desc())
        .limit(1)
    )
    health = result.scalar_one_or_none()
    
    if not health:
        return {
            "pool_id": pool_id,
            "pool_name": pool.name,
            "health_score": 0,
            "status": "No data",
            "reachable": False
        }
    
    status = "Healthy" if health.health_score >= 70 else "Warning" if health.health_score >= 50 else "Critical"
    
    return {
        "pool_id": pool_id,
        "pool_name": pool.name,
        "health_score": health.health_score or 0,
        "status": status,
        "reachable": health.is_reachable,
        "response_time_ms": health.response_time_ms or 0,
        "reject_rate": health.reject_rate or 0,
        "last_check": health.timestamp.isoformat() if health.timestamp else None
    }


@router.get("/widgets/miners-list")
async def get_miners_list_widget(db: AsyncSession = Depends(get_db)):
    """Get list of all miners with basic stats"""
    result = await db.execute(select(Miner).order_by(Miner.name))
    miners = result.scalars().all()
    
    if not miners:
        return {
            "miners": [],
            "total": 0,
            "online": 0
        }
    
    # Get latest telemetry for all miners in SINGLE QUERY (batch optimization)
    cutoff = datetime.utcnow() - timedelta(minutes=5)
    telemetry_map = await get_latest_telemetry_batch(db, [m.id for m in miners], cutoff)
    
    miners_data = []
    online_count = 0
    
    for miner in miners:
        latest = telemetry_map.get(miner.id)
        
        status = "online" if (miner.enabled and latest) else "offline"
        hashrate = latest.hashrate if latest else 0
        
        if status == "online":
            online_count += 1
        
        miners_data.append({
            "id": miner.id,
            "name": miner.name,
            "type": miner.miner_type,
            "status": status,
            "hashrate": hashrate,
            "temperature": latest.temperature if latest else 0,
            "power": latest.power_watts if latest else 0
        })
    
    return {
        "miners": miners_data,
        "total": len(miners_data),
        "online": online_count
    }


@router.get("/widgets/daily-cost")
async def get_daily_cost_widget(db: AsyncSession = Depends(get_db)):
    """Get 24-hour total energy cost"""
    # Get all miners
    result = await db.execute(select(Miner).where(Miner.enabled == True))
    miners = result.scalars().all()
    
    if not miners:
        return {
            "cost_gbp": 0,
            "cost_display": "£0.00",
            "period_hours": 24
        }
    
    # Get energy prices for last 24h
    cutoff = datetime.utcnow() - timedelta(hours=24)
    region = app_config.get("agile_region", "B")
    
    result = await db.execute(
        select(EnergyPrice)
        .where(EnergyPrice.region == region)
        .where(EnergyPrice.valid_from >= cutoff)
        .order_by(EnergyPrice.valid_from)
    )
    prices = result.scalars().all()
    
    if not prices:
        return {
            "cost_gbp": 0,
            "cost_display": "£0.00",
            "period_hours": 24
        }
    
    # CRITICAL OPTIMIZATION: Single batch query for ALL telemetry in 24h window
    # This replaces the catastrophic nested loop (48 slots × N miners = 480+ queries)
    miner_ids = [m.id for m in miners]
    telemetry_result = await db.execute(
        select(Telemetry)
        .where(Telemetry.miner_id.in_(miner_ids))
        .where(Telemetry.timestamp >= cutoff)
        .order_by(Telemetry.miner_id, Telemetry.timestamp)
    )
    all_telemetry = telemetry_result.scalars().all()
    
    # Index telemetry by time slots in memory (O(N) complexity, very fast)
    from collections import defaultdict
    slot_telemetry = defaultdict(list)
    
    for t in all_telemetry:
        # Find which price slot this telemetry belongs to
        for price in prices:
            if price.valid_from <= t.timestamp < price.valid_to:
                slot_telemetry[price.valid_from].append(t)
                break
    
    # Calculate cost for each slot (in-memory, fast)
    total_cost = 0
    for price in prices:
        slot_duration_hours = 0.5  # 30-minute slots
        slot_data = slot_telemetry.get(price.valid_from, [])
        
        if not slot_data:
            continue
        
        # Average power across all miners in this slot
        # Group by miner_id to get one reading per miner
        miner_power = {}
        for t in slot_data:
            if t.power_watts:
                # Keep most recent reading per miner in this slot
                if t.miner_id not in miner_power or t.timestamp > miner_power[t.miner_id][1]:
                    miner_power[t.miner_id] = (t.power_watts, t.timestamp)
        
        total_power_kw = sum(watts for watts, _ in miner_power.values()) / 1000
        
        # Cost = power (kW) × duration (h) × price (pence/kWh) ÷ 100 (to GBP)
        slot_cost = (total_power_kw * slot_duration_hours * price.price_pence) / 100
        total_cost += slot_cost
    
    return {
        "cost_gbp": round(total_cost, 2),
        "cost_display": f"£{total_cost:.2f}",
        "period_hours": 24
    }


@router.get("/widgets/efficiency")
async def get_efficiency_widget(db: AsyncSession = Depends(get_db)):
    """Get efficiency metrics: J/TH across all miners"""
    result = await db.execute(select(Miner))
    miners = result.scalars().all()
    
    if not miners:
        return {
            "efficiency": 0,
            "efficiency_display": "0 J/TH",
            "total_power": 0,
            "total_hashrate": 0
        }
    
    # Get latest telemetry for all miners in SINGLE QUERY (batch optimization)
    telemetry_map = await get_latest_telemetry_batch(db, [m.id for m in miners])
    
    total_power_w = 0
    total_hashrate_th = 0
    
    for miner in miners:
        latest = telemetry_map.get(miner.id)
        
        if latest and latest.power_watts and latest.hashrate:
            total_power_w += latest.power_watts
            # Convert GH/s to TH/s
            total_hashrate_th += latest.hashrate / 1000
    
    if total_hashrate_th > 0:
        efficiency_j_th = total_power_w / total_hashrate_th
    else:
        efficiency_j_th = 0
    
    return {
        "efficiency": round(efficiency_j_th, 2),
        "efficiency_display": f"{efficiency_j_th:.2f} J/TH",
        "total_power": total_power_w,
        "total_hashrate": total_hashrate_th
    }


@router.get("/widgets/uptime")
async def get_uptime_widget(db: AsyncSession = Depends(get_db)):
    """Get overall fleet uptime percentage"""
    result = await db.execute(select(Miner))
    miners = result.scalars().all()
    
    if not miners:
        return {
            "uptime_percent": 0,
            "uptime_display": "0%",
            "online_count": 0,
            "total_count": 0
        }
    
    # Get latest telemetry for all miners in SINGLE QUERY (batch optimization)
    cutoff = datetime.utcnow() - timedelta(minutes=5)
    telemetry_map = await get_latest_telemetry_batch(db, [m.id for m in miners], cutoff)
    
    online_count = len(telemetry_map)
    uptime_percent = (online_count / len(miners)) * 100
    
    return {
        "uptime_percent": round(uptime_percent, 1),
        "uptime_display": f"{uptime_percent:.1f}%",
        "online_count": online_count,
        "total_count": len(miners)
    }


@router.get("/widgets/reject-rate")
async def get_reject_rate_widget(db: AsyncSession = Depends(get_db)):
    """Get average reject rate across all miners"""
    result = await db.execute(select(Miner))
    miners = result.scalars().all()
    
    if not miners:
        return {
            "reject_rate": 0,
            "reject_display": "0%",
            "total_shares": 0,
            "rejected_shares": 0
        }
    
    # Get latest telemetry for all miners in SINGLE QUERY (batch optimization)
    telemetry_map = await get_latest_telemetry_batch(db, [m.id for m in miners])
    
    total_shares = 0
    total_rejected = 0
    
    for miner in miners:
        latest = telemetry_map.get(miner.id)
        
        if latest:
            accepted = latest.shares_accepted or 0
            rejected = latest.shares_rejected or 0
            total_shares += (accepted + rejected)
            total_rejected += rejected
    
    reject_rate = (total_rejected / total_shares * 100) if total_shares > 0 else 0
    
    return {
        "reject_rate": round(reject_rate, 2),
        "reject_display": f"{reject_rate:.2f}%",
        "total_shares": total_shares,
        "rejected_shares": total_rejected
    }


@router.get("/widgets/temperature-alert")
async def get_temperature_alert_widget(db: AsyncSession = Depends(get_db)):
    """Get miners with temperature warnings"""
    result = await db.execute(select(Miner))
    miners = result.scalars().all()
    
    if not miners:
        return {
            "alert_count": 0,
            "hot_miners": [],
            "status": "ok"
        }
    
    # Get latest telemetry for all miners in SINGLE QUERY (batch optimization)
    telemetry_map = await get_latest_telemetry_batch(db, [m.id for m in miners])
    
    hot_miners = []
    
    for miner in miners:
        latest = telemetry_map.get(miner.id)
        
        if latest and latest.temperature:
            # Type-aware thresholds
            threshold = 90 if miner.miner_type == 'avalon_nano' else 75
            
            if latest.temperature >= threshold:
                hot_miners.append({
                    "name": miner.name,
                    "temperature": latest.temperature,
                    "threshold": threshold
                })
    
    return {
        "alert_count": len(hot_miners),
        "hot_miners": hot_miners,
        "status": "warning" if hot_miners else "ok"
    }


@router.get("/widgets/profitability")
async def get_profitability_widget(db: AsyncSession = Depends(get_db)):
    """Get estimated 24h profitability (BTC mined - energy cost)"""
    # Get total hashrate
    result = await db.execute(select(Miner))
    miners = result.scalars().all()
    
    if not miners:
        return {
            "profit_btc": 0,
            "profit_gbp": 0,
            "profit_display": "£0.00",
            "btc_mined": 0,
            "energy_cost": 0,
            "status": "loss"
        }
    
    # Get latest telemetry for all miners in SINGLE QUERY (batch optimization)
    telemetry_map = await get_latest_telemetry_batch(db, [m.id for m in miners])
    
    total_hashrate_th = 0
    for miner in miners:
        latest = telemetry_map.get(miner.id)
        if latest and latest.hashrate:
            total_hashrate_th += latest.hashrate / 1000
    
    # Rough estimate: 1 TH/s = ~0.000000073 BTC/day at current difficulty
    # This is a simplified calculation - real pools would have actual earnings
    btc_per_day = total_hashrate_th * 0.000000073
    
    # Get energy cost from daily-cost widget
    energy_result = await get_daily_cost_widget(db)
    energy_cost_gbp = energy_result["cost_gbp"]
    
    # Get BTC price from cache
    from core.utils import get_cached_crypto_price
    btc_price_gbp = await get_cached_crypto_price(db, 'bitcoin')
    if btc_price_gbp == 0:
        btc_price_gbp = 50000  # Fallback if cache not available
    
    energy_cost_btc = energy_cost_gbp / btc_price_gbp
    
    profit_btc = btc_per_day - energy_cost_btc
    profit_gbp = profit_btc * btc_price_gbp
    
    return {
        "profit_btc": round(profit_btc, 8),
        "profit_gbp": round(profit_gbp, 2),
        "profit_display": f"£{profit_gbp:.2f}",
        "btc_mined": round(btc_per_day, 8),
        "energy_cost": energy_cost_gbp,
        "status": "profit" if profit_btc > 0 else "loss"
    }


@router.get("/widgets/automation-status")
async def get_automation_status_widget(db: AsyncSession = Depends(get_db)):
    """Get automation rules status"""
    from core.database import AutomationRule
    
    result = await db.execute(select(AutomationRule))
    rules = result.scalars().all()
    
    enabled_count = sum(1 for r in rules if r.enabled)
    disabled_count = len(rules) - enabled_count
    
    return {
        "total_rules": len(rules),
        "enabled_rules": enabled_count,
        "disabled_rules": disabled_count,
        "status_display": f"{enabled_count}/{len(rules)} Active"
    }


@router.get("/widgets/ckpool-coins")
async def get_ckpool_coins_widget(db: AsyncSession = Depends(get_db)):
    """Get list of all CKPool coins configured (BTC/BCH/DGB/etc)"""
    from core.ckpool import CKPoolService
    
    # Find all CKPool pools
    result = await db.execute(select(Pool))
    pools = result.scalars().all()
    
    coins = set()
    
    for pool in pools:
        if CKPoolService.is_ckpool(pool.name):
            pool_name_lower = pool.name.lower()
            if 'btc' in pool_name_lower or 'bitcoin' in pool_name_lower:
                coins.add('BTC')
            elif 'bch' in pool_name_lower or 'bitcoin cash' in pool_name_lower:
                coins.add('BCH')
            elif 'dgb' in pool_name_lower or 'digibyte' in pool_name_lower:
                coins.add('DGB')
    
    return {
        "coins": sorted(list(coins))
    }


@router.get("/widgets/ckpool-workers")
async def get_ckpool_workers_widget(db: AsyncSession = Depends(get_db), coin: str = None):
    """Get CKPool worker count and 1m hashrate. Optional coin parameter (BTC/BCH/DGB) to filter."""
    from core.ckpool import CKPoolService
    
    # Find all CKPool pools
    result = await db.execute(select(Pool))
    pools = result.scalars().all()
    
    total_workers = 0
    total_hashrate_1m = 0.0
    pool_count = 0
    
    for pool in pools:
        if CKPoolService.is_ckpool(pool.name):
            # Filter by coin type if specified
            if coin:
                pool_name_lower = pool.name.lower()
                if coin.upper() == 'BTC' and 'btc' not in pool_name_lower and 'bitcoin' not in pool_name_lower:
                    continue
                elif coin.upper() == 'BCH' and 'bch' not in pool_name_lower and 'bitcoin cash' not in pool_name_lower:
                    continue
                elif coin.upper() == 'DGB' and 'dgb' not in pool_name_lower and 'digibyte' not in pool_name_lower:
                    continue
            
            raw_stats = await CKPoolService.get_pool_stats(pool.url)
            if raw_stats:
                stats = CKPoolService.format_stats_summary(raw_stats)
                total_workers += stats["workers"]
                total_hashrate_1m += stats["hashrate_1m_gh"]
                pool_count += 1
    
    if pool_count == 0:
        return {
            "workers": 0,
            "hashrate_1m_gh": 0.0,
            "hashrate_display": "0 GH/s",
            "status": "offline"
        }
    
    # Format hashrate display
    if total_hashrate_1m >= 1000:
        hashrate_display = f"{total_hashrate_1m / 1000:.2f} TH/s"
    else:
        hashrate_display = f"{total_hashrate_1m:.2f} GH/s"
    
    return {
        "workers": total_workers,
        "hashrate_1m_gh": round(total_hashrate_1m, 2),
        "hashrate_display": hashrate_display,
        "status": "online"
    }


@router.get("/widgets/ckpool-luck")
async def get_ckpool_luck_widget(db: AsyncSession = Depends(get_db), coin: str = None):
    """Get CKPool round luck (bestshare/network_difficulty, reset on block found) and blocks submitted in 24h. Optional coin parameter (BTC/BCH/DGB) to filter."""
    from core.ckpool import CKPoolService
    from core.database import CKPoolBlock
    from sqlalchemy import select as sql_select
    from datetime import datetime, timedelta
    import pytz
    import asyncio
    
    # Find all CKPool pools
    result = await db.execute(select(Pool))
    pools = result.scalars().all()
    
    best_share = 0
    pool_count = 0
    total_blocks_submitted_24h = 0
    block_found_recently = False
    network_difficulty = 0.0
    best_share_updated_at = None
    
    # Hard cutoff: 29 December 2025 at 9am UK time - ignore anything before this (ONE-TIME)
    uk_tz = pytz.timezone('Europe/London')
    cutoff_9am = uk_tz.localize(datetime(2025, 12, 29, 9, 0, 0))
    cutoff_9am_utc = cutoff_9am.astimezone(pytz.UTC).replace(tzinfo=None)
    
    for pool in pools:
        if CKPoolService.is_ckpool(pool.name):
            # Filter by coin type if specified
            if coin:
                pool_name_lower = pool.name.lower()
                if coin.upper() == 'BTC' and 'btc' not in pool_name_lower and 'bitcoin' not in pool_name_lower:
                    continue
                elif coin.upper() == 'BCH' and 'bch' not in pool_name_lower and 'bitcoin cash' not in pool_name_lower:
                    continue
                elif coin.upper() == 'DGB' and 'dgb' not in pool_name_lower and 'digibyte' not in pool_name_lower:
                    continue
            
            # Use cached network difficulty from database if available
            if pool.network_difficulty:
                network_difficulty = pool.network_difficulty
            
            # Fetch and cache blocks from log in background (also updates network difficulty)
            asyncio.create_task(CKPoolService.fetch_and_cache_blocks(pool.url, pool.id))
            
            # Check if a block was ACCEPTED since 9am today
            block_result = await db.execute(
                sql_select(CKPoolBlock)
                .where(CKPoolBlock.pool_id == pool.id)
                .where(CKPoolBlock.block_accepted == True)
                .where(CKPoolBlock.timestamp >= cutoff_9am_utc)
                .limit(1)
            )
            recent_block = block_result.scalar_one_or_none()
            
            if recent_block:
                block_found_recently = True
            
            # Get pool stats
            raw_stats = await CKPoolService.get_pool_stats(pool.url)
            if raw_stats:
                stats = CKPoolService.format_stats_summary(raw_stats)
                current_best_share = stats.get("best_share", 0)
                
                # If block found recently, reset tracking (new round started)
                if block_found_recently:
                    # Check if we need to reset or if already reset
                    if pool.best_share is None or pool.best_share > 0:
                        # First time seeing this block - reset tracking
                        pool.best_share = 0
                        pool.best_share_updated_at = datetime.utcnow()
                        await db.commit()
                    
                    # Now check if we have a new share in the new round
                    if current_best_share > 0:
                        best_share = current_best_share
                        # Update tracking with new share
                        pool.best_share = current_best_share
                        pool.best_share_updated_at = datetime.utcnow()
                        await db.commit()
                        best_share_updated_at = pool.best_share_updated_at
                    else:
                        # Still at 0, use the reset timestamp
                        best_share = 0
                        best_share_updated_at = pool.best_share_updated_at
                else:
                    # Normal operation - track improvements
                    best_share = current_best_share
                    
                    # Track best_share improvements
                    if pool.best_share is None or current_best_share > pool.best_share:
                        # Best share improved!
                        pool.best_share = current_best_share
                        pool.best_share_updated_at = datetime.utcnow()
                        await db.commit()
                    
                    # Use stored timestamp
                    best_share_updated_at = pool.best_share_updated_at
                
                pool_count += 1
            
            # Get blocks SUBMITTED (not accepted) in last 24h
            blocks_submitted = await CKPoolService.get_blocks_24h(pool.id)
            total_blocks_submitted_24h += blocks_submitted
    
    if pool_count == 0:
        return {
            "round_luck": 0.0,
            "best_share": 0,
            "network_difficulty": 0.0,
            "blocks_submitted_24h": 0,
            "luck_display": "0%",
            "time_since_improvement": None,
            "status": "offline"
        }
    
    # Calculate time since last improvement (using central helper)
    time_since_improvement = format_time_elapsed(best_share_updated_at)
    
    # Calculate round luck percentage using network difficulty
    round_luck = (best_share / network_difficulty * 100) if network_difficulty > 0 else 0.0
    
    return {
        "round_luck": round(round_luck, 2),
        "best_share": best_share,
        "network_difficulty": network_difficulty,
        "blocks_submitted_24h": total_blocks_submitted_24h,
        "luck_display": f"{round_luck:.0f}%",
        "block_found_recently": block_found_recently,
        "time_since_improvement": time_since_improvement,
        "status": "online"
    }


@router.get("/widgets/ckpool-blocks")
async def get_ckpool_blocks_widget(db: AsyncSession = Depends(get_db), coin: str = None):
    """Get CKPool blocks found (1d/7d/28d) and 24h value in GBP. Optional coin parameter (BTC/BCH/DGB) to filter."""
    from core.ckpool import CKPoolService
    
    # Find all CKPool pools
    result = await db.execute(select(Pool))
    pools = result.scalars().all()
    
    total_blocks_1d = 0
    total_blocks_7d = 0
    total_blocks_28d = 0
    pool_count = 0
    coin_type = None  # Track coin type for reward calculation
    
    for pool in pools:
        if CKPoolService.is_ckpool(pool.name):
            # Try to determine coin type from pool name
            pool_name_lower = pool.name.lower()
            if 'btc' in pool_name_lower or 'bitcoin' in pool_name_lower:
                pool_coin_type = 'BTC'
            elif 'bch' in pool_name_lower or 'bitcoin cash' in pool_name_lower:
                pool_coin_type = 'BCH'
            elif 'dgb' in pool_name_lower or 'digibyte' in pool_name_lower:
                pool_coin_type = 'DGB'
            else:
                pool_coin_type = None
            
            # Filter by coin type if specified
            if coin and pool_coin_type != coin.upper():
                continue
            
            # Set coin_type if not set yet
            if not coin_type:
                coin_type = pool_coin_type
            
            # Fetch and cache blocks from log (non-blocking)
            import asyncio
            asyncio.create_task(CKPoolService.fetch_and_cache_blocks(pool.url, pool.id))
            
            # Get accepted blocks for different timeframes
            blocks_1d = await CKPoolService.get_blocks_accepted(pool.id, 1)
            blocks_7d = await CKPoolService.get_blocks_accepted(pool.id, 7)
            blocks_28d = await CKPoolService.get_blocks_accepted(pool.id, 28)
            
            total_blocks_1d += blocks_1d
            total_blocks_7d += blocks_7d
            total_blocks_28d += blocks_28d
            pool_count += 1
    
    if pool_count == 0:
        return {
            "blocks_1d": 0,
            "blocks_7d": 0,
            "blocks_28d": 0,
            "value_24h_gbp": 0.0,
            "value_display": "£0.00",
            "status": "offline"
        }
    
    # Calculate 24h value if blocks found (using cached prices)
    value_24h_gbp = 0.0
    if total_blocks_1d > 0 and coin_type:
        from core.utils import get_cached_crypto_price
        
        try:
            if coin_type == 'BTC':
                btc_price_gbp = await get_cached_crypto_price(db, 'bitcoin')
                value_24h_gbp = total_blocks_1d * 3.125 * btc_price_gbp
            elif coin_type == 'BCH':
                bch_price_gbp = await get_cached_crypto_price(db, 'bitcoin-cash')
                value_24h_gbp = total_blocks_1d * 3.125 * bch_price_gbp
            elif coin_type == 'DGB':
                dgb_price_gbp = await get_cached_crypto_price(db, 'digibyte')
                value_24h_gbp = total_blocks_1d * 277.376 * dgb_price_gbp
        except Exception as e:
            print(f"⚠️ Failed to get cached coin price: {e}")
    
    return {
        "blocks_1d": total_blocks_1d,
        "blocks_7d": total_blocks_7d,
        "blocks_28d": total_blocks_28d,
        "value_24h_gbp": round(value_24h_gbp, 2),
        "value_display": f"£{value_24h_gbp:.2f}",
        "coin_type": coin_type,
        "status": "online"
    }


@router.get("/widgets/ckpool-reward")
async def get_ckpool_reward_widget(db: AsyncSession = Depends(get_db), coin: str = None):
    """Get CKPool all-time rewards (cumulative blocks × reward) with GBP value. Optional coin parameter (BTC/BCH/DGB) to filter."""
    from core.ckpool import CKPoolService
    from core.database import CKPoolBlock
    from sqlalchemy import select as sql_select, func
    
    # Find all CKPool pools
    result = await db.execute(select(Pool))
    pools = result.scalars().all()
    
    total_blocks_all_time = 0
    total_confirmed_rewards = 0.0
    pool_count = 0
    coin_type = None
    
    for pool in pools:
        if CKPoolService.is_ckpool(pool.name):
            # Filter by coin type if specified
            if coin:
                pool_name_lower = pool.name.lower()
                if coin.upper() == 'BTC' and 'btc' not in pool_name_lower and 'bitcoin' not in pool_name_lower:
                    continue
                elif coin.upper() == 'BCH' and 'bch' not in pool_name_lower and 'bitcoin cash' not in pool_name_lower:
                    continue
                elif coin.upper() == 'DGB' and 'dgb' not in pool_name_lower and 'digibyte' not in pool_name_lower:
                    continue
            
            # Fetch and cache blocks from log (non-blocking)
            import asyncio
            asyncio.create_task(CKPoolService.fetch_and_cache_blocks(pool.url, pool.id))
            
            # Try to determine coin type from pool name
            pool_name_lower = pool.name.lower()
            if 'btc' in pool_name_lower or 'bitcoin' in pool_name_lower:
                coin_type = 'BTC'
            elif 'bch' in pool_name_lower or 'bitcoin cash' in pool_name_lower:
                coin_type = 'BCH'
            elif 'dgb' in pool_name_lower or 'digibyte' in pool_name_lower:
                coin_type = 'DGB'
            
            # Trigger explorer verification in background (non-blocking)
            if coin_type:
                asyncio.create_task(CKPoolService.update_confirmed_rewards(pool.id, coin_type))
            
            # Get ALL accepted blocks and sum confirmed rewards
            blocks_result = await db.execute(
                sql_select(CKPoolBlock)
                .where(CKPoolBlock.pool_id == pool.id)
                .where(CKPoolBlock.block_accepted == True)
            )
            blocks = blocks_result.scalars().all()
            
            for block in blocks:
                total_blocks_all_time += 1
                # Use confirmed reward if available from blockchain explorer, otherwise use fallback
                if block.confirmed_reward_coins and block.confirmed_from_explorer:
                    total_confirmed_rewards += block.confirmed_reward_coins
                else:
                    # Fallback to estimated reward (current block rewards as of January 2025)
                    # This applies to accepted blocks that haven't been verified via explorer yet
                    if coin_type == 'BTC' or coin_type == 'BCH':
                        total_confirmed_rewards += 3.125
                    elif coin_type == 'DGB':
                        total_confirmed_rewards += 277.376  # Current DGB block reward after latest halving
            
            pool_count += 1
    
    if pool_count == 0:
        return {
            "total_blocks": 0,
            "total_coins": 0.0,
            "coin_type": None,
            "value_gbp": 0.0,
            "coins_display": "0",
            "value_display": "£0.00",
            "status": "offline"
        }
    
    # Calculate GBP value using cached prices
    value_gbp = 0.0
    if coin_type and total_confirmed_rewards > 0:
        from core.utils import get_cached_crypto_price
        
        try:
            coin_id_map = {
                'BTC': 'bitcoin',
                'BCH': 'bitcoin-cash',
                'DGB': 'digibyte'
            }
            coin_id = coin_id_map.get(coin_type)
            if coin_id:
                price_gbp = await get_cached_crypto_price(db, coin_id)
                value_gbp = total_confirmed_rewards * price_gbp
        except Exception as e:
            print(f"⚠️ Failed to get cached coin price: {e}")
    
    # Format coin display
    coin_symbol = coin_type or "COIN"
    if coin_type == 'DGB':
        coins_display = f"{total_confirmed_rewards:.8f} {coin_symbol}"
    else:
        coins_display = f"{total_confirmed_rewards:.8f} {coin_symbol}"
    
    return {
        "total_blocks": total_blocks_all_time,
        "total_coins": total_confirmed_rewards,
        "coin_type": coin_type,
        "value_gbp": round(value_gbp, 2),
        "coins_display": coins_display,
        "value_display": f"£{value_gbp:,.2f}",
        "status": "online"
    }
