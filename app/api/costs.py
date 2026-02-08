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
    
    # Get telemetry data with pricing
    telemetry_result = await db.execute(
        select(
            func.strftime('%Y-%m-%d %H:00:00', Telemetry.timestamp).label('hour'),
            Telemetry.miner_id,
            func.avg(Telemetry.power_watts).label('avg_power'),
            func.count(Telemetry.id).label('data_points')
        )
        .where(
            and_(
                Telemetry.miner_id.in_(miner_ids),
                Telemetry.timestamp >= cutoff
            )
        )
        .group_by('hour', Telemetry.miner_id)
    )
    telemetry_data = telemetry_result.all()
    
    # Get pricing data for the period
    pricing_result = await db.execute(
        select(EnergyPrice)
        .where(EnergyPrice.valid_from >= cutoff)
        .order_by(EnergyPrice.valid_from)
    )
    prices = pricing_result.scalars().all()
    
    # Build price lookup by hour
    price_by_hour = {}
    for price in prices:
        hour_key = price.valid_from.strftime('%Y-%m-%d %H:00:00')
        if hour_key not in price_by_hour:
            price_by_hour[hour_key] = []
        price_by_hour[hour_key].append(float(price.price_pence))
    
    # Average prices per hour
    avg_price_by_hour = {
        hour: sum(prices) / len(prices) 
        for hour, prices in price_by_hour.items()
    }
    
    # Calculate costs per hour
    hourly_costs = {}
    miner_avg_power = {}  # Track avg power per miner for baseline
    
    for row in telemetry_data:
        hour = row.hour
        miner_id = row.miner_id
        avg_power = float(row.avg_power or 0)
        data_points = row.data_points
        
        # Track miner's average power
        if miner_id not in miner_avg_power:
            miner_avg_power[miner_id] = []
        miner_avg_power[miner_id].append(avg_power)
        
        # Calculate actual cost (kwh * price)
        # Each data point is ~30 seconds, so hours = data_points / 120
        actual_hours = data_points / 120.0
        kwh = (avg_power / 1000.0) * actual_hours
        
        avg_price = avg_price_by_hour.get(hour, 15.0)  # Default 15p if missing
        cost_pence = kwh * avg_price
        
        if hour not in hourly_costs:
            hourly_costs[hour] = {
                "hour": hour,
                "actual_cost": 0,
                "baseline_cost": 0,
                "miners": {}
            }
        
        hourly_costs[hour]["actual_cost"] += cost_pence / 100.0  # Convert to GBP
        hourly_costs[hour]["miners"][miner_id] = {
            "cost": cost_pence / 100.0,
            "kwh": kwh,
            "avg_power": avg_power,
            "uptime_percent": (actual_hours / 1.0) * 100  # % of the hour
        }
    
    # Calculate baseline costs (assume 24/7 operation)
    for miner_id, power_readings in miner_avg_power.items():
        avg_power_overall = sum(power_readings) / len(power_readings)
        
        # For each hour in range, calculate what it would have cost
        for hour_key, avg_price in avg_price_by_hour.items():
            if hour_key not in hourly_costs:
                hourly_costs[hour_key] = {
                    "hour": hour_key,
                    "actual_cost": 0,
                    "baseline_cost": 0,
                    "miners": {}
                }
            
            # Baseline: 1 full hour at average power
            baseline_kwh = (avg_power_overall / 1000.0) * 1.0
            baseline_cost_pence = baseline_kwh * avg_price
            hourly_costs[hour_key]["baseline_cost"] += baseline_cost_pence / 100.0
    
    # Sort by hour and calculate savings
    sorted_hours = sorted(hourly_costs.values(), key=lambda x: x["hour"])
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
