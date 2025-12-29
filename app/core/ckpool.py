"""
CKPool Local Node Integration Service
"""
import aiohttp
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class CKPoolService:
    """Service for interacting with CKPool local node API"""
    
    DEFAULT_PORT = 3333
    DEFAULT_API_PORT = 80
    
    @staticmethod
    def is_ckpool(pool_name: str) -> bool:
        """
        Check if a pool is a CKPool instance by name.
        """
        return "ckpool" in pool_name.lower()
    
    @staticmethod
    async def get_pool_stats(pool_ip: str, api_port: int = DEFAULT_API_PORT) -> Optional[Dict[str, Any]]:
        """
        Fetch pool statistics from CKPool's HTTP API
        
        Args:
            pool_ip: IP address of the CKPool instance
            api_port: HTTP API port (default 80)
            
        Returns:
            Dict with pool stats or None if request fails
            
        Example response structure:
        {
            "runtime": 9240,
            "lastupdate": 1767000053,
            "Users": 1,
            "Workers": 4,
            "Idle": 1,
            "Disconnected": 3,
            "hashrate1m": "1.71T",
            "hashrate5m": "1.79T",
            "hashrate15m": "1.8T",
            "hashrate1hr": "1.48T",
            "hashrate6hr": "439G",
            "hashrate1d": "121G",
            "hashrate7d": "17.8G",
            "diff": 0.24,
            "accepted": 2525312,
            "rejected": 637048,
            "bestshare": 169302,
            "SPS1m": 0.398,
            "SPS5m": 0.42,
            "SPS15m": 0.429,
            "SPS1h": 0.351
        }
        """
        try:
            url = f"http://{pool_ip}:{api_port}/pool/pool.status"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=5) as response:
                    if response.status == 200:
                        text = await response.text()
                        # Response is JSON lines format - parse each line
                        lines = text.strip().split('\n')
                        combined_stats = {}
                        for line in lines:
                            line = line.strip()
                            if line and not line.startswith('Pretty print'):
                                import json
                                data = json.loads(line)
                                combined_stats.update(data)
                        return combined_stats
                    else:
                        print(f"⚠️ CKPool API returned status {response.status} for {pool_ip}")
                        return None
        except Exception as e:
            print(f"❌ Failed to fetch CKPool stats from {pool_ip}: {e}")
            return None
    
    @staticmethod
    def parse_hashrate(hashrate_str: str) -> float:
        """
        Parse CKPool hashrate string to float in GH/s
        
        Args:
            hashrate_str: Hashrate string like "1.71T", "439G", "121M"
            
        Returns:
            Hashrate in GH/s
        """
        if not hashrate_str:
            return 0.0
        
        hashrate_str = hashrate_str.strip()
        try:
            # Extract numeric value and unit
            if hashrate_str.endswith('T'):
                return float(hashrate_str[:-1]) * 1000  # TH/s to GH/s
            elif hashrate_str.endswith('G'):
                return float(hashrate_str[:-1])  # Already GH/s
            elif hashrate_str.endswith('M'):
                return float(hashrate_str[:-1]) / 1000  # MH/s to GH/s
            elif hashrate_str.endswith('K'):
                return float(hashrate_str[:-1]) / 1_000_000  # KH/s to GH/s
            else:
                return float(hashrate_str) / 1_000_000_000  # H/s to GH/s
        except:
            return 0.0
    
    @staticmethod
    def format_stats_summary(raw_stats: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format raw CKPool stats into a standardized summary
        
        Returns:
            {
                "runtime": seconds,
                "users": int,
                "workers": int,
                "workers_idle": int,
                "workers_disconnected": int,
                "hashrate_1m_gh": float,
                "hashrate_5m_gh": float,
                "hashrate_15m_gh": float,
                "hashrate_1h_gh": float,
                "hashrate_6h_gh": float,
                "hashrate_1d_gh": float,
                "hashrate_7d_gh": float,
                "difficulty": float,
                "shares_accepted": int,
                "shares_rejected": int,
                "reject_rate": float (0-100),
                "best_share": int,
                "sps_1m": float,
                "sps_5m": float,
                "sps_15m": float,
                "sps_1h": float
            }
        """
        if not raw_stats:
            return {}
        
        accepted = raw_stats.get("accepted", 0)
        rejected = raw_stats.get("rejected", 0)
        total_shares = accepted + rejected
        reject_rate = (rejected / total_shares * 100) if total_shares > 0 else 0.0
        
        return {
            "runtime": raw_stats.get("runtime", 0),
            "last_update": raw_stats.get("lastupdate", 0),
            "users": raw_stats.get("Users", 0),
            "workers": raw_stats.get("Workers", 0),
            "workers_idle": raw_stats.get("Idle", 0),
            "workers_disconnected": raw_stats.get("Disconnected", 0),
            "hashrate_1m_gh": CKPoolService.parse_hashrate(raw_stats.get("hashrate1m", "0")),
            "hashrate_5m_gh": CKPoolService.parse_hashrate(raw_stats.get("hashrate5m", "0")),
            "hashrate_15m_gh": CKPoolService.parse_hashrate(raw_stats.get("hashrate15m", "0")),
            "hashrate_1h_gh": CKPoolService.parse_hashrate(raw_stats.get("hashrate1hr", "0")),
            "hashrate_6h_gh": CKPoolService.parse_hashrate(raw_stats.get("hashrate6hr", "0")),
            "hashrate_1d_gh": CKPoolService.parse_hashrate(raw_stats.get("hashrate1d", "0")),
            "hashrate_7d_gh": CKPoolService.parse_hashrate(raw_stats.get("hashrate7d", "0")),
            "difficulty": raw_stats.get("diff", 0.0),
            "shares_accepted": accepted,
            "shares_rejected": rejected,
            "reject_rate": round(reject_rate, 2),
            "best_share": raw_stats.get("bestshare", 0),
            "sps_1m": raw_stats.get("SPS1m", 0.0),
            "sps_5m": raw_stats.get("SPS5m", 0.0),
            "sps_15m": raw_stats.get("SPS15m", 0.0),
            "sps_1h": raw_stats.get("SPS1h", 0.0)
        }
    
    @staticmethod
    async def get_dgb_network_difficulty() -> float:
        """
        Fetch DigiByte network difficulty from ckpool.log
        
        Parses the most recent "Network diff set to X" entry from the log
        
        Returns:
            Network difficulty as float, or 0.0 if fetch fails
        """
        # This is now handled by fetch_and_cache_blocks which parses the log
        # and stores the latest network difficulty. This function is kept for
        # compatibility but should use the cached value from the database.
        return 0.0
    
    @staticmethod
    async def fetch_and_cache_blocks(pool_ip: str, pool_id: int, api_port: int = DEFAULT_API_PORT) -> Optional[float]:
        """
        Fetch ckpool.log from remote server and cache block submissions to database
        
        Args:
            pool_ip: IP address of the CKPool instance
            pool_id: Database ID of the pool
            api_port: HTTP API port (default 80)
        """
        try:
            # Fetch the ckpool.log file
            url = f"http://{pool_ip}:{api_port}/ckpool.log"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status != 200:
                        print(f"⚠️ Could not fetch ckpool.log from {pool_ip}: HTTP {response.status}")
                        return
                    
                    log_content = await response.text()
            
            # Parse log for "Submitting block data" entries
            from core.database import AsyncSessionLocal, CKPoolBlock
            from sqlalchemy import select
            import re
            
            async with AsyncSessionLocal() as db:
                # Get existing blocks to avoid duplicates
                result = await db.execute(
                    select(CKPoolBlock.log_entry).where(CKPoolBlock.pool_id == pool_id)
                )
                existing_entries = {row[0] for row in result.all()}
                
                # Parse log lines for both submitted and accepted blocks
                # Pattern: "Submitting block <hash>" followed by "BLOCK ACCEPTED by network"
                new_blocks = 0
                lines = log_content.split('\n')
                
                for i, line in enumerate(lines):
                    is_submitted = "Submitting block" in line
                    is_accepted = "BLOCK ACCEPTED" in line
                    
                    if is_submitted or is_accepted:
                        # Avoid duplicate entries
                        if line in existing_entries:
                            continue
                        
                        # Extract timestamp from log line (format: [2025-12-29 09:15:23.456])
                        timestamp_match = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                        if timestamp_match:
                            from datetime import datetime
                            timestamp_str = timestamp_match.group(1)
                            timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                        else:
                            timestamp = datetime.utcnow()
                        
                        # Extract block hash if this is a submission line
                        block_hash = None
                        if is_submitted:
                            # Format: "Submitting block 0000000000000002ca3316f963d896e0fd6dcb0f8bd9f07e18ad205c27976d6d"
                            hash_match = re.search(r'Submitting block ([0-9a-fA-F]{64})', line)
                            if hash_match:
                                block_hash = hash_match.group(1)
                        
                        # If this is BLOCK ACCEPTED, look back for the preceding "Submitting block" line
                        if is_accepted and i > 0:
                            prev_line = lines[i - 1]
                            hash_match = re.search(r'Submitting block ([0-9a-fA-F]{64})', prev_line)
                            if hash_match:
                                block_hash = hash_match.group(1)
                        
                        # Create block record
                        block = CKPoolBlock(
                            pool_id=pool_id,
                            pool_ip=pool_ip,
                            block_hash=block_hash,
                            block_accepted=is_accepted,
                            timestamp=timestamp,
                            log_entry=line
                        )
                        db.add(block)
                        new_blocks += 1
                
                # Parse log for latest network difficulty
                # Pattern: "Network diff set to 965051160.7"
                latest_network_diff = 0.0
                for line in reversed(lines):  # Start from most recent
                    diff_match = re.search(r'Network diff set to ([\d.]+)', line)
                    if diff_match:
                        latest_network_diff = float(diff_match.group(1))
                        logger.info(f"Found network difficulty in log: {latest_network_diff}")
                        break
                
                # Update pool's network difficulty in database
                if latest_network_diff > 0:
                    from core.database import Pool
                    from sqlalchemy import select as sql_select
                    
                    pool_result = await db.execute(sql_select(Pool).where(Pool.id == pool_id))
                    pool = pool_result.scalar_one_or_none()
                    if pool:
                        pool.network_difficulty = latest_network_diff
                        pool.network_difficulty_updated_at = datetime.utcnow()
                        logger.info(f"Updated pool {pool_id} network difficulty to {latest_network_diff}")
                
                # Commit all changes (blocks + network difficulty)
                await db.commit()
                
                if new_blocks > 0:
                    print(f"✅ Cached {new_blocks} new block submission(s) from CKPool {pool_ip}")
                if latest_network_diff > 0:
                    print(f"✅ Updated network difficulty to {latest_network_diff}")
                
                # Return the latest network difficulty found
                return latest_network_diff
        
        except Exception as e:
            print(f"❌ Failed to fetch/cache CKPool blocks from {pool_ip}: {e}")
            return 0.0
    
    @staticmethod
    async def get_blocks_24h(pool_id: int) -> int:
        """
        Get count of blocks submitted in last 24 hours for a CKPool instance
        
        Args:
            pool_id: Database ID of the pool
            
        Returns:
            Number of blocks submitted in last 24 hours
        """
        try:
            from core.database import AsyncSessionLocal, CKPoolBlock
            from sqlalchemy import select, func
            from datetime import datetime
            import pytz
            
            async with AsyncSessionLocal() as db:
                # Hard cutoff: 29 December 2025 at 9am UK time (ONE-TIME)
                uk_tz = pytz.timezone('Europe/London')
                cutoff_9am = uk_tz.localize(datetime(2025, 12, 29, 9, 0, 0))
                cutoff = cutoff_9am.astimezone(pytz.UTC).replace(tzinfo=None)
                
                result = await db.execute(
                    select(func.count(CKPoolBlock.id))
                    .where(CKPoolBlock.pool_id == pool_id)
                    .where(CKPoolBlock.timestamp >= cutoff)
                )
                count = result.scalar()
                return count or 0
        except Exception as e:
            print(f"❌ Failed to get blocks_24h for pool {pool_id}: {e}")
            return 0
    
    @staticmethod
    async def get_blocks_accepted(pool_id: int, days: int) -> int:
        """
        Get count of ACCEPTED blocks (not just submitted) in last N days
        
        Args:
            pool_id: Database ID of the pool
            days: Number of days to look back
            
        Returns:
            Number of blocks accepted
        """
        try:
            from core.database import AsyncSessionLocal, CKPoolBlock
            from sqlalchemy import select, func
            from datetime import datetime, timedelta
            
            async with AsyncSessionLocal() as db:
                cutoff = datetime.utcnow() - timedelta(days=days)
                result = await db.execute(
                    select(func.count(CKPoolBlock.id))
                    .where(CKPoolBlock.pool_id == pool_id)
                    .where(CKPoolBlock.block_accepted == True)
                    .where(CKPoolBlock.timestamp >= cutoff)
                )
                count = result.scalar()
                return count or 0
        except Exception as e:
            print(f"❌ Failed to get blocks_accepted for pool {pool_id}: {e}")
            return 0
    
    @staticmethod
    async def verify_block_from_explorer(block_hash: str, coin_type: str, wallet_address: str = None) -> Optional[Dict[str, Any]]:
        """
        Verify block and get actual reward from blockchain explorer
        
        Args:
            block_hash: Block hash to verify
            coin_type: Coin type (BTC, BCH, DGB)
            wallet_address: Optional wallet address to verify payout
            
        Returns:
            Dict with {
                "block_height": int,
                "reward": float,
                "confirmed": bool,
                "wallet_match": bool (if wallet_address provided)
            }
        """
        try:
            import aiohttp
            
            # Explorer API endpoints
            if coin_type == 'DGB':
                # DigiExplorer API
                url = f"https://digiexplorer.info/api/block/{block_hash}"
            elif coin_type == 'BCH':
                # BlockchairAPI
                url = f"https://api.blockchair.com/bitcoin-cash/dashboards/block/{block_hash}"
            elif coin_type == 'BTC':
                # Blockchain.info API
                url = f"https://blockchain.info/rawblock/{block_hash}"
            else:
                return None
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status != 200:
                        return None
                    
                    data = await response.json()
                    
                    # Parse response based on coin type
                    if coin_type == 'DGB':
                        # DigiExplorer format
                        block_height = data.get('height')
                        # Coinbase transaction is first tx
                        reward = 0.0
                        if 'tx' in data and len(data['tx']) > 0:
                            coinbase_tx = data['tx'][0]
                            if 'vout' in coinbase_tx:
                                for output in coinbase_tx['vout']:
                                    reward += float(output.get('value', 0))
                        
                        return {
                            "block_height": block_height,
                            "reward": reward,
                            "confirmed": True,
                            "wallet_match": None  # TODO: Check wallet if provided
                        }
                    
                    elif coin_type == 'BCH':
                        # Blockchair format
                        block_data = data.get('data', {}).get(block_hash, {}).get('block', {})
                        block_height = block_data.get('id')
                        reward = float(block_data.get('generation', 0)) / 100000000  # satoshis to BCH
                        
                        return {
                            "block_height": block_height,
                            "reward": reward,
                            "confirmed": True,
                            "wallet_match": None
                        }
                    
                    elif coin_type == 'BTC':
                        # Blockchain.info format
                        block_height = data.get('height')
                        # Coinbase tx
                        reward = 0.0
                        if 'tx' in data and len(data['tx']) > 0:
                            coinbase_tx = data['tx'][0]
                            if 'out' in coinbase_tx:
                                for output in coinbase_tx['out']:
                                    reward += float(output.get('value', 0)) / 100000000  # satoshis to BTC
                        
                        return {
                            "block_height": block_height,
                            "reward": reward,
                            "confirmed": True,
                            "wallet_match": None
                        }
        
        except Exception as e:
            print(f"❌ Failed to verify block {block_hash} from explorer: {e}")
            return None
    
    @staticmethod
    async def update_confirmed_rewards(pool_id: int, coin_type: str):
        """
        Update confirmed rewards for all accepted blocks that haven't been verified yet
        
        Args:
            pool_id: Database ID of the pool
            coin_type: Coin type (BTC, BCH, DGB)
        """
        try:
            from core.database import AsyncSessionLocal, CKPoolBlock
            from sqlalchemy import select
            
            async with AsyncSessionLocal() as db:
                # Get all accepted blocks without confirmed rewards
                result = await db.execute(
                    select(CKPoolBlock)
                    .where(CKPoolBlock.pool_id == pool_id)
                    .where(CKPoolBlock.block_accepted == True)
                    .where(CKPoolBlock.confirmed_from_explorer == False)
                    .where(CKPoolBlock.block_hash.isnot(None))
                )
                unconfirmed_blocks = result.scalars().all()
                
                for block in unconfirmed_blocks:
                    # Verify from explorer
                    explorer_data = await CKPoolService.verify_block_from_explorer(
                        block.block_hash,
                        coin_type
                    )
                    
                    if explorer_data and explorer_data.get('confirmed'):
                        # Update database with confirmed reward
                        block.confirmed_reward_coins = explorer_data['reward']
                        block.block_height = explorer_data['block_height']
                        block.confirmed_from_explorer = True
                        print(f"✅ Confirmed block {block.block_hash[:16]}... reward: {explorer_data['reward']} {coin_type}")
                
                await db.commit()
        
        except Exception as e:
            print(f"❌ Failed to update confirmed rewards: {e}")
