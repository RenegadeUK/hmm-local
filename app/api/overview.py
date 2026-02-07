"""
Long-term analytics overview API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from datetime import datetime, timedelta
from typing import List, Optional
from pydantic import BaseModel

from core.database import (
    get_db, Miner, DailyMinerStats, DailyPoolStats, MonthlyMinerStats
)
from core.utils import format_hashrate

router = APIRouter()


class MonthlyProfitData(BaseModel):
    """Monthly profit/loss data"""
    month: str  # YYYY-MM
    total_earnings: float
    total_energy_cost: float
    total_profit: float
    total_kwh: float
    avg_hashrate: Optional[float] = None
    hashrate_unit: str = "GH/s"


class MinerROI(BaseModel):
    """ROI data for a single miner"""
    miner_id: int
    miner_name: str
    miner_type: str
    total_earnings: float
    total_energy_cost: float
    total_profit: float
    avg_monthly_profit: float
    uptime_percent: float
    days_active: int


class PoolPerformanceSummary(BaseModel):
    """Pool performance summary"""
    pool_id: int
    pool_name: str
    avg_health_score: Optional[float] = None
    avg_latency_ms: Optional[float] = None
    avg_luck_percent: Optional[float] = None
    total_shares: int
    uptime_percent: float


@router.get("/api/analytics/overview/monthly-pl", response_model=List[MonthlyProfitData])
async def get_monthly_profit_loss(
    months: int = 12,
    db: AsyncSession = Depends(get_db)
):
    """Get monthly profit/loss data for all miners combined"""
    # Get monthly stats for last N months
    cutoff = datetime.utcnow() - timedelta(days=months * 31)
    
    query = select(MonthlyMinerStats).where(
        MonthlyMinerStats.created_at >= cutoff
    ).order_by(
        MonthlyMinerStats.year.asc(),
        MonthlyMinerStats.month.asc()
    )
    
    result = await db.execute(query)
    stats = result.scalars().all()
    
    # Group by year-month
    monthly_data = {}
    for stat in stats:
        key = f"{stat.year}-{stat.month:02d}"
        if key not in monthly_data:
            monthly_data[key] = {
                "earnings": 0.0,
                "cost": 0.0,
                "kwh": 0.0,
                "hashrates": []
            }
        monthly_data[key]["earnings"] += stat.total_earnings_gbp
        monthly_data[key]["cost"] += stat.total_energy_cost_gbp
        monthly_data[key]["kwh"] += stat.total_kwh or 0.0
        if stat.avg_hashrate:
            monthly_data[key]["hashrates"].append({
                "value": stat.avg_hashrate,
                "unit": stat.hashrate_unit or "GH/s"
            })
    
    # Convert to response format
    results = []
    for month_key in sorted(monthly_data.keys()):
        data = monthly_data[month_key]
        
        # Calculate average hashrate (only GH/s for now)
        gh_hashrates = [h["value"] for h in data["hashrates"] if h["unit"] == "GH/s"]
        avg_hashrate_value = sum(gh_hashrates) / len(gh_hashrates) if gh_hashrates else 0
        
        results.append(MonthlyProfitData(
            month=month_key,
            total_earnings=round(data["earnings"], 2),
            total_energy_cost=round(data["cost"], 2),
            total_profit=round(data["earnings"] - data["cost"], 2),
            total_kwh=round(data["kwh"], 2),
            avg_hashrate=format_hashrate(avg_hashrate_value, "GH/s"),
            hashrate_unit="GH/s"
        ))
    
    return results


@router.get("/api/analytics/overview/miner-roi", response_model=List[MinerROI])
async def get_miner_roi(
    months: int = 12,
    db: AsyncSession = Depends(get_db)
):
    """Get ROI comparison for all miners"""
    cutoff = datetime.utcnow() - timedelta(days=months * 31)
    
    # Get all miners
    miners_result = await db.execute(select(Miner))
    miners = {m.id: m for m in miners_result.scalars().all()}
    
    # Get monthly stats
    query = select(MonthlyMinerStats).where(
        MonthlyMinerStats.created_at >= cutoff
    )
    result = await db.execute(query)
    stats = result.scalars().all()
    
    # Aggregate by miner
    miner_data = {}
    for stat in stats:
        if stat.miner_id not in miner_data:
            miner_data[stat.miner_id] = {
                "earnings": 0.0,
                "cost": 0.0,
                "uptime": [],
                "days": 0
            }
        miner_data[stat.miner_id]["earnings"] += stat.total_earnings_gbp
        miner_data[stat.miner_id]["cost"] += stat.total_energy_cost_gbp
        miner_data[stat.miner_id]["uptime"].append(stat.uptime_percent)
        miner_data[stat.miner_id]["days"] += stat.days_active
    
    # Convert to response
    results = []
    for miner_id, data in miner_data.items():
        if miner_id not in miners:
            continue
        
        miner = miners[miner_id]
        total_profit = data["earnings"] - data["cost"]
        avg_monthly = total_profit / months if months > 0 else 0
        avg_uptime = sum(data["uptime"]) / len(data["uptime"]) if data["uptime"] else 0
        
        results.append(MinerROI(
            miner_id=miner.id,
            miner_name=miner.name,
            miner_type=miner.miner_type,
            total_earnings=round(data["earnings"], 2),
            total_energy_cost=round(data["cost"], 2),
            total_profit=round(total_profit, 2),
            avg_monthly_profit=round(avg_monthly, 2),
            uptime_percent=round(avg_uptime, 2),
            days_active=data["days"]
        ))
    
    return results


@router.get("/api/analytics/overview/hardware-comparison")
async def get_hardware_comparison(
    days: int = 30,
    db: AsyncSession = Depends(get_db)
):
    """Compare ASIC vs CPU miner operational performance"""
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    # Get daily stats
    query = select(DailyMinerStats).where(
        DailyMinerStats.date >= cutoff
    )
    result = await db.execute(query)
    stats = result.scalars().all()
    
    # Get miners
    miners_result = await db.execute(select(Miner))
    miners = {m.id: m for m in miners_result.scalars().all()}
    
    # Group by type
    asic_stats = {"hashrates": [], "temps": [], "powers": [], "costs": [], "kwh": 0, "uptime": [], "reject_rates": [], "count": 0}
    # All stats go to asic_stats since we no longer support CPU miners
    for stat in stats:
        if stat.miner_id not in miners:
            continue
        
        miner = miners[stat.miner_id]
        
        if stat.avg_hashrate: asic_stats["hashrates"].append(stat.avg_hashrate)
        if stat.avg_temperature: asic_stats["temps"].append(stat.avg_temperature)
        if stat.avg_power: asic_stats["powers"].append(stat.avg_power)
        asic_stats["costs"].append(stat.energy_cost_gbp)
        asic_stats["kwh"] += stat.total_kwh or 0
        asic_stats["uptime"].append(stat.uptime_percent)
        if stat.reject_rate_percent: asic_stats["reject_rates"].append(stat.reject_rate_percent)
        asic_stats["count"] += 1
    
    # Calculate averages
    avg_hr_value = sum(asic_stats["hashrates"]) / len(asic_stats["hashrates"]) if asic_stats["hashrates"] else 0
    return {
        "asic": {
            "avg_hashrate_ghs": format_hashrate(avg_hr_value, "GH/s"),
            "avg_temperature": round(sum(asic_stats["temps"]) / len(asic_stats["temps"]), 2) if asic_stats["temps"] else 0,
            "avg_power_watts": round(sum(asic_stats["powers"]) / len(asic_stats["powers"]), 2) if asic_stats["powers"] else 0,
            "total_cost_gbp": round(sum(asic_stats["costs"]), 2),
            "total_kwh": round(asic_stats["kwh"], 2),
            "avg_uptime_percent": round(sum(asic_stats["uptime"]) / len(asic_stats["uptime"]), 2) if asic_stats["uptime"] else 0,
            "avg_reject_rate": round(sum(asic_stats["reject_rates"]) / len(asic_stats["reject_rates"]), 2) if asic_stats["reject_rates"] else 0,
            "data_points": asic_stats["count"]
        },
        "period_days": days
    }


@router.get("/api/analytics/overview/pool-performance", response_model=List[PoolPerformanceSummary])
async def get_pool_performance(
    days: int = 30,
    db: AsyncSession = Depends(get_db)
):
    """Get pool performance summary"""
    from core.database import Pool
    
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    # Get pool stats
    query = select(DailyPoolStats).where(
        DailyPoolStats.date >= cutoff
    )
    result = await db.execute(query)
    stats = result.scalars().all()
    
    # Get pools
    pools_result = await db.execute(select(Pool))
    pools = {p.id: p for p in pools_result.scalars().all()}
    
    # Aggregate by pool
    pool_data = {}
    for stat in stats:
        if stat.pool_id not in pool_data:
            pool_data[stat.pool_id] = {
                "health": [],
                "latency": [],
                "luck": [],
                "shares": 0,
                "uptime": []
            }
        if stat.avg_health_score:
            pool_data[stat.pool_id]["health"].append(stat.avg_health_score)
        if stat.avg_latency_ms:
            pool_data[stat.pool_id]["latency"].append(stat.avg_latency_ms)
        if stat.avg_luck_percent:
            pool_data[stat.pool_id]["luck"].append(stat.avg_luck_percent)
        pool_data[stat.pool_id]["shares"] += stat.total_shares_submitted
        pool_data[stat.pool_id]["uptime"].append(stat.uptime_percent)
    
    # Convert to response
    results = []
    for pool_id, data in pool_data.items():
        if pool_id not in pools:
            continue
        
        pool = pools[pool_id]
        results.append(PoolPerformanceSummary(
            pool_id=pool.id,
            pool_name=pool.name,
            avg_health_score=round(sum(data["health"]) / len(data["health"]), 2) if data["health"] else None,
            avg_latency_ms=round(sum(data["latency"]) / len(data["latency"]), 2) if data["latency"] else None,
            avg_luck_percent=round(sum(data["luck"]) / len(data["luck"]), 2) if data["luck"] else None,
            total_shares=data["shares"],
            uptime_percent=round(sum(data["uptime"]) / len(data["uptime"]), 2) if data["uptime"] else 100.0
        ))
    
    return results
