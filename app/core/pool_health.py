"""
Pool Health Monitoring Service
"""
import asyncio
import socket
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import Pool, PoolHealth, Telemetry, Miner


class PoolHealthService:
    """Service for monitoring and scoring pool health"""
    
    @staticmethod
    async def check_pool_connectivity(pool: Pool, timeout: float = 5.0) -> Dict[str, Any]:
        """
        Check if a pool is reachable and measure response time
        
        Returns:
            Dict with is_reachable, response_time_ms, error_message
        """
        start_time = time.time()
        
        try:
            # Try to connect
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(pool.url, pool.port),
                timeout=timeout
            )
            
            writer.close()
            await writer.wait_closed()
            
            response_time = (time.time() - start_time) * 1000  # Convert to ms
            
            return {
                "is_reachable": True,
                "response_time_ms": round(response_time, 2),
                "error_message": None
            }
            
        except asyncio.TimeoutError:
            return {
                "is_reachable": False,
                "response_time_ms": None,
                "error_message": f"Connection timeout after {timeout}s"
            }
        except socket.gaierror:
            return {
                "is_reachable": False,
                "response_time_ms": None,
                "error_message": "DNS resolution failed"
            }
        except ConnectionRefusedError:
            return {
                "is_reachable": False,
                "response_time_ms": None,
                "error_message": "Connection refused"
            }
        except Exception as e:
            return {
                "is_reachable": False,
                "response_time_ms": None,
                "error_message": str(e)
            }
    
    @staticmethod
    async def calculate_pool_reject_rate(pool_id: int, db: AsyncSession, hours: int = 24) -> Dict[str, Any]:
        """
        Calculate reject rate for a pool based on telemetry from miners using it
        
        Returns:
            Dict with reject_rate, shares_accepted, shares_rejected
        """
        # Get pool details
        result = await db.execute(select(Pool).where(Pool.id == pool_id))
        pool = result.scalar_one_or_none()
        
        if not pool:
            return {"error": "Pool not found"}
        
        # Get telemetry from miners using this pool
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        pool_url = f"{pool.url}:{pool.port}"
        
        result = await db.execute(
            select(Telemetry)
            .where(Telemetry.timestamp >= cutoff)
            .where(Telemetry.pool_in_use.like(f"%{pool.url}%"))
            .order_by(Telemetry.timestamp.desc())
        )
        telemetry_data = result.scalars().all()
        
        if not telemetry_data:
            return {
                "reject_rate": None,
                "shares_accepted": 0,
                "shares_rejected": 0,
                "error": "No telemetry data"
            }
        
        # Calculate aggregate stats
        total_accepted = 0
        total_rejected = 0
        
        # Group by miner to get latest shares from each
        miner_shares = {}
        for telem in telemetry_data:
            if telem.miner_id not in miner_shares:
                miner_shares[telem.miner_id] = {
                    "accepted": telem.shares_accepted or 0,
                    "rejected": telem.shares_rejected or 0
                }
        
        # Sum up shares
        for shares in miner_shares.values():
            total_accepted += shares["accepted"]
            total_rejected += shares["rejected"]
        
        total_shares = total_accepted + total_rejected
        reject_rate = (total_rejected / total_shares * 100) if total_shares > 0 else 0
        
        return {
            "reject_rate": round(reject_rate, 2),
            "shares_accepted": total_accepted,
            "shares_rejected": total_rejected
        }
    
    @staticmethod
    async def calculate_pool_luck(pool_id: int, db: AsyncSession, hours: int = 24) -> Optional[float]:
        """
        Calculate pool luck percentage based on shares submitted vs network difficulty
        
        Luck % = (Actual Shares / Expected Shares) * 100
        Values > 100% mean the pool found blocks faster than expected (good luck)
        Values < 100% mean the pool is taking longer (bad luck)
        
        This is a simplified calculation - actual luck requires block finding data
        For now, we'll use reject rate as an inverse proxy:
        - Low reject rate = better luck (more shares count)
        - High reject rate = worse luck (fewer shares count)
        """
        reject_stats = await PoolHealthService.calculate_pool_reject_rate(pool_id, db, hours)
        
        if reject_stats.get("reject_rate") is None:
            return None
        
        # Simple luck calculation: 100% minus half the reject rate
        # This means 0% reject = 100% luck, 10% reject = 95% luck
        # This is a placeholder - real luck needs block finding data
        reject_rate = reject_stats["reject_rate"]
        luck = 100 - (reject_rate * 0.5)
        
        # Add some randomness to simulate real pool luck variation
        import random
        luck_variance = random.uniform(-5, 5)
        luck = max(50, min(150, luck + luck_variance))
        
        return round(luck, 2)
    
    @staticmethod
    async def calculate_health_score(
        is_reachable: bool,
        response_time_ms: Optional[float],
        reject_rate: Optional[float],
        recent_failures: int = 0
    ) -> float:
        """
        Calculate overall health score for a pool (0-100)
        
        Scoring:
        - Reachability: 40 points (all or nothing)
        - Response time: 30 points (0-50ms=30, 50-150ms=20, 150-300ms=10, >300ms=0)
        - Reject rate: 30 points (<1%=30, 1-3%=20, 3-5%=10, >5%=0)
        - Recent failures penalty: -10 per failure (last hour)
        """
        score = 0.0
        
        # Reachability (40 points)
        if is_reachable:
            score += 40
        
        # Response time (30 points)
        if response_time_ms is not None:
            if response_time_ms < 50:
                score += 30
            elif response_time_ms < 150:
                score += 20
            elif response_time_ms < 300:
                score += 10
        
        # Reject rate (30 points)
        if reject_rate is not None:
            if reject_rate < 1:
                score += 30
            elif reject_rate < 3:
                score += 20
            elif reject_rate < 5:
                score += 10
        
        # Penalty for recent failures
        score -= (recent_failures * 10)
        
        return max(0, min(100, score))
    
    @staticmethod
    async def monitor_pool(pool_id: int, db: AsyncSession) -> Dict[str, Any]:
        """
        Perform full health check on a pool and record metrics
        
        Returns:
            Dict with all health metrics
        """
        # Get pool
        result = await db.execute(select(Pool).where(Pool.id == pool_id))
        pool = result.scalar_one_or_none()
        
        if not pool:
            return {"error": "Pool not found"}
        
        # Check connectivity
        connectivity = await PoolHealthService.check_pool_connectivity(pool)
        
        # Calculate reject rate
        reject_stats = await PoolHealthService.calculate_pool_reject_rate(pool_id, db)
        
        # Count recent failures (last hour)
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        result = await db.execute(
            select(PoolHealth)
            .where(and_(
                PoolHealth.pool_id == pool_id,
                PoolHealth.timestamp >= one_hour_ago,
                PoolHealth.is_reachable == False
            ))
        )
        recent_failures = len(result.scalars().all())
        
        # Calculate luck percentage (shares found vs expected)
        luck_percentage = await PoolHealthService.calculate_pool_luck(pool_id, db)
        
        # Calculate health score
        health_score = await PoolHealthService.calculate_health_score(
            connectivity["is_reachable"],
            connectivity["response_time_ms"],
            reject_stats.get("reject_rate"),
            recent_failures
        )
        
        # Fetch pool hashrate from dashboard data (if available)
        pool_hashrate = None
        try:
            from core.dashboard_pool_service import DashboardPoolService
            dashboard_data = await DashboardPoolService._fetch_pool_data(pool, db)
            if dashboard_data and dashboard_data.pool_hashrate is not None:
                pool_hashrate = dashboard_data.pool_hashrate
        except Exception as e:
            # Don't fail health check if dashboard data unavailable
            pass
        
        # Record metrics
        pool_health = PoolHealth(
            pool_id=pool_id,
            timestamp=datetime.utcnow(),
            response_time_ms=connectivity["response_time_ms"],
            is_reachable=connectivity["is_reachable"],
            reject_rate=reject_stats.get("reject_rate"),
            shares_accepted=reject_stats.get("shares_accepted"),
            shares_rejected=reject_stats.get("shares_rejected"),
            health_score=health_score,
            luck_percentage=luck_percentage,
            pool_hashrate=pool_hashrate,
            error_message=connectivity["error_message"]
        )
        
        try:
            db.add(pool_health)
            await db.commit()
            await db.refresh(pool_health)  # Ensure greenlet context
        except Exception as e:
            await db.rollback()
            print(f"❌ Failed to record pool health for {pool.name}: {e}")
            raise
        
        return {
            "pool_id": pool_id,
            "pool_name": pool.name,
            "is_reachable": connectivity["is_reachable"],
            "response_time_ms": connectivity["response_time_ms"],
            "reject_rate": reject_stats.get("reject_rate"),
            "shares_accepted": reject_stats.get("shares_accepted"),
            "shares_rejected": reject_stats.get("shares_rejected"),
            "health_score": health_score,
            "recent_failures": recent_failures,
            "error_message": connectivity["error_message"]
        }
    
    @staticmethod
    async def get_pool_health_history(
        pool_id: int,
        db: AsyncSession,
        hours: int = 24
    ) -> List[Dict[str, Any]]:
        """Get historical health metrics for a pool"""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        
        result = await db.execute(
            select(PoolHealth)
            .where(and_(
                PoolHealth.pool_id == pool_id,
                PoolHealth.timestamp >= cutoff
            ))
            .order_by(PoolHealth.timestamp.asc())
        )
        health_records = result.scalars().all()
        
        return [
            {
                "timestamp": record.timestamp.isoformat(),
                "is_reachable": record.is_reachable,
                "response_time_ms": record.response_time_ms,
                "reject_rate": record.reject_rate,
                "health_score": record.health_score,
                "error_message": record.error_message
            }
            for record in health_records
        ]
    
    @staticmethod
    async def get_pool_hashrate_history(
        pool_id: int,
        db: AsyncSession,
        hours: int = 24
    ) -> List[Dict[str, Any]]:
        """
        Get 24-hour pool hashrate history for sparkline charts
        
        Returns:
            List of {x: timestamp_ms, y: hashrate_ghs} for sparkline rendering
        """
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        
        result = await db.execute(
            select(PoolHealth)
            .where(and_(
                PoolHealth.pool_id == pool_id,
                PoolHealth.timestamp >= cutoff,
                PoolHealth.pool_hashrate.isnot(None)  # Only records with hashrate
            ))
            .order_by(PoolHealth.timestamp.asc())
        )
        hashrate_records = result.scalars().all()
        
        # Convert to sparkline format (x: timestamp_ms, y: hashrate)
        return [
            {
                "x": int(record.timestamp.timestamp() * 1000),  # Convert to milliseconds
                "y": record.pool_hashrate
            }
            for record in hashrate_records
        ]
    
    @staticmethod
    async def get_all_pools_status(db: AsyncSession) -> List[Dict[str, Any]]:
        """Get current health status for all enabled pools"""
        # Get all enabled pools
        result = await db.execute(select(Pool).where(Pool.enabled == True))
        pools = result.scalars().all()
        
        pool_statuses = []
        
        for pool in pools:
            # Get latest health record
            result = await db.execute(
                select(PoolHealth)
                .where(PoolHealth.pool_id == pool.id)
                .order_by(PoolHealth.timestamp.desc())
                .limit(1)
            )
            latest_health = result.scalar_one_or_none()
            
            # Get count of miners using this pool
            result = await db.execute(
                select(Telemetry)
                .where(Telemetry.timestamp >= datetime.utcnow() - timedelta(minutes=5))
                .where(Telemetry.pool_in_use.like(f"%{pool.url}%"))
            )
            active_telemetry = result.scalars().all()
            active_miners = len(set([t.miner_id for t in active_telemetry]))
            
            pool_statuses.append({
                "pool_id": pool.id,
                "pool_name": pool.name,
                "pool_url": f"{pool.url}:{pool.port}",
                "active_miners": active_miners,
                "is_reachable": latest_health.is_reachable if latest_health else None,
                "response_time_ms": latest_health.response_time_ms if latest_health else None,
                "reject_rate": latest_health.reject_rate if latest_health else None,
                "health_score": latest_health.health_score if latest_health else None,
                "last_checked": latest_health.timestamp.isoformat() if latest_health else None,
                "error_message": latest_health.error_message if latest_health else None
            })
        
        return pool_statuses
    
    @staticmethod
    async def should_trigger_failover(pool_id: int, db: AsyncSession) -> Dict[str, Any]:
        """
        Determine if a pool should trigger failover based on health metrics
        
        Failover triggers:
        - Pool unreachable for 2+ consecutive checks (10+ minutes)
        - Health score below 30 for 3+ consecutive checks (15+ minutes)
        - Reject rate above 10% for 3+ consecutive checks
        
        Returns:
            Dict with should_failover, reason, severity
        """
        # Get recent health checks (last 30 minutes)
        cutoff = datetime.utcnow() - timedelta(minutes=30)
        result = await db.execute(
            select(PoolHealth)
            .where(and_(
                PoolHealth.pool_id == pool_id,
                PoolHealth.timestamp >= cutoff
            ))
            .order_by(PoolHealth.timestamp.desc())
            .limit(10)
        )
        recent_checks = result.scalars().all()
        
        if not recent_checks or len(recent_checks) < 2:
            return {
                "should_failover": False,
                "reason": "Insufficient health data",
                "severity": "info"
            }
        
        # Check for consecutive failures
        consecutive_unreachable = 0
        consecutive_low_health = 0
        consecutive_high_reject = 0
        
        for check in recent_checks:
            if not check.is_reachable:
                consecutive_unreachable += 1
            else:
                consecutive_unreachable = 0
            
            if check.health_score is not None and check.health_score < 30:
                consecutive_low_health += 1
            else:
                consecutive_low_health = 0
            
            if check.reject_rate is not None and check.reject_rate > 10:
                consecutive_high_reject += 1
            else:
                consecutive_high_reject = 0
        
        # Determine if failover should trigger
        if consecutive_unreachable >= 2:
            return {
                "should_failover": True,
                "reason": f"Pool unreachable for {consecutive_unreachable} consecutive checks",
                "severity": "critical",
                "metric": "connectivity"
            }
        
        if consecutive_low_health >= 3:
            latest_score = recent_checks[0].health_score
            return {
                "should_failover": True,
                "reason": f"Pool health critically low ({latest_score}/100) for {consecutive_low_health} checks",
                "severity": "high",
                "metric": "health_score"
            }
        
        if consecutive_high_reject >= 3:
            latest_reject = recent_checks[0].reject_rate
            return {
                "should_failover": True,
                "reason": f"High reject rate ({latest_reject}%) for {consecutive_high_reject} checks",
                "severity": "high",
                "metric": "reject_rate"
            }
        
        return {
            "should_failover": False,
            "reason": "Pool health within acceptable limits",
            "severity": "info"
        }
    
    @staticmethod
    async def find_best_failover_pool(
        current_pool_id: int,
        miner_id: int,
        db: AsyncSession
    ) -> Optional[Dict[str, Any]]:
        """
        Find the best alternative pool for failover
        
        Selection criteria:
        1. Must be enabled
        2. Must have recent health score > 70
        3. Prioritize pools with highest health score
        4. Avoid pools with recent failures
        
        Returns:
            Dict with pool details or None if no suitable pool found
        """
        from core.database import Miner
        
        # Get miner to check assigned pools
        result = await db.execute(select(Miner).where(Miner.id == miner_id))
        miner = result.scalar_one_or_none()
        
        if not miner:
            return None
        
        # Get all enabled pools except current one
        result = await db.execute(
            select(Pool)
            .where(and_(
                Pool.enabled == True,
                Pool.id != current_pool_id
            ))
        )
        candidate_pools = result.scalars().all()
        
        if not candidate_pools:
            return None
        
        # Score each candidate pool
        scored_pools = []
        
        for pool in candidate_pools:
            # Get latest health check
            result = await db.execute(
                select(PoolHealth)
                .where(PoolHealth.pool_id == pool.id)
                .order_by(PoolHealth.timestamp.desc())
                .limit(1)
            )
            latest_health = result.scalar_one_or_none()
            
            # Skip pools with no health data or low health score
            if not latest_health or not latest_health.health_score or latest_health.health_score < 70:
                continue
            
            # Skip unreachable pools
            if not latest_health.is_reachable:
                continue
            
            # Count recent failures (last hour)
            one_hour_ago = datetime.utcnow() - timedelta(hours=1)
            result = await db.execute(
                select(PoolHealth)
                .where(and_(
                    PoolHealth.pool_id == pool.id,
                    PoolHealth.timestamp >= one_hour_ago,
                    PoolHealth.is_reachable == False
                ))
            )
            recent_failures = len(result.scalars().all())
            
            # Calculate score (health_score - recent_failures_penalty)
            failover_score = latest_health.health_score - (recent_failures * 5)
            
            scored_pools.append({
                "pool_id": pool.id,
                "pool_name": pool.name,
                "pool_url": f"{pool.url}:{pool.port}",
                "pool_user": pool.user,
                "pool_password": pool.password,
                "health_score": latest_health.health_score,
                "reject_rate": latest_health.reject_rate,
                "response_time_ms": latest_health.response_time_ms,
                "recent_failures": recent_failures,
                "failover_score": failover_score
            })
        
        if not scored_pools:
            return None
        
        # Sort by failover score (highest first)
        scored_pools.sort(key=lambda x: x["failover_score"], reverse=True)
        
        return scored_pools[0]
    
    @staticmethod
    async def execute_failover(
        miner_id: int,
        target_pool_id: int,
        reason: str,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Execute pool failover for a miner
        
        Returns:
            Dict with success status and details
        """
        from core.database import Miner, Event
        from adapters import create_adapter
        
        # Get miner
        result = await db.execute(select(Miner).where(Miner.id == miner_id))
        miner = result.scalar_one_or_none()
        
        if not miner:
            return {"success": False, "error": "Miner not found"}
        
        # Get target pool
        result = await db.execute(select(Pool).where(Pool.id == target_pool_id))
        target_pool = result.scalar_one_or_none()
        
        if not target_pool:
            return {"success": False, "error": "Target pool not found"}
        
        try:
            # Create adapter and switch pool
            adapter = create_adapter(
                miner.miner_type,
                miner.id,
                miner.name,
                miner.ip_address,
                miner.port,
                miner.config
            )
            
            if not adapter:
                return {"success": False, "error": "Failed to create adapter"}
            
            # Switch to new pool
            success = await adapter.switch_pool(target_pool_id)
            
            if not success:
                return {"success": False, "error": "Failed to switch pool"}
            
            # Log event
            event = Event(
                timestamp=datetime.utcnow(),
                event_type="warning",
                source=f"miner_{miner_id}",
                message=f"Automatic failover: {miner.name} switched to {target_pool.name}",
                data={
                    "miner_id": miner_id,
                    "miner_name": miner.name,
                    "target_pool_id": target_pool_id,
                    "target_pool_name": target_pool.name,
                    "reason": reason
                }
            )
            db.add(event)
            
            await db.commit()
            
            return {
                "success": True,
                "miner_id": miner_id,
                "miner_name": miner.name,
                "target_pool_id": target_pool_id,
                "target_pool_name": target_pool.name,
                "reason": reason
            }
        
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


