"""
APScheduler for periodic tasks
"""
import logging
import asyncio
import aiohttp
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta
from sqlalchemy import select
from typing import Optional
from core.config import app_config

logger = logging.getLogger(__name__)


class SchedulerService:
    """Scheduler service wrapper"""
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.nmminer_listener = None
        self.nmminer_adapters = {}  # Shared adapter registry for NMMiner devices
    
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
            self._collect_telemetry,
            IntervalTrigger(seconds=60),
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
        
        self.scheduler.add_job(
            self._purge_old_telemetry,
            IntervalTrigger(hours=6),
            id="purge_old_telemetry",
            name="Purge telemetry older than 48 hours"
        )
        
        self.scheduler.add_job(
            self._update_crypto_prices,
            IntervalTrigger(minutes=10),
            id="update_crypto_prices",
            name="Update crypto price cache"
        )
        
        self.scheduler.add_job(
            self._purge_old_events,
            IntervalTrigger(hours=24),
            id="purge_old_events",
            name="Purge events older than 30 days"
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
            self._aggregate_daily_stats,
            IntervalTrigger(hours=24),
            id="aggregate_daily_stats",
            name="Aggregate daily statistics at midnight",
            next_run_time=self._get_next_midnight()
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
            self._capture_ckpool_hashrate,
            IntervalTrigger(minutes=5),
            id="capture_ckpool_hashrate",
            name="Capture CKPool hashrate snapshots every 5 minutes"
        )
        
        self.scheduler.add_job(
            self._purge_old_ckpool_hashrate,
            IntervalTrigger(hours=1),
            id="purge_old_ckpool_hashrate",
            name="Purge CKPool hashrate data older than 24 hours"
        )
        
        self.scheduler.add_job(
            self._purge_old_pool_health,
            IntervalTrigger(days=7),
            id="purge_old_pool_health",
            name="Purge pool health data older than 30 days"
        )
        
        self.scheduler.add_job(
            self._purge_old_ckpool_blocks,
            IntervalTrigger(days=7),
            id="purge_old_ckpool_blocks",
            name="Purge non-accepted CKPool blocks older than 30 days"
        )
        
        self.scheduler.add_job(
            self._purge_old_ckpool_metrics,
            IntervalTrigger(days=30),
            id="purge_old_ckpool_metrics",
            name="Purge CKPool metrics older than 12 months"
        )
        
        self.scheduler.add_job(
            self._purge_old_high_diff_shares,
            IntervalTrigger(days=1),
            id="purge_old_high_diff_shares",
            name="Purge high diff shares older than 180 days"
        )
        
        self.scheduler.add_job(
            self._check_pool_failover,
            IntervalTrigger(minutes=5),
            id="check_pool_failover",
            name="Check for pool failover conditions"
        )
        
        self.scheduler.add_job(
            self._reconcile_strategy_miners,
            IntervalTrigger(minutes=5),
            id="reconcile_strategy_miners",
            name="Reconcile miners out of sync with strategies"
        )
        
        self.scheduler.add_job(
            self._create_supportxmr_snapshots,
            IntervalTrigger(hours=1),
            id="create_supportxmr_snapshots",
            name="Create SupportXMR wallet snapshots"
        )
        
        self.scheduler.add_job(
            self._start_nmminer_listener,
            id="start_nmminer_listener",
            name="Start NMMiner UDP listener"
        )
        
        self.scheduler.start()
        print(f"⏰ Scheduler started with {len(self.scheduler.get_jobs())} jobs")
        print("⏰ Scheduler started")
        
        # Trigger immediate energy price fetch after scheduler is running
        self.scheduler.add_job(
            self._update_energy_prices,
            id="update_energy_prices_immediate",
            name="Immediate energy price fetch"
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
        
        # Trigger immediate SupportXMR snapshot creation
        self.scheduler.add_job(
            self._create_supportxmr_snapshots,
            id="create_supportxmr_snapshots_immediate",
            name="Immediate SupportXMR snapshot creation"
        )
        
        # Trigger immediate Monero block detection TEST
        self.scheduler.add_job(
            self._detect_monero_blocks,
            id="detect_monero_blocks_immediate",
            name="Immediate Monero block detection TEST"
        )
        
        # Agile Solo Strategy execution
        self.scheduler.add_job(
            self._execute_agile_solo_strategy,
            IntervalTrigger(minutes=30),
            id="execute_agile_solo_strategy",
            name="Execute Agile Solo Strategy every 30 minutes"
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
        from core.database import AsyncSessionLocal, EnergyPrice, Event
        
        enabled = app_config.get("octopus_agile.enabled", False)
        print(f"🔍 Octopus Agile enabled: {enabled}")
        
        if not enabled:
            print("⚠️ Octopus Agile is disabled in config")
            return
        
        region = app_config.get("octopus_agile.region", "H")
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
        
        except Exception as e:
            print(f"❌ Failed to update energy prices: {e}")
            # Log exception event
            async with AsyncSessionLocal() as db:
                event = Event(
                    event_type="error",
                    source="octopus_agile",
                    message=f"Exception fetching energy prices: {str(e)}"
                )
                db.add(event)
                await db.commit()
    
    async def _update_crypto_prices(self):
        """Update cached crypto prices every 10 minutes"""
        from api.settings import update_crypto_prices_cache
        await update_crypto_prices_cache()
    
    async def _collect_telemetry(self):
        """Collect telemetry from all miners"""
        from core.database import AsyncSessionLocal, Miner, Telemetry, Event, Pool
        from core.mqtt import mqtt_client
        from adapters import create_adapter
        from sqlalchemy import select, String
        
        print("🔄 Starting telemetry collection...")
        
        try:
            async with AsyncSessionLocal() as db:
                # Get all enabled miners
                result = await db.execute(select(Miner).where(Miner.enabled == True))
                miners = result.scalars().all()
                
                print(f"📊 Found {len(miners)} enabled miners")
                
                for miner in miners:
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
                            continue
                        
                        # Skip NMMiner - it uses passive UDP listening
                        if miner.miner_type == "nmminer":
                            continue
                        
                        # Get telemetry
                        telemetry = await adapter.get_telemetry()
                        
                        if telemetry:
                            # Track high difficulty shares (ASIC miners only)
                            if miner.miner_type in ["avalon_nano", "bitaxe", "nerdqaxe"] and telemetry.extra_data:
                                from core.high_diff_tracker import track_high_diff_share
                                
                                # Extract best diff based on miner type
                                current_best_diff = None
                                if miner.miner_type in ["bitaxe", "nerdqaxe"]:
                                    current_best_diff = telemetry.extra_data.get("best_diff")
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
                                            previous_best = prev_telemetry.data.get("best_diff")
                                        elif miner.miner_type == "avalon_nano":
                                            previous_best = prev_telemetry.data.get("best_share")
                                    
                                    # Only track if this is a new personal best
                                    if previous_best is None or current_best_diff > previous_best:
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
                            
                            # Update miner's current_mode if detected in telemetry
                            if telemetry.extra_data and "current_mode" in telemetry.extra_data:
                                detected_mode = telemetry.extra_data["current_mode"]
                                if detected_mode and miner.current_mode != detected_mode:
                                    miner.current_mode = detected_mode
                                    print(f"📝 Updated {miner.name} mode to: {detected_mode}")
                            
                            # Update firmware version if detected
                            if telemetry.extra_data:
                                version = telemetry.extra_data.get("version") or telemetry.extra_data.get("firmware")
                                if version and miner.firmware_version != version:
                                    miner.firmware_version = version
                                    print(f"📝 Updated {miner.name} firmware to: {version}")
                            
                            # Save to database
                            # Extract hashrate_unit from extra_data if present (XMRig = KH/s, ASICs = GH/s)
                            hashrate_unit = "GH/s"  # Default for ASIC miners
                            if telemetry.extra_data and "hashrate_unit" in telemetry.extra_data:
                                hashrate_unit = telemetry.extra_data["hashrate_unit"]
                            
                            db_telemetry = Telemetry(
                                miner_id=miner.id,
                                timestamp=telemetry.timestamp,
                                hashrate=telemetry.hashrate,
                                hashrate_unit=hashrate_unit,
                                temperature=telemetry.temperature,
                                power_watts=telemetry.power_watts,
                                shares_accepted=telemetry.shares_accepted,
                                shares_rejected=telemetry.shares_rejected,
                                pool_in_use=telemetry.pool_in_use,
                                data=telemetry.extra_data
                            )
                            db.add(db_telemetry)
                            
                            # Publish to MQTT if enabled
                            mqtt_client.publish(
                                f"telemetry/{miner.id}",
                                telemetry.to_dict()
                            )
                        else:
                            # Log offline event
                            event = Event(
                                event_type="warning",
                                source=f"miner_{miner.id}",
                                message=f"Failed to get telemetry from {miner.name}"
                            )
                            db.add(event)
                    
                    except Exception as e:
                        print(f"⚠️ Error collecting telemetry from miner {miner.id}: {e}")
                        # Log miner connection error
                        event = Event(
                            event_type="error",
                            source=f"miner_{miner.id}",
                            message=f"Error collecting telemetry from {miner.name}: {str(e)}"
                        )
                        db.add(event)
                    
                    # Stagger requests to avoid overwhelming miners
                    await asyncio.sleep(0.1)
                
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
        
        return telemetry.temperature > threshold
    
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
        """Start NMMiner UDP listener"""
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
                
                if not nmminers:
                    print("📡 No NMMiner devices configured, skipping UDP listener")
                    return
                
                # Create adapter registry (shared across system)
                self.nmminer_adapters = {}
                for miner in nmminers:
                    adapter = NMMinerAdapter(miner.id, miner.name, miner.ip_address, miner.port, miner.config)
                    self.nmminer_adapters[miner.ip_address] = adapter
                
                # Start UDP listener with shared adapters
                self.nmminer_listener = NMMinerUDPListener(self.nmminer_adapters)
                
                # Run in background (non-blocking)
                import asyncio
                asyncio.create_task(self.nmminer_listener.start())
                
                print(f"📡 NMMiner UDP listener started for {len(nmminers)} devices")
        
        except Exception as e:
            print(f"❌ Failed to start NMMiner UDP listener: {e}")
    
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
        """Run VACUUM to optimize SQLite database"""
        from core.database import engine
        
        try:
            async with engine.begin() as conn:
                await conn.execute("VACUUM")
            
            print(f"✨ Database optimized (VACUUM completed)")
        
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
                            
                            if latest_telemetry and latest_telemetry.temperature and \
                               latest_telemetry.temperature > threshold:
                                alert_triggered = True
                                message = f"🌡️ <b>High Temperature Alert</b>\n\n{miner.name} temperature: {latest_telemetry.temperature:.1f}°C (threshold: {threshold}°C)"
                        
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
                        
                                        # Check health predictions for critical issues
                        elif alert_config.alert_type == "health_prediction":
                            from core.predictions import HealthPredictionService
                            
                            prediction = await HealthPredictionService.predict_hardware_issues(miner.id, db)
                            if prediction and prediction.risk_score >= 70:  # High risk threshold
                                # Find the most severe prediction
                                critical_predictions = [p for p in prediction.predictions if p['severity'] in ['high', 'critical']]
                                if critical_predictions:
                                    top_issue = critical_predictions[0]
                                    alert_triggered = True
                                    message = f"⚠️ <b>Hardware Health Alert</b>\n\n{miner.name}: {top_issue['issue']}\n\nRisk Score: {prediction.risk_score:.0f}/100\n{top_issue['details']}"
                        
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
        
        price_threshold = app_config.get("energy_optimization.price_threshold", 15.0)
        print(f"⚡ Price threshold: {price_threshold}p/kWh")
        
        try:
            async with AsyncSessionLocal() as db:
                # Get current price recommendation
                recommendation = await EnergyOptimizationService.should_mine_now(db, price_threshold)
                print(f"⚡ Recommendation: {recommendation}")
                
                if "error" in recommendation:
                    print(f"⚡ Auto-optimization skipped: {recommendation['error']}")
                    return
                
                should_mine = recommendation["should_mine"]
                current_price = recommendation["current_price_pence"]
                print(f"⚡ Should mine: {should_mine}, Current price: {current_price}p/kWh")
                
                # Get all enabled miners that support mode changes (not NMMiner)
                result = await db.execute(
                    select(Miner)
                    .where(Miner.enabled == True)
                    .where(Miner.miner_type != 'nmminer')
                )
                miners = result.scalars().all()
                print(f"⚡ Found {len(miners)} enabled miners (excluding NMMiner)")
                
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
                    
                    target_mode = mode_map[miner.miner_type]["high"] if should_mine else mode_map[miner.miner_type]["low"]
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
                                    print(f"⚡ Auto-optimized {miner.name}: {current_mode} → {target_mode} (price: {current_price}p/kWh)")
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
                
                action = "mining at full power" if should_mine else "power-saving mode"
                print(f"⚡ Auto-optimization complete: {action} (price: {current_price}p/kWh)")
        
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
            
            price_threshold = app_config.get("energy_optimization.price_threshold", 15.0)
            
            async with AsyncSessionLocal() as db:
                # Get current price recommendation
                recommendation = await EnergyOptimizationService.should_mine_now(db, price_threshold)
                
                if "error" in recommendation:
                    logger.debug(f"Energy optimization reconciliation skipped: {recommendation.get('error')}")
                    return
                
                should_mine = recommendation["should_mine"]
                current_price = recommendation["current_price_pence"]
                
                logger.info(f"⚡ Energy reconciliation check: price={current_price}p, threshold={price_threshold}p, should_mine={should_mine}")
                
                # Get all enabled miners that support mode changes
                result = await db.execute(
                    select(Miner)
                    .where(Miner.enabled == True)
                    .where(Miner.miner_type != 'nmminer')
                )
                miners = result.scalars().all()
                
                logger.info(f"⚡ Checking {len(miners)} miners for energy optimization state")
                
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
                    
                    expected_mode = mode_map[miner.miner_type]["high"] if should_mine else mode_map[miner.miner_type]["low"]
                    
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
                                f"but should be '{expected_mode}' (price: {current_price}p, threshold: {price_threshold}p)"
                            )
                            
                            # Apply correct mode
                            success = await adapter.set_mode(expected_mode)
                            
                            if success:
                                miner.current_mode = expected_mode
                                reconciled_count += 1
                                logger.info(f"✅ Reconciled {miner.name} to mode '{expected_mode}'")
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
                                print(f"❌ Failed to monitor pool {pool_name}: {e}")
                                break
                    
                    # Stagger requests to avoid overwhelming pools
                    await asyncio.sleep(2)
        
        except Exception as e:
            print(f"❌ Failed to monitor pool health: {e}")
            import traceback
            traceback.print_exc()
    
    async def _purge_old_pool_health(self):
        """Purge pool health data older than 30 days"""
        from core.database import AsyncSessionLocal, PoolHealth
        from sqlalchemy import delete
        
        try:
            async with AsyncSessionLocal() as db:
                cutoff = datetime.utcnow() - timedelta(days=30)
                result = await db.execute(
                    delete(PoolHealth).where(PoolHealth.timestamp < cutoff)
                )
                await db.commit()
                print(f"🗑️ Purged {result.rowcount} old pool health records")
        
        except Exception as e:
            print(f"❌ Failed to purge old pool health data: {e}")
    
    async def _purge_old_ckpool_blocks(self):
        """Purge non-accepted CKPool blocks older than 30 days (keep accepted blocks forever)"""
        from core.database import AsyncSessionLocal, CKPoolBlock
        from sqlalchemy import delete
        
        try:
            async with AsyncSessionLocal() as db:
                cutoff = datetime.utcnow() - timedelta(days=30)
                result = await db.execute(
                    delete(CKPoolBlock)
                    .where(CKPoolBlock.block_accepted == False)
                    .where(CKPoolBlock.timestamp < cutoff)
                )
                await db.commit()
                
                if result.rowcount > 0:
                    print(f"🗑️ Purged {result.rowcount} non-accepted CKPool blocks older than 30 days")
        
        except Exception as e:
            print(f"❌ Failed to purge old CKPool blocks: {e}")
    
    async def _purge_old_ckpool_metrics(self):
        """Purge CKPool metrics older than 12 months (rolling window for analytics)"""
        from core.database import AsyncSessionLocal, CKPoolBlockMetrics
        from sqlalchemy import delete
        
        try:
            async with AsyncSessionLocal() as db:
                cutoff = datetime.utcnow() - timedelta(days=365)
                result = await db.execute(
                    delete(CKPoolBlockMetrics).where(CKPoolBlockMetrics.timestamp < cutoff)
                )
                await db.commit()
                
                if result.rowcount > 0:
                    print(f"🗑️ Purged {result.rowcount} CKPool metrics older than 12 months")
        
        except Exception as e:
            print(f"❌ Failed to purge old CKPool metrics: {e}")
    
    async def _check_pool_failover(self):
        """Check if any miners need pool failover due to poor health"""
        from core.database import AsyncSessionLocal, Miner, Telemetry, Pool
        from core.pool_health import PoolHealthService
        from core.config import app_config
        from sqlalchemy import select
        
        # Check if auto-failover is enabled
        failover_enabled = app_config.get("pool_failover.enabled", True)
        if not failover_enabled:
            return
        
        try:
            async with AsyncSessionLocal() as db:
                # Get all enabled miners
                result = await db.execute(select(Miner).where(Miner.enabled == True))
                miners = result.scalars().all()
                
                for miner in miners:
                    # Skip NMMiner (handled differently)
                    if miner.miner_type == 'nmminer':
                        continue
                    
                    try:
                        # Get latest telemetry to determine current pool
                        result = await db.execute(
                            select(Telemetry)
                            .where(Telemetry.miner_id == miner.id)
                            .order_by(Telemetry.timestamp.desc())
                            .limit(1)
                        )
                        latest_telemetry = result.scalar_one_or_none()
                        
                        if not latest_telemetry or not latest_telemetry.pool_in_use:
                            continue
                        
                        # Find pool ID from pool_in_use string
                        result = await db.execute(select(Pool).where(Pool.enabled == True))
                        pools = result.scalars().all()
                        
                        current_pool = None
                        for pool in pools:
                            if pool.url in latest_telemetry.pool_in_use:
                                current_pool = pool
                                break
                        
                        if not current_pool:
                            continue
                        
                        # Check if failover should trigger
                        failover_check = await PoolHealthService.should_trigger_failover(
                            current_pool.id, db
                        )
                        
                        if failover_check["should_failover"]:
                            print(f"🔄 Failover triggered for {miner.name}: {failover_check['reason']}")
                            
                            # Find best alternative pool
                            best_pool = await PoolHealthService.find_best_failover_pool(
                                current_pool.id, miner.id, db
                            )
                            
                            if best_pool:
                                print(f"🔄 Switching {miner.name} to {best_pool['pool_name']} (health: {best_pool['health_score']}/100)")
                                
                                # Execute failover
                                result = await PoolHealthService.execute_failover(
                                    miner.id,
                                    best_pool["pool_id"],
                                    failover_check["reason"],
                                    db
                                )
                                
                                if result["success"]:
                                    print(f"✅ Failover successful: {miner.name} → {best_pool['pool_name']}")
                                else:
                                    print(f"❌ Failover failed for {miner.name}: {result.get('error')}")
                            else:
                                print(f"⚠️ No suitable failover pool found for {miner.name}")
                    
                    except Exception as e:
                        print(f"❌ Failed to check failover for {miner.name}: {e}")
                    
                    # Stagger requests to avoid overwhelming miners
                    await asyncio.sleep(2)
        
        except Exception as e:
            print(f"❌ Failed to check pool failover: {e}")
            import traceback
            traceback.print_exc()
    
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
    
    async def _create_supportxmr_snapshots(self):
        """Create hourly snapshots for all SupportXMR wallets"""
        try:
            from core.database import AsyncSessionLocal, Pool, SupportXMRSnapshot
            from core.supportxmr import SupportXMRService
            from core.config import app_config
            from datetime import datetime, timedelta
            from sqlalchemy import select
            
            # Check if SupportXMR is enabled
            if not app_config.get("supportxmr_enabled", False):
                return
            
            async with AsyncSessionLocal() as db:
                # Get all SupportXMR pools
                pool_result = await db.execute(select(Pool))
                all_pools = pool_result.scalars().all()
                
                supportxmr_pools = [p for p in all_pools if SupportXMRService.is_supportxmr_pool(p.url, p.port)]
                
                if not supportxmr_pools:
                    return
                
                # Process each unique wallet
                processed_addresses = set()
                snapshots_created = 0
                
                for pool in supportxmr_pools:
                    wallet_address = SupportXMRService.extract_address(pool.user)
                    
                    if not wallet_address or wallet_address in processed_addresses:
                        continue
                    
                    processed_addresses.add(wallet_address)
                    
                    # Check if snapshot already exists in last hour
                    recent_snapshot = await db.execute(
                        select(SupportXMRSnapshot)
                        .where(SupportXMRSnapshot.wallet_address == wallet_address)
                        .where(SupportXMRSnapshot.timestamp >= datetime.utcnow() - timedelta(hours=1))
                        .limit(1)
                    )
                    
                    if recent_snapshot.scalar_one_or_none():
                        continue  # Skip if snapshot already exists
                    
                    # Fetch data from SupportXMR API
                    stats_data = await SupportXMRService.get_miner_stats(wallet_address)
                    
                    if not stats_data:
                        logger.warning(f"Failed to fetch SupportXMR stats for ...{wallet_address[-8:]}")
                        continue
                    
                    # Create snapshot
                    current_amount_due_xmr = float(SupportXMRService.format_xmr(stats_data.get("amtDue", 0)))
                    current_amount_paid_xmr = float(SupportXMRService.format_xmr(stats_data.get("amtPaid", 0)))
                    
                    new_snapshot = SupportXMRSnapshot(
                        wallet_address=wallet_address,
                        amount_due=current_amount_due_xmr,
                        amount_paid=current_amount_paid_xmr,
                        hashrate=stats_data.get("hash", 0),
                        valid_shares=stats_data.get("validShares", 0),
                        invalid_shares=stats_data.get("invalidShares", 0),
                        timestamp=datetime.utcnow()
                    )
                    db.add(new_snapshot)
                    snapshots_created += 1
                    logger.info(f"Created SupportXMR snapshot for ...{wallet_address[-8:]}: {current_amount_due_xmr + current_amount_paid_xmr:.6f} XMR")
                
                if snapshots_created > 0:
                    await db.commit()
                    logger.info(f"✅ Created {snapshots_created} SupportXMR snapshot(s)")
        
        except Exception as e:
            logger.error(f"Failed to create SupportXMR snapshots: {e}")
            import traceback
            traceback.print_exc()
    
    async def _capture_ckpool_hashrate(self):
        """Capture CKPool hashrate snapshots every 5 minutes"""
        try:
            from core.database import AsyncSessionLocal, Pool, CKPoolHashrateSnapshot
            from core.ckpool import CKPoolService
            from sqlalchemy import select
            
            async with AsyncSessionLocal() as db:
                # Find all enabled CKPool pools
                result = await db.execute(
                    select(Pool)
                    .where(Pool.name.ilike('%ckpool%'))
                    .where(Pool.enabled == True)
                )
                pools = result.scalars().all()
                
                if not pools:
                    return
                
                snapshots_created = 0
                
                for pool in pools:
                    # Determine coin from pool name
                    pool_name_lower = pool.name.lower()
                    coin = "UNKNOWN"
                    if 'dgb' in pool_name_lower or 'digibyte' in pool_name_lower:
                        coin = "DGB"
                    elif 'bch' in pool_name_lower or 'bitcoin cash' in pool_name_lower:
                        coin = "BCH"
                    elif 'btc' in pool_name_lower or 'bitcoin' in pool_name_lower:
                        coin = "BTC"
                    
                    if coin == "UNKNOWN":
                        continue
                    
                    # Fetch current hashrate from CKPool API
                    raw_stats = await CKPoolService.get_pool_stats(pool.url)
                    if not raw_stats:
                        continue
                    
                    stats = CKPoolService.format_stats_summary(raw_stats)
                    
                    # Create snapshot
                    snapshot = CKPoolHashrateSnapshot(
                        pool_id=pool.id,
                        coin=coin,
                        timestamp=datetime.utcnow(),
                        hashrate_gh=stats["hashrate_5m_gh"],  # Use 5-minute average
                        workers=stats["workers"]
                    )
                    db.add(snapshot)
                    snapshots_created += 1
                
                if snapshots_created > 0:
                    await db.commit()
                    logger.debug(f"Captured {snapshots_created} CKPool hashrate snapshot(s)")
        
        except Exception as e:
            logger.error(f"Failed to capture CKPool hashrate: {e}")
    
    async def _purge_old_ckpool_hashrate(self):
        """Purge CKPool hashrate data older than 24 hours"""
        try:
            from core.database import AsyncSessionLocal
            from sqlalchemy import text
            
            async with AsyncSessionLocal() as db:
                result = await db.execute(text("""
                    DELETE FROM ckpool_hashrate_snapshots
                    WHERE timestamp < datetime('now', '-24 hours')
                """))
                await db.commit()
                
                deleted_count = result.rowcount
                if deleted_count > 0:
                    logger.info(f"Purged {deleted_count} CKPool hashrate snapshot(s) older than 24 hours")
        
        except Exception as e:
            logger.error(f"Failed to purge old CKPool hashrate data: {e}")
            import traceback
            traceback.print_exc()
    
    async def _detect_monero_blocks(self):
        """Detect new Monero solo mining blocks every 5 minutes"""
        logger.info("🟢 MONERO BLOCK DETECTION FUNCTION CALLED - TOP OF FUNCTION")
        try:
            logger.info("🔍 Monero solo block detection job started")
            from core.database import AsyncSessionLocal
            from core.monero_solo import MoneroSoloService
            
            async with AsyncSessionLocal() as db:
                service = MoneroSoloService(db)
                settings = await service.get_settings()
                
                if not settings:
                    logger.warning("Monero solo settings not found in database")
                    return
                    
                if not settings.enabled:
                    logger.debug("Monero solo mining disabled, skipping block detection")
                    return
                
                logger.info(f"Monero solo enabled, checking for blocks (pool_id={settings.pool_id})")
                
                # Detect new blocks and reset effort
                new_blocks = await service.detect_new_blocks()
                if new_blocks:
                    logger.info(f"Detected {len(new_blocks)} new Monero block(s)")
                else:
                    logger.info("No new Monero blocks detected")
        
        except Exception as e:
            logger.error(f"Failed to detect Monero blocks: {e}")
            import traceback
            traceback.print_exc()
    
    async def _capture_monero_solo_snapshots(self):
        """Capture Monero solo mining hashrate snapshots every 5 minutes"""
        try:
            from core.database import AsyncSessionLocal, MoneroSoloSettings
            from core.monero_solo import MoneroSoloService
            
            async with AsyncSessionLocal() as db:
                service = MoneroSoloService(db)
                settings = await service.get_settings()
                
                if not settings or not settings.enabled:
                    return
                
                # Store hashrate snapshot
                await service.store_hashrate_snapshot()
                logger.debug("Captured Monero solo mining hashrate snapshot")
        
        except Exception as e:
            logger.error(f"Failed to capture Monero solo mining snapshot: {e}")
            import traceback
            traceback.print_exc()
    
    async def _purge_old_monero_solo_snapshots(self):
        """Purge Monero solo mining snapshots older than 24 hours"""
        try:
            from core.database import AsyncSessionLocal
            from sqlalchemy import text
            
            async with AsyncSessionLocal() as db:
                result = await db.execute(text("""
                    DELETE FROM monero_hashrate_snapshots
                    WHERE timestamp < datetime('now', '-24 hours')
                """))
                await db.commit()
                
                deleted_count = result.rowcount
                if deleted_count > 0:
                    logger.debug(f"Purged {deleted_count} old Monero hashrate snapshots")
        
        except Exception as e:
            logger.error(f"Failed to purge old Monero snapshots: {e}")
            import traceback
            traceback.print_exc()
    
    async def _execute_agile_solo_strategy(self):
        """Execute Agile Solo Mining Strategy every 30 minutes"""
        try:
            logger.info("Executing Agile Solo Strategy")
            from core.database import AsyncSessionLocal
            from core.agile_solo_strategy import AgileSoloStrategy
            
            async with AsyncSessionLocal() as db:
                report = await AgileSoloStrategy.execute_strategy(db)
                
                if report.get("enabled"):
                    logger.info(f"Agile Solo Strategy executed: {report}")
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


scheduler = SchedulerService()

# Make scheduler accessible to adapters
from adapters import set_scheduler_service
set_scheduler_service(scheduler)
