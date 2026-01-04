"""
Monero Solo Mining Service
Core logic for tracking solo mining effort, detecting blocks, and aggregating stats
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import (
    MoneroSoloSettings, MoneroSoloEffort, MoneroBlock,
    MoneroWalletTransaction, MoneroHashrateSnapshot, Miner, Pool
)
from core.monero_node import MoneroNodeRPC
from core.monero_wallet import MoneroWalletRPC, ATOMIC_UNITS_PER_XMR
from adapters.xmrig import XMRigAdapter

logger = logging.getLogger(__name__)


class MoneroSoloService:
    """Service for managing Monero solo mining operations"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        
    async def get_settings(self) -> Optional[MoneroSoloSettings]:
        """Get Monero solo mining settings"""
        result = await self.db.execute(select(MoneroSoloSettings).limit(1))
        return result.scalar_one_or_none()
        
    async def get_or_create_settings(self) -> MoneroSoloSettings:
        """Get settings or create default"""
        settings = await self.get_settings()
        
        if not settings:
            settings = MoneroSoloSettings(enabled=False)
            self.db.add(settings)
            await self.db.commit()
            await self.db.refresh(settings)
            
        return settings
        
    async def get_node_rpc(self, pool: Pool) -> Optional[MoneroNodeRPC]:
        """
        Create node RPC client from pool configuration
        
        Args:
            pool: Pool model with node connection info
            
        Returns:
            MoneroNodeRPC instance or None if invalid
        """
        if not pool:
            return None
            
        return MoneroNodeRPC(
            host=pool.url,
            port=pool.port,
            username=pool.user if pool.user else None,
            password=pool.password if pool.password else None
        )
        
    async def get_wallet_rpc(self) -> Optional[MoneroWalletRPC]:
        """
        Create wallet RPC client from settings
        
        Returns:
            MoneroWalletRPC instance or None if not configured
        """
        settings = await self.get_settings()
        
        if not settings or not settings.enabled or not settings.wallet_rpc_ip:
            return None
            
        return MoneroWalletRPC(
            host=settings.wallet_rpc_ip,
            port=settings.wallet_rpc_port,
            username=settings.wallet_rpc_user,
            password=settings.wallet_rpc_pass
        )
        
    async def get_active_xmrig_miners(self) -> List[tuple[Miner, Pool]]:
        """
        Find all XMRig miners that are mining to a solo pool
        
        Returns:
            List of (Miner, Pool) tuples
        """
        # Get all enabled XMRig miners
        result = await self.db.execute(
            select(Miner).where(
                and_(
                    Miner.miner_type == "xmrig",
                    Miner.enabled == True
                )
            )
        )
        miners = result.scalars().all()
        
        # For each miner, we'd need to check which pool they're pointed to
        # This would require extending the Miner model or using telemetry
        # For now, return all enabled XMRig miners with dummy pool
        
        # TODO: Implement proper pool detection from XMRig telemetry
        active = []
        for miner in miners:
            # Get a pool (simplified - need proper logic)
            pool_result = await self.db.execute(select(Pool).where(Pool.enabled == True).limit(1))
            pool = pool_result.scalar_one_or_none()
            if pool:
                active.append((miner, pool))
                
        return active
        
    async def aggregate_hashrate(self) -> Dict[str, Any]:
        """
        Aggregate hashrate from all active XMRig miners
        
        Returns:
            Dictionary with:
            - total_hashrate: Combined hashrate in H/s
            - worker_count: Number of active workers
            - miners: List of miner details
        """
        active_miners = await self.get_active_xmrig_miners()
        
        total_hashrate = 0.0
        worker_count = 0
        miner_details = []
        
        for miner, pool in active_miners:
            adapter = XMRigAdapter(
                miner_id=miner.id,
                miner_name=miner.name,
                ip_address=miner.ip_address,
                port=miner.port or 8080,
                config=miner.config
            )
            
            try:
                telemetry = await adapter.get_telemetry()
                if telemetry and telemetry.hashrate:
                    # XMRig returns H/s
                    total_hashrate += telemetry.hashrate
                    worker_count += 1
                    
                    miner_details.append({
                        "miner_id": miner.id,
                        "name": miner.name,
                        "hashrate": telemetry.hashrate,
                        "accepted": telemetry.shares_accepted,
                        "rejected": telemetry.shares_rejected
                    })
            except Exception as e:
                logger.error(f"Failed to get telemetry from {miner.name}: {e}")
                
        return {
            "total_hashrate": total_hashrate,
            "worker_count": worker_count,
            "miners": miner_details
        }
        
    async def update_effort(self, pool: Pool) -> Optional[float]:
        """
        Calculate and update current mining effort for a pool
        
        Args:
            pool: Pool to calculate effort for
            
        Returns:
            Current effort percentage or None on error
        """
        try:
            # Get or create effort tracker
            result = await self.db.execute(
                select(MoneroSoloEffort).where(MoneroSoloEffort.pool_id == pool.id)
            )
            effort = result.scalar_one_or_none()
            
            if not effort:
                effort = MoneroSoloEffort(pool_id=pool.id, total_hashes=0)
                self.db.add(effort)
                
            # Get current hashrate and accumulate hashes
            hashrate_data = await self.aggregate_hashrate()
            total_hashrate = hashrate_data["total_hashrate"]
            
            # Get network difficulty from node
            node_rpc = await self.get_node_rpc(pool)
            if not node_rpc:
                return None
                
            difficulty = await node_rpc.get_difficulty()
            if not difficulty:
                return None
                
            # Accumulate hashes (simple approximation: hashrate * time_since_last_update)
            now = datetime.utcnow()
            time_delta = (now - effort.updated_at).total_seconds() if effort.updated_at else 60
            new_hashes = int(total_hashrate * time_delta)
            effort.total_hashes += new_hashes
            effort.updated_at = now
            
            # Calculate effort percentage
            effort_percent = (effort.total_hashes / difficulty) * 100 if difficulty > 0 else 0
            
            await self.db.commit()
            
            return effort_percent
            
        except Exception as e:
            logger.error(f"Failed to update effort: {e}")
            return None
            
    async def detect_new_blocks(self) -> List[MoneroBlock]:
        """
        Check for newly found blocks and reset effort counters
        
        Returns:
            List of newly detected blocks
        """
        settings = await self.get_settings()
        if not settings or not settings.enabled:
            return []
            
        wallet_rpc = await self.get_wallet_rpc()
        if not wallet_rpc:
            return []
            
        try:
            # Get recent incoming transfers
            # Get the last block height we checked
            last_block_result = await self.db.execute(
                select(func.max(MoneroBlock.block_height))
            )
            last_checked_height = last_block_result.scalar() or 0
            
            # Get transfers since last check
            transfers = await wallet_rpc.get_incoming_transfers(min_height=last_checked_height + 1)
            
            new_blocks = []
            
            for transfer in transfers:
                block_height = transfer.get("height")
                if not block_height:
                    continue
                    
                # Check if we already have this block
                existing = await self.db.execute(
                    select(MoneroBlock).where(MoneroBlock.block_height == block_height)
                )
                if existing.scalar_one_or_none():
                    continue
                    
                # This is a new block reward!
                amount_atomic = transfer.get("amount", 0)
                amount_xmr = amount_atomic / ATOMIC_UNITS_PER_XMR
                
                # Get effort from tracker (assuming first pool for now)
                effort_result = await self.db.execute(select(MoneroSoloEffort).limit(1))
                effort_tracker = effort_result.scalar_one_or_none()
                
                effort_percent = 0.0
                total_hashes = 0
                difficulty = 0
                
                if effort_tracker:
                    # Calculate final effort
                    # TODO: Get actual difficulty from node at this block height
                    effort_percent = 100.0  # Placeholder
                    total_hashes = effort_tracker.total_hashes
                    
                    # Reset effort counter
                    effort_tracker.total_hashes = 0
                    effort_tracker.round_start_time = datetime.utcnow()
                    effort_tracker.last_reset = datetime.utcnow()
                    
                # Create block record
                block = MoneroBlock(
                    block_height=block_height,
                    block_hash=transfer.get("txid", ""),
                    timestamp=datetime.fromtimestamp(transfer.get("timestamp", 0)),
                    reward_atomic=amount_atomic,
                    reward_xmr=amount_xmr,
                    effort_percent=effort_percent,
                    total_hashes=total_hashes,
                    difficulty=difficulty,
                    pool_id=effort_tracker.pool_id if effort_tracker else None
                )
                
                self.db.add(block)
                new_blocks.append(block)
                
                logger.info(f"🎉 New Monero block found! Height: {block_height}, Reward: {amount_xmr:.6f} XMR")
                
            await self.db.commit()
            return new_blocks
            
        except Exception as e:
            logger.error(f"Failed to detect new blocks: {e}")
            return []
            
    async def sync_wallet_transactions(self) -> int:
        """
        Sync wallet transactions to database
        
        Returns:
            Number of new transactions synced
        """
        wallet_rpc = await self.get_wallet_rpc()
        if not wallet_rpc:
            return 0
            
        try:
            # Get last synced transaction height
            last_tx_result = await self.db.execute(
                select(func.max(MoneroWalletTransaction.block_height))
            )
            last_height = last_tx_result.scalar() or 0
            
            # Get new incoming transfers
            transfers = await wallet_rpc.get_incoming_transfers(min_height=last_height)
            
            new_count = 0
            
            for transfer in transfers:
                txid = transfer.get("txid")
                if not txid:
                    continue
                    
                # Check if already exists
                existing = await self.db.execute(
                    select(MoneroWalletTransaction).where(MoneroWalletTransaction.tx_hash == txid)
                )
                if existing.scalar_one_or_none():
                    continue
                    
                # Add new transaction
                amount_atomic = transfer.get("amount", 0)
                tx = MoneroWalletTransaction(
                    tx_hash=txid,
                    block_height=transfer.get("height", 0),
                    amount_atomic=amount_atomic,
                    amount_xmr=amount_atomic / ATOMIC_UNITS_PER_XMR,
                    timestamp=datetime.fromtimestamp(transfer.get("timestamp", 0)),
                    tx_type="in",
                    is_block_reward=True  # Assume all incoming are block rewards for solo mining
                )
                
                self.db.add(tx)
                new_count += 1
                
            if new_count > 0:
                # Update last sync time
                settings = await self.get_settings()
                if settings:
                    settings.last_sync = datetime.utcnow()
                    
                await self.db.commit()
                logger.info(f"Synced {new_count} new wallet transactions")
                
            return new_count
            
        except Exception as e:
            logger.error(f"Failed to sync wallet transactions: {e}")
            return 0
            
    async def calculate_expected_time(self, pool: Pool) -> Optional[int]:
        """
        Calculate expected time to find next block
        
        Args:
            pool: Pool to calculate for
            
        Returns:
            Expected seconds to block or None on error
        """
        try:
            # Get current hashrate
            hashrate_data = await self.aggregate_hashrate()
            if hashrate_data["worker_count"] == 0:
                return None
                
            total_hashrate = hashrate_data["total_hashrate"]
            
            # Get network difficulty
            node_rpc = await self.get_node_rpc(pool)
            if not node_rpc:
                return None
                
            difficulty = await node_rpc.get_difficulty()
            if not difficulty or total_hashrate == 0:
                return None
                
            # Expected time = difficulty / hashrate
            expected_seconds = int(difficulty / total_hashrate)
            
            return expected_seconds
            
        except Exception as e:
            logger.error(f"Failed to calculate expected time: {e}")
            return None
            
    async def store_hashrate_snapshot(self):
        """Store current hashrate snapshot for charting"""
        try:
            hashrate_data = await self.aggregate_hashrate()
            
            # Get current effort
            effort_result = await self.db.execute(select(MoneroSoloEffort).limit(1))
            effort_tracker = effort_result.scalar_one_or_none()
            
            # Get network difficulty (simplified - using first active pool)
            active_miners = await self.get_active_xmrig_miners()
            difficulty = 0
            
            if active_miners:
                _, pool = active_miners[0]
                node_rpc = await self.get_node_rpc(pool)
                if node_rpc:
                    difficulty = await node_rpc.get_difficulty() or 0
                    
            current_effort = 0.0
            if effort_tracker and difficulty > 0:
                current_effort = (effort_tracker.total_hashes / difficulty) * 100
                
            snapshot = MoneroHashrateSnapshot(
                total_hashrate=hashrate_data["total_hashrate"],
                worker_count=hashrate_data["worker_count"],
                network_difficulty=difficulty,
                current_effort=current_effort
            )
            
            self.db.add(snapshot)
            await self.db.commit()
            
        except Exception as e:
            logger.error(f"Failed to store hashrate snapshot: {e}")
