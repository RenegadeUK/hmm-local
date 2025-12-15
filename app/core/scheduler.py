"""
APScheduler for periodic tasks
"""
import aiohttp
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta
from sqlalchemy import select
from typing import Optional


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
        from core.database import AsyncSessionLocal, Miner, Telemetry, AlertConfig
        from core.notifications import send_alert
        
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
                            threshold = alert_config.config.get("threshold_celsius", 75)
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
                        
                        # Send notification if alert triggered
                        if alert_triggered:
                            await send_alert(message, alert_config.alert_type)
                            print(f"🔔 Alert sent: {alert_config.alert_type} for {miner.name}")
        
        except Exception as e:
            print(f"❌ Failed to check alerts: {e}")
            import traceback
            traceback.print_exc()


scheduler = SchedulerService()
