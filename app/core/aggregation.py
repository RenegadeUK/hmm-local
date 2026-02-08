"""
Daily and monthly aggregation service for long-term analytics
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from core.database import (
    Miner, Telemetry, PoolHealth, EnergyPrice, CryptoPrice,
    DailyMinerStats, DailyPoolStats, MonthlyMinerStats, get_db
)

logger = logging.getLogger(__name__)


async def aggregate_daily_stats(target_date: Optional[datetime] = None):
    """
    Aggregate yesterday's data into daily stats tables
    If target_date provided, aggregate that specific date
    """
    if target_date is None:
        # Default to yesterday
        target_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    else:
        # Ensure midnight
        target_date = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    
    logger.info(f"Starting daily aggregation for {target_date.date()}")
    
    async for db in get_db():
        try:
            # Aggregate miner stats
            await _aggregate_daily_miner_stats(db, target_date)
            
            # Aggregate pool stats
            await _aggregate_daily_pool_stats(db, target_date)
            
            # Update monthly rollups if it's the last day of the month
            next_day = target_date + timedelta(days=1)
            if next_day.month != target_date.month:
                await _aggregate_monthly_stats(db, target_date.year, target_date.month)
            
            await db.commit()
            logger.info(f"✓ Daily aggregation complete for {target_date.date()}")
        except Exception as e:
            logger.error(f"Error during daily aggregation: {e}", exc_info=True)
            await db.rollback()
        finally:
            break  # Only need one db session


async def _aggregate_daily_miner_stats(db: AsyncSession, target_date: datetime):
    """Aggregate daily miner statistics"""
    start_time = target_date
    end_time = target_date + timedelta(days=1)
    
    # Get all active miners
    result = await db.execute(select(Miner))
    miners = result.scalars().all()
    
    for miner in miners:
        # Get all telemetry for this miner on target date
        telemetry_query = select(Telemetry).where(
            and_(
                Telemetry.miner_id == miner.id,
                Telemetry.timestamp >= start_time,
                Telemetry.timestamp < end_time
            )
        )
        telemetry_result = await db.execute(telemetry_query)
        telemetry_data = telemetry_result.scalars().all()
        
        if not telemetry_data:
            logger.debug(f"No telemetry for miner {miner.name} on {target_date.date()}")
            continue
        
        # Calculate aggregated stats
        hashrates = [t.hashrate for t in telemetry_data if t.hashrate is not None]
        temperatures = [t.temperature for t in telemetry_data if t.temperature is not None]
        power_readings = [t.power_watts for t in telemetry_data if t.power_watts is not None]
        
        # Get hashrate unit from telemetry
        hashrate_unit = "GH/s"
        if telemetry_data:
            hashrate_unit = telemetry_data[0].hashrate_unit or "GH/s"
        
        # Calculate uptime (percentage of expected data points)
        # Expect ~2880 data points per day (30 second intervals)
        expected_points = 24 * 60 * 2  # 2880
        actual_points = len(telemetry_data)
        uptime_percent = (actual_points / expected_points) * 100.0
        offline_minutes = ((expected_points - actual_points) * 30) // 60
        
        # Calculate shares
        total_accepted = sum(t.shares_accepted for t in telemetry_data if t.shares_accepted is not None)
        total_rejected = sum(t.shares_rejected for t in telemetry_data if t.shares_rejected is not None)
        reject_rate = (total_rejected / (total_accepted + total_rejected) * 100) if (total_accepted + total_rejected) > 0 else 0.0
        
        # Calculate power consumption (kWh) based on actual runtime with telemetry
        total_kwh = 0.0
        energy_cost_gbp = 0.0
        
        if len(telemetry_data) > 1:
            # Sort telemetry by timestamp
            sorted_telemetry = sorted(telemetry_data, key=lambda t: t.timestamp)
            
            # Get energy prices for the day
            price_query = select(EnergyPrice).where(
                and_(
                    EnergyPrice.valid_from >= start_time,
                    EnergyPrice.valid_from < end_time
                )
            )
            price_result = await db.execute(price_query)
            energy_prices = price_result.scalars().all()
            
            def get_price_for_timestamp(ts):
                """Get energy price active at a given timestamp"""
                for price in energy_prices:
                    if price.valid_from <= ts < price.valid_to:
                        return price.price_pence
                return None
            
            # Calculate cost using duration between readings (same logic as dashboard)
            for i, telemetry in enumerate(sorted_telemetry):
                power = telemetry.power_watts
                
                # Skip if no power data
                if not power or power <= 0:
                    if miner.manual_power_watts:
                        power = miner.manual_power_watts
                    else:
                        continue
                
                # Get price for this timestamp
                price_pence = get_price_for_timestamp(telemetry.timestamp)
                if price_pence is None:
                    continue
                
                # Calculate duration until next reading
                if i < len(sorted_telemetry) - 1:
                    next_timestamp = sorted_telemetry[i + 1].timestamp
                    duration_seconds = (next_timestamp - telemetry.timestamp).total_seconds()
                    duration_hours = duration_seconds / 3600.0
                    
                    # Cap duration at 10 minutes to prevent counting offline gaps
                    max_duration_hours = 10.0 / 60.0
                    if duration_hours > max_duration_hours:
                        duration_hours = max_duration_hours
                else:
                    duration_hours = 30.0 / 3600.0
                
                # Calculate cost for this period
                kwh = (power / 1000.0) * duration_hours
                cost_pence = kwh * price_pence
                total_kwh += kwh
                energy_cost_gbp += cost_pence / 100.0  # Convert to pounds
        
        # Calculate earnings (simplified - actual earnings depend on pool and coin)
        # TODO: Implement real earnings calculation from pool data
        # For now, set to 0 - user can add earnings manually or via future pool integration
        earnings_gbp = 0.0
        profit_gbp = earnings_gbp - energy_cost_gbp
        
        # Create or update daily stats
        existing_query = select(DailyMinerStats).where(
            and_(
                DailyMinerStats.miner_id == miner.id,
                DailyMinerStats.date == target_date
            )
        )
        existing_result = await db.execute(existing_query)
        existing_stat = existing_result.scalar_one_or_none()
        
        if existing_stat:
            # Update existing
            existing_stat.avg_hashrate = sum(hashrates) / len(hashrates) if hashrates else None
            existing_stat.min_hashrate = min(hashrates) if hashrates else None
            existing_stat.max_hashrate = max(hashrates) if hashrates else None
            existing_stat.hashrate_unit = hashrate_unit
            existing_stat.avg_temperature = sum(temperatures) / len(temperatures) if temperatures else None
            existing_stat.max_temperature = max(temperatures) if temperatures else None
            existing_stat.avg_power = sum(power_readings) / len(power_readings) if power_readings else None
            existing_stat.total_kwh = total_kwh
            existing_stat.uptime_percent = uptime_percent
            existing_stat.offline_minutes = offline_minutes
            existing_stat.total_shares_accepted = total_accepted
            existing_stat.total_shares_rejected = total_rejected
            existing_stat.reject_rate_percent = reject_rate
            existing_stat.energy_cost_gbp = energy_cost_gbp
            existing_stat.earnings_gbp = earnings_gbp
            existing_stat.profit_gbp = profit_gbp
            existing_stat.data_points = actual_points
        else:
            # Create new
            new_stat = DailyMinerStats(
                miner_id=miner.id,
                date=target_date,
                avg_hashrate=sum(hashrates) / len(hashrates) if hashrates else None,
                min_hashrate=min(hashrates) if hashrates else None,
                max_hashrate=max(hashrates) if hashrates else None,
                hashrate_unit=hashrate_unit,
                avg_temperature=sum(temperatures) / len(temperatures) if temperatures else None,
                max_temperature=max(temperatures) if temperatures else None,
                avg_power=sum(power_readings) / len(power_readings) if power_readings else None,
                total_kwh=total_kwh,
                uptime_percent=uptime_percent,
                offline_minutes=offline_minutes,
                total_shares_accepted=total_accepted,
                total_shares_rejected=total_rejected,
                reject_rate_percent=reject_rate,
                energy_cost_gbp=energy_cost_gbp,
                earnings_gbp=earnings_gbp,
                profit_gbp=profit_gbp,
                data_points=actual_points
            )
            db.add(new_stat)
        
        logger.debug(f"Aggregated {actual_points} data points for {miner.name} on {target_date.date()}")
    
    await db.flush()


async def _aggregate_daily_pool_stats(db: AsyncSession, target_date: datetime):
    """Aggregate daily pool statistics"""
    start_time = target_date
    end_time = target_date + timedelta(days=1)
    
    # Get pool health data for target date
    health_query = select(PoolHealth).where(
        and_(
            PoolHealth.timestamp >= start_time,
            PoolHealth.timestamp < end_time
        )
    )
    health_result = await db.execute(health_query)
    health_data = health_result.scalars().all()
    
    # Group by pool_id
    pools_data: Dict[int, List[PoolHealth]] = {}
    for health in health_data:
        if health.pool_id not in pools_data:
            pools_data[health.pool_id] = []
        pools_data[health.pool_id].append(health)
    
    # Aggregate for each pool
    for pool_id, health_records in pools_data.items():
        latencies = [h.response_time_ms for h in health_records if h.response_time_ms is not None]
        health_scores = [h.health_score for h in health_records if h.health_score is not None]
        luck_values = [h.luck_percentage for h in health_records if h.luck_percentage is not None]
        
        # Count blocks found (if we track this in future)
        blocks_found = 0
        
        # Total shares (sum from all telemetry for pools active today)
        total_shares = sum(h.reject_rate for h in health_records if h.reject_rate is not None) * 100  # Placeholder
        
        # Calculate uptime
        expected_health_checks = 24 * 12  # Every 5 minutes = 288 per day
        actual_checks = len(health_records)
        uptime_percent = (actual_checks / expected_health_checks) * 100.0 if expected_health_checks > 0 else 100.0
        
        # Create or update
        existing_query = select(DailyPoolStats).where(
            and_(
                DailyPoolStats.pool_id == pool_id,
                DailyPoolStats.date == target_date
            )
        )
        existing_result = await db.execute(existing_query)
        existing_stat = existing_result.scalar_one_or_none()
        
        if existing_stat:
            existing_stat.blocks_found = blocks_found
            existing_stat.total_shares_submitted = int(total_shares)
            existing_stat.avg_luck_percent = sum(luck_values) / len(luck_values) if luck_values else None
            existing_stat.avg_latency_ms = sum(latencies) / len(latencies) if latencies else None
            existing_stat.avg_health_score = sum(health_scores) / len(health_scores) if health_scores else None
            existing_stat.uptime_percent = uptime_percent
        else:
            new_stat = DailyPoolStats(
                pool_id=pool_id,
                date=target_date,
                blocks_found=blocks_found,
                total_shares_submitted=int(total_shares),
                avg_luck_percent=sum(luck_values) / len(luck_values) if luck_values else None,
                avg_latency_ms=sum(latencies) / len(latencies) if latencies else None,
                avg_health_score=sum(health_scores) / len(health_scores) if health_scores else None,
                uptime_percent=uptime_percent
            )
            db.add(new_stat)
        
        logger.debug(f"Aggregated pool stats for pool_id={pool_id} on {target_date.date()}")
    
    await db.flush()


async def _aggregate_monthly_stats(db: AsyncSession, year: int, month: int):
    """Aggregate monthly miner statistics from daily stats"""
    logger.info(f"Aggregating monthly stats for {year}-{month:02d}")
    
    # Get all miners
    result = await db.execute(select(Miner))
    miners = result.scalars().all()
    
    for miner in miners:
        # Get all daily stats for this month
        daily_query = select(DailyMinerStats).where(
            and_(
                DailyMinerStats.miner_id == miner.id,
                func.extract('year', DailyMinerStats.date) == year,
                func.extract('month', DailyMinerStats.date) == month
            )
        )
        daily_result = await db.execute(daily_query)
        daily_stats = daily_result.scalars().all()
        
        if not daily_stats:
            continue
        
        # Aggregate
        hashrates = [d.avg_hashrate for d in daily_stats if d.avg_hashrate is not None]
        hashrate_unit = daily_stats[0].hashrate_unit if daily_stats else "GH/s"
        
        total_kwh = sum(d.total_kwh for d in daily_stats if d.total_kwh is not None)
        avg_uptime = sum(d.uptime_percent for d in daily_stats) / len(daily_stats)
        total_accepted = sum(d.total_shares_accepted for d in daily_stats)
        total_rejected = sum(d.total_shares_rejected for d in daily_stats)
        reject_rate = (total_rejected / (total_accepted + total_rejected) * 100) if (total_accepted + total_rejected) > 0 else 0.0
        
        total_energy_cost = sum(d.energy_cost_gbp for d in daily_stats)
        total_earnings = sum(d.earnings_gbp for d in daily_stats)
        total_profit = sum(d.profit_gbp for d in daily_stats)
        
        # Create or update
        existing_query = select(MonthlyMinerStats).where(
            and_(
                MonthlyMinerStats.miner_id == miner.id,
                MonthlyMinerStats.year == year,
                MonthlyMinerStats.month == month
            )
        )
        existing_result = await db.execute(existing_query)
        existing_stat = existing_result.scalar_one_or_none()
        
        if existing_stat:
            existing_stat.avg_hashrate = sum(hashrates) / len(hashrates) if hashrates else None
            existing_stat.hashrate_unit = hashrate_unit
            existing_stat.total_kwh = total_kwh
            existing_stat.uptime_percent = avg_uptime
            existing_stat.total_shares_accepted = total_accepted
            existing_stat.total_shares_rejected = total_rejected
            existing_stat.reject_rate_percent = reject_rate
            existing_stat.total_energy_cost_gbp = total_energy_cost
            existing_stat.total_earnings_gbp = total_earnings
            existing_stat.total_profit_gbp = total_profit
            existing_stat.days_active = len(daily_stats)
        else:
            new_stat = MonthlyMinerStats(
                miner_id=miner.id,
                year=year,
                month=month,
                avg_hashrate=sum(hashrates) / len(hashrates) if hashrates else None,
                hashrate_unit=hashrate_unit,
                total_kwh=total_kwh,
                uptime_percent=avg_uptime,
                total_shares_accepted=total_accepted,
                total_shares_rejected=total_rejected,
                reject_rate_percent=reject_rate,
                total_energy_cost_gbp=total_energy_cost,
                total_earnings_gbp=total_earnings,
                total_profit_gbp=total_profit,
                days_active=len(daily_stats)
            )
            db.add(new_stat)
        
        logger.debug(f"Aggregated monthly stats for {miner.name} ({year}-{month:02d})")
    
    await db.flush()
