"""
Energy Costs Analysis API
Provides cost breakdowns and baseline comparisons for energy consumption
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from datetime import datetime, timedelta
from typing import List, Dict, Any
from decimal import Decimal

from core.database import (
    get_db, Miner, Telemetry, EnergyPrice, 
    DailyMinerStats, MonthlyMinerStats
)

router = APIRouter()


@router.get("/hourly")
async def get_hourly_costs(
    hours: int = Query(default=24, ge=1, le=168),  # Max 7 days
    db: AsyncSession = Depends(get_db)
):
    """
    Get hourly energy costs for the last N hours.
    Calculates actual cost vs baseline (if all miners ran 24/7).
    Uses per-reading calculation (same as dashboard) for accuracy.
    """
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    
    # Get all active miners
    miners_result = await db.execute(
        select(Miner).where(Miner.enabled == True)
    )
    miners = miners_result.scalars().all()
    miner_ids = [m.id for m in miners]
    
    if not miner_ids:
        return {
            "hours": [],
            "summary": {
                "total_actual_cost": 0,
                "total_baseline_cost": 0,
                "total_savings": 0,
                "savings_percent": 0
            }
        }
    
    # Get pricing data for the period (past data only, no future)
    now = datetime.utcnow()
    pricing_result = await db.execute(
        select(EnergyPrice)
        .where(
            and_(
                EnergyPrice.valid_from >= cutoff,
                EnergyPrice.valid_from <= now
            )
        )
        .order_by(EnergyPrice.valid_from)
    )
    energy_prices = pricing_result.scalars().all()
    
    # Create price lookup function (same as dashboard)
    def get_price_for_timestamp(ts):
        for price in energy_prices:
            if price.valid_from <= ts < price.valid_to:
                return price.price_pence
        return None
    
    # Get all telemetry for the period
    telemetry_result = await db.execute(
        select(Telemetry)
        .where(
            and_(
                Telemetry.miner_id.in_(miner_ids),
                Telemetry.timestamp >= cutoff
            )
        )
        .order_by(Telemetry.miner_id, Telemetry.timestamp.asc())
    )
    all_telemetry = telemetry_result.scalars().all()
    
    # Group telemetry by miner
    telemetry_by_miner = {}
    for tel in all_telemetry:
        if tel.miner_id not in telemetry_by_miner:
            telemetry_by_miner[tel.miner_id] = []
        telemetry_by_miner[tel.miner_id].append(tel)
    
    # Calculate per-reading costs (same method as dashboard)
    hourly_costs = {}
    miner_avg_power = {}
    
    for miner in miners:
        telemetry_records = telemetry_by_miner.get(miner.id, [])
        if not telemetry_records:
            continue
        
        miner_power_readings = []
        
        # Process each telemetry reading
        for i, tel in enumerate(telemetry_records):
            power = tel.power_watts
            
            # Fallback to manual power if no auto-detected power
            if not power or power <= 0:
                if miner.manual_power_watts:
                    power = miner.manual_power_watts
                else:
                    continue
            
            miner_power_readings.append(power)
            
            # Get price for this timestamp
            price_pence = get_price_for_timestamp(tel.timestamp)
            if price_pence is None:
                continue
            
            # Calculate duration until next reading (capped at 10 minutes)
            if i < len(telemetry_records) - 1:
                next_timestamp = telemetry_records[i + 1].timestamp
                duration_seconds = (next_timestamp - tel.timestamp).total_seconds()
                duration_hours = duration_seconds / 3600.0
                
                # Cap at 10 minutes to prevent counting offline gaps
                max_duration_hours = 10.0 / 60.0
                if duration_hours > max_duration_hours:
                    duration_hours = max_duration_hours
            else:
                duration_hours = 30.0 / 3600.0  # Last reading assumes 30 seconds
            
            # Calculate cost for this period
            kwh = (power / 1000.0) * duration_hours
            cost_pence = kwh * price_pence
            
            # Group by hour
            hour_dt = tel.timestamp.replace(minute=0, second=0, microsecond=0)
            if hour_dt not in hourly_costs:
                hourly_costs[hour_dt] = {
                    "hour": hour_dt.strftime('%Y-%m-%d %H:00:00'),
                    "actual_cost": 0,
                    "baseline_cost": 0,
                    "miners": {}
                }
            
            hourly_costs[hour_dt]["actual_cost"] += cost_pence / 100.0  # Convert to GBP
        
        # Track average power for baseline calculation
        if miner_power_readings:
            avg_power = sum(miner_power_readings) / len(miner_power_readings)
            miner_avg_power[miner.id] = avg_power
    
    # Calculate baseline costs (if all miners ran 24/7 at their average power)
    # Use exact 30-minute price slots, not hourly averages
    current_hour = now.replace(minute=0, second=0, microsecond=0)
    
    for miner_id, avg_power in miner_avg_power.items():
        # Iterate through each 30-minute price slot
        for price in energy_prices:
            if price.valid_from > now:
                continue
            
            # Calculate cost for this 30-minute slot
            slot_duration_hours = 0.5  # 30 minutes
            baseline_kwh = (avg_power / 1000.0) * slot_duration_hours
            baseline_cost_pence = baseline_kwh * float(price.price_pence)
            
            # Add to the hour bucket for display
            hour_dt = price.valid_from.replace(minute=0, second=0, microsecond=0)
            if hour_dt not in hourly_costs:
                hourly_costs[hour_dt] = {
                    "hour": hour_dt.strftime('%Y-%m-%d %H:00:00'),
                    "actual_cost": 0,
                    "baseline_cost": 0,
                    "miners": {}
                }
            
            hourly_costs[hour_dt]["baseline_cost"] += baseline_cost_pence / 100.0
    
    # Filter out any future hours and sort by hour
    sorted_hours = sorted(
        [h for h in hourly_costs.values() if datetime.fromisoformat(h["hour"]) <= current_hour],
        key=lambda x: x["hour"]
    )
    for hour_data in sorted_hours:
        hour_data["savings"] = hour_data["baseline_cost"] - hour_data["actual_cost"]
        hour_data["savings_percent"] = (
            (hour_data["savings"] / hour_data["baseline_cost"] * 100)
            if hour_data["baseline_cost"] > 0 else 0
        )
    
    # Calculate summary
    total_actual = sum(h["actual_cost"] for h in sorted_hours)
    total_baseline = sum(h["baseline_cost"] for h in sorted_hours)
    total_savings = total_baseline - total_actual
    
    return {
        "hours": sorted_hours,
        "summary": {
            "total_actual_cost": round(total_actual, 2),
            "total_baseline_cost": round(total_baseline, 2),
            "total_savings": round(total_savings, 2),
            "savings_percent": round(
                (total_savings / total_baseline * 100) if total_baseline > 0 else 0,
                1
            )
        }
    }


@router.get("/daily")
async def get_daily_costs(
    days: int = Query(default=30, ge=1, le=90),
    db: AsyncSession = Depends(get_db)
):
    """
    Get daily energy costs from DailyMinerStats.
    Includes baseline comparison.
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    # Query daily stats
    result = await db.execute(
        select(DailyMinerStats)
        .where(DailyMinerStats.date >= cutoff)
        .order_by(DailyMinerStats.date)
    )
    daily_stats = result.scalars().all()
    
    # Group by date
    costs_by_date = {}
    for stat in daily_stats:
        date_key = stat.date.strftime('%Y-%m-%d')
        
        if date_key not in costs_by_date:
            costs_by_date[date_key] = {
                "date": date_key,
                "actual_cost": 0,
                "baseline_cost": 0,
                "total_kwh": 0,
                "miners": []
            }
        
        actual_cost = float(stat.energy_cost_gbp or 0)
        costs_by_date[date_key]["actual_cost"] += actual_cost
        costs_by_date[date_key]["total_kwh"] += float(stat.total_kwh or 0)
        
        # Baseline: assume ran 24 hours at average power
        avg_power = float(stat.avg_power or 0)
        uptime_hours = 24 * (stat.uptime_percent / 100.0)
        missed_hours = 24 - uptime_hours
        
        if missed_hours > 0 and avg_power > 0:
            # Calculate what the missed hours would have cost
            # Use actual cost per kwh as proxy for price that day
            kwh_when_on = float(stat.total_kwh or 0)
            if kwh_when_on > 0:
                price_per_kwh = actual_cost / kwh_when_on  # GBP per kWh
                baseline_kwh_missed = (avg_power / 1000.0) * missed_hours
                baseline_cost_missed = baseline_kwh_missed * price_per_kwh
                costs_by_date[date_key]["baseline_cost"] += actual_cost + baseline_cost_missed
            else:
                costs_by_date[date_key]["baseline_cost"] += actual_cost
        else:
            costs_by_date[date_key]["baseline_cost"] += actual_cost
        
        costs_by_date[date_key]["miners"].append({
            "miner_id": stat.miner_id,
            "cost": actual_cost,
            "kwh": float(stat.total_kwh or 0),
            "uptime_percent": stat.uptime_percent
        })
    
    # Sort and calculate savings
    sorted_days = sorted(costs_by_date.values(), key=lambda x: x["date"])
    for day_data in sorted_days:
        day_data["savings"] = day_data["baseline_cost"] - day_data["actual_cost"]
        day_data["savings_percent"] = (
            (day_data["savings"] / day_data["baseline_cost"] * 100)
            if day_data["baseline_cost"] > 0 else 0
        )
    
    # Calculate summary
    total_actual = sum(d["actual_cost"] for d in sorted_days)
    total_baseline = sum(d["baseline_cost"] for d in sorted_days)
    total_savings = total_baseline - total_actual
    
    return {
        "days": sorted_days,
        "summary": {
            "total_actual_cost": round(total_actual, 2),
            "total_baseline_cost": round(total_baseline, 2),
            "total_savings": round(total_savings, 2),
            "savings_percent": round(
                (total_savings / total_baseline * 100) if total_baseline > 0 else 0,
                1
            )
        }
    }


@router.get("/monthly")
async def get_monthly_costs(
    months: int = Query(default=12, ge=1, le=24),
    db: AsyncSession = Depends(get_db)
):
    """
    Get monthly energy costs from MonthlyMinerStats.
    """
    # Calculate cutoff (N months ago)
    now = datetime.utcnow()
    cutoff_year = now.year if now.month > months else now.year - 1
    cutoff_month = now.month - months if now.month > months else 12 - (months - now.month)
    
    # Query monthly stats
    result = await db.execute(
        select(MonthlyMinerStats)
        .where(
            and_(
                MonthlyMinerStats.year >= cutoff_year,
                MonthlyMinerStats.month >= cutoff_month if MonthlyMinerStats.year == cutoff_year else True
            )
        )
        .order_by(MonthlyMinerStats.year, MonthlyMinerStats.month)
    )
    monthly_stats = result.scalars().all()
    
    # Group by month
    costs_by_month = {}
    for stat in monthly_stats:
        month_key = f"{stat.year}-{stat.month:02d}"
        
        if month_key not in costs_by_month:
            costs_by_month[month_key] = {
                "year": stat.year,
                "month": stat.month,
                "month_name": datetime(stat.year, stat.month, 1).strftime('%B'),
                "actual_cost": 0,
                "baseline_cost": 0,
                "total_kwh": 0,
                "miners": []
            }
        
        actual_cost = float(stat.total_energy_cost_gbp or 0)
        costs_by_month[month_key]["actual_cost"] += actual_cost
        costs_by_month[month_key]["total_kwh"] += float(stat.total_kwh or 0)
        
        # Baseline estimate: uptime percent indicates missed hours
        days_in_month = stat.days_active
        uptime_fraction = stat.uptime_percent / 100.0
        missed_fraction = 1.0 - uptime_fraction
        
        if missed_fraction > 0 and actual_cost > 0:
            # Estimate baseline as actual / uptime_fraction
            estimated_baseline = actual_cost / uptime_fraction if uptime_fraction > 0 else actual_cost
            costs_by_month[month_key]["baseline_cost"] += estimated_baseline
        else:
            costs_by_month[month_key]["baseline_cost"] += actual_cost
        
        costs_by_month[month_key]["miners"].append({
            "miner_id": stat.miner_id,
            "cost": actual_cost,
            "uptime_percent": stat.uptime_percent
        })
    
    # Sort and calculate savings
    sorted_months = sorted(
        costs_by_month.values(), 
        key=lambda x: (x["year"], x["month"])
    )
    for month_data in sorted_months:
        month_data["savings"] = month_data["baseline_cost"] - month_data["actual_cost"]
        month_data["savings_percent"] = (
            (month_data["savings"] / month_data["baseline_cost"] * 100)
            if month_data["baseline_cost"] > 0 else 0
        )
    
    # Calculate summary
    total_actual = sum(m["actual_cost"] for m in sorted_months)
    total_baseline = sum(m["baseline_cost"] for m in sorted_months)
    total_savings = total_baseline - total_actual
    
    return {
        "months": sorted_months,
        "summary": {
            "total_actual_cost": round(total_actual, 2),
            "total_baseline_cost": round(total_baseline, 2),
            "total_savings": round(total_savings, 2),
            "savings_percent": round(
                (total_savings / total_baseline * 100) if total_baseline > 0 else 0,
                1
            )
        }
    }


@router.get("/yearly")
async def get_yearly_costs(
    db: AsyncSession = Depends(get_db)
):
    """
    Get yearly energy costs (all time).
    Aggregated from MonthlyMinerStats.
    """
    # Query all monthly stats
    result = await db.execute(
        select(MonthlyMinerStats)
        .order_by(MonthlyMinerStats.year, MonthlyMinerStats.month)
    )
    monthly_stats = result.scalars().all()
    
    # Group by year
    costs_by_year = {}
    for stat in monthly_stats:
        year = stat.year
        
        if year not in costs_by_year:
            costs_by_year[year] = {
                "year": year,
                "actual_cost": 0,
                "baseline_cost": 0,
                "total_kwh": 0,
                "months_with_data": 0
            }
        
        actual_cost = float(stat.total_energy_cost_gbp or 0)
        costs_by_year[year]["actual_cost"] += actual_cost
        costs_by_year[year]["total_kwh"] += float(stat.total_kwh or 0)
        costs_by_year[year]["months_with_data"] += 1
        
        # Baseline estimate
        uptime_fraction = stat.uptime_percent / 100.0
        estimated_baseline = actual_cost / uptime_fraction if uptime_fraction > 0 else actual_cost
        costs_by_year[year]["baseline_cost"] += estimated_baseline
    
    # Sort and calculate savings
    sorted_years = sorted(costs_by_year.values(), key=lambda x: x["year"])
    for year_data in sorted_years:
        year_data["savings"] = year_data["baseline_cost"] - year_data["actual_cost"]
        year_data["savings_percent"] = (
            (year_data["savings"] / year_data["baseline_cost"] * 100)
            if year_data["baseline_cost"] > 0 else 0
        )
    
    # Calculate summary
    total_actual = sum(y["actual_cost"] for y in sorted_years)
    total_baseline = sum(y["baseline_cost"] for y in sorted_years)
    total_savings = total_baseline - total_actual
    
    return {
        "years": sorted_years,
        "summary": {
            "total_actual_cost": round(total_actual, 2),
            "total_baseline_cost": round(total_baseline, 2),
            "total_savings": round(total_savings, 2),
            "savings_percent": round(
                (total_savings / total_baseline * 100) if total_baseline > 0 else 0,
                1
            )
        }
    }
