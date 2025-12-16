"""
APScheduler for periodic tasks
"""
import logging
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
            self._monitor_pool_health,
            IntervalTrigger(minutes=5),
            id="monitor_pool_health",
            name="Monitor pool health and connectivity"
        )
        
        self.scheduler.add_job(
            self._execute_pool_strategies,
            IntervalTrigger(minutes=1),
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
            self._check_pool_failover,
            IntervalTrigger(minutes=5),
            id="check_pool_failover",
            name="Check for pool failover conditions"
        )
        
        # Start NMMiner UDP listener
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
        from core.database import AsyncSessionLocal, Miner, Telemetry, Event
        from core.mqtt import mqtt_client
        from adapters import create_adapter
        
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
                            db_telemetry = Telemetry(
                                miner_id=miner.id,
                                timestamp=telemetry.timestamp,
                                hashrate=telemetry.hashrate,
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
                
                # Create adapter registry
                adapters = {}
                for miner in nmminers:
                    adapter = NMMinerAdapter(miner.id, miner.name, miner.ip_address, miner.port, miner.config)
                    adapters[miner.ip_address] = adapter
                
                # Start UDP listener
                self.nmminer_listener = NMMinerUDPListener(adapters)
                
                # Run in background (non-blocking)
                import asyncio
                asyncio.create_task(self.nmminer_listener.start())
                
                print(f"📡 NMMiner UDP listener started for {len(nmminers)} devices")
        
        except Exception as e:
            print(f"❌ Failed to start NMMiner UDP listener: {e}")
    
    async def _purge_old_telemetry(self):
        """Purge telemetry data older than 48 hours"""
        from core.database import AsyncSessionLocal, Telemetry
        from sqlalchemy import delete
        
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=48)
            
            async with AsyncSessionLocal() as db:
                # Delete old telemetry records
                result = await db.execute(
                    delete(Telemetry)
                    .where(Telemetry.timestamp < cutoff_time)
                )
                await db.commit()
                
                deleted_count = result.rowcount
                if deleted_count > 0:
                    print(f"🗑️ Purged {deleted_count} telemetry records older than 48 hours")
        
        except Exception as e:
            print(f"❌ Failed to purge old telemetry: {e}")
    
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
                            # Avalon Nano can reach 90°C safely
                            default_threshold = 90 if 'avalon' in miner.type.lower() else 75
                            threshold = alert_config.config.get("threshold_celsius", default_threshold)
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
                    "bitaxe": {"low": "eco", "high": "turbo"},
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
                    try:
                        await PoolHealthService.monitor_pool(pool.id, db)
                        print(f"🌊 Pool health check completed: {pool.name}")
                    except Exception as e:
                        print(f"❌ Failed to monitor pool {pool.name}: {e}")
        
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
        
        except Exception as e:
            print(f"❌ Failed to check pool failover: {e}")
            import traceback
            traceback.print_exc()
    
    async def _execute_pool_strategies(self):
        """Execute active pool strategies"""
        try:
            from core.database import AsyncSessionLocal
            from core.pool_strategy import execute_active_strategy
            
            async with AsyncSessionLocal() as db:
                result = await execute_active_strategy(db)
                
                if result:
                    logger.info(f"Pool strategy executed: {result}")
        
        except Exception as e:
            logger.error(f"Failed to execute pool strategies: {e}")
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


scheduler = SchedulerService()
