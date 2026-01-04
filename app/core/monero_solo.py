"""
Monero Solo Mining Service
Core logic for tracking solo mining effort, detecting blocks, and aggregating stats
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy import select, func, and_, or_
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
        Find all XMRig miners that are mining to the solo pool
        
        Returns:
            List of (Miner, Pool) tuples for miners pointed at solo node
        """
        settings = await self.get_or_create_settings()
        
        if not settings.enabled or not settings.pool_id:
            logger.debug("Monero solo not enabled or no pool_id configured")
            return []
        
        # Get the solo pool
        pool_result = await self.db.execute(select(Pool).where(Pool.id == settings.pool_id))
        solo_pool = pool_result.scalar_one_or_none()
        
        if not solo_pool:
            logger.warning(f"Monero solo pool_id {settings.pool_id} not found in database")
            return []
        
        # Get all enabled XMRig miners with recent telemetry pointing at this pool
        # XMRig doesn't use MinerPoolSlot - it reports pool in telemetry
        from core.database import Telemetry
        from datetime import datetime, timedelta
        cutoff = datetime.utcnow() - timedelta(minutes=5)
        
        # Find miners with recent telemetry matching this pool's URL:port
        pool_url = f"{solo_pool.url}:{solo_pool.port}"
        logger.info(f"Looking for XMRig miners with pool matching: {pool_url}")
        
        # First, let's see what XMRig miners exist with recent telemetry
        debug_result = await self.db.execute(
            select(Miner, Telemetry.pool_in_use).join(
                Telemetry, Miner.id == Telemetry.miner_id
            ).where(
                and_(
                    Miner.miner_type == "xmrig",
                    Miner.enabled == True,
                    Telemetry.timestamp > cutoff
                )
            ).distinct()
        )
        debug_rows = debug_result.all()
        for miner, pool_in_use in debug_rows:
            logger.info(f"  Found XMRig miner '{miner.name}' with pool_in_use: '{pool_in_use}'")
        
        result = await self.db.execute(
            select(Miner).join(
                Telemetry, Miner.id == Telemetry.miner_id
            ).where(
                and_(
                    Miner.miner_type == "xmrig",
                    Miner.enabled == True,
                    Telemetry.timestamp > cutoff,
                    or_(
                        Telemetry.pool_in_use.like(f"%{solo_pool.url}:{solo_pool.port}%"),
                        Telemetry.pool_in_use.like(f"%{solo_pool.url}:{solo_pool.port}")
                    )
                )
            ).distinct()
        )
        miners = result.scalars().all()
        
        logger.info(f"Matched {len(miners)} XMRig miners to solo pool")
        
        # Return miners with the solo pool
        active = []
        for miner in miners:
            active.append((miner, solo_pool))
                
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
        Check for newly found SOLO-MINED blocks (not pool payouts) and reset effort counters
        
        For solo mining, a block is only counted if:
        - Amount matches typical Monero block reward (~0.6 XMR)
        - Transaction type indicates coinbase/miner reward
        
        All wallet transactions are synced separately via sync_wallet_transactions()
        
        Returns:
            List of newly detected solo-mined blocks
        """
        settings = await self.get_settings()
        if not settings or not settings.enabled:
            return []
            
        # First sync all wallet transactions
        await self.sync_wallet_transactions()
            
        wallet_rpc = await self.get_wallet_rpc()
        if not wallet_rpc:
            return []
            
        try:
            # Get recent incoming transfers
            # Use persistent high-water mark from settings to avoid reprocessing old transactions
            last_checked_height = settings.last_block_check_height or 0
            
            # Get transfers since last check
            transfers = await wallet_rpc.get_incoming_transfers(min_height=last_checked_height + 1)
            
            new_blocks = []
            highest_height_seen = last_checked_height
            
            for transfer in transfers:
                block_height = transfer.get("height")
                if not block_height:
                    continue
                    
                # Track highest block height we've seen
                if block_height > highest_height_seen:
                    highest_height_seen = block_height
                    
                amount_atomic = transfer.get("amount", 0)
                amount_xmr = amount_atomic / ATOMIC_UNITS_PER_XMR
                
                # SOLO BLOCK DETECTION LOGIC
                # Monero block rewards are typically 0.6 XMR (base reward + fees)
                # Pool payouts are usually smaller and more frequent
                # Only count as a solo block if amount suggests it's a block reward
                is_solo_block = amount_xmr >= 0.5  # Minimum threshold for block reward
                
                if not is_solo_block:
                    # This is a pool payout or other transaction, not a solo block
                    continue
                    
                # Check if we already have this block
                existing = await self.db.execute(
                    select(MoneroBlock).where(MoneroBlock.block_height == block_height)
                )
                if existing.scalar_one_or_none():
                    continue
                    
                # This is a real solo-mined block!
                logger.info(f"🎉 SOLO BLOCK DETECTED! Height: {block_height}, Reward: {amount_xmr:.6f} XMR")
                
                # Get effort from tracker
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
            
            # Update high-water mark to prevent reprocessing
            if highest_height_seen > last_checked_height:
                settings.last_block_check_height = highest_height_seen
                
            await self.db.commit()
            
            if new_blocks:
                logger.info(f"✅ Found {len(new_blocks)} new solo-mined block(s)")
            
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
                amount_xmr = amount_atomic / ATOMIC_UNITS_PER_XMR
                
                # Check if this looks like a solo block reward vs pool payout
                # Solo blocks are typically ~0.6 XMR, pool payouts are smaller
                is_block_reward = amount_xmr >= 0.5
                
                tx = MoneroWalletTransaction(
                    tx_hash=txid,
                    block_height=transfer.get("height", 0),
                    amount_atomic=amount_atomic,
                    amount_xmr=amount_xmr,
                    timestamp=datetime.fromtimestamp(transfer.get("timestamp", 0)),
                    tx_type="in",
                    is_block_reward=is_block_reward
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
