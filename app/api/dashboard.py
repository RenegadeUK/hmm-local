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
    
    # Calculate total 24h cost across all miners
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
        
        # Calculate cost by matching telemetry with energy prices
        for i, (power, timestamp) in enumerate(telemetry_records):
            if power is None or power <= 0:
                continue
            
            # Find energy price for this timestamp
            result = await db.execute(
                select(EnergyPrice.price_pence)
                .where(EnergyPrice.valid_from <= timestamp)
                .where(EnergyPrice.valid_to > timestamp)
                .limit(1)
            )
            price_pence = result.scalar()
            
            if price_pence is None:
                continue
            
            # Calculate time duration (assume 30s intervals)
            duration_hours = 0.00833  # 30 seconds in hours
            
            # Calculate cost: (power_watts / 1000) * duration_hours * price_pence_per_kwh
            kwh = (power / 1000.0) * duration_hours
            cost = kwh * price_pence
            total_cost_pence += cost
    
    return {
        "total_miners": total_miners,
        "active_miners": active_miners,
        "total_hashrate_ghs": round(total_hashrate, 2),
        "current_energy_price_pence": current_price,
        "recent_events_24h": recent_events,
        "total_cost_24h_pence": round(total_cost_pence, 2),
        "total_cost_24h_pounds": round(total_cost_pence / 100, 2)
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
