"""
Pool strategy service - manages round-robin and load balancing
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import Pool, PoolStrategy, PoolStrategyLog, PoolHealth, Miner
import random

logger = logging.getLogger(__name__)


class PoolStrategyService:
    """Manages pool switching strategies"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_active_strategies(self) -> List[PoolStrategy]:
        """Get all currently active strategies"""
        result = await self.db.execute(
            select(PoolStrategy).where(PoolStrategy.enabled == True).order_by(PoolStrategy.id)
        )
        return result.scalars().all()
    
    async def execute_round_robin(self, strategy: PoolStrategy, force: bool = False) -> Dict:
        """
        Execute round-robin strategy - switches pools in order at regular intervals
        
        Config options:
        - interval_minutes: How often to switch (default: 60)
        
        Args:
            force: If True, bypass interval check and execute immediately
        """
        config = strategy.config or {}
        interval_minutes = config.get("interval_minutes", 60)
        
        # Check if it's time to switch (skip check if forced)
        if not force and strategy.last_switch:
            time_since_switch = datetime.utcnow() - strategy.last_switch
            if time_since_switch < timedelta(minutes=interval_minutes):
                logger.debug(f"Round-robin not due yet. Last switch: {strategy.last_switch}")
                return {"switched": False, "reason": "interval_not_reached"}
        
        # Get pools in the strategy
        result = await self.db.execute(
            select(Pool).where(
                and_(
                    Pool.id.in_(strategy.pool_ids),
                    Pool.enabled == True
                )
            ).order_by(Pool.id)
        )
        pools = result.scalars().all()
        
        if not pools:
            logger.warning(f"No enabled pools in strategy {strategy.id}")
            return {"switched": False, "reason": "no_enabled_pools"}
        
        # Get current pool
        current_index = strategy.current_pool_index
        current_pool_id = strategy.pool_ids[current_index] if current_index < len(strategy.pool_ids) else None
        
        # Move to next pool
        next_index = (current_index + 1) % len(strategy.pool_ids)
        next_pool_id = strategy.pool_ids[next_index]
        
        # Verify next pool is enabled
        next_pool = next((p for p in pools if p.id == next_pool_id), None)
        if not next_pool:
            logger.warning(f"Next pool {next_pool_id} not found or disabled, skipping")
            return {"switched": False, "reason": "next_pool_unavailable"}
        
        # Apply to assigned miners
        switch_result = await self._switch_miners_to_pool(next_pool_id, strategy.miner_ids)
        miners_affected = switch_result["success_count"]
        failed_miners = switch_result.get("failed_miners", [])
        
        # If some miners failed, log details
        if failed_miners:
            logger.warning(
                f"⚠️ Round-robin: {len(failed_miners)} miners failed to switch to pool {next_pool.name}: "
                f"{', '.join([m['name'] for m in failed_miners])}"
            )
        
        # Update strategy state only if at least one miner switched successfully
        if miners_affected > 0:
            strategy.current_pool_index = next_index
            strategy.last_switch = datetime.utcnow()
            await self.db.commit()
            
            # Log the switch
            reason = f"Round-robin rotation (interval: {interval_minutes}m)"
            if failed_miners:
                reason += f" - {len(failed_miners)} miners failed to switch"
            
            await self._log_strategy_switch(
                strategy.id,
                current_pool_id,
                next_pool_id,
                reason,
                miners_affected
            )
            
            logger.info(
                f"Round-robin switched from pool {current_pool_id} to {next_pool_id}, "
                f"{miners_affected} miners affected, {len(failed_miners)} failed"
            )
        else:
            logger.error(f"Round-robin: ALL miners failed to switch to pool {next_pool.name}. Strategy state not updated.")
            return {"switched": False, "reason": "all_miners_failed", "failed_miners": failed_miners}
        
        return {
            "switched": True,
            "from_pool_id": current_pool_id,
            "to_pool_id": next_pool_id,
            "miners_affected": miners_affected,
            "next_switch_eta": interval_minutes
        }
    
    async def execute_load_balance(self, strategy: PoolStrategy, force: bool = False) -> Dict:
        """
        Execute load balancing strategy - distributes miners across pools based on health
        
        Config options:
        - rebalance_interval_minutes: How often to rebalance (default: 30)
        - health_weight: Weight of health score (default: 0.4)
        - latency_weight: Weight of latency (default: 0.3)
        - reject_weight: Weight of reject rate (default: 0.3)
        - min_health_threshold: Minimum health to consider pool (default: 50)
        
        Args:
            force: If True, bypass interval check and execute immediately
        """
        config = strategy.config or {}
        rebalance_interval = config.get("rebalance_interval_minutes", 30)
        health_weight = config.get("health_weight", 0.4)
        latency_weight = config.get("latency_weight", 0.3)
        reject_weight = config.get("reject_weight", 0.3)
        min_health_threshold = config.get("min_health_threshold", 50)
        
        # Check if it's time to rebalance
        if strategy.last_switch:
            time_since_switch = datetime.utcnow() - strategy.last_switch
            if time_since_switch < timedelta(minutes=rebalance_interval):
                logger.debug(f"Load balance not due yet. Last switch: {strategy.last_switch}")
                return {"rebalanced": False, "reason": "interval_not_reached"}
        
        # Get pools in the strategy
        result = await self.db.execute(
            select(Pool).where(
                and_(
                    Pool.id.in_(strategy.pool_ids),
                    Pool.enabled == True
                )
            )
        )
        pools = list(result.scalars().all())
        
        if not pools:
            logger.warning(f"No enabled pools in strategy {strategy.id}")
            return {"rebalanced": False, "reason": "no_enabled_pools"}
        
        # Get latest health data for each pool
        pool_scores = {}
        for pool in pools:
            health_result = await self.db.execute(
                select(PoolHealth)
                .where(PoolHealth.pool_id == pool.id)
                .order_by(PoolHealth.timestamp.desc())
                .limit(10)
            )
            health_records = health_result.scalars().all()
            
            if not health_records:
                # No health data, use default low score
                pool_scores[pool.id] = 25.0
                continue
            
            # Calculate average metrics
            avg_health = sum(h.health_score or 0 for h in health_records) / len(health_records)
            avg_latency = sum(h.response_time_ms or 1000 for h in health_records) / len(health_records)
            avg_reject = sum(h.reject_rate or 0 for h in health_records) / len(health_records)
            
            # Skip pools below minimum health
            if avg_health < min_health_threshold:
                logger.info(f"Pool {pool.id} ({pool.name}) below minimum health threshold: {avg_health:.1f}")
                continue
            
            # Calculate composite score (higher is better)
            # Normalize latency (lower is better, so invert)
            latency_score = max(0, 100 - (avg_latency / 10))  # 0-1000ms -> 0-100
            reject_score = max(0, 100 - (avg_reject * 10))  # 0-10% -> 100-0
            
            composite_score = (
                (avg_health * health_weight) +
                (latency_score * latency_weight) +
                (reject_score * reject_weight)
            )
            
            # Add priority bonus (configured weight)
            priority_bonus = pool.priority * 2  # Each priority point = +2 to score
            composite_score += priority_bonus
            
            pool_scores[pool.id] = composite_score
            logger.debug(f"Pool {pool.id} ({pool.name}): score={composite_score:.1f}, health={avg_health:.1f}, latency={avg_latency:.0f}ms, reject={avg_reject:.2f}%")
        
        if not pool_scores:
            logger.warning("No pools with sufficient health for load balancing")
            return {"rebalanced": False, "reason": "no_healthy_pools"}
        
        # Get miners - either specific ones or all enabled
        if strategy.miner_ids:
            result = await self.db.execute(
                select(Miner).where(
                    and_(
                        Miner.id.in_(strategy.miner_ids),
                        Miner.enabled == True
                    )
                )
            )
        else:
            result = await self.db.execute(
                select(Miner).where(Miner.enabled == True)
            )
        miners = list(result.scalars().all())
        
        if not miners:
            logger.info("No enabled miners to balance")
            return {"rebalanced": False, "reason": "no_miners"}
        
        # Distribute miners proportionally to pool scores
        total_score = sum(pool_scores.values())
        pool_allocations = {
            pool_id: int((score / total_score) * len(miners))
            for pool_id, score in pool_scores.items()
        }
        
        # Ensure all miners are allocated (handle rounding)
        allocated = sum(pool_allocations.values())
        if allocated < len(miners):
            # Allocate remaining to highest scoring pool
            best_pool = max(pool_scores, key=pool_scores.get)
            pool_allocations[best_pool] += len(miners) - allocated
        
        # Apply allocations
        miners_switched = 0
        assignment_index = 0
        
        # Create assignment list with pools repeated by allocation count
        assignments = []
        for pool_id, count in pool_allocations.items():
            assignments.extend([pool_id] * count)
        
        # Shuffle to distribute evenly
        random.shuffle(assignments)
        
        failed_miners = []
        
        for miner in miners:
            if assignment_index >= len(assignments):
                break
            
            target_pool_id = assignments[assignment_index]
            assignment_index += 1
            
            # Get the target pool
            target_pool = next((p for p in pools if p.id == target_pool_id), None)
            if not target_pool:
                logger.warning(f"Load balance: target pool {target_pool_id} not found")
                failed_miners.append({"id": miner.id, "name": miner.name, "reason": "pool_not_found"})
                continue
            
            # Switch miner to assigned pool
            try:
                from adapters import get_adapter
                
                adapter = get_adapter(miner)
                if not adapter:
                    logger.warning(f"No adapter found for miner {miner.id} ({miner.name})")
                    failed_miners.append({"id": miner.id, "name": miner.name, "reason": "no_adapter"})
                    continue
                
                # Device-specific pool switching
                if miner.miner_type == "avalon_nano":
                    logger.info(f"🔄 Load balance - Avalon Nano {miner.name}: Attempting slot switch to {target_pool.name}")
                    success = await adapter.switch_pool(target_pool.url, target_pool.port, target_pool.user, target_pool.password)
                    
                    if success:
                        logger.info(f"✓ Load balance - Switched Avalon Nano {miner.id} ({miner.name}) to {target_pool.name}")
                        miners_switched += 1
                    else:
                        logger.warning(f"✗ Load balance - Avalon Nano {miner.id} ({miner.name}) could not switch to {target_pool.name}")
                        failed_miners.append({"id": miner.id, "name": miner.name, "reason": "pool_not_in_slots"})
                else:
                    logger.info(f"🔄 Load balance - {miner.miner_type} {miner.name}: Assigning pool {target_pool.name}")
                    success = await adapter.switch_pool(target_pool.url, target_pool.port, target_pool.user, target_pool.password)
                    
                    if success:
                        logger.info(f"✓ Load balance - Switched {miner.miner_type} {miner.id} ({miner.name}) to {target_pool.name}")
                        miners_switched += 1
                    else:
                        logger.warning(f"✗ Load balance - Failed to switch {miner.miner_type} {miner.id} ({miner.name}) to {target_pool.name}")
                        failed_miners.append({"id": miner.id, "name": miner.name, "reason": "switch_failed"})
                        
            except Exception as e:
                logger.error(f"Load balance - Error switching miner {miner.id} ({miner.name}): {e}")
                failed_miners.append({"id": miner.id, "name": miner.name, "reason": f"exception: {str(e)}"})
                continue
        
        # Only update strategy state if at least one miner succeeded
        if miners_switched > 0:
            # Update strategy state
            strategy.last_switch = datetime.utcnow()
            await self.db.commit()
            
            # Log the rebalance
            await self._log_strategy_switch(
                strategy.id,
                None,
                None,
                f"Load balance rebalance (interval: {rebalance_interval}m, pools: {len(pool_scores)})",
                miners_switched
            )
            
            if failed_miners:
                failed_list = ', '.join([f"{m['name']} ({m['reason']})" for m in failed_miners])
                logger.warning(
                    f"Load balance completed with {len(failed_miners)} failures: {miners_switched} miners distributed across {len(pool_scores)} pools. "
                    f"Failed miners: {failed_list}"
                )
            else:
                logger.info(f"Load balance completed: {miners_switched} miners distributed across {len(pool_scores)} pools")
        else:
            logger.error(f"Load balance: ALL miners failed to switch. Strategy state not updated.")
            return {"rebalanced": False, "reason": "all_miners_failed", "failed_miners": failed_miners}
        
        return {
            "rebalanced": True,
            "pools_used": len(pool_scores),
            "miners_affected": miners_switched,
            "failed_miners": failed_miners,
            "pool_allocations": pool_allocations,
            "next_rebalance_eta": rebalance_interval
        }
    
    async def _switch_miners_to_pool(self, pool_id: int, miner_ids: List[int] = None) -> int:
        """
        Switch miners to the specified pool with device-specific logic
        
        Args:
            pool_id: Pool to switch to
            miner_ids: List of specific miner IDs, or None/empty list for all miners
        """
        # Get the pool details
        result = await self.db.execute(
            select(Pool).where(Pool.id == pool_id)
        )
        pool = result.scalar_one_or_none()
        
        if not pool:
            logger.error(f"Pool {pool_id} not found")
            return 0
        
        # Get miners - either specific ones or all enabled
        # Empty list means all miners (unassigned), None also means all miners
        if miner_ids and len(miner_ids) > 0:
            logger.info(f"Switching specific miners {miner_ids} to pool {pool_id} ({pool.name})")
            result = await self.db.execute(
                select(Miner).where(
                    and_(
                        Miner.id.in_(miner_ids),
                        Miner.enabled == True
                    )
                )
            )
        else:
            logger.info(f"Switching all enabled miners to pool {pool_id} ({pool.name})")
            result = await self.db.execute(
                select(Miner).where(Miner.enabled == True)
            )
        miners = result.scalars().all()
        
        if not miners:
            logger.warning(f"No miners found to switch (miner_ids={miner_ids})")
            return 0
        
        logger.info(f"Found {len(miners)} miners to switch: {[m.name for m in miners]}")
        
        # Check if we need to verify Avalon Nano pool availability
        avalon_miners = [m for m in miners if m.miner_type == "avalon_nano"]
        if avalon_miners:
            # For Avalon Nano miners, verify the pool exists in their slots
            from core.database import MinerPoolSlot
            for avalon_miner in avalon_miners:
                slot_result = await self.db.execute(
                    select(MinerPoolSlot).where(
                        and_(
                            MinerPoolSlot.miner_id == avalon_miner.id,
                            MinerPoolSlot.pool_id == pool_id
                        )
                    )
                )
                slot = slot_result.scalar_one_or_none()
                
                if not slot:
                    logger.warning(
                        f"⚠️ Avalon Nano miner {avalon_miner.id} ({avalon_miner.name}) does not have "
                        f"pool {pool.name} in its 3 configured slots. Pool switch will fail for this miner."
                    )
        
        # Actually switch miners to the pool
        count = 0
        failed_miners = []
        
        for miner in miners:
            try:
                # Import adapters
                from adapters import get_adapter
                
                adapter = get_adapter(miner)
                if not adapter:
                    logger.warning(f"No adapter found for miner {miner.id} ({miner.name})")
                    failed_miners.append({"id": miner.id, "name": miner.name, "reason": "no_adapter"})
                    continue
                
                # Device-specific pool switching
                if miner.miner_type == "avalon_nano":
                    # Avalon Nano: Can only switch between its 3 configured slots
                    # The adapter will check if the pool exists and switch to that slot
                    logger.info(f"🔄 Avalon Nano {miner.name}: Attempting slot switch to {pool.name}")
                    success = await adapter.switch_pool(pool.url, pool.port, pool.user, pool.password)
                    
                    if success:
                        logger.info(f"✓ Switched Avalon Nano {miner.id} ({miner.name}) to pool slot with {pool.name}")
                        count += 1
                    else:
                        logger.warning(
                            f"✗ Avalon Nano {miner.id} ({miner.name}) could not switch to {pool.name}. "
                            f"Pool may not exist in miner's 3 configured slots."
                        )
                        failed_miners.append({"id": miner.id, "name": miner.name, "reason": "pool_not_in_slots"})
                else:
                    # Bitaxe/NerdQaxe: Can use any pool via direct assignment
                    logger.info(f"🔄 {miner.miner_type} {miner.name}: Assigning pool {pool.name}")
                    success = await adapter.switch_pool(pool.url, pool.port, pool.user, pool.password)
                    
                    if success:
                        logger.info(f"✓ Switched {miner.miner_type} {miner.id} ({miner.name}) to pool {pool.name}")
                        count += 1
                    else:
                        logger.warning(f"✗ Failed to switch {miner.miner_type} {miner.id} ({miner.name}) to pool {pool.name}")
                        failed_miners.append({"id": miner.id, "name": miner.name, "reason": "switch_failed"})
                    
            except Exception as e:
                logger.error(f"Error switching miner {miner.id} ({miner.name}): {e}")
                failed_miners.append({"id": miner.id, "name": miner.name, "reason": f"exception: {str(e)}"})
                continue
        
        return {
            "success_count": count,
            "failed_miners": failed_miners,
            "total_miners": len(miners)
        }
    
    async def _log_strategy_switch(
        self,
        strategy_id: int,
        from_pool_id: Optional[int],
        to_pool_id: Optional[int],
        reason: str,
        miners_affected: int
    ):
        """Log a strategy switch event"""
        log_entry = PoolStrategyLog(
            strategy_id=strategy_id,
            from_pool_id=from_pool_id,
            to_pool_id=to_pool_id,
            reason=reason,
            miners_affected=miners_affected,
            timestamp=datetime.utcnow()
        )
        self.db.add(log_entry)
        await self.db.commit()


async def execute_active_strategies(db: AsyncSession) -> List[Dict]:
    """Execute all currently active pool strategies"""
    service = PoolStrategyService(db)
    strategies = await service.get_active_strategies()
    
    if not strategies:
        logger.debug("No active pool strategies")
        return []
    
    results = []
    for strategy in strategies:
        try:
            if strategy.strategy_type == "round_robin":
                result = await service.execute_round_robin(strategy)
            elif strategy.strategy_type == "load_balance":
                result = await service.execute_load_balance(strategy)
            else:
                logger.warning(f"Unknown strategy type: {strategy.strategy_type}")
                continue
            
            if result:
                result["strategy_name"] = strategy.name
                results.append(result)
        except Exception as e:
            logger.error(f"Failed to execute strategy {strategy.name}: {e}")
            continue
    
    return results


async def reconcile_strategy_miners(db: AsyncSession):
    """
    Reconciliation process - detect and fix miners out of sync with their strategy
    Runs every 5 minutes to handle transient failures (miners restarting, updating, etc)
    """
    service = PoolStrategyService(db)
    strategies = await service.get_active_strategies()
    
    if not strategies:
        logger.debug("No active strategies for reconciliation")
        return []
    
    reconciliation_results = []
    
    for strategy in strategies:
        try:
            # Determine expected pool for this strategy
            expected_pool_id = None
            
            if strategy.strategy_type == "round_robin":
                # Get current pool from rotation
                if not strategy.pool_ids:
                    continue
                current_index = strategy.current_pool_index or 0
                if current_index >= len(strategy.pool_ids):
                    current_index = 0
                expected_pool_id = strategy.pool_ids[current_index]
            elif strategy.strategy_type == "load_balance":
                # Load balance doesn't have a single expected pool - skip reconciliation
                logger.debug(f"Skipping reconciliation for load_balance strategy {strategy.name}")
                continue
            else:
                logger.warning(f"Unknown strategy type for reconciliation: {strategy.strategy_type}")
                continue
            
            if not expected_pool_id:
                continue
            
            # Get expected pool details
            result = await db.execute(
                select(Pool).where(Pool.id == expected_pool_id)
            )
            expected_pool = result.scalar_one_or_none()
            if not expected_pool:
                logger.warning(f"Expected pool {expected_pool_id} not found for strategy {strategy.name}")
                continue
            
            # Get miners in this strategy
            if strategy.miner_ids:
                result = await db.execute(
                    select(Miner).where(
                        and_(
                            Miner.id.in_(strategy.miner_ids),
                            Miner.enabled == True
                        )
                    )
                )
            else:
                result = await db.execute(
                    select(Miner).where(Miner.enabled == True)
                )
            miners = list(result.scalars().all())
            
            if not miners:
                continue
            
            # Check each miner and reconcile if out of sync
            out_of_sync = []
            reconciled = []
            failed_reconciliation = []
            
            for miner in miners:
                try:
                    from adapters import get_adapter
                    
                    adapter = get_adapter(miner)
                    if not adapter:
                        logger.warning(f"No adapter for miner {miner.id} ({miner.name}) - skipping reconciliation")
                        continue
                    
                    # Get current pool from miner
                    current_pool_url = None
                    
                    if miner.miner_type == "avalon_nano":
                        # For Avalon, check current active pool slot
                        from adapters.avalon_nano import AvalonNanoAdapter
                        if isinstance(adapter, AvalonNanoAdapter):
                            # Get pool info from cgminer
                            pools_info = await adapter._get_pools()
                            if pools_info:
                                # Find the active pool (priority 0)
                                for pool_data in pools_info:
                                    if pool_data.get("Priority") == 0:
                                        current_pool_url = pool_data.get("URL", "")
                                        break
                    else:
                        # For Bitaxe/NerdQaxe, get current pool from status
                        telemetry = await adapter.get_telemetry()
                        if telemetry and "pool_url" in telemetry:
                            current_pool_url = telemetry["pool_url"]
                    
                    if not current_pool_url:
                        logger.debug(f"Could not determine current pool for miner {miner.name}")
                        continue
                    
                    # Check if current pool matches expected pool
                    # Compare by URL (some miners include port, some don't)
                    expected_pool_url = f"{expected_pool.url}"
                    if expected_pool.port and expected_pool.port not in [80, 443]:
                        expected_pool_url = f"{expected_pool.url}:{expected_pool.port}"
                    
                    # Normalize URLs for comparison (remove protocol, trailing slashes)
                    def normalize_url(url: str) -> str:
                        url = url.replace("stratum+tcp://", "").replace("http://", "").replace("https://", "")
                        url = url.rstrip("/")
                        return url.lower()
                    
                    if normalize_url(current_pool_url) != normalize_url(expected_pool_url):
                        out_of_sync.append({
                            "miner_id": miner.id,
                            "miner_name": miner.name,
                            "current_pool": current_pool_url,
                            "expected_pool": expected_pool_url
                        })
                        
                        # Attempt to reconcile
                        logger.info(f"🔄 Reconciling {miner.name}: switching from {current_pool_url} to {expected_pool.name}")
                        
                        if miner.miner_type == "avalon_nano":
                            success = await adapter.switch_pool(expected_pool.url, expected_pool.port, expected_pool.user, expected_pool.password)
                        else:
                            success = await adapter.switch_pool(expected_pool.url, expected_pool.port, expected_pool.user, expected_pool.password)
                        
                        if success:
                            logger.info(f"✓ Reconciled {miner.name} to {expected_pool.name}")
                            reconciled.append(miner.name)
                        else:
                            logger.warning(f"✗ Failed to reconcile {miner.name}")
                            failed_reconciliation.append(miner.name)
                
                except Exception as e:
                    logger.error(f"Error checking miner {miner.name} for reconciliation: {e}")
                    continue
            
            if out_of_sync:
                reconciliation_results.append({
                    "strategy_name": strategy.name,
                    "expected_pool": expected_pool.name,
                    "out_of_sync_count": len(out_of_sync),
                    "reconciled_count": len(reconciled),
                    "failed_count": len(failed_reconciliation),
                    "out_of_sync": out_of_sync,
                    "reconciled": reconciled,
                    "failed": failed_reconciliation
                })
                
                logger.info(
                    f"Reconciliation for strategy '{strategy.name}': "
                    f"{len(out_of_sync)} out of sync, "
                    f"{len(reconciled)} reconciled, "
                    f"{len(failed_reconciliation)} failed"
                )
        
        except Exception as e:
            logger.error(f"Error reconciling strategy {strategy.name}: {e}")
            continue
    
    return reconciliation_results
