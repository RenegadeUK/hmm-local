"""
Unified Metrics System - Pre-compute and store metrics for fast querying
"""
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import Metric, Telemetry, Miner, Pool, EnergyPrice, PoolHealth
from core.config import app_config
import logging

logger = logging.getLogger(__name__)


class MetricsEngine:
    """Compute and store metrics for fast querying"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def compute_hourly_metrics(self, hour: datetime):
        """
        Compute all hourly metrics for the given hour
        
        Args:
            hour: Start of the hour to compute (e.g. 2026-01-24 12:00:00)
        """
        hour_end = hour + timedelta(hours=1)
        
        logger.info(f"📊 Computing hourly metrics for {hour}")
        
        # Compute per-miner energy costs
        await self._compute_energy_cost_hourly(hour, hour_end)
        
        # Compute per-miner performance
        await self._compute_hashrate_hourly(hour, hour_end)
        await self._compute_temperature_hourly(hour, hour_end)
        await self._compute_reject_rate_hourly(hour, hour_end)
        
        # Compute pool health
        await self._compute_pool_health_hourly(hour, hour_end)
        
        # Compute system-wide aggregates
        await self._compute_system_energy_hourly(hour, hour_end)
        
        await self.db.commit()
        logger.info(f"✅ Hourly metrics computed for {hour}")
    
    async def compute_daily_metrics(self, date: datetime):
        """
        Compute all daily metrics for the given date
        
        Args:
            date: The day to compute (e.g. 2026-01-24 00:00:00)
        """
        date_end = date + timedelta(days=1)
        
        logger.info(f"📊 Computing daily metrics for {date.date()}")
        
        # Aggregate from hourly metrics
        await self._compute_energy_cost_daily(date, date_end)
        await self._compute_hashrate_daily(date, date_end)
        await self._compute_temperature_daily(date, date_end)
        await self._compute_reject_rate_daily(date, date_end)
        await self._compute_uptime_daily(date, date_end)
        
        # System-wide aggregates
        await self._compute_system_energy_daily(date, date_end)
        
        await self.db.commit()
        logger.info(f"✅ Daily metrics computed for {date.date()}")
    
    # Energy Cost Metrics
    
    async def _compute_energy_cost_hourly(self, hour_start: datetime, hour_end: datetime):
        """Compute hourly energy costs per miner"""
        region = app_config.get("octopus_agile.region", "H")
        
        # Get all enabled miners
        miners_result = await self.db.execute(
            select(Miner).where(Miner.enabled == True)
        )
        miners = miners_result.scalars().all()
        
        # Fetch all prices for this hour once
        prices_result = await self.db.execute(
            select(EnergyPrice)
            .where(EnergyPrice.region == region)
            .where(EnergyPrice.valid_from >= hour_start)
            .where(EnergyPrice.valid_from < hour_end)
        )
        prices = {p.valid_from: p.price_pence for p in prices_result.scalars().all()}
        
        for miner in miners:
            # Get telemetry for this miner in this hour
            telemetry_result = await self.db.execute(
                select(Telemetry)
                .where(Telemetry.miner_id == miner.id)
                .where(Telemetry.timestamp >= hour_start)
                .where(Telemetry.timestamp < hour_end)
                .where(Telemetry.power_watts.isnot(None))
            )
            telemetry = telemetry_result.scalars().all()
            
            if not telemetry:
                continue
            
            # Calculate cost
            total_cost_pence = 0
            total_kwh = 0
            price_sum = 0
            price_count = 0
            
            for telem in telemetry:
                # Find price for this timestamp
                price_pence = None
                for valid_from, pence in prices.items():
                    if valid_from <= telem.timestamp < valid_from + timedelta(minutes=30):
                        price_pence = pence
                        break
                
                if price_pence and telem.power_watts:
                    interval_hours = 30 / 3600  # 30 seconds
                    energy_kwh = (telem.power_watts / 1000) * interval_hours
                    total_cost_pence += energy_kwh * price_pence
                    total_kwh += energy_kwh
                    price_sum += price_pence
                    price_count += 1
            
            if total_kwh > 0:
                # Store metric
                metric = Metric(
                    metric_type="energy_cost",
                    entity_type="miner",
                    entity_id=miner.id,
                    period="hourly",
                    timestamp=hour_start,
                    value_json={
                        "kwh": round(total_kwh, 4),
                        "cost_pence": round(total_cost_pence, 2),
                        "cost_gbp": round(total_cost_pence / 100, 4),
                        "avg_price_pence": round(price_sum / price_count, 2) if price_count > 0 else 0,
                        "records": len(telemetry)
                    }
                )
                self.db.add(metric)
    
    async def _compute_system_energy_hourly(self, hour_start: datetime, hour_end: datetime):
        """Compute system-wide energy costs for this hour"""
        # Aggregate from per-miner hourly metrics
        result = await self.db.execute(
            select(Metric)
            .where(Metric.metric_type == "energy_cost")
            .where(Metric.entity_type == "miner")
            .where(Metric.period == "hourly")
            .where(Metric.timestamp == hour_start)
        )
        miner_metrics = result.scalars().all()
        
        if miner_metrics:
            total_kwh = sum(m.value_json["kwh"] for m in miner_metrics)
            total_cost_pence = sum(m.value_json["cost_pence"] for m in miner_metrics)
            
            metric = Metric(
                metric_type="energy_cost",
                entity_type="system",
                entity_id=None,
                period="hourly",
                timestamp=hour_start,
                value_json={
                    "total_kwh": round(total_kwh, 4),
                    "total_cost_gbp": round(total_cost_pence / 100, 4),
                    "miner_count": len(miner_metrics)
                }
            )
            self.db.add(metric)
    
    async def _compute_energy_cost_daily(self, date_start: datetime, date_end: datetime):
        """Aggregate daily energy costs from hourly metrics"""
        # Per-miner daily aggregates
        miners_result = await self.db.execute(
            select(Miner).where(Miner.enabled == True)
        )
        miners = miners_result.scalars().all()
        
        for miner in miners:
            # Get all hourly metrics for this miner for this day
            result = await self.db.execute(
                select(Metric)
                .where(Metric.metric_type == "energy_cost")
                .where(Metric.entity_type == "miner")
                .where(Metric.entity_id == miner.id)
                .where(Metric.period == "hourly")
                .where(Metric.timestamp >= date_start)
                .where(Metric.timestamp < date_end)
            )
            hourly_metrics = result.scalars().all()
            
            if hourly_metrics:
                total_kwh = sum(m.value_json["kwh"] for m in hourly_metrics)
                total_cost_pence = sum(m.value_json["cost_pence"] for m in hourly_metrics)
                avg_price = sum(m.value_json["avg_price_pence"] for m in hourly_metrics) / len(hourly_metrics)
                
                metric = Metric(
                    metric_type="energy_cost",
                    entity_type="miner",
                    entity_id=miner.id,
                    period="daily",
                    timestamp=date_start,
                    value_json={
                        "kwh": round(total_kwh, 3),
                        "cost_gbp": round(total_cost_pence / 100, 2),
                        "avg_price_pence": round(avg_price, 2),
                        "hours": len(hourly_metrics)
                    }
                )
                self.db.add(metric)
    
    async def _compute_system_energy_daily(self, date_start: datetime, date_end: datetime):
        """Aggregate system-wide daily energy costs"""
        result = await self.db.execute(
            select(Metric)
            .where(Metric.metric_type == "energy_cost")
            .where(Metric.entity_type == "miner")
            .where(Metric.period == "daily")
            .where(Metric.timestamp == date_start)
        )
        miner_metrics = result.scalars().all()
        
        if miner_metrics:
            total_kwh = sum(m.value_json["kwh"] for m in miner_metrics)
            total_cost_gbp = sum(m.value_json["cost_gbp"] for m in miner_metrics)
            
            metric = Metric(
                metric_type="energy_cost",
                entity_type="system",
                entity_id=None,
                period="daily",
                timestamp=date_start,
                value_json={
                    "total_kwh": round(total_kwh, 2),
                    "total_cost_gbp": round(total_cost_gbp, 2),
                    "miner_count": len(miner_metrics)
                }
            )
            self.db.add(metric)
    
    # Hashrate Metrics
    
    async def _compute_hashrate_hourly(self, hour_start: datetime, hour_end: datetime):
        """Compute hourly hashrate stats per miner"""
        miners_result = await self.db.execute(
            select(Miner).where(Miner.enabled == True)
        )
        miners = miners_result.scalars().all()
        
        for miner in miners:
            result = await self.db.execute(
                select(
                    func.avg(Telemetry.hashrate).label("avg"),
                    func.min(Telemetry.hashrate).label("min"),
                    func.max(Telemetry.hashrate).label("max"),
                    func.count(Telemetry.id).label("count"),
                    Telemetry.hashrate_unit
                )
                .where(Telemetry.miner_id == miner.id)
                .where(Telemetry.timestamp >= hour_start)
                .where(Telemetry.timestamp < hour_end)
                .where(Telemetry.hashrate.isnot(None))
                .group_by(Telemetry.hashrate_unit)
            )
            row = result.first()
            
            if row and row.count > 0:
                metric = Metric(
                    metric_type="hashrate",
                    entity_type="miner",
                    entity_id=miner.id,
                    period="hourly",
                    timestamp=hour_start,
                    value_json={
                        "avg": round(row.avg, 2),
                        "min": round(row.min, 2),
                        "max": round(row.max, 2),
                        "unit": row.hashrate_unit,
                        "records": row.count
                    }
                )
                self.db.add(metric)
    
    async def _compute_hashrate_daily(self, date_start: datetime, date_end: datetime):
        """Aggregate daily hashrate from hourly metrics"""
        miners_result = await self.db.execute(
            select(Miner).where(Miner.enabled == True)
        )
        miners = miners_result.scalars().all()
        
        for miner in miners:
            result = await self.db.execute(
                select(Metric)
                .where(Metric.metric_type == "hashrate")
                .where(Metric.entity_type == "miner")
                .where(Metric.entity_id == miner.id)
                .where(Metric.period == "hourly")
                .where(Metric.timestamp >= date_start)
                .where(Metric.timestamp < date_end)
            )
            hourly_metrics = result.scalars().all()
            
            if hourly_metrics:
                avg_hashrate = sum(m.value_json["avg"] for m in hourly_metrics) / len(hourly_metrics)
                min_hashrate = min(m.value_json["min"] for m in hourly_metrics)
                max_hashrate = max(m.value_json["max"] for m in hourly_metrics)
                unit = hourly_metrics[0].value_json["unit"]
                
                metric = Metric(
                    metric_type="hashrate",
                    entity_type="miner",
                    entity_id=miner.id,
                    period="daily",
                    timestamp=date_start,
                    value_json={
                        "avg": round(avg_hashrate, 2),
                        "min": round(min_hashrate, 2),
                        "max": round(max_hashrate, 2),
                        "unit": unit,
                        "hours": len(hourly_metrics)
                    }
                )
                self.db.add(metric)
    
    # Temperature Metrics
    
    async def _compute_temperature_hourly(self, hour_start: datetime, hour_end: datetime):
        """Compute hourly temperature stats per miner"""
        miners_result = await self.db.execute(
            select(Miner).where(Miner.enabled == True)
        )
        miners = miners_result.scalars().all()
        
        for miner in miners:
            result = await self.db.execute(
                select(
                    func.avg(Telemetry.temperature).label("avg"),
                    func.min(Telemetry.temperature).label("min"),
                    func.max(Telemetry.temperature).label("max"),
                    func.count(Telemetry.id).label("count")
                )
                .where(Telemetry.miner_id == miner.id)
                .where(Telemetry.timestamp >= hour_start)
                .where(Telemetry.timestamp < hour_end)
                .where(Telemetry.temperature.isnot(None))
            )
            row = result.first()
            
            if row and row.count > 0:
                metric = Metric(
                    metric_type="temperature",
                    entity_type="miner",
                    entity_id=miner.id,
                    period="hourly",
                    timestamp=hour_start,
                    value_json={
                        "avg": round(row.avg, 1),
                        "min": round(row.min, 1),
                        "max": round(row.max, 1),
                        "records": row.count
                    }
                )
                self.db.add(metric)
    
    async def _compute_temperature_daily(self, date_start: datetime, date_end: datetime):
        """Aggregate daily temperature from hourly metrics"""
        miners_result = await self.db.execute(
            select(Miner).where(Miner.enabled == True)
        )
        miners = miners_result.scalars().all()
        
        for miner in miners:
            result = await self.db.execute(
                select(Metric)
                .where(Metric.metric_type == "temperature")
                .where(Metric.entity_type == "miner")
                .where(Metric.entity_id == miner.id)
                .where(Metric.period == "hourly")
                .where(Metric.timestamp >= date_start)
                .where(Metric.timestamp < date_end)
            )
            hourly_metrics = result.scalars().all()
            
            if hourly_metrics:
                avg_temp = sum(m.value_json["avg"] for m in hourly_metrics) / len(hourly_metrics)
                min_temp = min(m.value_json["min"] for m in hourly_metrics)
                max_temp = max(m.value_json["max"] for m in hourly_metrics)
                
                metric = Metric(
                    metric_type="temperature",
                    entity_type="miner",
                    entity_id=miner.id,
                    period="daily",
                    timestamp=date_start,
                    value_json={
                        "avg": round(avg_temp, 1),
                        "min": round(min_temp, 1),
                        "max": round(max_temp, 1),
                        "hours": len(hourly_metrics)
                    }
                )
                self.db.add(metric)
    
    # Reject Rate Metrics
    
    async def _compute_reject_rate_hourly(self, hour_start: datetime, hour_end: datetime):
        """Compute hourly reject rate per miner"""
        miners_result = await self.db.execute(
            select(Miner).where(Miner.enabled == True)
        )
        miners = miners_result.scalars().all()
        
        for miner in miners:
            result = await self.db.execute(
                select(
                    func.sum(Telemetry.shares_accepted).label("accepted"),
                    func.sum(Telemetry.shares_rejected).label("rejected")
                )
                .where(Telemetry.miner_id == miner.id)
                .where(Telemetry.timestamp >= hour_start)
                .where(Telemetry.timestamp < hour_end)
            )
            row = result.first()
            
            if row and row.accepted:
                total_shares = (row.accepted or 0) + (row.rejected or 0)
                reject_rate = (row.rejected / total_shares * 100) if total_shares > 0 else 0
                
                metric = Metric(
                    metric_type="reject_rate",
                    entity_type="miner",
                    entity_id=miner.id,
                    period="hourly",
                    timestamp=hour_start,
                    value_json={
                        "reject_rate": round(reject_rate, 2),
                        "shares_accepted": row.accepted or 0,
                        "shares_rejected": row.rejected or 0
                    }
                )
                self.db.add(metric)
    
    async def _compute_reject_rate_daily(self, date_start: datetime, date_end: datetime):
        """Aggregate daily reject rate from hourly metrics"""
        miners_result = await self.db.execute(
            select(Miner).where(Miner.enabled == True)
        )
        miners = miners_result.scalars().all()
        
        for miner in miners:
            result = await self.db.execute(
                select(Metric)
                .where(Metric.metric_type == "reject_rate")
                .where(Metric.entity_type == "miner")
                .where(Metric.entity_id == miner.id)
                .where(Metric.period == "hourly")
                .where(Metric.timestamp >= date_start)
                .where(Metric.timestamp < date_end)
            )
            hourly_metrics = result.scalars().all()
            
            if hourly_metrics:
                total_accepted = sum(m.value_json["shares_accepted"] for m in hourly_metrics)
                total_rejected = sum(m.value_json["shares_rejected"] for m in hourly_metrics)
                total_shares = total_accepted + total_rejected
                reject_rate = (total_rejected / total_shares * 100) if total_shares > 0 else 0
                
                metric = Metric(
                    metric_type="reject_rate",
                    entity_type="miner",
                    entity_id=miner.id,
                    period="daily",
                    timestamp=date_start,
                    value_json={
                        "reject_rate": round(reject_rate, 2),
                        "shares_accepted": total_accepted,
                        "shares_rejected": total_rejected
                    }
                )
                self.db.add(metric)
    
    # Pool Health Metrics
    
    async def _compute_pool_health_hourly(self, hour_start: datetime, hour_end: datetime):
        """Compute hourly pool health averages"""
        pools_result = await self.db.execute(
            select(Pool).where(Pool.enabled == True)
        )
        pools = pools_result.scalars().all()
        
        for pool in pools:
            result = await self.db.execute(
                select(
                    func.avg(PoolHealth.health_score).label("avg_score"),
                    func.avg(PoolHealth.response_time_ms).label("avg_response"),
                    func.avg(PoolHealth.reject_rate).label("avg_reject"),
                    func.count(PoolHealth.id).label("count")
                )
                .where(PoolHealth.pool_id == pool.id)
                .where(PoolHealth.timestamp >= hour_start)
                .where(PoolHealth.timestamp < hour_end)
            )
            row = result.first()
            
            if row and row.count > 0:
                metric = Metric(
                    metric_type="pool_health",
                    entity_type="pool",
                    entity_id=pool.id,
                    period="hourly",
                    timestamp=hour_start,
                    value_json={
                        "health_score": round(row.avg_score, 1) if row.avg_score is not None else 0,
                        "response_time_ms": round(row.avg_response, 1) if row.avg_response is not None else 0,
                        "reject_rate": round(row.avg_reject, 2) if row.avg_reject is not None else 0,
                        "checks": row.count
                    }
                )
                self.db.add(metric)
    
    # Uptime Metrics
    
    async def _compute_uptime_daily(self, date_start: datetime, date_end: datetime):
        """Compute daily uptime per miner"""
        miners_result = await self.db.execute(
            select(Miner).where(Miner.enabled == True)
        )
        miners = miners_result.scalars().all()
        
        for miner in miners:
            result = await self.db.execute(
                select(func.count(Telemetry.id))
                .where(Telemetry.miner_id == miner.id)
                .where(Telemetry.timestamp >= date_start)
                .where(Telemetry.timestamp < date_end)
            )
            record_count = result.scalar()
            
            # Expected: 2 records/min × 60 min × 24 hours = 2880 records
            expected_records = 2880
            uptime_percent = (record_count / expected_records * 100) if expected_records > 0 else 0
            
            metric = Metric(
                metric_type="uptime",
                entity_type="miner",
                entity_id=miner.id,
                period="daily",
                timestamp=date_start,
                value_json={
                    "uptime_percent": round(uptime_percent, 2),
                    "telemetry_records": record_count,
                    "expected_records": expected_records
                }
            )
            self.db.add(metric)
    
    # Cleanup
    
    async def cleanup_old_metrics(self, days: int = 365):
        """Delete metrics older than specified days"""
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        result = await self.db.execute(
            select(func.count(Metric.id))
            .where(Metric.timestamp < cutoff)
        )
        count = result.scalar()
        
        if count > 0:
            await self.db.execute(
                Metric.__table__.delete().where(Metric.timestamp < cutoff)
            )
            await self.db.commit()
            logger.info(f"🗑️ Deleted {count} metrics older than {days} days")


# Helper functions for querying metrics

async def get_metric(
    db: AsyncSession,
    metric_type: str,
    period: str,
    timestamp: datetime,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """Get a single metric"""
    result = await db.execute(
        select(Metric)
        .where(Metric.metric_type == metric_type)
        .where(Metric.period == period)
        .where(Metric.timestamp == timestamp)
        .where(Metric.entity_type == entity_type if entity_type else True)
        .where(Metric.entity_id == entity_id if entity_id else True)
    )
    metric = result.scalar_one_or_none()
    return metric.value_json if metric else None


async def get_metrics_range(
    db: AsyncSession,
    metric_type: str,
    period: str,
    start: datetime,
    end: datetime,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Get metrics for a time range"""
    query = select(Metric).where(
        and_(
            Metric.metric_type == metric_type,
            Metric.period == period,
            Metric.timestamp >= start,
            Metric.timestamp < end
        )
    )
    
    if entity_type:
        query = query.where(Metric.entity_type == entity_type)
    if entity_id:
        query = query.where(Metric.entity_id == entity_id)
    
    query = query.order_by(Metric.timestamp)
    
    result = await db.execute(query)
    metrics = result.scalars().all()
    
    return [
        {
            "timestamp": m.timestamp.isoformat(),
            "entity_id": m.entity_id,
            **m.value_json
        }
        for m in metrics
    ]
