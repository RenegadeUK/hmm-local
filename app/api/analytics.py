"""
Analytics API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta
from typing import List, Optional
from pydantic import BaseModel
import io
import csv

from core.database import get_db, Miner, Telemetry, HealthScore
from core.health import HealthScoringService


router = APIRouter()


class HealthScoreResponse(BaseModel):
    overall_score: float
    uptime_score: float
    temperature_score: Optional[float] = None  # Optional for XMRig miners without temp sensors
    hashrate_score: float
    reject_rate_score: float
    data_points: int
    period_hours: int


class TelemetryStatsResponse(BaseModel):
    avg_hashrate: Optional[float]
    min_hashrate: Optional[float]
    max_hashrate: Optional[float]
    hashrate_unit: Optional[str]
    avg_temperature: Optional[float]
    max_temperature: Optional[float]
    avg_power: Optional[float]
    total_accepted: Optional[int]
    total_rejected: Optional[int]
    reject_rate: Optional[float]
    uptime_percent: float
    data_points: int


@router.get("/miners/{miner_id}/health", response_model=HealthScoreResponse)
async def get_miner_health(
    miner_id: int,
    hours: int = 24,
    db: AsyncSession = Depends(get_db)
):
    """Get current health score for a miner"""
    # Check miner exists
    result = await db.execute(select(Miner).where(Miner.id == miner_id))
    miner = result.scalar_one_or_none()
    
    if not miner:
        raise HTTPException(status_code=404, detail="Miner not found")
    
    score_data = await HealthScoringService.calculate_health_score(miner_id, db, hours)
    
    if not score_data:
        raise HTTPException(status_code=404, detail="Insufficient data to calculate health score")
    
    return score_data


@router.get("/miners/{miner_id}/health/trend")
async def get_miner_health_trend(
    miner_id: int,
    days: int = 7,
    db: AsyncSession = Depends(get_db)
):
    """Get health score trend over time"""
    result = await db.execute(select(Miner).where(Miner.id == miner_id))
    miner = result.scalar_one_or_none()
    
    if not miner:
        raise HTTPException(status_code=404, detail="Miner not found")
    
    trend_data = await HealthScoringService.get_health_trend(miner_id, db, days)
    
    return {"miner_id": miner_id, "miner_name": miner.name, "trend": trend_data}


@router.get("/miners/{miner_id}/telemetry/stats", response_model=TelemetryStatsResponse)
async def get_telemetry_stats(
    miner_id: int,
    hours: int = 24,
    db: AsyncSession = Depends(get_db)
):
    """Get aggregated telemetry statistics"""
    result = await db.execute(select(Miner).where(Miner.id == miner_id))
    miner = result.scalar_one_or_none()
    
    if not miner:
        raise HTTPException(status_code=404, detail="Miner not found")
    
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)
    
    # Get telemetry data
    result = await db.execute(
        select(Telemetry)
        .where(Telemetry.miner_id == miner_id)
        .where(Telemetry.timestamp >= cutoff_time)
        .order_by(Telemetry.timestamp.asc())
    )
    telemetry_data = result.scalars().all()
    
    if not telemetry_data:
        raise HTTPException(status_code=404, detail="No telemetry data found")
    
    # Calculate statistics
    hashrates = [t.hashrate for t in telemetry_data if t.hashrate is not None]
    temperatures = [t.temperature for t in telemetry_data if t.temperature is not None]
    powers = [t.power_watts for t in telemetry_data if t.power_watts is not None]
    
    first = telemetry_data[0]
    last = telemetry_data[-1]
    
    accepted_delta = (last.shares_accepted or 0) - (first.shares_accepted or 0)
    rejected_delta = (last.shares_rejected or 0) - (first.shares_rejected or 0)
    total_shares = accepted_delta + rejected_delta
    reject_rate = (rejected_delta / total_shares * 100) if total_shares > 0 else 0
    
    # Calculate uptime
    expected_points = hours * 120  # One every 30 seconds
    actual_points = len(telemetry_data)
    uptime_percent = min((actual_points / expected_points) * 100, 100)
    
    return {
        "avg_hashrate": sum(hashrates) / len(hashrates) if hashrates else None,
        "min_hashrate": min(hashrates) if hashrates else None,
        "max_hashrate": max(hashrates) if hashrates else None,
        "hashrate_unit": last.hashrate_unit if last else "GH/s",
        "avg_temperature": sum(temperatures) / len(temperatures) if temperatures else None,
        "max_temperature": max(temperatures) if temperatures else None,
        "avg_power": sum(powers) / len(powers) if powers else None,
        "total_accepted": accepted_delta,
        "total_rejected": rejected_delta,
        "reject_rate": round(reject_rate, 2),
        "uptime_percent": round(uptime_percent, 2),
        "data_points": len(telemetry_data)
    }


@router.get("/miners/{miner_id}/telemetry/timeseries")
async def get_telemetry_timeseries(
    miner_id: int,
    hours: int = 24,
    metric: str = "hashrate",
    db: AsyncSession = Depends(get_db)
):
    """Get time-series data for charts"""
    result = await db.execute(select(Miner).where(Miner.id == miner_id))
    miner = result.scalar_one_or_none()
    
    if not miner:
        raise HTTPException(status_code=404, detail="Miner not found")
    
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)
    
    result = await db.execute(
        select(Telemetry)
        .where(Telemetry.miner_id == miner_id)
        .where(Telemetry.timestamp >= cutoff_time)
        .order_by(Telemetry.timestamp.asc())
    )
    telemetry_data = result.scalars().all()
    
    # Map metric to field
    metric_map = {
        "hashrate": "hashrate",
        "temperature": "temperature",
        "power": "power_watts"
    }
    
    if metric not in metric_map:
        raise HTTPException(status_code=400, detail=f"Invalid metric. Choose from: {', '.join(metric_map.keys())}")
    
    field = metric_map[metric]
    
    data_points = [
        {
            "timestamp": t.timestamp.isoformat(),
            "value": getattr(t, field)
        }
        for t in telemetry_data
        if getattr(t, field) is not None
    ]
    
    return {
        "miner_id": miner_id,
        "miner_name": miner.name,
        "metric": metric,
        "data": data_points
    }


@router.get("/miners/{miner_id}/export/csv")
async def export_telemetry_csv(
    miner_id: int,
    hours: int = 24,
    db: AsyncSession = Depends(get_db)
):
    """Export telemetry data as CSV"""
    result = await db.execute(select(Miner).where(Miner.id == miner_id))
    miner = result.scalar_one_or_none()
    
    if not miner:
        raise HTTPException(status_code=404, detail="Miner not found")
    
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)
    
    result = await db.execute(
        select(Telemetry)
        .where(Telemetry.miner_id == miner_id)
        .where(Telemetry.timestamp >= cutoff_time)
        .order_by(Telemetry.timestamp.asc())
    )
    telemetry_data = result.scalars().all()
    
    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        "Timestamp",
        "Hashrate (GH/s)",
        "Temperature (°C)",
        "Power (W)",
        "Shares Accepted",
        "Shares Rejected",
        "Pool"
    ])
    
    # Write data
    for t in telemetry_data:
        writer.writerow([
            t.timestamp.isoformat(),
            t.hashrate or "",
            t.temperature or "",
            t.power_watts or "",
            t.shares_accepted or "",
            t.shares_rejected or "",
            t.pool_in_use or ""
        ])
    
    output.seek(0)
    
    filename = f"{miner.name}_telemetry_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/overview/stats")
async def get_overview_stats(db: AsyncSession = Depends(get_db)):
    """Get overview statistics for all miners"""
    from sqlalchemy import func
    result = await db.execute(select(Miner).where(Miner.enabled == True).order_by(func.lower(Miner.name)))
    miners = result.scalars().all()
    
    total_miners = len(miners)
    online_miners = 0
    total_hashrate = 0.0
    avg_temperature = 0.0
    total_power = 0.0
    
    cutoff_time = datetime.utcnow() - timedelta(minutes=5)
    
    for miner in miners:
        # Get latest telemetry
        result = await db.execute(
            select(Telemetry)
            .where(Telemetry.miner_id == miner.id)
            .where(Telemetry.timestamp >= cutoff_time)
            .order_by(Telemetry.timestamp.desc())
            .limit(1)
        )
        latest = result.scalar_one_or_none()
        
        if latest:
            online_miners += 1
            if latest.hashrate:
                total_hashrate += latest.hashrate
            if latest.temperature:
                avg_temperature += latest.temperature
            if latest.power_watts:
                total_power += latest.power_watts
    
    avg_temperature = avg_temperature / online_miners if online_miners > 0 else 0
    
    return {
        "total_miners": total_miners,
        "online_miners": online_miners,
        "offline_miners": total_miners - online_miners,
        "total_hashrate": round(total_hashrate, 2),
        "avg_temperature": round(avg_temperature, 1),
        "total_power": round(total_power, 2)
    }


@router.get("/miners/{miner_id}/health/predictions")
async def get_health_predictions(miner_id: int, db: AsyncSession = Depends(get_db)):
    """Get hardware health predictions for a miner"""
    from core.predictions import HealthPredictionService
    
    result = await db.execute(select(Miner).where(Miner.id == miner_id))
    miner = result.scalar_one_or_none()
    
    if not miner:
        raise HTTPException(status_code=404, detail="Miner not found")
    
    prediction = await HealthPredictionService.predict_hardware_issues(miner_id, db)
    
    if not prediction:
        raise HTTPException(status_code=404, detail="Could not generate predictions")
    
    return prediction.to_dict()
