"""
APScheduler for periodic tasks
"""
import logging
import asyncio
import aiohttp
import os
import random
from pathlib import Path
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func, and_, delete, text
from typing import Optional
from core.config import app_config
from core.cloud_push import init_cloud_service, get_cloud_service
from core.database import EnergyPrice, Telemetry, Miner

logger = logging.getLogger(__name__)


class SchedulerService:
    """Scheduler service wrapper"""
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.nmminer_listener = None
        self.nmminer_adapters = {}  # Shared adapter registry for NMMiner devices
        
        # Initialize cloud service
        cloud_config = app_config.get("cloud", {})
        init_cloud_service(cloud_config)
    
    def start(self):
        """Start scheduler"""
        # Add default jobs
        self.scheduler.add_job(
            self._update_energy_prices,
            IntervalTrigger(minutes=30),
            id="update_energy_prices",
            name="Update Octopus Agile prices"
        )

        self.scheduler.add_job(
            self._update_agile_forecast,
            CronTrigger(hour=4, minute=30),
            id="update_agile_forecast",
            name="Update Agile Predict forecast (daily)"
        )

        self.scheduler.add_job(
            self._purge_old_agile_forecasts,
            IntervalTrigger(days=1),
            id="purge_old_agile_forecasts",
            name="Purge stale Agile Predict forecasts"
        )
        
        self.scheduler.add_job(
            self._collect_telemetry,
            IntervalTrigger(seconds=30),
            id="collect_telemetry",
            name="Collect miner telemetry"
        )
        
        self.scheduler.add_job(
            self._evaluate_automation_rules,
            IntervalTrigger(seconds=60),
            id="evaluate_automation_rules",
            name="Evaluate automation rules"
        )
        
        self.scheduler.add_job(
            self._reconcile_automation_rules,
            IntervalTrigger(minutes=5),
            id="reconcile_automation_rules",
            name="Reconcile miners with active automation rules"
        )
        
        self.scheduler.add_job(
            self._check_alerts,
            IntervalTrigger(minutes=5),
            id="check_alerts",
            name="Check for alert conditions"
        )
        
        self.scheduler.add_job(
            self._record_health_scores,
            IntervalTrigger(hours=1),
            id="record_health_scores",
            name="Record miner health scores"
        )
        
        self.scheduler.add_job(
            self._auto_optimize_miners,
            IntervalTrigger(minutes=30),
            id="auto_optimize_miners",
            name="Auto-optimize miners based on energy prices"
        )
        
        self.scheduler.add_job(
            self._reconcile_energy_optimization,
            IntervalTrigger(minutes=5),
            id="reconcile_energy_optimization",
            name="Reconcile miners with energy optimization state"
        )
        
        # Heavy maintenance tasks now run during Agile OFF periods instead of fixed schedules
        # Includes: aggregation, purge operations, VACUUM, ANALYZE
        # Triggered by _execute_agile_solo_strategy() when entering OFF state
        # Fallback: If strategy disabled or hasn't run in 7 days, runs daily at 3am
        
        self.scheduler.add_job(
            self._fallback_maintenance,
            CronTrigger(hour=3, minute=0),
            id="fallback_maintenance",
            name="Fallback maintenance (3am daily if needed)"
        )
        
        self.scheduler.add_job(
            self._update_crypto_prices,
            IntervalTrigger(minutes=10),
            id="update_crypto_prices",
            name="Update crypto price cache"
        )
        
        self.scheduler.add_job(
            self._log_system_summary,
            IntervalTrigger(hours=6),
            id="log_system_summary",
            name="Log system status summary"
        )
        
        self.scheduler.add_job(
            self._auto_discover_miners,
            IntervalTrigger(hours=24),
            id="auto_discover_miners",
            name="Auto-discover miners on configured networks"
        )
        
        self.scheduler.add_job(
            self._purge_old_energy_prices,
            IntervalTrigger(days=7),
            id="purge_old_energy_prices",
            name="Purge energy prices older than 60 days"
        )
        
        self.scheduler.add_job(
            self._vacuum_database,
            IntervalTrigger(days=30),
            id="vacuum_database",
            name="Optimize database (VACUUM)"
        )
        
        self.scheduler.add_job(
            self._backup_database,
            CronTrigger(hour=2, minute=0),
            id="backup_database",
            name="Backup database daily at 2am"
        )
        
        self.scheduler.add_job(
            self._monitor_database_health,
            IntervalTrigger(minutes=5),
            id="monitor_database_health",
            name="Monitor database connection pool and performance"
        )
        
        self.scheduler.add_job(
            self._refresh_dashboard_materialized_view,
            IntervalTrigger(minutes=5),
            id="refresh_dashboard_mv",
            name="Refresh dashboard materialized view (PostgreSQL)"
        )
        
        self.scheduler.add_job(
            self._ensure_future_partitions,
            CronTrigger(day=1, hour=1, minute=0),  # 1st of each month at 1am
            id="ensure_partitions",
            name="Ensure future telemetry partitions exist (PostgreSQL)"
        )
        
        self.scheduler.add_job(
            self._check_index_health,
            IntervalTrigger(days=7),
            id="check_index_health",
            name="Check PostgreSQL index health and bloat"
        )
        
        self.scheduler.add_job(
            self._aggregate_daily_stats,
            IntervalTrigger(hours=24),
            id="aggregate_daily_stats",
            name="Aggregate daily statistics at midnight",
            next_run_time=self._get_next_midnight(),
            misfire_grace_time=600  # Allow up to 10 minutes late execution
        )
        
        self.scheduler.add_job(
            self._monitor_pool_health,
            IntervalTrigger(minutes=5),
            id="monitor_pool_health",
            name="Monitor pool health and connectivity"
        )
        
        self.scheduler.add_job(
            self._execute_pool_strategies,
            IntervalTrigger(minutes=5),
            id="execute_pool_strategies",
            name="Execute active pool strategies"
        )
        
        self.scheduler.add_job(
            self._sync_avalon_pool_slots,
            IntervalTrigger(minutes=15),
            id="sync_avalon_pool_slots",
            name="Sync Avalon Nano pool slot configurations"
        )
        
        self.scheduler.add_job(
            self._purge_old_pool_health,
            IntervalTrigger(days=7),
            id="purge_old_pool_health",
            name="Purge pool health data older than 30 days"
        )
        
        self.scheduler.add_job(
            self._purge_old_high_diff_shares,
            IntervalTrigger(days=1),
            id="purge_old_high_diff_shares",
            name="Purge high diff shares older than 180 days"
        )
        
        self.scheduler.add_job(
            self._reconcile_strategy_miners,
            IntervalTrigger(minutes=5),
            id="reconcile_strategy_miners",
            name="Reconcile miners out of sync with strategies"
        )
        
        self.scheduler.add_job(
            self._monitor_ha_keepalive,
            IntervalTrigger(minutes=1),
            id="monitor_ha_keepalive",
            name="Monitor Home Assistant connectivity"
        )
        
        self.scheduler.add_job(
            self._poll_ha_device_states,
            IntervalTrigger(minutes=5),
            id="poll_ha_device_states",
            name="Poll Home Assistant device states"
        )
        
        self.scheduler.add_job(
            self._reconcile_ha_device_states,
            IntervalTrigger(minutes=5),
            id="reconcile_ha_device_states",
            name="Reconcile stuck Home Assistant devices"
        )
        
        self.scheduler.add_job(
            self._update_platform_version_cache,
            IntervalTrigger(minutes=5),
            id="update_platform_version_cache",
            name="Update platform version cache from GitHub"
        )
        
        self.scheduler.add_job(
            self._check_update_notifications,
            IntervalTrigger(hours=6),
            id="check_update_notifications",
            name="Check for platform and driver updates"
        )
        
        self.scheduler.add_job(
            self._start_nmminer_listener,
            id="start_nmminer_listener",
            name="Start NMMiner UDP listener"
        )
        
        # Cloud push - runs every X minutes (configurable)
        cloud_config = app_config.get("cloud", {})
        if cloud_config.get("enabled", False):
            push_interval = cloud_config.get("push_interval_minutes", 5)
            self.scheduler.add_job(
                self._push_to_cloud,
                IntervalTrigger(minutes=push_interval),
                id="push_to_cloud",
                name="Push telemetry to HMM Cloud"
            )
        
        # Metrics computation - hourly at XX:05
        self.scheduler.add_job(
            self._compute_hourly_metrics,
            'cron',
            minute=5,
            id="compute_hourly_metrics",
            name="Compute hourly metrics"
        )
        
        # Metrics computation - daily at 00:30
        self.scheduler.add_job(
            self._compute_daily_metrics,
            'cron',
            hour=0,
            minute=30,
            id="compute_daily_metrics",
            name="Compute daily metrics"
        )
        
        # Cleanup old metrics - monthly on 1st at 02:00
        self.scheduler.add_job(
            self._cleanup_old_metrics,
            'cron',
            day=1,
            hour=2,
            minute=0,
            id="cleanup_old_metrics",
            name="Cleanup old metrics (>1 year)"
        )
        
        self.scheduler.start()
        print(f"⏰ Scheduler started with {len(self.scheduler.get_jobs())} jobs")
        print("⏰ Scheduler started")
        
        # Anomaly detection jobs
        self.scheduler.add_job(
            self._update_miner_baselines,
            IntervalTrigger(hours=1),
            id="update_miner_baselines",
            name="Update miner performance baselines"
        )
        
        self.scheduler.add_job(
            self._check_miner_health,
            IntervalTrigger(minutes=5),
            id="check_miner_health",
            name="Check miner health and detect anomalies"
        )
        
        # ML model training (weekly)
        self.scheduler.add_job(
            self._train_ml_models,
            IntervalTrigger(days=7),
            id="train_ml_models",
            name="Train ML anomaly detection models (weekly)"
        )
        
        # Trigger immediate energy price fetch after scheduler is running
        self.scheduler.add_job(
            self._update_energy_prices,
            id="update_energy_prices_immediate",
            name="Immediate energy price fetch"
        )

        self.scheduler.add_job(
            self._update_agile_forecast,
            id="update_agile_forecast_immediate",
            name="Immediate Agile Predict forecast fetch"
        )
        
        # Trigger immediate crypto price fetch
        self.scheduler.add_job(
            self._update_crypto_prices,
            id="update_crypto_prices_immediate",
            name="Immediate crypto price fetch"
        )
        
        # Trigger immediate pool slots sync
        self.scheduler.add_job(
            self._sync_avalon_pool_slots,
            id="sync_avalon_pool_slots_immediate",
            name="Immediate Avalon pool slots sync"
        )
        
        # Trigger immediate energy optimization reconciliation
        self.scheduler.add_job(
            self._reconcile_energy_optimization,
            id="reconcile_energy_optimization_immediate",
            name="Immediate energy optimization reconciliation"
        )
        
        # Agile Solo Strategy execution
        self.scheduler.add_job(
            self._execute_agile_solo_strategy,
            IntervalTrigger(minutes=1),
            id="execute_agile_solo_strategy",
            name="Execute Agile Solo Strategy every minute"
        )
        
        # Agile Solo Strategy reconciliation (check for drift)
        self.scheduler.add_job(
            self._reconcile_agile_solo_strategy,
            IntervalTrigger(minutes=5),
            id="reconcile_agile_solo_strategy",
            name="Reconcile Agile Solo Strategy every 5 minutes"
        )
        
        # Trigger immediate strategy execution
        self.scheduler.add_job(
            self._execute_agile_solo_strategy,
            id="execute_agile_solo_strategy_immediate",
            name="Immediate Agile Solo Strategy execution"
        )
        
        # Trigger immediate reconciliation
        self.scheduler.add_job(
            self._reconcile_agile_solo_strategy,
            id="reconcile_agile_solo_strategy_immediate",
            name="Immediate Agile Solo Strategy reconciliation"
        )
        
        # Check for and backfill any missing daily aggregations on startup
        self.scheduler.add_job(
            self._backfill_missing_daily_stats,
            id="backfill_missing_daily_stats_immediate",
            name="Backfill missing daily aggregations on startup"
        )
        
        # Update auto-discovery job interval based on config
        self._update_discovery_schedule()
    
    def _update_discovery_schedule(self):
        """Update auto-discovery job interval based on config"""
        try:
            discovery_config = app_config.get("network_discovery", {})
            scan_interval_hours = discovery_config.get("scan_interval_hours", 24)
            
            # Remove existing job
            try:
                self.scheduler.remove_job("auto_discover_miners")
            except:
                pass
            
            # Re-add with new interval
            self.scheduler.add_job(
                self._auto_discover_miners,
                IntervalTrigger(hours=scan_interval_hours),
                id="auto_discover_miners",
                name=f"Auto-discover miners every {scan_interval_hours}h"
            )
            print(f"⏰ Updated auto-discovery interval to {scan_interval_hours} hours")
        except Exception as e:
            print(f"❌ Failed to update discovery schedule: {e}")
    
    def shutdown(self):
        """Shutdown scheduler"""
        if self.nmminer_listener:
            self.nmminer_listener.stop()
        self.scheduler.shutdown()
        print("⏰ Scheduler stopped")
    
    async def _update_energy_prices(self):
        """Update Octopus Agile energy prices"""
        from core.config import app_config
        from core.database import AsyncSessionLocal, EnergyPrice, Event, engine
        
        enabled = app_config.get("octopus_agile.enabled", False)
        print(f"🔍 Octopus Agile enabled: {enabled}")
        
        if not enabled:
            print("⚠️ Octopus Agile is disabled in config")
            return
        
        region = app_config.get("octopus_agile.region", "H")
        is_postgresql = 'postgresql' in str(engine.url)
        print(f"🌍 Fetching prices for region: {region}")
        
        # Octopus Agile API endpoint - using current product code
        url = f"https://api.octopus.energy/v1/products/AGILE-24-10-01/electricity-tariffs/E-1R-AGILE-24-10-01-{region}/standard-unit-rates/"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status != 200:
                        print(f"⚠️ Failed to fetch Agile prices: HTTP {response.status}")
                        # Log error event
                        async with AsyncSessionLocal() as db:
                            event = Event(
                                event_type="error",
                                source="octopus_agile",
                                message=f"Failed to fetch energy prices: HTTP {response.status}"
                            )
                            db.add(event)
                            await db.commit()
                        return
                    
                    data = await response.json()
                    results = data.get("results", [])
                    
                    if not results:
                        print("⚠️ No price data returned from Octopus API")
                        # Log warning event
                        async with AsyncSessionLocal() as db:
                            event = Event(
                                event_type="warning",
                                source="octopus_agile",
                                message="No price data returned from Octopus Agile API"
                            )
                            db.add(event)
                            await db.commit()
                        return
                    
                    # Insert prices into database
                    async with AsyncSessionLocal() as db:
                        for item in results:
                            valid_from = datetime.fromisoformat(item["valid_from"].replace("Z", "+00:00"))
                            valid_to = datetime.fromisoformat(item["valid_to"].replace("Z", "+00:00"))
                            if is_postgresql:
                                if valid_from.tzinfo is not None:
                                    valid_from = valid_from.astimezone(timezone.utc).replace(tzinfo=None)
                                if valid_to.tzinfo is not None:
                                    valid_to = valid_to.astimezone(timezone.utc).replace(tzinfo=None)
                            price_pence = item["value_inc_vat"]
                            
                            # Check if price already exists
                            result = await db.execute(
                                select(EnergyPrice)
                                .where(EnergyPrice.region == region)
                                .where(EnergyPrice.valid_from == valid_from)
                            )
                            existing = result.scalar_one_or_none()
                            
                            if not existing:
                                price = EnergyPrice(
                                    region=region,
                                    valid_from=valid_from,
                                    valid_to=valid_to,
                                    price_pence=price_pence
                                )
                                db.add(price)
                        
                        await db.commit()
                    
                    print(f"💡 Updated {len(results)} energy prices for region {region}")
                    
                    # Log success event
                    async with AsyncSessionLocal() as db:
                        event = Event(
                            event_type="info",
                            source="octopus_agile",
                            message=f"Updated {len(results)} energy prices for region {region}"[:500]
                        )
                        db.add(event)
                        await db.commit()
        
        except Exception as e:
            print(f"❌ Failed to update energy prices: {e}")
            # Log exception event
            async with AsyncSessionLocal() as db:
                msg = f"Exception fetching energy prices: {str(e)}"
                event = Event(
                    event_type="error",
                    source="octopus_agile",
                    message=msg[:500]
                )
                db.add(event)
                await db.commit()

    async def _update_agile_forecast(self, days: int = 7):
        """Fetch Agile Predict forecast for the active region"""
        from core.config import app_config
        from core.database import AsyncSessionLocal, AgileForecastSlot, Event, engine

        enabled = app_config.get("octopus_agile.enabled", False)
        if not enabled:
            logger.info("Agile Predict skipped because Octopus Agile is disabled")
            return

        region = app_config.get("octopus_agile.region", "H")
        days = int(app_config.get("agile_predict.days", days))
        url = f"https://agilepredict.com/api/{region}/?format=json"
        logger.info("Fetching Agile Predict forecast", extra={"region": region, "url": url})

        is_postgresql = 'postgresql' in str(engine.url)

        def _parse_iso(value: Optional[str]) -> Optional[datetime]:
            if not value:
                return None
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if is_postgresql and parsed.tzinfo is not None:
                return parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return parsed

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=15) as response:
                    if response.status != 200:
                        logger.warning("Failed Agile Predict fetch", extra={"status": response.status})
                        async with AsyncSessionLocal() as db:
                            event = Event(
                                event_type="warning",
                                source="agile_predict",
                                message=f"Failed to fetch Agile Predict forecast: HTTP {response.status}"
                            )
                            db.add(event)
                            await db.commit()
                        return

                    payload = await response.json()
        except Exception as exc:
            logger.exception("Exception fetching Agile Predict forecast")
            async with AsyncSessionLocal() as db:
                event = Event(
                    event_type="error",
                    source="agile_predict",
                    message=f"Exception fetching Agile Predict forecast: {exc}"
                )
                db.add(event)
                await db.commit()
            return

        if not payload:
            logger.warning("Agile Predict returned empty payload")
            return

        forecast = payload[0]
        created_at = _parse_iso(forecast.get("created_at")) or datetime.utcnow()
        prices = forecast.get("prices", [])

        if not prices:
            logger.warning("Agile Predict response missing prices")
            return

        slot_objects = []
        for entry in prices:
            slot_start = _parse_iso(entry.get("date_time"))
            if not slot_start:
                continue
            slot_end = slot_start + timedelta(minutes=30)
            slot_objects.append(
                AgileForecastSlot(
                    region=region,
                    slot_start=slot_start,
                    slot_end=slot_end,
                    price_pred_pence=entry.get("agile_pred"),
                    price_low_pence=entry.get("agile_low"),
                    price_high_pence=entry.get("agile_high"),
                    forecast_created_at=created_at,
                )
            )

        if not slot_objects:
            logger.warning("No valid Agile Predict slots parsed")
            return

        async with AsyncSessionLocal() as db:
            await db.execute(delete(AgileForecastSlot).where(AgileForecastSlot.region == region))
            db.add_all(slot_objects)
            await db.commit()

        logger.info(
            "Stored Agile Predict forecast",
            extra={"region": region, "slots": len(slot_objects)}
        )

        async with AsyncSessionLocal() as db:
            event = Event(
                event_type="info",
                source="agile_predict",
                message=f"Stored {len(slot_objects)} Agile Predict slots for region {region}"
            )
            db.add(event)
            await db.commit()

    async def _purge_old_agile_forecasts(self):
        """Remove forecast slots that are in the distant past"""
        from core.database import AsyncSessionLocal, AgileForecastSlot

        cutoff = datetime.utcnow() - timedelta(days=1)

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                delete(AgileForecastSlot).where(AgileForecastSlot.slot_end < cutoff)
            )
            await db.commit()

        deleted = result.rowcount or 0
        if deleted:
            logger.info("Purged stale Agile Predict slots", extra={"deleted": deleted})
    
    async def _update_crypto_prices(self):
        """Update cached crypto prices every 10 minutes"""
        from api.settings import update_crypto_prices_cache
        await update_crypto_prices_cache()
    
    async def _collect_miner_telemetry(self, miner, agile_in_off_state, db):
        """Collect telemetry from a single miner (used for parallel collection)"""
        from core.database import Telemetry, Event, Pool, MinerStrategy, EnergyPrice, HomeAssistantDevice
        from adapters import create_adapter
        from sqlalchemy import select
        
        try:
            print(f"📡 Collecting telemetry from {miner.name} ({miner.miner_type})")
            
            # Create adapter
            adapter = create_adapter(
                miner.miner_type,
                miner.id,
                miner.name,
                miner.ip_address,
                miner.port,
                miner.config
            )
            
            if not adapter:
                return

            # Check if HA explicitly turned this miner OFF
            ha_off_state = False
            with db.no_autoflush:
                ha_result = await db.execute(
                    select(HomeAssistantDevice)
                    .where(HomeAssistantDevice.miner_id == miner.id)
                    .where(HomeAssistantDevice.enrolled == True)
                )
                ha_device = ha_result.scalar_one_or_none()

            if ha_device:
                if (ha_device.current_state or "").lower() == "off":
                    ha_off_state = True
                elif ha_device.last_off_command_timestamp:
                    hours_since_off = (datetime.utcnow() - ha_device.last_off_command_timestamp).total_seconds() / 3600
                    if hours_since_off <= 6:
                        ha_off_state = True
            
            # Optimization: If Agile is OFF, ping first before attempting full telemetry
            # This avoids long timeout waits for miners that are powered off
            if agile_in_off_state or ha_off_state:
                try:
                    is_online = await asyncio.wait_for(adapter.is_online(), timeout=2.0)
                    if not is_online:
                        reason = "Agile OFF" if agile_in_off_state else "HA OFF"
                        print(f"💤 {miner.name} offline ({reason} ping failed) - skipping telemetry")
                        return
                except asyncio.TimeoutError:
                    reason = "Agile OFF" if agile_in_off_state else "HA OFF"
                    print(f"💤 {miner.name} ping timeout ({reason}) - skipping telemetry")
                    return
            
            # Get telemetry
            telemetry = await adapter.get_telemetry()
            
            if telemetry:
                # Track high difficulty shares (ASIC miners only)
                if miner.miner_type in ["avalon_nano", "bitaxe", "nerdqaxe"] and telemetry.extra_data:
                    from core.high_diff_tracker import track_high_diff_share
                    
                    # Extract best diff based on miner type
                    current_best_diff = None
                    if miner.miner_type in ["bitaxe", "nerdqaxe"]:
                        current_best_diff = telemetry.extra_data.get("best_session_diff")
                    elif miner.miner_type == "avalon_nano":
                        current_best_diff = telemetry.extra_data.get("best_share")
                    
                    if current_best_diff:
                        # Get previous best from last telemetry reading
                        prev_result = await db.execute(
                            select(Telemetry)
                            .where(Telemetry.miner_id == miner.id)
                            .order_by(Telemetry.timestamp.desc())
                            .limit(1)
                        )
                        prev_telemetry = prev_result.scalar_one_or_none()
                        
                        previous_best = None
                        if prev_telemetry and prev_telemetry.data:
                            if miner.miner_type in ["bitaxe", "nerdqaxe"]:
                                previous_best = prev_telemetry.data.get("best_session_diff")
                            elif miner.miner_type == "avalon_nano":
                                previous_best = prev_telemetry.data.get("best_share")
                        
                        # Only track if this is a new personal best (ensure numeric comparison)
                        try:
                            # Parse values that may have unit suffixes (e.g., "130.46 k" = 130460)
                            def parse_difficulty(value):
                                if value is None:
                                    return None
                                if isinstance(value, (int, float)):
                                    return float(value)
                                
                                # Handle string values with unit suffixes
                                value_str = str(value).strip().lower()
                                multipliers = {
                                    'k': 1_000,
                                    'm': 1_000_000,
                                    'g': 1_000_000_000,
                                    't': 1_000_000_000_000
                                }
                                
                                for suffix, multiplier in multipliers.items():
                                    if suffix in value_str:
                                        # Extract numeric part and multiply
                                        num_str = value_str.replace(suffix, '').strip()
                                        return float(num_str) * multiplier
                                
                                # No suffix, just convert to float
                                return float(value_str)
                            
                            current_val = parse_difficulty(current_best_diff)
                            previous_val = parse_difficulty(previous_best)
                            
                            if previous_val is None or current_val > previous_val:
                                # Get network difficulty if available
                                network_diff = telemetry.extra_data.get("network_difficulty")
                                
                                # Get pool name from active pool (parse like dashboard.py does)
                                pool_name = "Unknown Pool"
                                if telemetry.pool_in_use:
                                    pool_str = telemetry.pool_in_use
                                    # Remove protocol
                                    if '://' in pool_str:
                                        pool_str = pool_str.split('://')[1]
                                    # Extract host and port
                                    if ':' in pool_str:
                                        parts = pool_str.split(':')
                                        host = parts[0]
                                        try:
                                            port = int(parts[1])
                                            # Look up pool by host and port
                                            pool_result = await db.execute(
                                                select(Pool).where(
                                                    Pool.url == host,
                                                    Pool.port == port
                                                )
                                            )
                                            pool = pool_result.scalar_one_or_none()
                                            if pool:
                                                pool_name = pool.name
                                        except (ValueError, IndexError):
                                            pass
                                
                                await track_high_diff_share(
                                    db=db,
                                    miner_id=miner.id,
                                    miner_name=miner.name,
                                    miner_type=miner.miner_type,
                                    pool_name=pool_name,
                                    difficulty=current_best_diff,
                                    network_difficulty=network_diff,
                                    hashrate=telemetry.hashrate,
                                    hashrate_unit=telemetry.extra_data.get("hashrate_unit", "GH/s"),
                                    miner_mode=miner.current_mode,
                                    previous_best=previous_best
                                )
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Invalid difficulty value for {miner.name}: current={current_best_diff}, previous={previous_best}")
                
                # Update miner's current_mode if detected in telemetry
                # BUT: Skip if miner is enrolled in Agile Solo Strategy (strategy owns mode)
                if telemetry.extra_data and "current_mode" in telemetry.extra_data:
                    detected_mode = telemetry.extra_data["current_mode"]
                    if detected_mode and miner.current_mode != detected_mode:
                        # Check if miner is enrolled in strategy
                        strategy_result = await db.execute(
                            select(MinerStrategy)
                            .where(MinerStrategy.miner_id == miner.id)
                            .where(MinerStrategy.strategy_enabled == True)
                        )
                        enrolled_in_strategy = strategy_result.scalar_one_or_none()
                        
                        if enrolled_in_strategy:
                            print(f"⚠️ {miner.name} enrolled in strategy - ignoring telemetry mode {detected_mode} (keeping {miner.current_mode})")
                        else:
                            miner.current_mode = detected_mode
                            print(f"📝 Updated {miner.name} mode to: {detected_mode}")
                
                # Update firmware version if detected
                if telemetry.extra_data:
                    version = telemetry.extra_data.get("version") or telemetry.extra_data.get("firmware")
                    if version and miner.firmware_version != version:
                        miner.firmware_version = version
                        print(f"📝 Updated {miner.name} firmware to: {version}")
                
                # Save to database
                # Extract hashrate_unit from extra_data if present (ASICs = GH/s)
                hashrate_unit = "GH/s"  # Default for ASIC miners
                if telemetry.extra_data and "hashrate_unit" in telemetry.extra_data:
                    hashrate_unit = telemetry.extra_data["hashrate_unit"]
                
                # Calculate energy cost if we have power data
                energy_cost = None
                if telemetry.power_watts is not None and telemetry.power_watts > 0:
                    try:
                        # Query Agile price for this timestamp
                        with db.no_autoflush:
                            price_query = select(EnergyPrice).where(
                                EnergyPrice.valid_from <= telemetry.timestamp,
                                EnergyPrice.valid_to > telemetry.timestamp
                            ).limit(1)
                            result = await db.execute(price_query)
                            price_row = result.scalar_one_or_none()
                        
                        if price_row:
                            # Calculate cost for 1 minute: (watts / 60 / 1000) * price_pence
                            # Result is in pence
                            energy_cost = (telemetry.power_watts / 60.0 / 1000.0) * price_row.price_pence
                    except Exception as e:
                        print(f"⚠️ Could not calculate energy cost: {e}")
                
                db_telemetry = Telemetry(
                    miner_id=miner.id,
                    timestamp=telemetry.timestamp,
                    hashrate=telemetry.hashrate,
                    hashrate_unit=hashrate_unit,
                    temperature=telemetry.temperature,
                    power_watts=telemetry.power_watts,
                    energy_cost=energy_cost,
                    shares_accepted=telemetry.shares_accepted,
                    shares_rejected=telemetry.shares_rejected,
                    pool_difficulty=telemetry.pool_difficulty,
                    pool_in_use=telemetry.pool_in_use,
                    mode=miner.current_mode,
                    data=telemetry.extra_data
                )
                db.add(db_telemetry)
                
                # Update pool block effort tracking (accumulate shares)
                if telemetry.pool_in_use and telemetry.pool_difficulty and telemetry.shares_accepted:
                    try:
                        from core.high_diff_tracker import update_pool_block_effort, extract_coin_from_pool_name, get_network_difficulty
                        from sqlalchemy import select
                        from core.database import Pool
                        
                        # Find pool by matching URL and port (same logic as high diff tracking)
                        pool_str = telemetry.pool_in_use
                        if '://' in pool_str:
                            pool_str = pool_str.split('://')[1]
                        
                        if ':' in pool_str:
                            parts = pool_str.split(':')
                            pool_url = parts[0]
                            pool_port = int(parts[1])
                            
                            # Look up pool by exact host and port match
                            result = await db.execute(
                                select(Pool).where(
                                    Pool.url == pool_url,
                                    Pool.port == pool_port
                                )
                            )
                            pool = result.scalar_one_or_none()
                        
                        if pool:
                            # Extract coin from pool name
                            coin = extract_coin_from_pool_name(pool.name)
                            
                            if coin:
                                # Get network difficulty from pool's driver if possible, fallback to Solopool.org
                                network_diff = await get_network_difficulty(coin, pool_name=pool.name)
                                
                                # Update cumulative effort using proper pool name
                                await update_pool_block_effort(
                                    db=db,
                                    pool_name=pool.name,
                                    coin=coin,
                                    new_shares=telemetry.shares_accepted,
                                    pool_difficulty=telemetry.pool_difficulty,
                                    network_difficulty=network_diff
                                )
                        else:
                            logger.debug(f"Could not find pool for URL: {telemetry.pool_in_use}")
                    except Exception as e:
                        logger.warning(f"Failed to update pool effort for {miner.name}: {e}")
                
                return True
            else:
                # Log offline event
                event = Event(
                    event_type="warning",
                    source=f"miner_{miner.id}",
                    message=f"Failed to get telemetry from {miner.name}"
                )
                db.add(event)
                return False
        
        except Exception as e:
            print(f"⚠️ Error collecting telemetry from miner {miner.id}: {e}")
            # Log miner connection error
            event = Event(
                event_type="error",
                source=f"miner_{miner.id}",
                message=f"Error collecting telemetry from {miner.name}: {str(e)}"
            )
            db.add(event)
            return False
        return False
    
    async def _collect_telemetry(self):
        """Collect telemetry from all miners"""
        from core.database import AsyncSessionLocal, Miner, Telemetry, Event, Pool, MinerStrategy, EnergyPrice, AgileStrategy, engine
        from core.telemetry_metrics import update_concurrency_peak, update_backlog
        from adapters import create_adapter
        from sqlalchemy import select, String
        
        print("🔄 Starting telemetry collection...")
        
        # Detect database type
        is_postgresql = 'postgresql' in str(engine.url)
        collection_mode = "parallel" if is_postgresql else "sequential"
        print(f"🗄️ Using {collection_mode} collection mode")

        telemetry_concurrency = app_config.get("telemetry.concurrency", 5)
        jitter_max_ms = app_config.get("telemetry.jitter_max_ms", 500)
        
        try:
            async with AsyncSessionLocal() as db:
                # Check if Agile strategy is in OFF state
                agile_in_off_state = False
                strategy_result = await db.execute(select(AgileStrategy).limit(1))
                strategy = strategy_result.scalar_one_or_none()
                if strategy and strategy.enabled and strategy.current_price_band == "OFF":
                    agile_in_off_state = True
                    print("⚡ Agile strategy is OFF - using ping-first optimization")
                
                # Get all enabled miners
                result = await db.execute(select(Miner).where(Miner.enabled == True))
                miners = result.scalars().all()
                
                print(f"📊 Found {len(miners)} enabled miners")
                
                # PostgreSQL: Use parallel collection with concurrency + jitter
                if is_postgresql:
                    semaphore = asyncio.Semaphore(telemetry_concurrency)
                    counter_lock = asyncio.Lock()
                    current_inflight = 0
                    concurrency_peak = 0

                    async def collect_with_metrics(target_miner):
                        nonlocal current_inflight, concurrency_peak
                        if target_miner.miner_type == "nmminer":
                            return None
                        jitter_seconds = random.uniform(0, jitter_max_ms) / 1000.0
                        if jitter_seconds > 0:
                            await asyncio.sleep(jitter_seconds)
                        async with semaphore:
                            async with counter_lock:
                                current_inflight += 1
                                concurrency_peak = max(concurrency_peak, current_inflight)
                            try:
                                from core.database import AsyncSessionLocal
                                async with AsyncSessionLocal() as task_db:
                                    wrote = await self._collect_miner_telemetry(
                                        target_miner,
                                        agile_in_off_state,
                                        task_db
                                    )
                                    if wrote:
                                        await task_db.commit()
                                    else:
                                        await task_db.rollback()
                                    return wrote
                            finally:
                                async with counter_lock:
                                    current_inflight = max(0, current_inflight - 1)

                    tasks = [collect_with_metrics(miner) for miner in miners]
                    
                    # Collect telemetry in parallel (bounded)
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    # Log any exceptions
                    for i, result in enumerate(results):
                        if isinstance(result, Exception):
                            print(f"⚠️ Error collecting telemetry: {result}")

                    update_concurrency_peak(concurrency_peak)
                
                # Sequential mode: Use one-at-a-time collection
                else:
                    sequential_miners = [m for m in miners if m.miner_type != "nmminer"]
                    for miner in miners:
                        # Skip NMMiner - it uses passive UDP listening
                        if miner.miner_type == "nmminer":
                            continue
                        
                        jitter_seconds = random.uniform(0, jitter_max_ms) / 1000.0
                        if jitter_seconds > 0:
                            await asyncio.sleep(jitter_seconds)

                        # Collect telemetry sequentially
                        try:
                            await self._collect_miner_telemetry(miner, agile_in_off_state, db)
                        except Exception as e:
                            print(f"⚠️ Error in sequential collection: {e}")
                        
                        # Stagger requests to avoid overwhelming miners
                        await asyncio.sleep(0.05)

                    update_concurrency_peak(1 if sequential_miners else 0)

                # Track telemetry backlog (miners without recent telemetry)
                await db.flush()
                cutoff = datetime.utcnow() - timedelta(minutes=2)
                backlog_result = await db.execute(
                    select(Miner.id, func.max(Telemetry.timestamp))
                    .outerjoin(Telemetry, Telemetry.miner_id == Miner.id)
                    .where(Miner.enabled == True)
                    .where(Miner.miner_type != "nmminer")
                    .group_by(Miner.id)
                )
                backlog_rows = backlog_result.all()
                backlog_count = sum(
                    1
                    for _, last_ts in backlog_rows
                    if last_ts is None or last_ts < cutoff
                )
                update_backlog(backlog_count)
                
                # Commit with retry logic for database locks
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        await db.commit()
                        break
                    except Exception as commit_error:
                        if "database is locked" in str(commit_error) and attempt < max_retries - 1:
                            print(f"Database locked, retrying commit (attempt {attempt + 1}/{max_retries})...")
                            await asyncio.sleep(0.5 * (attempt + 1))  # Exponential backoff
                            await db.rollback()
                        else:
                            raise
        
                # Log successful collection
                print(f"✅ Telemetry collection completed: {len(miners)} miners")
                async with AsyncSessionLocal() as db:
                    event = Event(
                        event_type="info",
                        source="telemetry",
                        message=f"Collected telemetry from {len(miners)} enabled miners"
                    )
                    db.add(event)
                    await db.commit()
        
        except Exception as e:
            print(f"❌ Error in telemetry collection: {e}")
            # Log system error
            async with AsyncSessionLocal() as db:
                event = Event(
                    event_type="error",
                    source="scheduler",
                    message=f"Error in telemetry collection: {str(e)}"
                )
                db.add(event)
                await db.commit()
    
    async def _push_to_cloud(self):
        """Push telemetry data to HMM Cloud"""
        from core.database import AsyncSessionLocal, Miner, Telemetry
        from sqlalchemy import desc
        
        cloud_service = get_cloud_service()
        if not cloud_service or not cloud_service.enabled:
            return
        
        print("☁️ Pushing telemetry to cloud...")
        
        try:
            async with AsyncSessionLocal() as db:
                # Get all enabled miners
                result = await db.execute(
                    select(Miner).where(Miner.enabled == True)
                )
                miners = result.scalars().all()
                
                if not miners:
                    print("☁️ No enabled miners to push")
                    return
                
                # Build telemetry data for each miner
                miners_data = []
                for miner in miners:
                    # Get latest telemetry
                    telemetry_result = await db.execute(
                        select(Telemetry)
                        .where(Telemetry.miner_id == miner.id)
                        .order_by(desc(Telemetry.timestamp))
                        .limit(1)
                    )
                    latest_telemetry = telemetry_result.scalar_one_or_none()
                    
                    if not latest_telemetry:
                        continue
                    
                    # Build miner data
                    miner_data = {
                        "name": miner.name,
                        "type": miner.miner_type,
                        "ip_address": miner.ip_address or "0.0.0.0",
                        "telemetry": {
                            "timestamp": int(latest_telemetry.timestamp.timestamp()),
                            "hashrate": float(latest_telemetry.hashrate) if latest_telemetry.hashrate else 0.0,
                            "temperature": float(latest_telemetry.temperature) if latest_telemetry.temperature else 0.0,
                            "power": float(latest_telemetry.power) if latest_telemetry.power else 0.0,
                            "shares_accepted": latest_telemetry.shares_accepted or 0,
                            "shares_rejected": latest_telemetry.shares_rejected or 0,
                            "uptime": latest_telemetry.uptime or 0
                        }
                    }
                    miners_data.append(miner_data)
                
                if miners_data:
                    # Push to cloud
                    success = await cloud_service.push_telemetry(miners_data)
                    if success:
                        print(f"☁️ Successfully pushed {len(miners_data)} miners to cloud")
                        
                        # Log system event
                        event = Event(
                            event_type="info",
                            source="cloud_push",
                            message=f"Pushed telemetry for {len(miners_data)} miners to HMM-Cloud"
                        )
                        db.add(event)
                        await db.commit()
                    else:
                        print("☁️ Failed to push telemetry to cloud")
                        
                        # Log warning event
                        event = Event(
                            event_type="warning",
                            source="cloud_push",
                            message=f"Failed to push telemetry to HMM-Cloud"
                        )
                        db.add(event)
                        await db.commit()
                else:
                    print("☁️ No telemetry data to push")
                    
        except Exception as e:
            logger.error(f"❌ Cloud push error: {e}")
            print(f"❌ Cloud push error: {e}")
            
            # Log error event
            async with AsyncSessionLocal() as db:
                event = Event(
                    event_type="error",
                    source="cloud_push",
                    message=f"Cloud push error: {str(e)}"
                )
                db.add(event)
                await db.commit()
    
    async def _evaluate_automation_rules(self):
        """Evaluate and execute automation rules"""
        from core.database import AsyncSessionLocal, AutomationRule, Miner, EnergyPrice, Telemetry, Event
        from adapters import create_adapter
        
        try:
            async with AsyncSessionLocal() as db:
                # Get all enabled rules
                result = await db.execute(
                    select(AutomationRule)
                    .where(AutomationRule.enabled == True)
                    .order_by(AutomationRule.priority)
                )
                rules = result.scalars().all()
                
                for rule in rules:
                    try:
                        triggered = False
                        execution_context = {}
                        
                        print(f"🔍 Evaluating rule '{rule.name}' (ID: {rule.id}, Type: {rule.trigger_type})")
                        
                        # Evaluate trigger
                        if rule.trigger_type == "price_threshold":
                            triggered, execution_context = await self._check_price_threshold(db, rule.trigger_config, rule)
                            print(f"  💰 Price threshold check: triggered={triggered}, config={rule.trigger_config}")
                        
                        elif rule.trigger_type == "time_window":
                            triggered = self._check_time_window(rule.trigger_config)
                            print(f"  ⏰ Time window check: triggered={triggered}")
                        
                        elif rule.trigger_type == "miner_offline":
                            triggered = await self._check_miner_offline(db, rule.trigger_config)
                            print(f"  📴 Miner offline check: triggered={triggered}")
                        
                        elif rule.trigger_type == "miner_overheat":
                            triggered = await self._check_miner_overheat(db, rule.trigger_config)
                            print(f"  🔥 Miner overheat check: triggered={triggered}")
                        
                        elif rule.trigger_type == "pool_failure":
                            triggered = await self._check_pool_failure(db, rule.trigger_config)
                            print(f"  ⚠️ Pool failure check: triggered={triggered}")
                        
                        # Execute action if triggered
                        if triggered:
                            print(f"✅ Rule '{rule.name}' triggered, executing action: {rule.action_type}")
                            await self._execute_action(db, rule)
                            # Update execution tracking
                            rule.last_executed_at = datetime.utcnow()
                            if execution_context:
                                rule.last_execution_context = execution_context
                        else:
                            print(f"⏭️ Rule '{rule.name}' not triggered, skipping")
                    
                    except Exception as e:
                        print(f"⚠️ Error evaluating rule {rule.id}: {e}")
                        import traceback
                        traceback.print_exc()
                
                await db.commit()
        
        except Exception as e:
            print(f"❌ Error in automation rule evaluation: {e}")
    
    async def _check_price_threshold(self, db, config: dict, rule: "AutomationRule" = None) -> tuple[bool, dict]:
        """Check if current energy price meets threshold
        Returns: (triggered, context_dict)
        """
        condition = config.get("condition", "below")  # below, above, between, outside
        
        from core.database import EnergyPrice
        
        now = datetime.utcnow()
        result = await db.execute(
            select(EnergyPrice)
            .where(EnergyPrice.valid_from <= now)
            .where(EnergyPrice.valid_to > now)
            .limit(1)
        )
        price = result.scalar_one_or_none()
        
        if not price:
            return False, {}
        
        # Create execution context with price slot info
        context = {
            "price_id": price.id,
            "valid_from": price.valid_from.isoformat(),
            "valid_to": price.valid_to.isoformat(),
            "price_pence": price.price_pence
        }
        
        # Check if we already executed for this price slot
        if rule and rule.last_execution_context:
            last_price_id = rule.last_execution_context.get("price_id")
            if last_price_id == price.id:
                # Already executed for this price slot, don't trigger again
                print(f"    ⏭️ Already executed for price slot {price.id}, skipping")
                return False, context
        
        triggered = False
        if condition == "below":
            threshold = config.get("threshold", 0)
            triggered = price.price_pence < threshold
            print(f"    📊 Price {price.price_pence}p < {threshold}p? {triggered}")
        elif condition == "above":
            threshold = config.get("threshold", 0)
            triggered = price.price_pence > threshold
            print(f"    📊 Price {price.price_pence}p > {threshold}p? {triggered}")
        elif condition == "between":
            threshold_min = config.get("threshold_min", 0)
            threshold_max = config.get("threshold_max", 999)
            triggered = threshold_min <= price.price_pence <= threshold_max
            print(f"    📊 Price {price.price_pence}p between {threshold_min}p and {threshold_max}p? {triggered}")
        elif condition == "outside":
            threshold_min = config.get("threshold_min", 0)
            threshold_max = config.get("threshold_max", 999)
            triggered = price.price_pence < threshold_min or price.price_pence > threshold_max
            print(f"    📊 Price {price.price_pence}p outside {threshold_min}p-{threshold_max}p? {triggered}")
        
        return triggered, context
    
    def _check_time_window(self, config: dict) -> bool:
        """Check if current time is within window"""
        from datetime import time
        
        start_str = config.get("start", "00:00")
        end_str = config.get("end", "23:59")
        
        start_time = datetime.strptime(start_str, "%H:%M").time()
        end_time = datetime.strptime(end_str, "%H:%M").time()
        current_time = datetime.utcnow().time()
        
        if start_time < end_time:
            return start_time <= current_time <= end_time
        else:
            # Handle overnight windows
            return current_time >= start_time or current_time <= end_time
    
    async def _check_miner_offline(self, db, config: dict) -> bool:
        """Check if miner is offline"""
        from core.database import Miner, Telemetry
        
        miner_id = config.get("miner_id")
        timeout_minutes = config.get("timeout_minutes", 5)
        
        if not miner_id:
            return False
        
        # Check last telemetry
        cutoff = datetime.utcnow() - timedelta(minutes=timeout_minutes)
        result = await db.execute(
            select(Telemetry)
            .where(Telemetry.miner_id == miner_id)
            .where(Telemetry.timestamp > cutoff)
            .limit(1)
        )
        
        return result.scalar_one_or_none() is None
    
    async def _check_miner_overheat(self, db, config: dict) -> bool:
        """Check if miner is overheating"""
        from core.database import Telemetry
        
        miner_id = config.get("miner_id")
        threshold = config.get("threshold", 80)
        
        if not miner_id:
            return False
        
        # Get latest telemetry
        result = await db.execute(
            select(Telemetry)
            .where(Telemetry.miner_id == miner_id)
            .order_by(Telemetry.timestamp.desc())
            .limit(1)
        )
        telemetry = result.scalar_one_or_none()
        
        if not telemetry or not telemetry.temperature:
            return False
        
        try:
            temp_value = float(telemetry.temperature)
            return temp_value > threshold
        except (ValueError, TypeError):
            logger.warning(f"Invalid temperature value in overheat check: {telemetry.temperature}")
            return False
    
    async def _check_pool_failure(self, db, config: dict) -> bool:
        """Check if pool connection is failing"""
        from core.database import Telemetry
        
        miner_id = config.get("miner_id")
        
        if not miner_id:
            return False
        
        # Get latest telemetry
        result = await db.execute(
            select(Telemetry)
            .where(Telemetry.miner_id == miner_id)
            .order_by(Telemetry.timestamp.desc())
            .limit(1)
        )
        telemetry = result.scalar_one_or_none()
        
        # Consider pool failure if no pool_in_use or shares not increasing
        return telemetry and not telemetry.pool_in_use
    
    async def _execute_action(self, db, rule: "AutomationRule"):
        """Execute automation action"""
        from core.database import Miner, Pool, Event
        from adapters import create_adapter
        
        action_type = rule.action_type
        action_config = rule.action_config
        
        if action_type == "apply_mode":
            mode = action_config.get("mode")
            miner_id = action_config.get("miner_id")
            
            print(f"🎯 Automation: Action config miner_id={miner_id}, mode={mode}")
            
            if not miner_id or not mode:
                print(f"❌ Automation: Missing miner_id or mode in action config")
                return
            
            # Resolve miner(s) to apply mode to
            miners_to_update = []
            
            if isinstance(miner_id, str) and miner_id.startswith("type:"):
                # Apply to all miners of this type
                miner_type = miner_id[5:]  # Remove "type:" prefix
                print(f"🔍 Automation: Applying to all miners of type '{miner_type}'")
                result = await db.execute(
                    select(Miner).where(Miner.miner_type == miner_type).where(Miner.enabled == True)
                )
                miners_to_update = result.scalars().all()
                print(f"📋 Found {len(miners_to_update)} enabled miners of type '{miner_type}'")
            else:
                # Single miner by ID
                result = await db.execute(select(Miner).where(Miner.id == miner_id))
                miner = result.scalar_one_or_none()
                if miner:
                    miners_to_update = [miner]
                else:
                    print(f"❌ Automation: Miner ID {miner_id} not found")
            
            # Apply mode to all resolved miners
            for miner in miners_to_update:
                adapter = create_adapter(miner.miner_type, miner.id, miner.name, miner.ip_address, miner.port, miner.config)
                if adapter:
                    print(f"🎯 Automation: Applying mode '{mode}' to {miner.name} ({miner.miner_type})")
                    success = await adapter.set_mode(mode)
                    if success:
                        miner.current_mode = mode
                        miner.last_mode_change = datetime.utcnow()
                        
                        # Control linked Home Assistant device (turn OFF for low/eco modes, ON for high/turbo/oc)
                        low_power_modes = ['low', 'eco']
                        turn_on = mode not in low_power_modes
                        await self._control_ha_device_for_automation(db, miner, turn_on)
                        
                        event = Event(
                            event_type="info",
                            source=f"automation_rule_{rule.id}",
                            message=f"Applied mode '{mode}' to {miner.name} (triggered by '{rule.name}')",
                            data={"rule": rule.name, "miner": miner.name, "mode": mode}
                        )
                        db.add(event)
                        print(f"✅ Automation: Successfully applied mode '{mode}' to {miner.name}")
                    else:
                        print(f"❌ Automation: Failed to apply mode '{mode}' to {miner.name}")
                else:
                    print(f"❌ Automation: Failed to create adapter for {miner.name}")
        
        elif action_type == "switch_pool":
            miner_id = action_config.get("miner_id")
            pool_id = action_config.get("pool_id")
            
            if miner_id and pool_id:
                result = await db.execute(select(Miner).where(Miner.id == miner_id))
                miner = result.scalar_one_or_none()
                
                result = await db.execute(select(Pool).where(Pool.id == pool_id))
                pool = result.scalar_one_or_none()
                
                if miner and pool:
                    adapter = create_adapter(miner.miner_type, miner.id, miner.name, miner.ip_address, miner.port, miner.config)
                    if adapter:
                        success = await adapter.switch_pool(pool.url, pool.port, pool.user, pool.password)
                        if success:
                            event = Event(
                                event_type="info",
                                source=f"automation_rule_{rule.id}",
                                message=f"Switched {miner.name} to pool {pool.name} (triggered by '{rule.name}')",
                                data={"rule": rule.name, "miner": miner.name, "pool": pool.name}
                            )
                            db.add(event)
        
        elif action_type == "control_ha_device":
            device_id = action_config.get("device_id")
            command = action_config.get("command")  # "turn_on" or "turn_off"
            
            if device_id and command:
                from core.database import HomeAssistantConfig, HomeAssistantDevice
                
                # Check if HA is configured
                result = await db.execute(select(HomeAssistantConfig).where(HomeAssistantConfig.enabled == True).limit(1))
                ha_config = result.scalar_one_or_none()
                
                if not ha_config:
                    print(f"❌ Automation: Home Assistant not configured")
                    return
                
                # Get the device
                result = await db.execute(select(HomeAssistantDevice).where(HomeAssistantDevice.id == device_id))
                ha_device = result.scalar_one_or_none()
                
                if not ha_device:
                    print(f"❌ Automation: HA device ID {device_id} not found")
                    return
                
                # Import HA integration at runtime
                from integrations.homeassistant import HomeAssistantIntegration
                
                ha = HomeAssistantIntegration(ha_config.base_url, ha_config.access_token)
                
                print(f"🏠 Automation: {command} HA device {ha_device.name} (triggered by '{rule.name}')")
                
                if command == "turn_on":
                    success = await ha.turn_on(ha_device.entity_id)
                elif command == "turn_off":
                    success = await ha.turn_off(ha_device.entity_id)
                else:
                    print(f"❌ Automation: Invalid command '{command}'")
                    return
                
                if success:
                    ha_device.current_state = "on" if command == "turn_on" else "off"
                    await db.commit()
                    
                    event = Event(
                        event_type="info",
                        source=f"automation_rule_{rule.id}",
                        message=f"Turned {command.replace('_', ' ')} HA device {ha_device.name} (triggered by '{rule.name}')",
                        data={"rule": rule.name, "device": ha_device.name, "command": command}
                    )
                    db.add(event)
                    print(f"✅ Automation: HA device {ha_device.name} {command.replace('_', ' ')}")
                else:
                    print(f"❌ Automation: Failed to {command} HA device {ha_device.name}")
        
        elif action_type == "send_alert":
            message = action_config.get("message", "Automation alert triggered")
            event = Event(
                event_type="alert",
                source=f"automation_rule_{rule.id}",
                message=f"{message} (triggered by '{rule.name}')",
                data={"rule": rule.name}
            )
            db.add(event)
            print(f"🚨 Alert: {message}")
        
        elif action_type == "log_event":
            message = action_config.get("message", "Automation event logged")
            event = Event(
                event_type="info",
                source=f"automation_rule_{rule.id}",
                message=f"{message} (triggered by '{rule.name}')",
                data={"rule": rule.name}
            )
            db.add(event)
    
    async def _reconcile_automation_rules(self):
        """Reconcile miners that should be in a specific state based on currently active automation rules"""
        from core.database import AsyncSessionLocal, AutomationRule, Miner, EnergyPrice, Pool
        from adapters import get_adapter
        
        try:
            async with AsyncSessionLocal() as db:
                # Get all enabled rules
                result = await db.execute(
                    select(AutomationRule)
                    .where(AutomationRule.enabled == True)
                    .order_by(AutomationRule.priority)
                )
                rules = result.scalars().all()
                
                reconciled_count = 0
                checked_count = 0
                
                for rule in rules:
                    try:
                        # Check if rule is currently triggered
                        triggered = False
                        
                        if rule.trigger_type == "price_threshold":
                            triggered, _ = await self._check_price_threshold(db, rule.trigger_config, None)
                        elif rule.trigger_type == "time_window":
                            triggered = self._check_time_window(rule.trigger_config)
                        # Note: miner_offline, overheat, pool_failure are reactive, not persistent states to reconcile
                        
                        if not triggered:
                            continue
                        
                        # Rule is currently active - verify miners are in correct state
                        action_type = rule.action_type
                        action_config = rule.action_config
                        
                        if action_type == "apply_mode":
                            expected_mode = action_config.get("mode")
                            miner_id = action_config.get("miner_id")
                            
                            if not expected_mode or not miner_id:
                                continue
                            
                            # Resolve miners
                            miners_to_check = []
                            
                            if isinstance(miner_id, str) and miner_id.startswith("type:"):
                                miner_type = miner_id[5:]
                                result = await db.execute(
                                    select(Miner).where(Miner.miner_type == miner_type).where(Miner.enabled == True)
                                )
                                miners_to_check = result.scalars().all()
                            else:
                                result = await db.execute(select(Miner).where(Miner.id == miner_id))
                                miner = result.scalar_one_or_none()
                                if miner:
                                    miners_to_check = [miner]
                            
                            # Check each miner's current mode
                            for miner in miners_to_check:
                                checked_count += 1
                                adapter = get_adapter(miner)
                                
                                if not adapter:
                                    continue
                                
                                # Get current mode from miner
                                try:
                                    current_mode = await adapter.get_mode()
                                    
                                    if current_mode and current_mode != expected_mode:
                                        logger.info(
                                            f"🔄 Reconciling automation: {miner.name} is in mode '{current_mode}' "
                                            f"but should be '{expected_mode}' (rule: {rule.name})"
                                        )
                                        
                                        # Apply correct mode
                                        success = await adapter.set_mode(expected_mode)
                                        
                                        if success:
                                            miner.current_mode = expected_mode
                                            reconciled_count += 1
                                            logger.info(f"✓ Reconciled {miner.name} to mode '{expected_mode}'")
                                            
                                            from core.database import Event
                                            event = Event(
                                                event_type="info",
                                                source=f"automation_reconciliation",
                                                message=f"Reconciled {miner.name} to mode '{expected_mode}' (rule: {rule.name})",
                                                data={"rule": rule.name, "miner": miner.name, "mode": expected_mode}
                                            )
                                            db.add(event)
                                            await db.commit()
                                            
                                            # Log to audit trail
                                            from core.audit import log_audit
                                            await log_audit(
                                                db,
                                                action="automation_rule_reconciled",
                                                resource_type="miner",
                                                resource_name=miner.name,
                                                changes={
                                                    "rule_name": rule.name,
                                                    "from_mode": current_mode,
                                                    "to_mode": expected_mode,
                                                    "reason": "Miner was out of sync with active automation rule"
                                                }
                                            )
                                            await db.commit()
                                            
                                            # Log system event
                                            event = Event(
                                                event_type="info",
                                                source="automation",
                                                message=f"Reconciled {miner.name} to {expected_mode} mode (rule: {rule.name})"
                                            )
                                            db.add(event)
                                            await db.commit()
                                        else:
                                            logger.warning(f"✗ Failed to reconcile {miner.name} to mode '{expected_mode}'")
                                
                                except Exception as e:
                                    logger.debug(f"Could not get current mode for {miner.name}: {e}")
                                    continue
                        
                        elif action_type == "switch_pool":
                            miner_id = action_config.get("miner_id")
                            pool_id = action_config.get("pool_id")
                            
                            if not miner_id or not pool_id:
                                continue
                            
                            result = await db.execute(select(Miner).where(Miner.id == miner_id))
                            miner = result.scalar_one_or_none()
                            
                            result = await db.execute(select(Pool).where(Pool.id == pool_id))
                            expected_pool = result.scalar_one_or_none()
                            
                            if not miner or not expected_pool:
                                continue
                            
                            checked_count += 1
                            adapter = get_adapter(miner)
                            
                            if not adapter:
                                continue
                            
                            # Get current pool
                            try:
                                telemetry = await adapter.get_telemetry()
                                
                                if telemetry and telemetry.pool_in_use:
                                    current_pool_url = telemetry.pool_in_use
                                    expected_pool_url = f"{expected_pool.url}"
                                    
                                    # Normalize URLs for comparison
                                    def normalize_url(url: str) -> str:
                                        url = url.replace("stratum+tcp://", "").replace("http://", "").replace("https://", "")
                                        url = url.rstrip("/")
                                        return url.lower()
                                    
                                    if normalize_url(current_pool_url) != normalize_url(expected_pool_url):
                                        logger.info(
                                            f"🔄 Reconciling automation: {miner.name} is on pool '{current_pool_url}' "
                                            f"but should be on '{expected_pool.name}' (rule: {rule.name})"
                                        )
                                        
                                        # Switch to correct pool
                                        success = await adapter.switch_pool(
                                            expected_pool.url, expected_pool.port, 
                                            expected_pool.user, expected_pool.password
                                        )
                                        
                                        if success:
                                            reconciled_count += 1
                                            logger.info(f"✓ Reconciled {miner.name} to pool '{expected_pool.name}'")
                                            
                                            from core.database import Event
                                            event = Event(
                                                event_type="info",
                                                source=f"automation_reconciliation",
                                                message=f"Reconciled {miner.name} to pool '{expected_pool.name}' (rule: {rule.name})",
                                                data={"rule": rule.name, "miner": miner.name, "pool": expected_pool.name}
                                            )
                                            db.add(event)
                                        else:
                                            logger.warning(f"✗ Failed to reconcile {miner.name} to pool '{expected_pool.name}'")
                            
                            except Exception as e:
                                logger.debug(f"Could not get current pool for {miner.name}: {e}")
                                continue
                    
                    except Exception as e:
                        logger.error(f"Error reconciling automation rule {rule.name}: {e}")
                        continue
                
                await db.commit()
                
                if reconciled_count > 0:
                    logger.info(f"✅ Automation reconciliation: {reconciled_count}/{checked_count} miners reconciled")
        
        except Exception as e:
            logger.error(f"Failed to reconcile automation rules: {e}")
            import traceback
            traceback.print_exc()
    
    async def _start_nmminer_listener(self):
        """Start NMMiner UDP listener (one-time startup)"""
        from core.database import AsyncSessionLocal, Miner
        from adapters.nmminer import NMMinerAdapter, NMMinerUDPListener
        
        try:
            async with AsyncSessionLocal() as db:
                # Get all NMMiner devices
                result = await db.execute(
                    select(Miner)
                    .where(Miner.miner_type == "nmminer")
                    .where(Miner.enabled == True)
                )
                nmminers = result.scalars().all()
                
                # Create adapter registry (shared across system)
                self.nmminer_adapters = {}
                for miner in nmminers:
                    adapter = NMMinerAdapter(miner.id, miner.name, miner.ip_address, miner.port, miner.config)
                    self.nmminer_adapters[miner.ip_address] = adapter
                
                if not self.nmminer_adapters:
                    print("📡 No NMMiner devices found - UDP listener not started")
                    return
                
                # Start UDP listener with shared adapters
                self.nmminer_listener = NMMinerUDPListener(self.nmminer_adapters)
                
                # Run in background (non-blocking) with error handling
                import asyncio
                
                async def run_listener():
                    try:
                        await self.nmminer_listener.start()
                    except Exception as e:
                        print(f"❌ NMMiner UDP listener crashed: {e}")
                        import traceback
                        traceback.print_exc()
                
                asyncio.create_task(run_listener())
                
                print(f"📡 NMMiner UDP listener started for {len(nmminers)} devices")
        
        except Exception as e:
            print(f"❌ Failed to start NMMiner UDP listener: {e}")
            import traceback
            traceback.print_exc()
    
    async def reload_nmminer_adapters(self):
        """Reload NMMiner adapter registry (called when miners added/removed/updated)"""
        from core.database import AsyncSessionLocal, Miner
        from adapters.nmminer import NMMinerAdapter, NMMinerUDPListener
        
        try:
            async with AsyncSessionLocal() as db:
                # Get all NMMiner devices
                result = await db.execute(
                    select(Miner)
                    .where(Miner.miner_type == "nmminer")
                    .where(Miner.enabled == True)
                )
                nmminers = result.scalars().all()
                
                # Update adapter registry
                old_count = len(self.nmminer_adapters)
                self.nmminer_adapters.clear()
                
                for miner in nmminers:
                    adapter = NMMinerAdapter(miner.id, miner.name, miner.ip_address, miner.port, miner.config)
                    self.nmminer_adapters[miner.ip_address] = adapter
                
                new_count = len(self.nmminer_adapters)
                print(f"♻️ NMMiner adapter registry reloaded: {old_count} → {new_count} devices")
                
                # If we went from 0 to >0 and listener isn't running, start it
                if old_count == 0 and new_count > 0 and self.nmminer_listener is None:
                    await self._start_nmminer_listener()
        
        except Exception as e:
            print(f"❌ Failed to reload NMMiner adapters: {e}")
            import traceback
            traceback.print_exc()
    
    async def _aggregate_telemetry(self):
        """
        Aggregate telemetry data at 00:05 daily.
        
        Creates hourly and daily aggregates from raw telemetry, then prunes old raw data:
        - Hourly aggregates: Keep for 30 days
        - Daily aggregates: Keep forever
        - Raw telemetry: Keep for 7 days only
        
        This reduces AI context size by 56x (hourly) to 789x (daily).
        """
        from core.database import AsyncSessionLocal, Telemetry, TelemetryHourly, TelemetryDaily, Miner
        from sqlalchemy import delete
        
        try:
            async with AsyncSessionLocal() as db:
                # Get yesterday's date range
                yesterday = (datetime.utcnow() - timedelta(days=1)).date()
                start_time = datetime.combine(yesterday, datetime.min.time())
                end_time = datetime.combine(yesterday, datetime.max.time())
                
                print(f"📊 Aggregating telemetry for {yesterday}...")
                
                # Get all active miners
                result = await db.execute(select(Miner))
                miners = result.scalars().all()
                
                hourly_count = 0
                daily_count = 0
                
                for miner in miners:
                    # ========== HOURLY AGGREGATION ==========
                    # Get raw telemetry for this miner for yesterday
                    query = select(Telemetry).where(
                        and_(
                            Telemetry.miner_id == miner.id,
                            Telemetry.timestamp >= start_time,
                            Telemetry.timestamp <= end_time
                        )
                    ).order_by(Telemetry.timestamp)
                    
                    result = await db.execute(query)
                    telemetry_records = result.scalars().all()
                    
                    if not telemetry_records:
                        continue
                    
                    # Group by hour
                    hourly_data = {}
                    for record in telemetry_records:
                        hour_start = record.timestamp.replace(minute=0, second=0, microsecond=0)
                        
                        if hour_start not in hourly_data:
                            hourly_data[hour_start] = []
                        hourly_data[hour_start].append(record)
                    
                    # Create hourly aggregates
                    for hour_start, records in hourly_data.items():
                        # Calculate aggregates
                        uptime_minutes = len(records)
                        hashrates = [r.hashrate for r in records if r.hashrate is not None]
                        temperatures = [r.temperature for r in records if r.temperature is not None]
                        power_values = [r.power_watts for r in records if r.power_watts is not None]
                        energy_costs = [r.energy_cost for r in records if r.energy_cost is not None]
                        
                        # Get hashrate unit (assume consistent)
                        hashrate_unit = records[0].hashrate_unit if records[0].hashrate_unit else "GH/s"
                        
                        # Calculate totals and averages
                        avg_hashrate = sum(hashrates) / len(hashrates) if hashrates else None
                        min_hashrate = min(hashrates) if hashrates else None
                        max_hashrate = max(hashrates) if hashrates else None
                        avg_temperature = sum(temperatures) / len(temperatures) if temperatures else None
                        peak_temperature = max(temperatures) if temperatures else None
                        
                        # Total kWh = sum of (watts / 60 / 1000) for each minute
                        total_kwh = sum(p / 60.0 / 1000.0 for p in power_values) if power_values else None
                        
                        # Total energy cost = sum of all energy_cost values (already in pence)
                        total_energy_cost = sum(energy_costs) if energy_costs else None
                        
                        # Shares (use last cumulative value - first cumulative value for delta)
                        shares_records = [r for r in records if r.shares_accepted is not None]
                        shares_accepted = shares_records[-1].shares_accepted if shares_records else None
                        
                        shares_rejected_records = [r for r in records if r.shares_rejected is not None]
                        shares_rejected = shares_rejected_records[-1].shares_rejected if shares_rejected_records else None
                        
                        # Reject rate
                        reject_rate_pct = None
                        if shares_accepted and shares_rejected is not None:
                            total_shares = shares_accepted + shares_rejected
                            reject_rate_pct = (shares_rejected / total_shares * 100) if total_shares > 0 else 0
                        
                        # Check if hourly aggregate already exists
                        existing = await db.execute(
                            select(TelemetryHourly).where(
                                and_(
                                    TelemetryHourly.miner_id == miner.id,
                                    TelemetryHourly.hour_start == hour_start
                                )
                            )
                        )
                        if existing.scalar_one_or_none():
                            continue  # Skip if already aggregated
                        
                        # Create hourly aggregate
                        hourly_agg = TelemetryHourly(
                            miner_id=miner.id,
                            hour_start=hour_start,
                            uptime_minutes=uptime_minutes,
                            avg_hashrate=avg_hashrate,
                            min_hashrate=min_hashrate,
                            max_hashrate=max_hashrate,
                            hashrate_unit=hashrate_unit,
                            avg_temperature=avg_temperature,
                            peak_temperature=peak_temperature,
                            total_kwh=total_kwh,
                            total_energy_cost=total_energy_cost,
                            shares_accepted=shares_accepted,
                            shares_rejected=shares_rejected,
                            reject_rate_pct=reject_rate_pct
                        )
                        db.add(hourly_agg)
                        hourly_count += 1
                    
                    # ========== DAILY AGGREGATION ==========
                    # Use the hourly data we already have
                    if telemetry_records:
                        # Calculate daily aggregates from raw data
                        daily_uptime = len(telemetry_records)
                        uptime_percentage = (daily_uptime / 1440.0) * 100  # 1440 minutes in a day
                        
                        hashrates = [r.hashrate for r in telemetry_records if r.hashrate is not None]
                        temperatures = [r.temperature for r in telemetry_records if r.temperature is not None]
                        power_values = [r.power_watts for r in telemetry_records if r.power_watts is not None]
                        energy_costs = [r.energy_cost for r in telemetry_records if r.energy_cost is not None]
                        
                        daily_avg_hashrate = sum(hashrates) / len(hashrates) if hashrates else None
                        daily_min_hashrate = min(hashrates) if hashrates else None
                        daily_max_hashrate = max(hashrates) if hashrates else None
                        daily_avg_temperature = sum(temperatures) / len(temperatures) if temperatures else None
                        daily_peak_temperature = max(temperatures) if temperatures else None
                        daily_total_kwh = sum(p / 60.0 / 1000.0 for p in power_values) if power_values else None
                        daily_total_cost = sum(energy_costs) if energy_costs else None
                        
                        # Shares (use last - first for daily delta)
                        shares_records = [r for r in telemetry_records if r.shares_accepted is not None]
                        daily_shares_accepted = shares_records[-1].shares_accepted if shares_records else None
                        
                        shares_rejected_records = [r for r in telemetry_records if r.shares_rejected is not None]
                        daily_shares_rejected = shares_rejected_records[-1].shares_rejected if shares_rejected_records else None
                        
                        daily_reject_rate = None
                        if daily_shares_accepted and daily_shares_rejected is not None:
                            total_shares = daily_shares_accepted + daily_shares_rejected
                            daily_reject_rate = (daily_shares_rejected / total_shares * 100) if total_shares > 0 else 0
                        
                        # Simple health score (0-100) based on uptime and reject rate
                        health_score = None
                        if uptime_percentage is not None:
                            health_score = uptime_percentage  # Start with uptime %
                            if daily_reject_rate is not None:
                                # Reduce health by reject rate penalty
                                health_score = max(0, health_score - (daily_reject_rate * 5))
                        
                        # Check if daily aggregate already exists
                        existing = await db.execute(
                            select(TelemetryDaily).where(
                                and_(
                                    TelemetryDaily.miner_id == miner.id,
                                    TelemetryDaily.date == start_time
                                )
                            )
                        )
                        if existing.scalar_one_or_none():
                            continue  # Skip if already aggregated
                        
                        # Create daily aggregate
                        daily_agg = TelemetryDaily(
                            miner_id=miner.id,
                            date=start_time,
                            uptime_minutes=daily_uptime,
                            uptime_percentage=uptime_percentage,
                            avg_hashrate=daily_avg_hashrate,
                            min_hashrate=daily_min_hashrate,
                            max_hashrate=daily_max_hashrate,
                            hashrate_unit=hashrate_unit,
                            avg_temperature=daily_avg_temperature,
                            peak_temperature=daily_peak_temperature,
                            total_kwh=daily_total_kwh,
                            total_energy_cost=daily_total_cost,
                            shares_accepted=daily_shares_accepted,
                            shares_rejected=daily_shares_rejected,
                            reject_rate_pct=daily_reject_rate,
                            health_score=health_score
                        )
                        db.add(daily_agg)
                        daily_count += 1
                
                # Commit all aggregates
                await db.commit()
                print(f"✅ Created {hourly_count} hourly and {daily_count} daily aggregates for {yesterday}")
                
                # ========== PRUNE OLD DATA ==========
                # Prune raw telemetry older than 7 days
                cutoff_raw = datetime.utcnow() - timedelta(days=7)
                result = await db.execute(
                    delete(Telemetry).where(Telemetry.timestamp < cutoff_raw)
                )
                await db.commit()
                pruned_raw = result.rowcount
                if pruned_raw > 0:
                    print(f"🗑️ Pruned {pruned_raw} raw telemetry records older than 7 days")
                
                # Prune hourly aggregates older than 30 days
                cutoff_hourly = datetime.utcnow() - timedelta(days=30)
                result = await db.execute(
                    delete(TelemetryHourly).where(TelemetryHourly.hour_start < cutoff_hourly)
                )
                await db.commit()
                pruned_hourly = result.rowcount
                if pruned_hourly > 0:
                    print(f"🗑️ Pruned {pruned_hourly} hourly aggregates older than 30 days")
                
                # Daily aggregates are kept forever
                
        except Exception as e:
            logger.error(f"Failed to aggregate telemetry: {e}", exc_info=True)
            print(f"❌ Telemetry aggregation failed: {e}")
    
    async def _purge_old_telemetry(self):
        """Purge telemetry data older than 30 days (increased for long-term analytics)"""
        from core.database import AsyncSessionLocal, Telemetry
        from sqlalchemy import delete
        
        try:
            cutoff_time = datetime.utcnow() - timedelta(days=30)
            
            async with AsyncSessionLocal() as db:
                # Delete old telemetry records
                result = await db.execute(
                    delete(Telemetry)
                    .where(Telemetry.timestamp < cutoff_time)
                )
                await db.commit()
                
                deleted_count = result.rowcount
                if deleted_count > 0:
                    print(f"🗑️ Purged {deleted_count} telemetry records older than 30 days")
        
        except Exception as e:
            print(f"❌ Failed to purge old telemetry: {e}")
    
    def _get_next_midnight(self):
        """Calculate next midnight UTC for daily aggregation"""
        now = datetime.utcnow()
        next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return next_midnight
    
    async def _aggregate_daily_stats(self):
        """Aggregate yesterday's stats into daily tables at midnight"""
        from core.aggregation import aggregate_daily_stats
        
        try:
            await aggregate_daily_stats()
            print("✓ Daily stats aggregation complete")
        except Exception as e:
            logger.error(f"Failed to aggregate daily stats: {e}", exc_info=True)
            print(f"❌ Daily stats aggregation failed: {e}")
    
    async def _backfill_missing_daily_stats(self):
        """Check for and backfill any missing daily aggregations (last 30 days)"""
        from core.aggregation import aggregate_daily_stats
        from core.database import AsyncSessionLocal, DailyMinerStats, Telemetry
        from sqlalchemy import select, func
        
        try:
            print("🔍 Checking for missing daily aggregations...")
            
            async with AsyncSessionLocal() as db:
                # Check last 30 days for missing data
                today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                start_date = today - timedelta(days=30)
                
                missing_dates = []
                
                for i in range(30):
                    check_date = today - timedelta(days=i+1)  # Yesterday and older
                    
                    # Check if we have any daily stats for this date
                    result = await db.execute(
                        select(func.count(DailyMinerStats.id))
                        .where(DailyMinerStats.date == check_date)
                    )
                    count = result.scalar()
                    
                    # If no stats but we have telemetry data for that day, it's missing
                    if count == 0:
                        # Check if there's telemetry for this date
                        tel_result = await db.execute(
                            select(func.count(Telemetry.id))
                            .where(
                                and_(
                                    Telemetry.timestamp >= check_date,
                                    Telemetry.timestamp < check_date + timedelta(days=1)
                                )
                            )
                        )
                        tel_count = tel_result.scalar()
                        
                        if tel_count > 0:
                            missing_dates.append(check_date)
                
                if missing_dates:
                    print(f"📊 Found {len(missing_dates)} missing daily aggregation(s)")
                    for missing_date in sorted(missing_dates):
                        print(f"   Backfilling: {missing_date.date()}")
                        try:
                            await aggregate_daily_stats(missing_date)
                            print(f"   ✓ Backfilled: {missing_date.date()}")
                        except Exception as e:
                            print(f"   ❌ Failed to backfill {missing_date.date()}: {e}")
                            logger.error(f"Failed to backfill {missing_date.date()}: {e}", exc_info=True)
                else:
                    print("✓ No missing daily aggregations found")
        
        except Exception as e:
            logger.error(f"Failed to check for missing daily stats: {e}", exc_info=True)
            print(f"❌ Failed to check for missing daily stats: {e}")
    
    async def _log_system_summary(self):
        """Log system status summary every 6 hours"""
        from core.database import AsyncSessionLocal, Event, Miner, Telemetry
        from sqlalchemy import select, func
        
        try:
            async with AsyncSessionLocal() as db:
                # Get miner counts
                result = await db.execute(select(Miner))
                all_miners = result.scalars().all()
                total_miners = len(all_miners)
                enabled_miners = len([m for m in all_miners if m.enabled])
                
                # Get recent telemetry success count (last 6 hours)
                six_hours_ago = datetime.utcnow() - timedelta(hours=6)
                result = await db.execute(
                    select(func.count(Telemetry.id))
                    .where(Telemetry.timestamp >= six_hours_ago)
                )
                telemetry_count = result.scalar() or 0
                
                # Get average hashrate and power for enabled miners
                from core.health import get_miner_health_score
                total_hashrate = 0.0
                total_power = 0.0
                health_scores = []
                
                for miner in all_miners:
                    if miner.enabled:
                        result = await db.execute(
                            select(Telemetry)
                            .where(Telemetry.miner_id == miner.id)
                            .order_by(Telemetry.timestamp.desc())
                            .limit(1)
                        )
                        latest_telemetry = result.scalars().first()
                        
                        if latest_telemetry:
                            total_hashrate += latest_telemetry.hashrate or 0
                            total_power += latest_telemetry.power or 0
                            health_score = await get_miner_health_score(miner.id, db)
                            if health_score is not None:
                                health_scores.append(health_score)
                
                avg_health = sum(health_scores) / len(health_scores) if health_scores else 0
                
                # Create summary event
                message = (
                    f"System Status: {enabled_miners}/{total_miners} miners online | "
                    f"Telemetry collected: {telemetry_count} | "
                    f"Total hashrate: {total_hashrate:.2f} GH/s | "
                    f"Total power: {total_power:.2f}W | "
                    f"Avg health: {avg_health:.1f}/100"
                )
                
                event = Event(
                    event_type="info",
                    source="scheduler",
                    message=message
                )
                db.add(event)
                await db.commit()
                
                print(f"ℹ️ {message}")
        
        except Exception as e:
            print(f"❌ Failed to log system summary: {e}")
    
    async def _auto_discover_miners(self):
        """Auto-discover miners on configured networks"""
        from core.database import AsyncSessionLocal, Miner, Event
        from core.discovery import MinerDiscoveryService
        from sqlalchemy import select
        
        try:
            # Check if discovery is enabled
            discovery_config = app_config.get("network_discovery", {})
            if not discovery_config.get("enabled", False):
                print("🔍 Auto-discovery is disabled, skipping scan")
                return
            
            # Get configured networks
            networks = discovery_config.get("networks", [])
            if not networks:
                print("🔍 No networks configured for auto-discovery")
                return
            
            auto_add = discovery_config.get("auto_add", False)
            total_found = 0
            total_added = 0
            
            print(f"🔍 Starting auto-discovery on {len(networks)} network(s)")
            
            async with AsyncSessionLocal() as db:
                # Get existing miners
                result = await db.execute(select(Miner))
                existing_miners = result.scalars().all()
                existing_ips = {m.ip_address for m in existing_miners}
                
                # Scan each network
                for network in networks:
                    network_cidr = network.get("cidr") if isinstance(network, dict) else network
                    network_name = network.get("name", network_cidr) if isinstance(network, dict) else network_cidr
                    
                    print(f"🔍 Scanning network: {network_name}")
                    
                    discovered = await MinerDiscoveryService.discover_miners(
                        network_cidr=network_cidr,
                        timeout=2.0
                    )
                    
                    total_found += len(discovered)
                    
                    # Add new miners if auto-add is enabled
                    if auto_add:
                        for miner_info in discovered:
                            if miner_info['ip'] not in existing_ips:
                                # Create new miner
                                new_miner = Miner(
                                    name=miner_info['name'],
                                    miner_type=miner_info['type'],
                                    ip_address=miner_info['ip'],
                                    port=miner_info['port'],
                                    enabled=True
                                )
                                db.add(new_miner)
                                existing_ips.add(miner_info['ip'])
                                total_added += 1
                                print(f"➕ Auto-added: {miner_info['name']} ({miner_info['ip']})")
                
                # Commit changes
                if total_added > 0:
                    await db.commit()
                    
                    # Log event
                    event = Event(
                        event_type="info",
                        source="scheduler",
                        message=f"Auto-discovery: Found {total_found} miner(s), added {total_added} new miner(s)"
                    )
                    db.add(event)
                    await db.commit()
                
                print(f"✅ Auto-discovery complete: {total_found} found, {total_added} added")
        
        except Exception as e:
            print(f"❌ Auto-discovery failed: {e}")
            import traceback
            traceback.print_exc()
    
    async def _purge_old_events(self):
        """Purge events older than 30 days"""
        from core.database import AsyncSessionLocal, Event
        from sqlalchemy import delete
        
        try:
            cutoff_time = datetime.utcnow() - timedelta(days=30)
            
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    delete(Event)
                    .where(Event.timestamp < cutoff_time)
                )
                await db.commit()
                
                deleted_count = result.rowcount
                if deleted_count > 0:
                    print(f"🗑️ Purged {deleted_count} events older than 30 days")
        
        except Exception as e:
            print(f"❌ Failed to purge old events: {e}")
    
    async def _db_maintenance(self):
        """
        Comprehensive database maintenance during OFF periods
        Includes: purge old data, VACUUM, ANALYZE
        """
        from core.database import AsyncSessionLocal, engine
        from sqlalchemy import text
        
        print("🔧 Starting database maintenance...")
        
        try:
            # 1. Aggregate pool health data
            await self._aggregate_pool_health()
            
            # 2. Aggregate miner analytics data
            await self._aggregate_miner_analytics()
            
            # 3. Purge old telemetry
            await self._purge_old_telemetry()
            
            # 4. Purge old events
            await self._purge_old_events()
            
            # 5. Purge old pool health (raw + hourly)
            await self._purge_old_pool_health()
            
            # 6. Purge old miner analytics (hourly only)
            await self._purge_old_miner_analytics()
            
            # 7. Purge old audit logs
            await self._purge_old_audit_logs()
            
            # 8. Purge old notification logs
            await self._purge_old_notification_logs()
            
            # 9. Purge old health scores
            await self._purge_old_health_scores()
            
            # 10. Database VACUUM (defragment and reclaim space)
            print("🧹 Running VACUUM...")
            # PostgreSQL VACUUM must run outside a transaction
            # Create connection with AUTOCOMMIT isolation for VACUUM
            async with engine.execution_options(isolation_level="AUTOCOMMIT").connect() as conn:
                await conn.execute(text("VACUUM ANALYZE"))
                print("✅ VACUUM ANALYZE complete")
            
            print("✅ Database maintenance complete")
            
        except Exception as e:
            print(f"❌ Database maintenance failed: {e}")
            raise
    
    async def _fallback_maintenance(self):
        """
        Fallback maintenance runs daily at 3am IF:
        1. Agile strategy is disabled (no OFF triggers), OR
        2. Last maintenance was >7 days ago (strategy never hitting OFF)
        """
        from core.database import AsyncSessionLocal, AgileStrategy
        from sqlalchemy import select
        
        try:
            async with AsyncSessionLocal() as db:
                # Check strategy state
                strategy_result = await db.execute(select(AgileStrategy).limit(1))
                strategy = strategy_result.scalar_one_or_none()
                
                should_run = False
                reason = ""
                
                if not strategy or not strategy.enabled:
                    should_run = True
                    reason = "Agile strategy disabled"
                elif strategy.last_aggregation_time is None:
                    should_run = True
                    reason = "Never run before"
                else:
                    days_since = (datetime.utcnow() - strategy.last_aggregation_time).total_seconds() / 86400
                    if days_since >= 7:
                        should_run = True
                        reason = f"Last run {days_since:.1f} days ago"
                
                if should_run:
                    logger.info(f"🔧 Fallback maintenance triggered: {reason}")
                    
                    # Run aggregation
                    await self._aggregate_telemetry()
                    
                    # Run database maintenance
                    await self._db_maintenance()
                    
                    # Update timestamp if we have strategy
                    if strategy:
                        strategy.last_aggregation_time = datetime.utcnow()
                        await db.commit()
                    
                    logger.info("✅ Fallback maintenance complete")
                    
                    # Send notification
                    from core.notifications import send_alert
                    await send_alert(
                        "🔧 Database maintenance complete (fallback)\n\n"
                        f"Reason: {reason}\n"
                        "✅ Telemetry aggregation complete\n"
                        "✅ Old data purged\n"
                        "✅ Database optimized (VACUUM + ANALYZE)\n"
                        f"⏰ Time: {datetime.utcnow().strftime('%H:%M UTC')}",
                        alert_type="aggregation_status"
                    )
                else:
                    logger.debug("Fallback maintenance skipped (Agile strategy handling it)")
        
        except Exception as e:
            logger.error(f"Fallback maintenance failed: {e}")
            import traceback
            traceback.print_exc()
    
    async def _purge_old_energy_prices(self):
        """Purge energy prices older than 60 days"""
        from core.database import AsyncSessionLocal, EnergyPrice
        from sqlalchemy import delete
        
        try:
            cutoff_time = datetime.utcnow() - timedelta(days=60)
            
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    delete(EnergyPrice)
                    .where(EnergyPrice.valid_from < cutoff_time)
                )
                await db.commit()
                
                deleted_count = result.rowcount
                if deleted_count > 0:
                    print(f"🗑️ Purged {deleted_count} energy prices older than 60 days")
        
        except Exception as e:
            print(f"❌ Failed to purge old energy prices: {e}")
    
    async def _vacuum_database(self):
        """Run VACUUM to optimize PostgreSQL database"""
        from core.database import engine
        from sqlalchemy import text
        
        try:
            async with engine.begin() as conn:
                # PostgreSQL: VACUUM ANALYZE (outside transaction)
                await conn.execution_options(isolation_level="AUTOCOMMIT").execute(text("VACUUM ANALYZE"))
                print(f"✨ PostgreSQL optimized (VACUUM ANALYZE completed)")
        
        except Exception as e:
            print(f"❌ Failed to vacuum database: {e}")
    
    async def _check_alerts(self):
        """Check for alert conditions and send notifications"""
        from core.database import AsyncSessionLocal, Miner, Telemetry, AlertConfig, AlertThrottle
        from core.notifications import send_alert
        from sqlalchemy import and_
        
        try:
            async with AsyncSessionLocal() as db:
                # Get enabled alert configs
                result = await db.execute(
                    select(AlertConfig).where(AlertConfig.enabled == True)
                )
                alert_configs = result.scalars().all()
                
                if not alert_configs:
                    return
                
                # Get all miners
                result = await db.execute(select(Miner).where(Miner.enabled == True))
                miners = result.scalars().all()
                
                for miner in miners:
                    # Get latest telemetry
                    result = await db.execute(
                        select(Telemetry)
                        .where(Telemetry.miner_id == miner.id)
                        .order_by(Telemetry.timestamp.desc())
                        .limit(1)
                    )
                    latest_telemetry = result.scalar_one_or_none()
                    
                    for alert_config in alert_configs:
                        alert_triggered = False
                        message = ""
                        
                        # Check miner offline
                        if alert_config.alert_type == "miner_offline":
                            timeout_minutes = alert_config.config.get("timeout_minutes", 5)
                            if not latest_telemetry or \
                               (datetime.utcnow() - latest_telemetry.timestamp).seconds > timeout_minutes * 60:
                                alert_triggered = True
                                message = f"⚠️ <b>Miner Offline</b>\n\n{miner.name} has been offline for more than {timeout_minutes} minutes"
                        
                        # Check high temperature
                        elif alert_config.alert_type == "high_temperature":
                            # Use different default thresholds for different miner types
                            # Avalon Nano: 95°C, NerdQaxe: 75°C, Bitaxe: 70°C
                            if 'avalon' in miner.miner_type.lower():
                                default_threshold = 95
                            elif 'nerdqaxe' in miner.miner_type.lower():
                                default_threshold = 75
                            elif 'bitaxe' in miner.miner_type.lower():
                                default_threshold = 70
                            else:
                                default_threshold = 75  # Generic fallback
                            
                            threshold = alert_config.config.get("threshold_celsius", default_threshold)
                            
                            # Auto-upgrade old thresholds to new standards
                            if 'avalon' in miner.miner_type.lower() and threshold in [75, 90]:
                                threshold = 95
                            elif 'bitaxe' in miner.miner_type.lower() and threshold == 75:
                                threshold = 70
                            
                            # Ensure temperature is a float for comparison
                            if latest_telemetry and latest_telemetry.temperature:
                                try:
                                    temp_value = float(latest_telemetry.temperature)
                                    if temp_value > threshold:
                                        alert_triggered = True
                                        message = f"🌡️ <b>High Temperature Alert</b>\n\n{miner.name} temperature: {temp_value:.1f}°C (threshold: {threshold}°C)"
                                except (ValueError, TypeError):
                                    logger.warning(f"Invalid temperature value for {miner.name}: {latest_telemetry.temperature}")
                        
                        # Check high reject rate
                        elif alert_config.alert_type == "high_reject_rate":
                            threshold_percent = alert_config.config.get("threshold_percent", 5)
                            if latest_telemetry and latest_telemetry.shares_accepted and latest_telemetry.shares_rejected:
                                total_shares = latest_telemetry.shares_accepted + latest_telemetry.shares_rejected
                                if total_shares > 0:
                                    reject_rate = (latest_telemetry.shares_rejected / total_shares) * 100
                                    if reject_rate > threshold_percent:
                                        alert_triggered = True
                                        message = f"📉 <b>High Reject Rate</b>\n\n{miner.name} reject rate: {reject_rate:.1f}% (threshold: {threshold_percent}%)"
                        
                        # Check pool failure
                        elif alert_config.alert_type == "pool_failure":
                            if latest_telemetry and not latest_telemetry.pool_in_use:
                                alert_triggered = True
                                message = f"🌊 <b>Pool Connection Failed</b>\n\n{miner.name} is not connected to any pool"
                        
                        # Check low hashrate
                        elif alert_config.alert_type == "low_hashrate":
                            drop_percent = alert_config.config.get("drop_percent", 30)
                            if latest_telemetry and latest_telemetry.hashrate:
                                # Skip alert if mode changed in last 20 minutes (intentional hashrate change)
                                if miner.last_mode_change:
                                    time_since_mode_change = (datetime.utcnow() - miner.last_mode_change).total_seconds() / 60
                                    if time_since_mode_change < 20:
                                        print(f"⏭️ Skipping hashrate alert for {miner.name}: mode changed {time_since_mode_change:.1f} min ago")
                                        continue
                                
                                # Get average hashrate from last 10 readings
                                result = await db.execute(
                                    select(Telemetry)
                                    .where(Telemetry.miner_id == miner.id)
                                    .where(Telemetry.hashrate != None)
                                    .order_by(Telemetry.timestamp.desc())
                                    .limit(10)
                                )
                                recent_telemetry = result.scalars().all()
                                
                                if len(recent_telemetry) >= 5:
                                    avg_hashrate = sum(t.hashrate for t in recent_telemetry) / len(recent_telemetry)
                                    if latest_telemetry.hashrate < avg_hashrate * (1 - drop_percent / 100):
                                        alert_triggered = True
                                        message = f"⚡ <b>Low Hashrate Alert</b>\n\n{miner.name} hashrate dropped {drop_percent}% below average\nCurrent: {latest_telemetry.hashrate:.2f} GH/s\nAverage: {avg_hashrate:.2f} GH/s"
                        
                        # Send notification if alert triggered
                        if alert_triggered:
                            # Check throttling - get cooldown period from alert config (default 1 hour)
                            cooldown_minutes = alert_config.config.get("cooldown_minutes", 60)
                            
                            # Check if we recently sent this alert for this miner
                            result = await db.execute(
                                select(AlertThrottle).where(
                                    and_(
                                        AlertThrottle.miner_id == miner.id,
                                        AlertThrottle.alert_type == alert_config.alert_type
                                    )
                                )
                            )
                            throttle = result.scalar_one_or_none()
                            
                            should_send = False
                            if not throttle:
                                # First time sending this alert
                                should_send = True
                                throttle = AlertThrottle(
                                    miner_id=miner.id,
                                    alert_type=alert_config.alert_type,
                                    last_sent=datetime.utcnow(),
                                    send_count=1
                                )
                                db.add(throttle)
                            else:
                                # Check if cooldown period has passed
                                time_since_last = (datetime.utcnow() - throttle.last_sent).total_seconds() / 60
                                if time_since_last >= cooldown_minutes:
                                    should_send = True
                                    throttle.last_sent = datetime.utcnow()
                                    throttle.send_count += 1
                            
                            if should_send:
                                await send_alert(message, alert_config.alert_type)
                                await db.commit()
                                print(f"🔔 Alert sent: {alert_config.alert_type} for {miner.name}")
                            else:
                                print(f"⏳ Alert throttled: {alert_config.alert_type} for {miner.name} (cooldown: {cooldown_minutes}min)")
        
        except Exception as e:
            print(f"❌ Failed to check alerts: {e}")
            import traceback
            traceback.print_exc()
    
    async def _record_health_scores(self):
        """Record health scores for all active miners"""
        from core.database import AsyncSessionLocal
        from core.health import record_health_scores
        
        try:
            async with AsyncSessionLocal() as db:
                await record_health_scores(db)
                print(f"📊 Health scores recorded")
        
        except Exception as e:
            print(f"❌ Failed to record health scores: {e}")
            import traceback
            traceback.print_exc()
    
    async def _update_platform_version_cache(self):
        """Update platform version cache from GitHub API every 5 minutes"""
        from core.database import AsyncSessionLocal, PlatformVersionCache
        from sqlalchemy import select
        import httpx
        import os
        
        print("🔄 Updating platform version cache from GitHub...")
        
        try:
            async with AsyncSessionLocal() as db:
                # Fetch from GitHub
                github_owner = "renegadeuk"
                github_repo = "hmm-local"
                github_branch = "main"
                
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        # Get latest commits
                        commits_url = f"https://api.github.com/repos/{github_owner}/{github_repo}/commits"
                        params = {"sha": github_branch, "per_page": 20}
                        response = await client.get(commits_url, params=params)
                        
                        if response.status_code == 403:
                            # Rate limited - keep existing cache
                            print(f"⚠️ GitHub API rate limited, keeping existing cache")
                            
                            # Update last_checked and mark as unavailable
                            result = await db.execute(select(PlatformVersionCache).where(PlatformVersionCache.id == 1))
                            cache = result.scalar_one_or_none()
                            if cache:
                                cache.last_checked = datetime.utcnow()
                                cache.github_available = False
                                cache.error_message = "GitHub API rate limited (60 requests/hour)"
                                await db.commit()
                                print(f"✅ Cache last_checked updated (rate limited)")
                            return
                        
                        response.raise_for_status()
                        commits = response.json()
                        
                        if not commits:
                            print(f"⚠️ No commits found")
                            return
                        
                        latest_commit = commits[0]
                        sha = latest_commit["sha"]
                        sha_short = sha[:7]
                        message = latest_commit["commit"]["message"].split("\n")[0]
                        author = latest_commit["commit"]["author"]["name"]
                        date = latest_commit["commit"]["author"]["date"]
                        
                        # Generate tag and image
                        tag = f"{github_branch}-{sha_short}"
                        image = f"ghcr.io/{github_owner}/{github_repo}:{tag}"
                        
                        # Prepare changelog
                        changelog = []
                        for commit in commits:
                            changelog.append({
                                "sha": commit["sha"][:7],
                                "message": commit["commit"]["message"].split("\n")[0],
                                "author": commit["commit"]["author"]["name"],
                                "date": commit["commit"]["author"]["date"]
                            })
                        
                        # Upsert cache (single row with id=1)
                        result = await db.execute(select(PlatformVersionCache).where(PlatformVersionCache.id == 1))
                        cache = result.scalar_one_or_none()
                        
                        if cache:
                            # Update existing
                            cache.latest_commit = sha
                            cache.latest_commit_short = sha_short
                            cache.latest_message = message
                            cache.latest_author = author
                            cache.latest_date = date
                            cache.latest_tag = tag
                            cache.latest_image = image
                            cache.changelog = changelog
                            cache.last_checked = datetime.utcnow()
                            cache.github_available = True
                            cache.error_message = None
                        else:
                            # Insert new
                            cache = PlatformVersionCache(
                                id=1,
                                latest_commit=sha,
                                latest_commit_short=sha_short,
                                latest_message=message,
                                latest_author=author,
                                latest_date=date,
                                latest_tag=tag,
                                latest_image=image,
                                changelog=changelog,
                                last_checked=datetime.utcnow(),
                                github_available=True,
                                error_message=None
                            )
                            db.add(cache)
                        
                        await db.commit()
                        print(f"✅ Platform version cache updated: {tag}")
                
                except httpx.HTTPError as e:
                    print(f"❌ GitHub API error: {e}")
                    # Mark cache as unavailable but keep existing data
                    result = await db.execute(select(PlatformVersionCache).where(PlatformVersionCache.id == 1))
                    cache = result.scalar_one_or_none()
                    if cache:
                        cache.last_checked = datetime.utcnow()
                        cache.github_available = False
                        cache.error_message = str(e)
                        await db.commit()
        
        except Exception as e:
            print(f"❌ Failed to update platform version cache: {e}")
            import traceback
            traceback.print_exc()
    
    async def _check_update_notifications(self):
        """Check for platform and driver updates and send notifications"""
        from core.database import AsyncSessionLocal
        from core.notifications import NotificationService
        import httpx
        
        print("🔔 Checking for available updates...")
        
        try:
            notifications_to_send = []
            
            # Check platform updates
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get("http://localhost:8080/api/updates/check")
                    if response.status_code == 200:
                        version_info = response.json()
                        if version_info.get("update_available"):
                            commits_behind = version_info.get("commits_behind", 0)
                            current_tag = version_info.get("current_tag", "unknown")
                            latest_tag = version_info.get("latest_tag", "unknown")
                            
                            message = (
                                f"🚀 <b>Platform Update Available</b>\n\n"
                                f"Current: {current_tag}\n"
                                f"Latest: {latest_tag}\n"
                                f"Commits behind: {commits_behind}\n\n"
                                f"Visit Settings → Platform Updates to install"
                            )
                            notifications_to_send.append(("platform_update", message))
                            print(f"✅ Platform update available: {current_tag} → {latest_tag}")
            except Exception as e:
                print(f"⚠️ Failed to check platform updates: {e}")
            
            # Check driver updates
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get("http://localhost:8080/api/drivers/status")
                    if response.status_code == 200:
                        drivers_info = response.json()
                        updates_available = []
                        
                        for driver in drivers_info:
                            if driver.get("status") == "update_available":
                                updates_available.append(f"{driver['display_name']} ({driver['current_version']} → {driver['available_version']})")
                        
                        if updates_available:
                            message = (
                                f"📦 <b>Driver Updates Available</b>\n\n"
                                f"{len(updates_available)} driver(s) have updates:\n"
                                + "\n".join(f"• {u}" for u in updates_available[:5])  # Show first 5
                            )
                            if len(updates_available) > 5:
                                message += f"\n... and {len(updates_available) - 5} more"
                            
                            message += "\n\nVisit Settings → Driver Updates to install"
                            notifications_to_send.append(("driver_update", message))
                            print(f"✅ {len(updates_available)} driver update(s) available")
            except Exception as e:
                print(f"⚠️ Failed to check driver updates: {e}")
            
            # Send notifications if any updates found
            if notifications_to_send:
                notification_service = NotificationService()
                
                for alert_type, message in notifications_to_send:
                    # Send to all enabled channels
                    telegram_sent = await notification_service.send_notification("telegram", message, alert_type)
                    
                    # Format message for Discord (replace HTML tags)
                    discord_message = message.replace("<b>", "**").replace("</b>", "**").replace("<i>", "*").replace("</i>", "*")
                    discord_sent = await notification_service.send_notification("discord", discord_message, alert_type)
                    
                    if telegram_sent or discord_sent:
                        print(f"📨 Sent {alert_type} notification")
            else:
                print("✅ No updates available")
        
        except Exception as e:
            print(f"❌ Failed to check for updates: {e}")
            import traceback
            traceback.print_exc()
    
    async def _auto_optimize_miners(self):
        """Automatically optimize miner modes based on energy prices"""
        from core.config import app_config
        from core.database import AsyncSessionLocal, Miner
        from core.energy import EnergyOptimizationService
        from sqlalchemy import select
        
        print("⚡ Auto-optimization job triggered")
        
        # Check if auto-optimization is enabled
        enabled = app_config.get("energy_optimization.enabled", False)
        print(f"⚡ Auto-optimization enabled: {enabled}")
        if not enabled:
            return
        
        # Get band thresholds (CHEAP / MODERATE / EXPENSIVE)
        cheap_threshold = app_config.get("energy_optimization.cheap_threshold", 15.0)
        expensive_threshold = app_config.get("energy_optimization.expensive_threshold", 25.0)
        print(f"⚡ Band thresholds: CHEAP < {cheap_threshold}p | MODERATE {cheap_threshold}-{expensive_threshold}p | EXPENSIVE ≥ {expensive_threshold}p")
        
        try:
            async with AsyncSessionLocal() as db:
                # Get current price band recommendation
                recommendation = await EnergyOptimizationService.should_mine_now(db, cheap_threshold, expensive_threshold)
                print(f"⚡ Recommendation: {recommendation}")
                
                if "error" in recommendation:
                    print(f"⚡ Auto-optimization skipped: {recommendation['error']}")
                    return
                
                band = recommendation["band"]
                target_mode_name = recommendation["mode"]
                current_price = recommendation["current_price_pence"]
                print(f"⚡ Current band: {band}, Mode: {target_mode_name}, Price: {current_price}p/kWh")
                
                # Get all enabled miners that support mode changes (not NMMiner)
                result = await db.execute(
                    select(Miner)
                    .where(Miner.enabled == True)
                    .where(Miner.miner_type != 'nmminer')
                )
                miners = result.scalars().all()
                print(f"⚡ Found {len(miners)} enabled miners (excluding NMMiner)")
                
                # Skip if EXPENSIVE band (can't turn off miners)
                if band == "EXPENSIVE":
                    print(f"⚡ Band is EXPENSIVE - skipping miner control (cannot turn off miners)")
                    # Still control HA devices below
                else:
                    # Mode mapping: CHEAP → high/oc, MODERATE → low/eco
                    mode_map = {
                        "avalon_nano_3": {"low": "low", "high": "high"},
                        "avalon_nano": {"low": "low", "high": "high"},
                        "bitaxe": {"low": "eco", "high": "oc"},
                        "nerdqaxe": {"low": "eco", "high": "turbo"}
                    }
                    
                    for miner in miners:
                        print(f"⚡ Processing miner: {miner.name} (type: {miner.miner_type})")
                        if miner.miner_type not in mode_map:
                            print(f"⚡ Skipping {miner.name}: type not in mode_map")
                            continue
                        
                        # Determine target mode: "high" for CHEAP, "low" for MODERATE
                        target_mode = mode_map[miner.miner_type][target_mode_name]
                        print(f"⚡ Target mode for {miner.name}: {target_mode}")
                        
                        # Create adapter
                        from adapters import create_adapter
                        adapter = create_adapter(miner.miner_type, miner.id, miner.name, miner.ip_address, miner.port, miner.config)
                        
                        if adapter:
                            try:
                                # Get current mode from database
                                current_mode = miner.current_mode
                                print(f"⚡ Current mode for {miner.name}: {current_mode}")
                                
                                # Only change if different
                                if current_mode != target_mode:
                                    print(f"⚡ Changing {miner.name} mode: {current_mode} → {target_mode}")
                                    success = await adapter.set_mode(target_mode)
                                    if success:
                                        # Update database
                                        miner.current_mode = target_mode
                                        miner.last_mode_change = datetime.utcnow()
                                        await db.commit()
                                        print(f"⚡ Auto-optimized {miner.name}: {current_mode} → {target_mode} (band: {band}, price: {current_price}p/kWh)")
                                    else:
                                        print(f"❌ Failed to set mode for {miner.name}")
                                else:
                                    print(f"⚡ {miner.name} already in {target_mode} mode, skipping")
                            
                            except Exception as e:
                                print(f"❌ Failed to auto-optimize {miner.name}: {e}")
                                import traceback
                                traceback.print_exc()
                        else:
                            print(f"❌ No adapter for {miner.name}")
                
                # Control Home Assistant devices based on band (ON for CHEAP/MODERATE, OFF for EXPENSIVE)
                ha_should_be_on = band in ["CHEAP", "MODERATE"]
                await self._control_ha_device_for_energy_optimization(db, ha_should_be_on)
                
                action_desc = {"CHEAP": "full power", "MODERATE": "reduced power", "EXPENSIVE": "HA devices off"}
                print(f"⚡ Auto-optimization complete: {action_desc.get(band)} (band: {band}, price: {current_price}p/kWh)")
        
        except Exception as e:
            print(f"❌ Failed to auto-optimize miners: {e}")
            import traceback
            traceback.print_exc()
    
    async def _reconcile_energy_optimization(self):
        """Reconcile miners that are out of sync with energy optimization state"""
        from core.config import app_config
        from core.database import AsyncSessionLocal, Miner
        from core.energy import EnergyOptimizationService
        from adapters import get_adapter
        from sqlalchemy import select
        
        try:
            # Check if auto-optimization is enabled
            enabled = app_config.get("energy_optimization.enabled", False)
            if not enabled:
                logger.debug("Energy optimization reconciliation skipped: not enabled")
                return
            
            # Get band thresholds
            cheap_threshold = app_config.get("energy_optimization.cheap_threshold", 15.0)
            expensive_threshold = app_config.get("energy_optimization.expensive_threshold", 25.0)
            
            async with AsyncSessionLocal() as db:
                # Get current price band recommendation
                recommendation = await EnergyOptimizationService.should_mine_now(db, cheap_threshold, expensive_threshold)
                
                if "error" in recommendation:
                    logger.debug(f"Energy optimization reconciliation skipped: {recommendation.get('error')}")
                    return
                
                band = recommendation["band"]
                target_mode_name = recommendation["mode"]
                current_price = recommendation["current_price_pence"]
                
                logger.info(f"⚡ Energy reconciliation check: price={current_price}p, band={band}, target_mode={target_mode_name}")
                
                # Get all enabled miners that support mode changes
                result = await db.execute(
                    select(Miner)
                    .where(Miner.enabled == True)
                    .where(Miner.miner_type != 'nmminer')
                )
                miners = result.scalars().all()
                
                logger.info(f"⚡ Checking {len(miners)} miners for energy optimization state")
                
                # Skip if EXPENSIVE band (can't turn off miners)
                if band == "EXPENSIVE":
                    logger.info("⚡ Band is EXPENSIVE - skipping miner reconciliation")
                else:
                    mode_map = {
                        "avalon_nano_3": {"low": "low", "high": "high"},
                        "avalon_nano": {"low": "low", "high": "high"},
                        "bitaxe": {"low": "eco", "high": "oc"},
                        "nerdqaxe": {"low": "eco", "high": "turbo"}
                    }
                    
                    reconciled_count = 0
                    checked_count = 0
                    
                    for miner in miners:
                        if miner.miner_type not in mode_map:
                            logger.debug(f"Skipping {miner.name}: type {miner.miner_type} not in mode_map")
                            continue
                        
                        # Determine expected mode based on band: "high" for CHEAP, "low" for MODERATE
                        expected_mode = mode_map[miner.miner_type][target_mode_name]
                        
                        adapter = get_adapter(miner)
                        if not adapter:
                            logger.warning(f"No adapter for {miner.name}")
                            continue
                        
                        try:
                            # Get actual current mode from miner hardware
                            logger.info(f"⚡ Checking {miner.name} ({miner.miner_type}): expected mode='{expected_mode}'")
                            current_mode = await adapter.get_mode()
                            checked_count += 1
                            
                            logger.info(f"⚡ {miner.name}: current_mode='{current_mode}', expected='{expected_mode}'")
                            
                            if current_mode is None:
                                logger.warning(f"{miner.name}: could not determine current mode from hardware")
                            elif current_mode == expected_mode:
                                logger.info(f"✓ {miner.name}: already in correct mode '{expected_mode}'")
                            else:
                                logger.info(
                                    f"🔄 Reconciling energy optimization: {miner.name} is in mode '{current_mode}' "
                                    f"but should be '{expected_mode}' (band: {band}, price: {current_price}p)"
                                )
                                
                                # Apply correct mode
                                success = await adapter.set_mode(expected_mode)
                                
                                if success:
                                    miner.current_mode = expected_mode
                                    reconciled_count += 1
                                    logger.info(f"✅ Reconciled {miner.name} to mode '{expected_mode}'")
                                    
                                    # Log to audit trail
                                    from core.audit import log_audit
                                    await log_audit(
                                        db,
                                        action="energy_optimization_reconciled",
                                        resource_type="miner",
                                        resource_name=miner.name,
                                        changes={
                                            "from_mode": current_mode,
                                            "to_mode": expected_mode,
                                            "current_price": current_price,
                                            "band": band,
                                            "cheap_threshold": cheap_threshold,
                                            "expensive_threshold": expensive_threshold,
                                            "reason": "Miner was out of sync with energy optimization state"
                                        }
                                    )
                                    await db.commit()
                                    
                                    # Log system event
                                    event = Event(
                                        event_type="info",
                                        source="energy_optimization",
                                        message=f"Reconciled {miner.name} to {expected_mode} mode (band: {band}, price: {current_price}p)"
                                    )
                                    db.add(event)
                                    await db.commit()
                                else:
                                    logger.warning(f"❌ Failed to reconcile {miner.name} to mode '{expected_mode}'")
                        
                        except Exception as e:
                            logger.error(f"❌ Error checking {miner.name}: {e}")
                            import traceback
                            traceback.print_exc()
                            continue
                        
                        # Stagger requests to avoid overwhelming miners
                        await asyncio.sleep(2)
                    
                    if reconciled_count > 0:
                        await db.commit()
                        logger.info(f"✅ Energy reconciliation complete: {reconciled_count}/{checked_count} miners reconciled")
                    else:
                        logger.info(f"✅ Energy reconciliation complete: All {checked_count} miners already in correct state")
                
                # Control Home Assistant devices based on band (ON for CHEAP/MODERATE, OFF for EXPENSIVE)
                ha_should_be_on = band in ["CHEAP", "MODERATE"]
                await self._control_ha_device_for_energy_optimization(db, ha_should_be_on)
        
        except Exception as e:
            logger.error(f"Failed to reconcile energy optimization: {e}")
            import traceback
            traceback.print_exc()
    
    async def _monitor_pool_health(self):
        """Monitor health of all enabled pools"""
        from core.database import AsyncSessionLocal, Pool
        from core.pool_health import PoolHealthService
        from sqlalchemy import select
        
        try:
            # Use asyncio.create_task to ensure proper greenlet context
            async with AsyncSessionLocal() as db:
                # Get all enabled pools
                result = await db.execute(select(Pool).where(Pool.enabled == True))
                pools = result.scalars().all()
                
                for pool in pools:
                    # Store pool name before try block to avoid post-failure DB access
                    pool_name = pool.name
                    pool_id = pool.id
                    
                    # Retry logic for database locks
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            await PoolHealthService.monitor_pool(pool_id, db)
                            print(f"🌊 Pool health check completed: {pool_name}")
                            break
                        except Exception as e:
                            error_str = str(e)
                            if "database is locked" in error_str and attempt < max_retries - 1:
                                print(f"⚠️ Pool health check for {pool_name} locked, retrying (attempt {attempt + 1}/{max_retries})...")
                                await db.rollback()
                                await asyncio.sleep(0.5 * (attempt + 1))  # Exponential backoff
                            else:
                                # Final attempt failed or non-lock error
                                await db.rollback()
                                logger.error(f"Failed to monitor pool {pool_name}: {e}", exc_info=True)
                                print(f"❌ Failed to monitor pool {pool_name}: {e}")
                                break
                    
                    # Stagger requests to avoid overwhelming pools
                    await asyncio.sleep(2)
        
        except Exception as e:
            print(f"❌ Failed to monitor pool health: {e}")
            import traceback
            traceback.print_exc()
    
    async def _purge_old_pool_health(self):
        """Purge raw pool health data older than 7 days (aggregated data retained longer)"""
        from core.database import AsyncSessionLocal, PoolHealth, PoolHealthHourly
        from sqlalchemy import delete
        
        try:
            async with AsyncSessionLocal() as db:
                # Purge raw data older than 7 days
                raw_cutoff = datetime.utcnow() - timedelta(days=7)
                raw_result = await db.execute(
                    delete(PoolHealth).where(PoolHealth.timestamp < raw_cutoff)
                )
                
                # Purge hourly aggregates older than 30 days
                hourly_cutoff = datetime.utcnow() - timedelta(days=30)
                hourly_result = await db.execute(
                    delete(PoolHealthHourly).where(PoolHealthHourly.hour_start < hourly_cutoff)
                )
                
                await db.commit()
                print(f"🗑️ Purged {raw_result.rowcount} raw pool health records (>7d), {hourly_result.rowcount} hourly aggregates (>30d)")
        
        except Exception as e:
            print(f"❌ Failed to purge old pool health data: {e}")
    
    async def _purge_old_miner_analytics(self):
        """Purge hourly miner analytics older than 30 days (daily aggregates retained forever)"""
        from core.database import AsyncSessionLocal, HourlyMinerAnalytics
        from sqlalchemy import delete
        
        try:
            async with AsyncSessionLocal() as db:
                # Purge hourly data older than 30 days (daily aggregates kept forever)
                hourly_cutoff = datetime.utcnow() - timedelta(days=30)
                hourly_result = await db.execute(
                    delete(HourlyMinerAnalytics).where(HourlyMinerAnalytics.hour_start < hourly_cutoff)
                )
                
                await db.commit()
                print(f"🗑️ Purged {hourly_result.rowcount} hourly miner analytics records (>30d)")
        
        except Exception as e:
            print(f"❌ Failed to purge old miner analytics data: {e}")
    
    async def _purge_old_audit_logs(self):
        """Purge audit logs older than 90 days"""
        from core.database import AsyncSessionLocal, AuditLog
        from sqlalchemy import delete
        
        try:
            async with AsyncSessionLocal() as db:
                cutoff = datetime.utcnow() - timedelta(days=90)
                result = await db.execute(
                    delete(AuditLog).where(AuditLog.timestamp < cutoff)
                )
                
                await db.commit()
                if result.rowcount > 0:
                    print(f"🗑️ Purged {result.rowcount} audit log records (>90d)")
        
        except Exception as e:
            print(f"❌ Failed to purge old audit logs: {e}")
    
    async def _purge_old_notification_logs(self):
        """Purge notification logs older than 90 days"""
        from core.database import AsyncSessionLocal, NotificationLog
        from sqlalchemy import delete
        
        try:
            async with AsyncSessionLocal() as db:
                cutoff = datetime.utcnow() - timedelta(days=90)
                result = await db.execute(
                    delete(NotificationLog).where(NotificationLog.timestamp < cutoff)
                )
                
                await db.commit()
                if result.rowcount > 0:
                    print(f"🗑️ Purged {result.rowcount} notification log records (>90d)")
        
        except Exception as e:
            print(f"❌ Failed to purge old notification logs: {e}")
    
    async def _purge_old_health_scores(self):
        """Purge health scores older than 30 days"""
        from core.database import AsyncSessionLocal, HealthScore
        from sqlalchemy import delete
        
        try:
            async with AsyncSessionLocal() as db:
                cutoff = datetime.utcnow() - timedelta(days=30)
                result = await db.execute(
                    delete(HealthScore).where(HealthScore.timestamp < cutoff)
                )
                
                await db.commit()
                if result.rowcount > 0:
                    print(f"🗑️ Purged {result.rowcount} health score records (>30d)")
        
        except Exception as e:
            print(f"❌ Failed to purge old health scores: {e}")
    
    async def _aggregate_pool_health(self):
        """Aggregate raw pool health checks into hourly and daily summaries"""
        from core.database import AsyncSessionLocal, PoolHealth, PoolHealthHourly, PoolHealthDaily, Pool
        from sqlalchemy import select, func, and_
        
        print("📊 Aggregating pool health data...")
        
        try:
            async with AsyncSessionLocal() as db:
                # Get all pools
                pools_result = await db.execute(select(Pool))
                pools = pools_result.scalars().all()
                
                if not pools:
                    print("ℹ️ No pools to aggregate")
                    return
                
                now = datetime.utcnow()
                hourly_created = 0
                daily_created = 0
                
                for pool in pools:
                    # ===== HOURLY AGGREGATION =====
                    # Find the latest hourly aggregate
                    latest_hourly = await db.execute(
                        select(PoolHealthHourly)
                        .where(PoolHealthHourly.pool_id == pool.id)
                        .order_by(PoolHealthHourly.hour_start.desc())
                        .limit(1)
                    )
                    last_hourly = latest_hourly.scalar_one_or_none()
                    
                    # Start from last aggregate or 7 days ago
                    if last_hourly:
                        start_time = last_hourly.hour_start + timedelta(hours=1)
                    else:
                        start_time = now - timedelta(days=7)
                    
                    # Round down to start of hour
                    start_time = start_time.replace(minute=0, second=0, microsecond=0)
                    
                    # Aggregate each complete hour
                    current_hour = start_time
                    while current_hour < now.replace(minute=0, second=0, microsecond=0):
                        hour_end = current_hour + timedelta(hours=1)
                        
                        # Get all checks for this hour
                        checks = await db.execute(
                            select(PoolHealth)
                            .where(and_(
                                PoolHealth.pool_id == pool.id,
                                PoolHealth.timestamp >= current_hour,
                                PoolHealth.timestamp < hour_end
                            ))
                        )
                        hour_checks = checks.scalars().all()
                        
                        if hour_checks:
                            # Calculate aggregates
                            total_checks = len(hour_checks)
                            uptime_checks = sum(1 for c in hour_checks if c.is_reachable)
                            response_times = [c.response_time_ms for c in hour_checks if c.response_time_ms is not None]
                            health_scores = [c.health_score for c in hour_checks if c.health_score is not None]
                            reject_rates = [c.reject_rate for c in hour_checks if c.reject_rate is not None]
                            
                            hourly_agg = PoolHealthHourly(
                                pool_id=pool.id,
                                hour_start=current_hour,
                                checks_count=total_checks,
                                avg_response_time_ms=sum(response_times) / len(response_times) if response_times else None,
                                max_response_time_ms=max(response_times) if response_times else None,
                                uptime_checks=uptime_checks,
                                uptime_percentage=(uptime_checks / total_checks * 100) if total_checks > 0 else 0,
                                avg_health_score=sum(health_scores) / len(health_scores) if health_scores else None,
                                avg_reject_rate=sum(reject_rates) / len(reject_rates) if reject_rates else None,
                                total_shares_accepted=sum(c.shares_accepted or 0 for c in hour_checks),
                                total_shares_rejected=sum(c.shares_rejected or 0 for c in hour_checks)
                            )
                            db.add(hourly_agg)
                            hourly_created += 1
                        
                        current_hour = hour_end
                    
                    # ===== DAILY AGGREGATION =====
                    # Find the latest daily aggregate
                    latest_daily = await db.execute(
                        select(PoolHealthDaily)
                        .where(PoolHealthDaily.pool_id == pool.id)
                        .order_by(PoolHealthDaily.date.desc())
                        .limit(1)
                    )
                    last_daily = latest_daily.scalar_one_or_none()
                    
                    # Start from last aggregate or 7 days ago
                    if last_daily:
                        start_date = last_daily.date + timedelta(days=1)
                    else:
                        start_date = now - timedelta(days=7)
                    
                    # Round down to start of day
                    start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
                    
                    # Aggregate each complete day
                    current_date = start_date
                    yesterday = now.replace(hour=0, minute=0, second=0, microsecond=0)
                    
                    while current_date < yesterday:
                        date_end = current_date + timedelta(days=1)
                        
                        # Get all checks for this day
                        checks = await db.execute(
                            select(PoolHealth)
                            .where(and_(
                                PoolHealth.pool_id == pool.id,
                                PoolHealth.timestamp >= current_date,
                                PoolHealth.timestamp < date_end
                            ))
                        )
                        day_checks = checks.scalars().all()
                        
                        if day_checks:
                            # Calculate aggregates
                            total_checks = len(day_checks)
                            uptime_checks = sum(1 for c in day_checks if c.is_reachable)
                            downtime_checks = total_checks - uptime_checks
                            # Estimate downtime: assume 5-min check interval
                            downtime_minutes = downtime_checks * 5
                            
                            response_times = [c.response_time_ms for c in day_checks if c.response_time_ms is not None]
                            health_scores = [c.health_score for c in day_checks if c.health_score is not None]
                            reject_rates = [c.reject_rate for c in day_checks if c.reject_rate is not None]
                            
                            daily_agg = PoolHealthDaily(
                                pool_id=pool.id,
                                date=current_date,
                                checks_count=total_checks,
                                avg_response_time_ms=sum(response_times) / len(response_times) if response_times else None,
                                max_response_time_ms=max(response_times) if response_times else None,
                                uptime_checks=uptime_checks,
                                uptime_percentage=(uptime_checks / total_checks * 100) if total_checks > 0 else 0,
                                avg_health_score=sum(health_scores) / len(health_scores) if health_scores else None,
                                avg_reject_rate=sum(reject_rates) / len(reject_rates) if reject_rates else None,
                                total_shares_accepted=sum(c.shares_accepted or 0 for c in day_checks),
                                total_shares_rejected=sum(c.shares_rejected or 0 for c in day_checks),
                                downtime_minutes=downtime_minutes
                            )
                            db.add(daily_agg)
                            daily_created += 1
                        
                        current_date = date_end
                
                await db.commit()
                print(f"✅ Pool health aggregation complete: {hourly_created} hourly, {daily_created} daily records created")
        
        except Exception as e:
            logger.error(f"Failed to aggregate pool health: {e}", exc_info=True)
            print(f"❌ Pool health aggregation failed: {e}")
    
    async def _aggregate_miner_analytics(self):
        """Aggregate raw telemetry into hourly and daily miner analytics"""
        try:
            from core.database import AsyncSessionLocal, Telemetry, HourlyMinerAnalytics, DailyMinerAnalytics, Miner, Pool
            from sqlalchemy import select, func, and_
            from datetime import datetime, timedelta
            
            async with AsyncSessionLocal() as db:
                print("📊 Starting miner analytics aggregation...")
                
                # Get all miners
                miners_result = await db.execute(select(Miner))
                miners = miners_result.scalars().all()
                
                hourly_created = 0
                daily_created = 0
                
                for miner in miners:
                    # Determine coin type based on miner type or pool
                    coin = "BTC"  # Default
                    
                    # ========== HOURLY AGGREGATION ==========
                    # Find last hourly aggregation for this miner
                    last_hourly = await db.execute(
                        select(HourlyMinerAnalytics)
                        .where(HourlyMinerAnalytics.miner_id == miner.id)
                        .order_by(HourlyMinerAnalytics.hour_start.desc())
                        .limit(1)
                    )
                    last_hourly_record = last_hourly.scalar_one_or_none()
                    
                    # Start from last aggregation or 30 days ago
                    if last_hourly_record:
                        start_time = last_hourly_record.hour_start + timedelta(hours=1)
                    else:
                        start_time = datetime.utcnow() - timedelta(days=30)
                    
                    # Aggregate hour by hour
                    current_hour = start_time.replace(minute=0, second=0, microsecond=0)
                    now = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
                    
                    while current_hour < now:
                        hour_end = current_hour + timedelta(hours=1)
                        
                        # Get all telemetry for this hour
                        telemetry_result = await db.execute(
                            select(Telemetry)
                            .where(and_(
                                Telemetry.miner_id == miner.id,
                                Telemetry.timestamp >= current_hour,
                                Telemetry.timestamp < hour_end
                            ))
                            .order_by(Telemetry.timestamp)
                        )
                        telemetry_records = telemetry_result.scalars().all()
                        
                        if telemetry_records:
                            # Calculate aggregates
                            hashrates = [t.hashrate for t in telemetry_records if t.hashrate is not None]
                            powers = [t.power_watts for t in telemetry_records if t.power_watts is not None]
                            temps = [t.temperature for t in telemetry_records if t.temperature is not None]
                            
                            if hashrates:
                                avg_hashrate_gh = sum(hashrates) / len(hashrates)
                                
                                # Calculate total hashes (avg_hashrate * uptime_seconds)
                                uptime_seconds = len(telemetry_records) * 60  # Assuming 1min intervals
                                total_hashes_gh = (avg_hashrate_gh * uptime_seconds) / 3600  # Convert to GH
                                
                                # Aggregate shares
                                total_accepted = sum(t.shares_accepted or 0 for t in telemetry_records if t.shares_accepted is not None)
                                total_rejected = sum(t.shares_rejected or 0 for t in telemetry_records if t.shares_rejected is not None)
                                
                                # Calculate mode distribution and changes
                                mode_minutes = {}
                                mode_changes = 0
                                prev_mode = None
                                
                                for t in telemetry_records:
                                    if t.mode:
                                        mode_minutes[t.mode] = mode_minutes.get(t.mode, 0) + 1
                                        if prev_mode and prev_mode != t.mode:
                                            mode_changes += 1
                                        prev_mode = t.mode
                                
                                # Dominant mode = most minutes
                                dominant_mode = max(mode_minutes.items(), key=lambda x: x[1])[0] if mode_minutes else None
                                mode_distribution = mode_minutes if mode_minutes else None
                                
                                # Get pool_id (from first record with pool info)
                                pool_id = None
                                for t in telemetry_records:
                                    if t.pool_in_use:
                                        # Try to match pool by URL/user
                                        pool_result = await db.execute(
                                            select(Pool).where(Pool.url.like(f"%{t.pool_in_use}%")).limit(1)
                                        )
                                        pool = pool_result.scalar_one_or_none()
                                        if pool:
                                            pool_id = pool.id
                                            break
                                
                                # Calculate derived metrics
                                avg_power = sum(powers) / len(powers) if powers else None
                                avg_temp = sum(temps) / len(temps) if temps else None
                                watts_per_gh = avg_power / avg_hashrate_gh if avg_power and avg_hashrate_gh else None
                                reject_rate = (total_rejected * 100.0 / (total_accepted + total_rejected)) if (total_accepted + total_rejected) > 0 else None
                                hashes_per_share = total_hashes_gh / total_accepted if total_accepted > 0 else None
                                
                                # Create hourly record
                                hourly_agg = HourlyMinerAnalytics(
                                    miner_id=miner.id,
                                    pool_id=pool_id,
                                    coin=coin,
                                    hour_start=current_hour,
                                    mode=dominant_mode,
                                    mode_changes=mode_changes,
                                    mode_distribution=mode_distribution,
                                    total_hashes_gh=total_hashes_gh,
                                    avg_hashrate_gh=avg_hashrate_gh,
                                    peak_hashrate_gh=max(hashrates),
                                    min_hashrate_gh=min(hashrates),
                                    uptime_seconds=uptime_seconds,
                                    shares_accepted=total_accepted,
                                    shares_rejected=total_rejected,
                                    avg_power_watts=avg_power,
                                    min_power_watts=min(powers) if powers else None,
                                    max_power_watts=max(powers) if powers else None,
                                    avg_chip_temp_c=avg_temp,
                                    max_chip_temp_c=max(temps) if temps else None,
                                    watts_per_gh=watts_per_gh,
                                    hashes_per_share=hashes_per_share,
                                    reject_rate_percent=reject_rate
                                )
                                db.add(hourly_agg)
                                hourly_created += 1
                        
                        current_hour = hour_end
                    
                    # ========== DAILY AGGREGATION ==========
                    # Find last daily aggregation
                    last_daily = await db.execute(
                        select(DailyMinerAnalytics)
                        .where(DailyMinerAnalytics.miner_id == miner.id)
                        .order_by(DailyMinerAnalytics.date.desc())
                        .limit(1)
                    )
                    last_daily_record = last_daily.scalar_one_or_none()
                    
                    # Start from last aggregation or 90 days ago
                    if last_daily_record:
                        start_date = last_daily_record.date + timedelta(days=1)
                    else:
                        start_date = datetime.utcnow() - timedelta(days=90)
                    
                    # Aggregate day by day from hourly data
                    current_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
                    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                    
                    while current_date < today:
                        date_end = current_date + timedelta(days=1)
                        
                        # Get hourly records for this day
                        hourly_result = await db.execute(
                            select(HourlyMinerAnalytics)
                            .where(and_(
                                HourlyMinerAnalytics.miner_id == miner.id,
                                HourlyMinerAnalytics.hour_start >= current_date,
                                HourlyMinerAnalytics.hour_start < date_end
                            ))
                        )
                        hourly_records = hourly_result.scalars().all()
                        
                        if hourly_records:
                            # Aggregate daily metrics
                            total_hashes_th = sum(h.total_hashes_gh for h in hourly_records) / 1000.0  # Convert to TH
                            uptime_hours = sum(h.uptime_seconds for h in hourly_records) / 3600.0
                            
                            hashrates = [h.avg_hashrate_gh for h in hourly_records]
                            powers = [h.avg_power_watts for h in hourly_records if h.avg_power_watts is not None]
                            temps = [h.avg_chip_temp_c for h in hourly_records if h.avg_chip_temp_c is not None]
                            
                            # Mode distribution
                            mode_counts = {}
                            for h in hourly_records:
                                if h.mode:
                                    mode_counts[h.mode] = mode_counts.get(h.mode, 0) + (h.uptime_seconds / 3600.0)
                            
                            # Calculate daily aggregates
                            avg_hashrate_gh = sum(hashrates) / len(hashrates)
                            avg_power = sum(powers) / len(powers) if powers else None
                            total_energy_kwh = (avg_power * uptime_hours / 1000.0) if avg_power else None
                            avg_watts_per_gh = avg_power / avg_hashrate_gh if avg_power and avg_hashrate_gh else None
                            
                            total_shares = sum(h.shares_accepted for h in hourly_records)
                            total_rejects = sum(h.shares_rejected for h in hourly_records)
                            avg_reject_rate = (total_rejects * 100.0 / (total_shares + total_rejects)) if (total_shares + total_rejects) > 0 else None
                            
                            # Create daily record
                            daily_agg = DailyMinerAnalytics(
                                miner_id=miner.id,
                                coin=coin,
                                date=current_date,
                                total_hashes_th=total_hashes_th,
                                avg_hashrate_gh=avg_hashrate_gh,
                                peak_hashrate_gh=max(h.peak_hashrate_gh for h in hourly_records if h.peak_hashrate_gh),
                                uptime_hours=uptime_hours,
                                total_shares_accepted=total_shares,
                                total_shares_rejected=total_rejects,
                                avg_reject_rate_percent=avg_reject_rate,
                                best_share_difficulty=max((h.best_share_difficulty for h in hourly_records if h.best_share_difficulty), default=None),
                                avg_power_watts=avg_power,
                                max_power_watts=max(powers) if powers else None,
                                total_energy_kwh=total_energy_kwh,
                                avg_temp_c=sum(temps) / len(temps) if temps else None,
                                max_temp_c=max(temps) if temps else None,
                                avg_watts_per_gh=avg_watts_per_gh,
                                mode_distribution=mode_counts
                            )
                            db.add(daily_agg)
                            daily_created += 1
                        
                        current_date = date_end
                
                await db.commit()
                print(f"✅ Miner analytics aggregation complete: {hourly_created} hourly, {daily_created} daily records created")
        
        except Exception as e:
            logger.error(f"Failed to aggregate miner analytics: {e}", exc_info=True)
            print(f"❌ Miner analytics aggregation failed: {e}")
    
    async def _execute_pool_strategies(self):
        """Execute active pool strategies"""
        try:
            from core.database import AsyncSessionLocal
            from core.pool_strategy import execute_active_strategies
            
            async with AsyncSessionLocal() as db:
                results = await execute_active_strategies(db)
                
                if results:
                    logger.info(f"Executed {len(results)} pool strategies: {results}")
        
        except Exception as e:
            logger.error(f"Failed to execute pool strategies: {e}")
            import traceback
            traceback.print_exc()
    
    async def _reconcile_strategy_miners(self):
        """Reconcile miners that are out of sync with their pool strategies"""
        try:
            from core.database import AsyncSessionLocal
            from core.pool_strategy import reconcile_strategy_miners
            
            async with AsyncSessionLocal() as db:
                results = await reconcile_strategy_miners(db)
                
                if results:
                    logger.info(f"Strategy reconciliation: {len(results)} strategies checked")
                    for result in results:
                        if result["out_of_sync_count"] > 0:
                            logger.info(
                                f"  {result['strategy_name']}: "
                                f"{result['reconciled_count']} reconciled, "
                                f"{result['failed_count']} failed"
                            )
        
        except Exception as e:
            logger.error(f"Failed to reconcile strategy miners: {e}")
            import traceback
            traceback.print_exc()
    
    async def _sync_avalon_pool_slots(self):
        """Sync Avalon Nano pool slot configurations"""
        try:
            from core.database import AsyncSessionLocal
            from core.pool_slots import sync_avalon_nano_pool_slots
            
            async with AsyncSessionLocal() as db:
                await sync_avalon_nano_pool_slots(db)
        
        except Exception as e:
            logger.error(f"Failed to sync Avalon pool slots: {e}")
            import traceback
            traceback.print_exc()
    
    async def _monitor_ha_keepalive(self):
        """Monitor Home Assistant connectivity and send alerts if down"""
        try:
            from core.database import AsyncSessionLocal, HomeAssistantConfig
            from integrations.homeassistant import HomeAssistantIntegration
            from core.notifications import NotificationService
            from datetime import datetime, timedelta
            from sqlalchemy import select
            
            async with AsyncSessionLocal() as db:
                # Get HA config
                result = await db.execute(select(HomeAssistantConfig))
                ha_config = result.scalar_one_or_none()
                
                if not ha_config:
                    return
                
                # Only monitor if keepalive is enabled
                if not ha_config.keepalive_enabled:
                    return
                
                ha_config.keepalive_last_check = datetime.utcnow()
                
                # Test connection
                ha_integration = HomeAssistantIntegration(ha_config.base_url, ha_config.access_token)
                success = await ha_integration.test_connection()
                
                now = datetime.utcnow()
                
                if success:
                    # Connection successful
                    was_down = ha_config.keepalive_downtime_start is not None
                    
                    ha_config.keepalive_last_success = now
                    
                    # Send recovery notification if was previously down
                    if was_down:
                        downtime_duration = (now - ha_config.keepalive_downtime_start).total_seconds()
                        minutes_down = int(downtime_duration / 60)
                        
                        try:
                            notification_service = NotificationService()
                            await notification_service.send_to_all_channels(
                                message=(
                                    "🟢 Home Assistant Online\n"
                                    f"Home Assistant is back online after {minutes_down} minute(s) of downtime."
                                ),
                                alert_type="ha_offline"
                            )
                            logger.info(f"✅ Home Assistant recovered after {minutes_down} minutes")
                        except Exception as e:
                            logger.error(f"Failed to send HA recovery notification: {e}")
                    
                    # Reset downtime tracking (always do this, even if notification fails)
                    ha_config.keepalive_downtime_start = None
                    ha_config.keepalive_alerts_sent = 0
                
                else:
                    # Connection failed
                    if ha_config.keepalive_downtime_start is None:
                        # First failure - start tracking and send immediate notification
                        ha_config.keepalive_downtime_start = now
                        ha_config.keepalive_alerts_sent = 1  # Mark first alert as sent
                        
                        try:
                            notification_service = NotificationService()
                            results = await notification_service.send_to_all_channels(
                                message=(
                                    "🔴 Home Assistant Offline\n"
                                    f"Home Assistant has gone offline. Unable to reach {ha_config.base_url}"
                                ),
                                alert_type="ha_offline"
                            )
                            if results:
                                logger.warning(f"⚠️  Home Assistant offline - immediate alert sent to: {list(results.keys())}")
                            else:
                                logger.warning(f"⚠️  Home Assistant offline - NO notification channels enabled!")
                        except Exception as e:
                            logger.error(f"Failed to send HA offline notification: {e}")
                    
                    else:
                        # Calculate downtime
                        downtime_seconds = (now - ha_config.keepalive_downtime_start).total_seconds()
                        downtime_minutes = int(downtime_seconds / 60)
                        
                        # Escalating follow-up alerts: 5 min, 15 min, 30 min
                        alert_thresholds = [5, 15, 30]
                        should_alert = False
                        
                        for threshold in alert_thresholds:
                            # Check if we've crossed this threshold and haven't sent this alert yet
                            threshold_index = alert_thresholds.index(threshold)
                            # alerts_sent = 1 (immediate), so 5min is index 1, 15min is index 2, etc.
                            if downtime_minutes >= threshold and ha_config.keepalive_alerts_sent <= (threshold_index + 1):
                                should_alert = True
                                ha_config.keepalive_alerts_sent = threshold_index + 2
                                break
                        
                        if should_alert:
                            try:
                                notification_service = NotificationService()
                                
                                if downtime_minutes >= 30:
                                    severity = "🔴🔴"
                                elif downtime_minutes >= 15:
                                    severity = "🔴"
                                else:
                                    severity = "🟠"
                                
                                results = await notification_service.send_to_all_channels(
                                    message=(
                                        f"{severity} Home Assistant Still Offline\n"
                                        f"Home Assistant has been offline for {downtime_minutes} minute(s). "
                                        f"Still unable to reach {ha_config.base_url}"
                                    ),
                                    alert_type="ha_offline"
                                )
                                if results:
                                    logger.warning(f"⚠️  Home Assistant offline for {downtime_minutes} minutes (escalation alert sent to: {list(results.keys())})")
                                else:
                                    logger.warning(f"⚠️  Home Assistant offline for {downtime_minutes} minutes (NO notification channels enabled!)")
                            except Exception as e:
                                logger.error(f"Failed to send HA offline escalation notification: {e}")
                        else:
                            logger.debug(f"Home Assistant offline for {downtime_minutes} minutes (no new alert)")
                
                await db.commit()
        
        except Exception as e:
            logger.error(f"Failed to monitor Home Assistant keepalive: {e}")
            import traceback
            traceback.print_exc()
    
    async def _poll_ha_device_states(self):
        """Poll Home Assistant device states every 5 minutes"""
        try:
            from core.database import AsyncSessionLocal, HomeAssistantConfig, HomeAssistantDevice
            from integrations.homeassistant import HomeAssistantIntegration
            from sqlalchemy import select
            
            async with AsyncSessionLocal() as db:
                # Check if HA is configured and enabled
                result = await db.execute(select(HomeAssistantConfig))
                ha_config = result.scalar_one_or_none()
                
                if not ha_config or not ha_config.enabled:
                    return
                
                # Get all enrolled devices (only poll devices we care about)
                result = await db.execute(
                    select(HomeAssistantDevice).where(HomeAssistantDevice.enrolled == True)
                )
                devices = result.scalars().all()
                
                if not devices:
                    return
                
                # Initialize HA integration
                ha = HomeAssistantIntegration(ha_config.base_url, ha_config.access_token)
                
                # Poll each device state
                updated_count = 0
                for device in devices:
                    try:
                        state = await ha.get_device_state(device.entity_id)
                        
                        if state:
                            # Only update if state has changed
                            if device.current_state != state.state:
                                device.current_state = state.state
                                device.last_state_change = datetime.utcnow()
                                updated_count += 1
                            
                    except Exception as e:
                        logger.warning(f"Failed to poll state for {device.entity_id}: {e}")
                        # Mark as unavailable if we can't reach it
                        if device.current_state != "unavailable":
                            device.current_state = "unavailable"
                            device.last_state_change = datetime.utcnow()
                            updated_count += 1
                
                await db.commit()
                
                if updated_count > 0:
                    logger.info(f"📊 Updated {updated_count}/{len(devices)} HA device states")
        
        except Exception as e:
            logger.error(f"Failed to poll Home Assistant device states: {e}")
    
    async def _reconcile_ha_device_states(self):
        """Check devices that were turned OFF and reconcile if still receiving telemetry"""
        try:
            from core.database import AsyncSessionLocal, HomeAssistantDevice, HomeAssistantConfig, Telemetry, AgileStrategy
            from integrations.homeassistant import HomeAssistantIntegration
            from core.notifications import NotificationService
            from sqlalchemy import select
            from datetime import timedelta
            import asyncio
            
            async with AsyncSessionLocal() as db:
                # Get HA config
                ha_config_result = await db.execute(
                    select(HomeAssistantConfig).where(HomeAssistantConfig.enabled == True)
                )
                ha_config = ha_config_result.scalars().first()
                if not ha_config:
                    return
                
                # Check if champion mode is active (skip reconciliation for current champion)
                strategy_result = await db.execute(select(AgileStrategy).limit(1))
                strategy = strategy_result.scalar_one_or_none()
                
                champion_miner_id = None
                if strategy and strategy.champion_mode_enabled and strategy.current_champion_miner_id:
                    champion_miner_id = strategy.current_champion_miner_id
                    logger.info(f"🏆 Champion mode active: protecting champion miner #{champion_miner_id} from reconciliation")
                
                # Get devices that should be OFF and have linked miners
                now = datetime.utcnow()
                five_minutes_ago = now - timedelta(minutes=5)
                three_minutes_ago = now - timedelta(minutes=3)
                
                devices_result = await db.execute(
                    select(HomeAssistantDevice).where(
                        HomeAssistantDevice.current_state == "off",
                        HomeAssistantDevice.miner_id.isnot(None),
                        HomeAssistantDevice.last_off_command_timestamp.isnot(None),
                        HomeAssistantDevice.last_off_command_timestamp <= five_minutes_ago
                    )
                )
                devices = devices_result.scalars().all()
                
                if not devices:
                    return
                
                ha_integration = HomeAssistantIntegration(
                    base_url=ha_config.base_url,
                    access_token=ha_config.access_token
                )
                
                notification_service = NotificationService()
                
                for ha_device in devices:
                    # Skip reconciliation for active champion miner
                    if champion_miner_id and ha_device.miner_id == champion_miner_id:
                        logger.info(
                            f"⏭️  Skipping reconciliation for {ha_device.name} (miner #{ha_device.miner_id}) - "
                            "active champion in champion mode"
                        )
                        continue
                    
                    # Check if miner has sent telemetry in last 3 minutes
                    telemetry_result = await db.execute(
                        select(Telemetry)
                        .where(
                            Telemetry.miner_id == ha_device.miner_id,
                            Telemetry.timestamp >= three_minutes_ago
                        )
                        .limit(1)
                    )
                    recent_telemetry = telemetry_result.scalars().first()
                    
                    if recent_telemetry:
                        # Device is still sending telemetry despite being OFF - reconcile!
                        logger.warning(
                            f"⚠️  HA Device {ha_device.name} ({ha_device.entity_id}) is OFF but miner "
                            f"#{ha_device.miner_id} still sending telemetry. Reconciling..."
                        )
                        
                        # Cycle device: ON → wait 10s → OFF
                        on_success = await ha_integration.turn_on(ha_device.entity_id)
                        if on_success:
                            logger.info(f"🔄 Turned ON {ha_device.name} for reconciliation")
                            await asyncio.sleep(10)
                            
                            off_success = await ha_integration.turn_off(ha_device.entity_id)
                            if off_success:
                                ha_device.last_off_command_timestamp = datetime.utcnow()
                                ha_device.current_state = "off"
                                ha_device.last_state_change = datetime.utcnow()
                                await db.commit()
                                
                                logger.info(f"✅ Reconciled {ha_device.name} - turned OFF after 10s delay")
                                
                                # Send notification
                                await notification_service.send_to_all_channels(
                                    message=(
                                        "🔄 HA Device Reconciled\n"
                                        f"Device {ha_device.name} was stuck ON despite OFF command. "
                                        "Cycled device (ON → wait 10s → OFF) to force shutdown."
                                    ),
                                    alert_type="ha_device_reconciliation"
                                )
                            else:
                                logger.error(f"❌ Failed to turn OFF {ha_device.name} during reconciliation")
                        else:
                            logger.error(f"❌ Failed to turn ON {ha_device.name} during reconciliation")
        
        except Exception as e:
            logger.error(f"Error reconciling HA device states: {e}", exc_info=True)
    
    async def _execute_agile_solo_strategy(self):
        """Execute Agile Solo Mining Strategy every minute"""
        try:
            logger.info("Executing Agile Strategy")
            from core.database import AsyncSessionLocal, AgileStrategy
            from core.agile_solo_strategy import AgileSoloStrategy
            from sqlalchemy import select
            from datetime import datetime
            
            async with AsyncSessionLocal() as db:
                report = await AgileSoloStrategy.execute_strategy(db)
                
                if report.get("enabled"):
                    logger.info(f"Agile Solo Strategy executed: {report}")
                    
                    # Check if we just entered OFF state and should trigger aggregation
                    if report.get("band") and "OFF" in report.get("band", ""):
                        strategy_result = await db.execute(select(AgileStrategy).limit(1))
                        strategy = strategy_result.scalar_one_or_none()
                        
                        if strategy:
                            # Check if aggregation hasn't run in the last 22 hours
                            should_aggregate = False
                            if strategy.last_aggregation_time is None:
                                should_aggregate = True
                            else:
                                hours_since_agg = (datetime.utcnow() - strategy.last_aggregation_time).total_seconds() / 3600
                                if hours_since_agg >= 22:
                                    should_aggregate = True
                            
                            if should_aggregate:
                                logger.info("🗜️ OFF state detected - triggering maintenance (miners idle)")
                                
                                # Try aggregation + maintenance with retry (max 3 attempts over 90 minutes)
                                max_retries = 3
                                retry_interval = 1800  # 30 minutes between retries
                                
                                for attempt in range(1, max_retries + 1):
                                    try:
                                        logger.info(f"📊 Maintenance attempt {attempt}/{max_retries}")
                                        
                                        # Run telemetry aggregation
                                        await self._aggregate_telemetry()
                                        
                                        # Run database maintenance (purge + VACUUM + ANALYZE)
                                        await self._db_maintenance()
                                        
                                        strategy.last_aggregation_time = datetime.utcnow()
                                        await db.commit()
                                        logger.info("✅ Maintenance complete during OFF period")
                                        
                                        # Send success notification
                                        from core.notifications import send_alert
                                        await send_alert(
                                            "🔧 Database maintenance complete\n\n"
                                            "✅ Telemetry aggregation complete\n"
                                            "✅ Old data purged\n"
                                            "✅ Database optimized (VACUUM + ANALYZE)\n"
                                            f"⏰ Time: {datetime.utcnow().strftime('%H:%M UTC')}\n"
                                            f"🔄 Attempt: {attempt}/{max_retries}",
                                            alert_type="aggregation_status"
                                        )
                                        break  # Success, exit retry loop
                                        
                                    except Exception as e:
                                        logger.error(f"❌ Maintenance attempt {attempt}/{max_retries} failed: {e}")
                                        
                                        if attempt < max_retries:
                                            # Not last attempt, schedule retry
                                            logger.info(f"⏳ Retrying in {retry_interval // 60} minutes...")
                                            await asyncio.sleep(retry_interval)
                                        else:
                                            # Final attempt failed, send notification
                                            from core.notifications import send_alert
                                            await send_alert(
                                                "⚠️ Database maintenance FAILED\n\n"
                                                f"❌ All {max_retries} attempts failed\n"
                                                f"Last error: {str(e)[:200]}\n"
                                                f"⏰ Time: {datetime.utcnow().strftime('%H:%M UTC')}\n\n"
                                                "Check logs for details.",
                                                alert_type="aggregation_status"
                                            )
                            else:
                                logger.debug(f"⏭️ Skipping maintenance (last ran {hours_since_agg:.1f}h ago)")
                else:
                    logger.debug(f"Agile Solo Strategy: {report.get('message', 'disabled')}")
        
        except Exception as e:
            logger.error(f"Failed to execute Agile Solo Strategy: {e}")
            import traceback
            traceback.print_exc()
    
    async def _reconcile_agile_solo_strategy(self):
        """Reconcile Agile Solo Strategy - ensure miners match intended state"""
        try:
            from core.database import AsyncSessionLocal
            from core.agile_solo_strategy import AgileSoloStrategy
            
            async with AsyncSessionLocal() as db:
                report = await AgileSoloStrategy.reconcile_strategy(db)
                
                if report.get("reconciled"):
                    logger.info(f"Agile Solo Strategy reconciliation: {report}")
        
        except Exception as e:
            logger.error(f"Failed to reconcile Agile Solo Strategy: {e}")
            import traceback
            traceback.print_exc()
    
    async def _purge_old_high_diff_shares(self):
        """Purge high diff shares older than 180 days"""
        from core.high_diff_tracker import cleanup_old_shares
        from core.database import AsyncSessionLocal
        
        try:
            async with AsyncSessionLocal() as db:
                await cleanup_old_shares(db, days=180)
        except Exception as e:
            logger.error(f"Failed to purge old high diff shares: {e}", exc_info=True)
    
    async def _push_to_cloud(self):
        """Push telemetry to HMM Cloud"""
        from core.database import AsyncSessionLocal, Miner, Telemetry
        from sqlalchemy import select
        
        cloud_service = get_cloud_service()
        if not cloud_service or not cloud_service.enabled:
            logger.debug("Cloud push skipped (not enabled)")
            return
        
        try:
            async with AsyncSessionLocal() as db:
                # Get all miners
                result = await db.execute(select(Miner))
                miners = result.scalars().all()
                
                # Build telemetry payload with latest telemetry for each miner
                miners_data = []
                for miner in miners:
                    # Get latest telemetry for this miner
                    telemetry_result = await db.execute(
                        select(Telemetry)
                        .where(Telemetry.miner_id == miner.id)
                        .order_by(Telemetry.timestamp.desc())
                        .limit(1)
                    )
                    latest_telemetry = telemetry_result.scalar_one_or_none()
                    
                    # Check if telemetry is recent (within last 10 minutes)
                    has_recent_data = False
                    if latest_telemetry:
                        telemetry_age_seconds = (datetime.utcnow() - latest_telemetry.timestamp).total_seconds()
                        has_recent_data = telemetry_age_seconds <= 600  # 10 minutes
                    
                    # Always include the miner, but use zeros if data is stale/missing
                    if has_recent_data:
                        # Normalize hashrate to GH/s for cloud consistency
                        hashrate_ghs = 0.0
                        if latest_telemetry.hashrate:
                            # Get unit from column or default to GH/s
                            unit = latest_telemetry.hashrate_unit or "GH/s"
                            hashrate_value = float(latest_telemetry.hashrate)
                            
                            # Convert to GH/s
                            if unit == "KH/s":
                                hashrate_ghs = hashrate_value / 1_000_000  # KH/s to GH/s
                            elif unit == "MH/s":
                                hashrate_ghs = hashrate_value / 1_000  # MH/s to GH/s
                            elif unit == "GH/s":
                                hashrate_ghs = hashrate_value
                            elif unit == "TH/s":
                                hashrate_ghs = hashrate_value * 1_000  # TH/s to GH/s
                            else:
                                hashrate_ghs = hashrate_value  # Assume GH/s if unknown
                        
                        miners_data.append({
                            "name": miner.name,
                            "type": miner.miner_type,
                            "ip_address": miner.ip_address,
                            "telemetry": {
                                "timestamp": int(latest_telemetry.timestamp.timestamp()),
                                "hashrate": hashrate_ghs,  # Always in GH/s
                                "temperature": float(latest_telemetry.temperature) if latest_telemetry.temperature else None,
                                "power": float(latest_telemetry.power_watts) if latest_telemetry.power_watts else 0.0,
                                "shares_accepted": latest_telemetry.shares_accepted or 0,
                                "shares_rejected": latest_telemetry.shares_rejected or 0
                            }
                        })
                    else:
                        # Send miner with zero values (offline/stale data)
                        miners_data.append({
                            "name": miner.name,
                            "type": miner.miner_type,
                            "ip_address": miner.ip_address,
                            "telemetry": {
                                "timestamp": int(datetime.utcnow().timestamp()),
                                "hashrate": 0.0,
                                "temperature": None,
                                "power": 0.0,
                                "shares_accepted": 0,
                                "shares_rejected": 0
                            }
                        })
                        logger.debug(f"Pushing {miner.name} with zeros (offline/stale)")
                
                # Calculate aggregated totals
                total_hashrate_ghs = sum(m["telemetry"]["hashrate"] for m in miners_data)
                total_power_watts = sum(m["telemetry"]["power"] for m in miners_data)
                miners_online = sum(1 for m in miners_data if m["telemetry"]["hashrate"] > 0.000001)
                
                # Calculate 24h cost using actual energy prices (same logic as dashboard)
                from core.config import app_config
                cost_24h_gbp = 0.0
                try:
                    if app_config.get("octopus_agile.enabled", False):
                        # Get energy prices for last 24 hours
                        cutoff_24h = datetime.utcnow() - timedelta(hours=24)
                        price_result = await db.execute(
                            select(EnergyPrice)
                            .where(EnergyPrice.valid_from >= cutoff_24h)
                            .order_by(EnergyPrice.valid_from)
                        )
                        energy_prices = price_result.scalars().all()
                        
                        # Helper to find price for timestamp
                        def get_price(ts):
                            for price in energy_prices:
                                if price.valid_from <= ts < price.valid_to:
                                    return price.price_pence
                            return None
                        
                        # Calculate cost for each miner
                        total_cost_pence = 0.0
                        for miner in miners:
                            telem_result = await db.execute(
                                select(Telemetry.power_watts, Telemetry.timestamp)
                                .where(Telemetry.miner_id == miner.id)
                                .where(Telemetry.timestamp > cutoff_24h)
                                .order_by(Telemetry.timestamp)
                            )
                            telem_records = telem_result.all()
                            
                            for i, (power, ts) in enumerate(telem_records):
                                # Fallback to manual power if no auto-detected power
                                if not power or power <= 0:
                                    if miner.manual_power_watts:
                                        power = miner.manual_power_watts
                                    else:
                                        continue
                                
                                price_pence = get_price(ts)
                                if not price_pence:
                                    continue
                                
                                # Calculate duration
                                if i < len(telem_records) - 1:
                                    next_ts = telem_records[i + 1][1]
                                    duration_hours = (next_ts - ts).total_seconds() / 3600.0
                                    
                                    # Cap duration at 10 minutes to prevent counting offline gaps
                                    # Telemetry is recorded every 30s, so >10min gap = miner was offline
                                    max_duration_hours = 10.0 / 60.0  # 10 minutes in hours
                                    if duration_hours > max_duration_hours:
                                        duration_hours = max_duration_hours
                                else:
                                    duration_hours = 30.0 / 3600.0  # 30 seconds
                                
                                kwh = (power / 1000.0) * duration_hours
                                total_cost_pence += kwh * price_pence
                        
                        cost_24h_gbp = total_cost_pence / 100.0
                except Exception as e:
                    logger.warning(f"Failed to calculate 24h cost: {e}")
                
                # Always push (even if empty) to maintain keepalive/heartbeat
                success = await cloud_service.push_telemetry(
                    miners_data,
                    aggregate={
                        "total_hashrate_ghs": total_hashrate_ghs,
                        "total_power_watts": total_power_watts,
                        "miners_online": miners_online,
                        "total_miners": len(miners_data),
                        "cost_24h_gbp": cost_24h_gbp
                    }
                )
                if success:
                    if miners_data:
                        logger.info(f"✓ Pushed {len(miners_data)} miners to cloud")
                    else:
                        logger.debug("✓ Sent keepalive to cloud (no miners)")
                else:
                    logger.warning(f"✗ Failed to push to cloud ({len(miners_data)} miners)")
                    
        except Exception as e:
            logger.error(f"Failed to push to cloud: {e}", exc_info=True)

    async def _compute_hourly_metrics(self):
        """Compute metrics for the previous hour"""
        try:
            from core.metrics import MetricsEngine
            from core.database import AsyncSessionLocal
            from datetime import datetime, timedelta
            
            # Calculate previous hour (floor to hour)
            now = datetime.utcnow()
            previous_hour = (now - timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
            
            async with AsyncSessionLocal() as db:
                engine = MetricsEngine(db)
                await engine.compute_hourly_metrics(previous_hour)
                await db.commit()
            
            logger.info(f"✅ Computed hourly metrics for {previous_hour.strftime('%Y-%m-%d %H:00')}")
        except Exception as e:
            logger.error(f"❌ Failed to compute hourly metrics: {e}", exc_info=True)

    async def _compute_daily_metrics(self):
        """Compute daily metrics for the previous day"""
        try:
            from core.metrics import MetricsEngine
            from core.database import AsyncSessionLocal
            from datetime import datetime, timedelta
            
            # Calculate previous day (midnight)
            now = datetime.utcnow()
            previous_day = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            
            async with AsyncSessionLocal() as db:
                engine = MetricsEngine(db)
                await engine.compute_daily_metrics(previous_day)
                await db.commit()
            
            logger.info(f"✅ Computed daily metrics for {previous_day.strftime('%Y-%m-%d')}")
        except Exception as e:
            logger.error(f"❌ Failed to compute daily metrics: {e}", exc_info=True)

    async def _cleanup_old_metrics(self):
        """Cleanup metrics older than 1 year"""
        try:
            from core.metrics import MetricsEngine
            from core.database import AsyncSessionLocal
            
            async with AsyncSessionLocal() as db:
                engine = MetricsEngine(db)
                deleted_count = await engine.cleanup_old_metrics(days=365)
                await db.commit()
            
            logger.info(f"✅ Cleaned up {deleted_count} old metrics (>365 days)")
        except Exception as e:
            logger.error(f"❌ Failed to cleanup old metrics: {e}", exc_info=True)

    async def _control_ha_device_for_energy_optimization(self, db, miner, turn_on: bool):
        """Control Home Assistant device linked to miner for energy optimization"""
        try:
            from core.database import HomeAssistantConfig, HomeAssistantDevice
            
            # Check if HA is configured
            result = await db.execute(select(HomeAssistantConfig).where(HomeAssistantConfig.enabled == True).limit(1))
            ha_config = result.scalar_one_or_none()
            if not ha_config:
                return
            
            # Find device linked to this miner
            result = await db.execute(
                select(HomeAssistantDevice)
                .where(HomeAssistantDevice.miner_id == miner.id)
                .where(HomeAssistantDevice.enrolled == True)
            )
            ha_device = result.scalar_one_or_none()
            if not ha_device:
                return
            
            # Import HA integration at runtime to avoid circular dependencies
            from integrations.homeassistant import HomeAssistantIntegration
            
            ha = HomeAssistantIntegration(ha_config.base_url, ha_config.access_token)
            
            action = "ON" if turn_on else "OFF"
            logger.info(f"⚡ Energy Optimization: turn_{action.lower()} HA device {ha_device.name} for miner {miner.name}")
            
            if turn_on:
                success = await ha.turn_on(ha_device.entity_id)
            else:
                success = await ha.turn_off(ha_device.entity_id)
            
            if success:
                ha_device.current_state = "on" if turn_on else "off"
                if not turn_on:  # Track when OFF command sent for reconciliation
                    ha_device.last_off_command_timestamp = datetime.utcnow()
                await db.commit()
                logger.info(f"✅ Energy Optimization: HA device {ha_device.name} turned {action}")
            else:
                logger.warning(f"❌ Energy Optimization: Failed to turn {action} HA device {ha_device.name}")
        
        except Exception as e:
            logger.error(f"❌ Failed to control HA device for {miner.name}: {e}")

    async def _control_ha_device_for_automation(self, db, miner, turn_on: bool):
        """Control Home Assistant device linked to miner for automation rules"""
        try:
            from core.database import HomeAssistantConfig, HomeAssistantDevice
            
            # Check if HA is configured
            result = await db.execute(select(HomeAssistantConfig).where(HomeAssistantConfig.enabled == True).limit(1))
            ha_config = result.scalar_one_or_none()
            if not ha_config:
                return
            
            # Find device linked to this miner
            result = await db.execute(
                select(HomeAssistantDevice)
                .where(HomeAssistantDevice.miner_id == miner.id)
                .where(HomeAssistantDevice.enrolled == True)
            )
            ha_device = result.scalar_one_or_none()
            if not ha_device:
                return
            
            # Import HA integration at runtime to avoid circular dependencies
            from integrations.homeassistant import HomeAssistantIntegration
            
            ha = HomeAssistantIntegration(ha_config.base_url, ha_config.access_token)
            
            action = "ON" if turn_on else "OFF"
            logger.info(f"🤖 Automation: turn_{action.lower()} HA device {ha_device.name} for miner {miner.name}")
            
            if turn_on:
                success = await ha.turn_on(ha_device.entity_id)
            else:
                success = await ha.turn_off(ha_device.entity_id)
            
            if success:
                ha_device.current_state = "on" if turn_on else "off"
                if not turn_on:  # Track when OFF command sent for reconciliation
                    ha_device.last_off_command_timestamp = datetime.utcnow()
                await db.commit()
                logger.info(f"✅ Automation: HA device {ha_device.name} turned {action}")
            else:
                logger.warning(f"❌ Automation: Failed to turn {action} HA device {ha_device.name}")
        
        except Exception as e:
            logger.error(f"❌ Failed to control HA device for {miner.name}: {e}")
    
    async def _update_miner_baselines(self):
        """Update statistical baselines for all miners"""
        from core.database import AsyncSessionLocal
        from core.anomaly_detection import update_baselines_for_all_miners
        
        try:
            async with AsyncSessionLocal() as db:
                await update_baselines_for_all_miners(db)
        except Exception as e:
            logger.error(f"❌ Failed to update miner baselines: {e}", exc_info=True)
    
    async def _check_miner_health(self):
        """Check health for all miners and detect anomalies"""
        from core.database import AsyncSessionLocal
        from core.anomaly_detection import check_all_miners_health
        
        try:
            async with AsyncSessionLocal() as db:
                await check_all_miners_health(db)
        except Exception as e:
            logger.error(f"❌ Failed to check miner health: {e}", exc_info=True)
    
    async def _train_ml_models(self):
        """Train ML anomaly detection models (weekly)"""
        from core.database import AsyncSessionLocal
        from core.ml_anomaly import train_all_models
        
        try:
            async with AsyncSessionLocal() as db:
                await train_all_models(db)
        except Exception as e:
            logger.error(f"❌ Failed to train ML models: {e}", exc_info=True)
    
    async def _backup_database(self):
        """Backup PostgreSQL database using pg_dump"""
        from core.database import engine
        from core.config import settings, app_config
        import subprocess
        from datetime import datetime
        
        try:
            backup_dir = settings.CONFIG_DIR / "backups"
            backup_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            
            # PostgreSQL: Use pg_dump
            pg_config = app_config.get("database.postgresql", {})
            
            host = pg_config.get("host", "localhost")
            port = pg_config.get("port", 5432)
            database = pg_config.get("database", "hmm")
            username = pg_config.get("username", "hmm")
            password = pg_config.get("password", "")
            
            backup_file = backup_dir / f"hmm_pg_{timestamp}.sql"
            
            # Use pg_dump via docker exec or direct command
            env = os.environ.copy()
            env['PGPASSWORD'] = password
            
            result = subprocess.run(
                ['pg_dump', '-h', host, '-p', str(port), '-U', username, '-d', database, '-f', str(backup_file)],
                env=env,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode == 0:
                # Compress backup
                subprocess.run(['gzip', str(backup_file)], check=True)
                backup_file_gz = Path(f"{backup_file}.gz")
                
                size_mb = os.path.getsize(backup_file_gz) / (1024 * 1024)
                logger.info(f"✅ PostgreSQL backup created: {backup_file_gz} ({size_mb:.2f} MB)")
                
                # Cleanup old backups (keep last 7 days)
                self._cleanup_old_backups(backup_dir, days=7)
                
                # Send notification
                from core.notifications import send_alert
                await send_alert(
                    f"💾 PostgreSQL backup complete\n\n"
                    f"File: {backup_file_gz.name}\n"
                    f"Size: {size_mb:.2f} MB\n"
                    f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
                    alert_type="backup_status"
                )
            else:
                logger.error(f"❌ pg_dump failed: {result.stderr}")
        
        except Exception as e:
            logger.error(f"❌ Database backup failed: {e}", exc_info=True)
            
            # Send alert on failure
            from core.notifications import send_alert
            await send_alert(
                f"⚠️ Database backup FAILED\n\n"
                f"Error: {str(e)}\n"
                f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
                alert_type="backup_failure"
            )
    
    def _cleanup_old_backups(self, backup_dir: Path, days: int):
        """Remove backups older than specified days"""
        import time
        
        cutoff = time.time() - (days * 86400)
        
        for backup_file in backup_dir.glob("hmm_*.gz"):
            if backup_file.stat().st_mtime < cutoff:
                backup_file.unlink()
                logger.info(f"🗑️ Removed old backup: {backup_file.name}")
    
    async def _monitor_database_health(self):
        """Monitor database connection pool and performance"""
        from core.database import engine
        from core.db_pool_metrics import update_peaks
        from sqlalchemy import text
        
        try:
            # Get connection pool stats
            pool = engine.pool
            pool_size = pool.size()
            checked_out = pool.checkedout()
            overflow = pool.overflow() if hasattr(pool, 'overflow') else 0
            
            # Calculate pool utilization
            total_capacity = pool_size + overflow
            utilization_pct = (checked_out / total_capacity * 100) if total_capacity > 0 else 0
            
            # Update high-water marks
            update_peaks(in_use=checked_out)

            # Check for pool exhaustion warning
            if utilization_pct > 80:
                logger.warning(
                    f"⚠️ Database connection pool high utilization: {utilization_pct:.1f}% "
                    f"({checked_out}/{total_capacity} connections in use)"
                )
                
                # Send alert if critical (>90%)
                if utilization_pct > 90:
                    from core.notifications import send_alert
                    await send_alert(
                        f"🚨 Database connection pool critical\n\n"
                        f"Utilization: {utilization_pct:.1f}%\n"
                        f"In use: {checked_out}/{total_capacity}\n"
                        f"Consider increasing pool_size or investigating connection leaks",
                        alert_type="database_critical"
                    )
            
            # PostgreSQL-specific monitoring
            if 'postgresql' in str(engine.url):
                async with engine.begin() as conn:
                    # Check active connections
                    result = await conn.execute(text("""
                        SELECT count(*) as active_connections
                        FROM pg_stat_activity
                        WHERE datname = current_database()
                        AND state = 'active'
                    """))
                    row = result.fetchone()
                    active_conns = row[0] if row else 0
                    
                    # Check for long-running queries (>1 minute)
                    result = await conn.execute(text("""
                        SELECT count(*) as long_queries
                        FROM pg_stat_activity
                        WHERE datname = current_database()
                        AND state = 'active'
                        AND query_start < NOW() - INTERVAL '1 minute'
                        AND query NOT LIKE '%pg_stat_activity%'
                    """))
                    row = result.fetchone()
                    long_queries = row[0] if row else 0
                    
                    update_peaks(in_use=checked_out, active_queries=active_conns, slow_queries=long_queries)

                    if long_queries > 0:
                        logger.warning(f"⚠️ {long_queries} long-running PostgreSQL queries detected (>1min)")
                    
                    # Check database size
                    result = await conn.execute(text("""
                        SELECT pg_database_size(current_database()) as db_size
                    """))
                    row = result.fetchone()
                    db_size_mb = (row[0] / (1024 * 1024)) if row else 0
                    
                    # Log periodic summary
                    if datetime.utcnow().minute % 15 == 0:
                        logger.info(
                            f"📊 Database health: Pool {utilization_pct:.1f}% "
                            f"({checked_out}/{total_capacity}), "
                            f"Active queries: {active_conns}, "
                            f"Size: {db_size_mb:.1f} MB"
                        )
        
        except Exception as e:
            logger.error(f"❌ Database health check failed: {e}")
    
    async def _check_index_health(self):
        """Check PostgreSQL index health, bloat, and usage"""
        from core.database import engine
        from sqlalchemy import text
        
        try:
            async with engine.begin() as conn:
                # Check for unused indexes
                result = await conn.execute(text("""
                    SELECT
                        schemaname,
                        tablename,
                        indexname,
                        idx_scan as scans,
                        pg_size_pretty(pg_relation_size(indexrelid)) as size
                    FROM pg_stat_user_indexes
                    WHERE idx_scan = 0
                    AND indexrelid::regclass::text NOT LIKE '%_pkey'
                    ORDER BY pg_relation_size(indexrelid) DESC
                    LIMIT 10
                """))
                
                unused_indexes = result.fetchall()
                
                if unused_indexes:
                    logger.warning(f"⚠️ Found {len(unused_indexes)} unused indexes:")
                    for idx in unused_indexes:
                        logger.warning(f"  - {idx[2]} on {idx[1]} ({idx[4]}, 0 scans)")
                
                # Check for bloated indexes (rough estimate)
                result = await conn.execute(text("""
                    SELECT
                        tablename,
                        indexname,
                        pg_size_pretty(pg_relation_size(indexrelid)) as size,
                        idx_scan as scans
                    FROM pg_stat_user_indexes
                    WHERE pg_relation_size(indexrelid) > 10485760  -- >10MB
                    ORDER BY pg_relation_size(indexrelid) DESC
                    LIMIT 10
                """))
                
                large_indexes = result.fetchall()
                
                if large_indexes:
                    logger.info("📊 Largest indexes:")
                    for idx in large_indexes:
                        logger.info(f"  - {idx[1]} on {idx[0]}: {idx[2]} ({idx[3]} scans)")
                
                # Check for missing indexes (sequential scans on large tables)
                result = await conn.execute(text("""
                    SELECT
                        schemaname,
                        tablename,
                        seq_scan,
                        seq_tup_read,
                        idx_scan,
                        pg_size_pretty(pg_relation_size(relid)) as size
                    FROM pg_stat_user_tables
                    WHERE seq_scan > 1000
                    AND pg_relation_size(relid) > 1048576  -- >1MB
                    AND (idx_scan = 0 OR seq_scan > idx_scan * 10)
                    ORDER BY seq_tup_read DESC
                    LIMIT 5
                """))
                
                seq_scan_tables = result.fetchall()
                
                if seq_scan_tables:
                    logger.warning("⚠️ Tables with excessive sequential scans (may need indexes):")
                    for tbl in seq_scan_tables:
                        logger.warning(
                            f"  - {tbl[1]}: {tbl[2]} seq scans ({tbl[3]} rows), "
                            f"{tbl[4]} index scans, size: {tbl[5]}"
                        )
                    
                    # Send notification
                    from core.notifications import send_alert
                    await send_alert(
                        f"🔍 Index health check\n\n"
                        f"Unused indexes: {len(unused_indexes)}\n"
                        f"Tables needing indexes: {len(seq_scan_tables)}\n"
                        f"Consider running REINDEX or adding indexes",
                        alert_type="index_health"
                    )
        
        except Exception as e:
            logger.error(f"❌ Index health check failed: {e}")
    
    async def _refresh_dashboard_materialized_view(self):
        """Refresh dashboard materialized view (PostgreSQL only)"""
        from core.database import AsyncSessionLocal
        from core.postgres_optimizations import refresh_dashboard_materialized_view
        
        try:
            async with AsyncSessionLocal() as db:
                await refresh_dashboard_materialized_view(db)
        except Exception as e:
            logger.error(f"Failed to refresh dashboard materialized view: {e}")
    
    async def _ensure_future_partitions(self):
        """Ensure future telemetry partitions exist (PostgreSQL only)"""
        from core.database import AsyncSessionLocal
        from core.postgres_optimizations import ensure_future_partitions
        
        try:
            async with AsyncSessionLocal() as db:
                await ensure_future_partitions(db)
        except Exception as e:
            logger.error(f"Failed to ensure future partitions: {e}")


scheduler = SchedulerService()

# Make scheduler accessible to adapters
from adapters import set_scheduler_service
set_scheduler_service(scheduler)
