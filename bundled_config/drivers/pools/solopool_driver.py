"""
Solopool.org Integration Plugin
Public API solo mining pool for BTC, BCH, DGB, BC2
"""
import logging
import aiohttp
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime

from integrations.base_pool import (
    BasePoolIntegration,
    PoolHealthStatus,
    PoolStats,
    PoolBlock,
    DashboardTileData,
    PoolTemplate,
    MiningModel
)
from core.utils import format_hashrate

logger = logging.getLogger(__name__)

__version__ = "1.0.6"


class SolopoolIntegration(BasePoolIntegration):
    """Integration for Solopool.org solo mining pools."""
    
    # Class attributes
    pool_type = "solopool"
    display_name = "Solopool.org"
    driver_version = __version__
    documentation_url = "https://solopool.org"
    supports_coins = ["BTC", "BCH", "DGB", "BC2"]
    requires_api_key = False
    
    # API endpoints per coin
    API_BASES = {
        "BCH": "https://bch.solopool.org/api",
        "DGB": "https://dgb-sha.solopool.org/api",
        "BTC": "https://btc.solopool.org/api",
        "BC2": "https://bc2.solopool.org/api"
    }
    
    # Pool URLs and ports
    POOL_CONFIGS = {
        "BCH": {"pools": ["eu2.solopool.org", "us1.solopool.org"], "port": 8002},
        "DGB": {"pools": ["eu1.solopool.org", "us1.solopool.org"], "port": 8004},
        "BTC": {"pools": ["eu3.solopool.org"], "port": 8005},
        "BC2": {"pools": ["eu3.solopool.org"], "port": 8001}
    }
    
    API_TIMEOUT = 10
    
    def get_pool_templates(self) -> List[PoolTemplate]:
        """
        Return all available Solopool.org pool configurations.
        
        Solopool.org offers solo mining for multiple coins with geographic distribution.
        """
        templates = []
        
        # DGB - DigiByte (EU and US servers)
        templates.append(PoolTemplate(
            template_id="dgb_eu1",
            display_name="Solopool.org DGB (EU1)",
            url="eu1.solopool.org",
            port=8004,
            coin="DGB",
            mining_model=MiningModel.SOLO,
            region="EU",
            requires_auth=False,
            supports_shares=False,
            supports_earnings=False,
            supports_balance=False,
            description="DigiByte solo mining - European server",
            fee_percent=0.0
        ))
        
        templates.append(PoolTemplate(
            template_id="dgb_us1",
            display_name="Solopool.org DGB (US1)",
            url="us1.solopool.org",
            port=8004,
            coin="DGB",
            mining_model=MiningModel.SOLO,
            region="US",
            requires_auth=False,
            supports_shares=False,
            supports_earnings=False,
            supports_balance=False,
            description="DigiByte solo mining - US server",
            fee_percent=0.0
        ))
        
        # BCH - Bitcoin Cash (EU and US servers)
        templates.append(PoolTemplate(
            template_id="bch_eu2",
            display_name="Solopool.org BCH (EU2)",
            url="eu2.solopool.org",
            port=8002,
            coin="BCH",
            mining_model=MiningModel.SOLO,
            region="EU",
            requires_auth=False,
            supports_shares=False,
            supports_earnings=False,
            supports_balance=False,
            description="Bitcoin Cash solo mining - European server",
            fee_percent=0.0
        ))
        
        templates.append(PoolTemplate(
            template_id="bch_us1",
            display_name="Solopool.org BCH (US1)",
            url="us1.solopool.org",
            port=8002,
            coin="BCH",
            mining_model=MiningModel.SOLO,
            region="US",
            requires_auth=False,
            supports_shares=False,
            supports_earnings=False,
            supports_balance=False,
            description="Bitcoin Cash solo mining - US server",
            fee_percent=0.0
        ))
        
        # BTC - Bitcoin (EU server only)
        templates.append(PoolTemplate(
            template_id="btc_eu3",
            display_name="Solopool.org BTC (EU3)",
            url="eu3.solopool.org",
            port=8005,
            coin="BTC",
            mining_model=MiningModel.SOLO,
            region="EU",
            requires_auth=False,
            supports_shares=False,
            supports_earnings=False,
            supports_balance=False,
            description="Bitcoin solo mining - European server",
            fee_percent=0.0
        ))
        
        # BC2 - BitcoinCashClassic (EU server only)
        templates.append(PoolTemplate(
            template_id="bc2_eu3",
            display_name="Solopool.org BC2 (EU3)",
            url="eu3.solopool.org",
            port=8001,
            coin="BC2",
            mining_model=MiningModel.SOLO,
            region="EU",
            requires_auth=False,
            supports_shares=False,
            supports_earnings=False,
            supports_balance=False,
            description="Bitcoin Cash Classic solo mining - European server",
            fee_percent=0.0
        ))
        
        return templates
    
    async def detect(self, url: str, port: int) -> bool:
        """Auto-detect if URL:port is a Solopool pool."""
        for coin, config in self.POOL_CONFIGS.items():
            if url in config["pools"] and port == config["port"]:
                return True
        return False
    
    async def get_health(self, url: str, port: int, **kwargs) -> Optional[PoolHealthStatus]:
        """Check Solopool health by hitting /api/stats endpoint."""
        # Determine coin from port
        coin = self._get_coin_from_port(port)
        if not coin:
            return PoolHealthStatus(
                is_healthy=False,
                error_message="Could not determine coin from port"
            )
        
        api_base = self.API_BASES.get(coin)
        if not api_base:
            return PoolHealthStatus(
                is_healthy=False,
                error_message=f"No API endpoint for {coin}"
            )
        
        try:
            start_time = datetime.utcnow()
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{api_base}/stats",
                    timeout=aiohttp.ClientTimeout(total=self.API_TIMEOUT)
                ) as response:
                    latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                    
                    if response.status == 200:
                        return PoolHealthStatus(
                            is_healthy=True,
                            latency_ms=latency_ms
                        )
                    else:
                        return PoolHealthStatus(
                            is_healthy=False,
                            latency_ms=latency_ms,
                            error_message=f"HTTP {response.status}"
                        )
        except Exception as e:
            logger.error(f"Solopool health check failed for {coin}: {e}")
            return PoolHealthStatus(
                is_healthy=False,
                error_message=str(e)
            )
    
    async def get_network_difficulty(self, coin: str, **kwargs) -> Optional[float]:
        """Get network difficulty from Solopool /api/stats."""
        api_base = self.API_BASES.get(coin.upper())
        if not api_base:
            return None
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{api_base}/stats",
                    timeout=aiohttp.ClientTimeout(total=self.API_TIMEOUT)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        # Network difficulty is nested under stats object
                        diff = data.get("stats", {}).get("difficulty")
                        return float(diff) if diff is not None else None
        except Exception as e:
            logger.error(f"Failed to get network difficulty for {coin}: {e}")
        return None
    
    async def get_pool_stats(
        self,
        url: str,
        coin: str,
        username: Optional[str] = None,
        **kwargs
    ) -> Optional[PoolStats]:
        """Get pool statistics from Solopool /api/stats endpoint."""
        api_base = self.API_BASES.get(coin.upper())
        if not api_base:
            logger.warning(f"No Solopool API for coin {coin}")
            return None
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{api_base}/stats",
                    timeout=aiohttp.ClientTimeout(total=self.API_TIMEOUT)
                ) as response:
                    if response.status != 200:
                        return None
                    
                    data = await response.json()
                    
                    # Format hashrates (raw values are in H/s)
                    pool_hashrate_hs = data.get("poolHashrate", 0)
                    network_hashrate_hs = data.get("networkHashrate", 0)
                    
                    return PoolStats(
                        hashrate=format_hashrate(pool_hashrate_hs, "H/s"),
                        active_workers=data.get("poolMiners", 0),
                        blocks_found=data.get("poolBlocks", 0),
                        network_difficulty=data.get("networkDifficulty"),
                        additional_stats={
                            "pool_fee": data.get("poolFee", 0),
                            "network_hashrate": format_hashrate(network_hashrate_hs, "H/s")
                        }
                    )
        except Exception as e:
            logger.error(f"Failed to get Solopool stats for {coin}: {e}")
            return None
    
    async def get_blocks(
        self,
        url: str,
        coin: str,
        limit: int = 10,
        **kwargs
    ) -> List[PoolBlock]:
        """Get recent blocks from Solopool /api/blocks endpoint."""
        api_base = self.API_BASES.get(coin.upper())
        if not api_base:
            return []
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{api_base}/blocks",
                    timeout=aiohttp.ClientTimeout(total=self.API_TIMEOUT)
                ) as response:
                    if response.status != 200:
                        return []
                    
                    data = await response.json()
                    
                    # Combine immature and matured blocks
                    all_blocks = []
                    if 'immature' in data:
                        all_blocks.extend(data['immature'])
                    if 'matured' in data:
                        all_blocks.extend(data['matured'])
                    
                    # Convert to PoolBlock format
                    blocks = []
                    for block in all_blocks[:limit]:
                        blocks.append(PoolBlock(
                            height=block.get('height'),
                            hash=block.get('hash'),
                            miner=block.get('worker', 'Unknown'),
                            timestamp=block.get('timestamp'),
                            difficulty=block.get('shareDifficulty'),
                            network_difficulty=block.get('difficulty'),
                            coin=coin.upper(),
                            reward=block.get('reward'),
                            confirmed=not block.get('orphan', False)
                        ))
                    
                    return blocks
        except Exception as e:
            logger.error(f"Failed to get Solopool blocks for {coin}: {e}")
            return []
    
    async def get_worker_stats(
        self,
        url: str,
        coin: str,
        username: str,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """Get user/worker stats from Solopool /api/accounts/{username} endpoint."""
        if not username:
            return None
        
        # Remove .workername suffix if present
        username = username.split('.')[0]
        
        api_base = self.API_BASES.get(coin.upper())
        if not api_base:
            return None
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{api_base}/accounts/{username}",
                    timeout=aiohttp.ClientTimeout(total=self.API_TIMEOUT)
                ) as response:
                    if response.status != 200:
                        return None
                    
                    data = await response.json()
                    return data
        except Exception as e:
            logger.error(f"Failed to get Solopool worker stats for {username}: {e}")
            return None
    
    async def get_dashboard_data(
        self,
        url: str,
        coin: str,
        username: Optional[str] = None,
        **kwargs
    ) -> Optional[DashboardTileData]:
        """
        Get all dashboard tile data from Solopool in optimized calls.
        
        Fetches:
        - Network stats (/api/stats) for difficulty
        - Recent blocks (/api/blocks)
        - Worker stats (/api/accounts/{username}) for YOUR hashrate and shares
        """
        api_base = self.API_BASES.get(coin.upper())
        if not api_base:
            logger.warning(f"No Solopool API for {coin}")
            return None
        
        logger.info(f"Solopool get_dashboard_data: coin={coin}, username={username}")
        
        try:
            async with aiohttp.ClientSession() as session:
                # Fetch stats, blocks, and worker stats in parallel
                start_time = datetime.utcnow()
                
                tasks = [
                    session.get(f"{api_base}/stats", timeout=aiohttp.ClientTimeout(total=self.API_TIMEOUT)),
                    session.get(f"{api_base}/blocks", timeout=aiohttp.ClientTimeout(total=self.API_TIMEOUT))
                ]
                
                # Add worker stats if username provided
                if username:
                    worker_username = username.split('.')[0]  # Remove .workername suffix
                    tasks.append(
                        session.get(f"{api_base}/accounts/{worker_username}", 
                                  timeout=aiohttp.ClientTimeout(total=self.API_TIMEOUT))
                    )
                
                # Execute parallel requests
                responses = await asyncio.gather(*tasks, return_exceptions=True)
                latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                
                stats_resp = responses[0]
                blocks_resp = responses[1]
                worker_resp = responses[2] if len(responses) > 2 else None
                
                # Check if requests succeeded
                if isinstance(stats_resp, Exception):
                    return DashboardTileData(
                        health_status=False,
                        health_message="API request failed",
                        currency=coin.upper()
                    )
                
                # Parse stats
                stats_data = await stats_resp.json() if stats_resp.status == 200 else {}
                blocks_data = await blocks_resp.json() if blocks_resp and blocks_resp.status == 200 else {}
                worker_data = await worker_resp.json() if worker_resp and not isinstance(worker_resp, Exception) and worker_resp.status == 200 else None
                
                # Get YOUR hashrate and shares from worker stats
                user_hashrate = 0.0
                shares_valid = None
                shares_invalid = None
                active_workers = 0
                
                if worker_data:
                    logger.info(f"Solopool worker data received: {list(worker_data.keys())}")
                    # Worker hashrate is in H/s, convert to TH/s for display
                    user_hashrate_hs = worker_data.get("currentHashrate", 0)
                    user_hashrate = user_hashrate_hs / 1_000_000_000_000  # Convert H/s to TH/s
                    logger.info(f"User hashrate: {user_hashrate_hs} H/s = {user_hashrate} TH/s")
                    
                    # Get active workers count
                    active_workers = worker_data.get("workersOnline", 0)
                    
                    # Shares data from stats object (24h period)
                    stats = worker_data.get("stats", {})
                    if stats:
                        logger.info(f"Stats object keys: {list(stats.keys()) if isinstance(stats, dict) else 'not a dict'}")
                        # Try to get shares from various possible fields
                        shares_valid = stats.get("validShares", stats.get("validShares24h", stats.get("sharesValid", None)))
                        shares_invalid = stats.get("invalidShares", stats.get("invalidShares24h", stats.get("sharesInvalid", None)))
                        logger.info(f"Shares from stats: valid={shares_valid}, invalid={shares_invalid}")
                    
                    # If not in stats, try workers array as fallback
                    if shares_valid is None:
                        workers = worker_data.get("workers", {})
                        if workers:
                            logger.info(f"Workers count: {len(workers)}, first worker sample: {list(workers.values())[0] if workers else 'none'}")
                            total_valid = 0
                            total_invalid = 0
                            for worker_name, worker_info in workers.items():
                                # Solopool uses camelCase field names
                                total_valid += worker_info.get("sharesValid", worker_info.get("validShares", 0))
                                total_invalid += worker_info.get("sharesInvalid", worker_info.get("invalidShares", 0))
                            shares_valid = total_valid  # Always set, even if 0
                            shares_invalid = total_invalid  # Always set, even if 0 (for reject rate calculation)
                            logger.info(f"Shares from workers: valid={shares_valid}, invalid={shares_invalid}")
                else:
                    logger.warning(f"No worker data returned for username={username}")
                
                # Count recent blocks (last 24h)
                all_blocks = []
                if blocks_data and isinstance(blocks_data, dict):
                    if 'immature' in blocks_data and blocks_data['immature']:
                        all_blocks.extend(blocks_data['immature'])
                    if 'matured' in blocks_data and blocks_data['matured']:
                        all_blocks.extend(blocks_data['matured'])
                
                cutoff = datetime.utcnow().timestamp() - (24 * 3600)
                blocks_24h = len([b for b in all_blocks if b.get('timestamp', 0) >= cutoff])
                
                # Network difficulty for time estimates (nested under stats object)
                network_diff = stats_data.get("stats", {}).get("difficulty", 0)
                network_hashrate = stats_data.get("stats", {}).get("hashrate", 0)
                
                # Calculate YOUR percentage of network (not pool's percentage)
                user_percentage = None
                if network_hashrate and network_hashrate > 0 and user_hashrate > 0:
                    user_percentage = (user_hashrate / network_hashrate) * 100
                
                # Estimate time to block based on YOUR hashrate
                estimated_time = None
                if user_hashrate and user_hashrate > 0 and network_diff:
                    seconds = network_diff * (2**32) / user_hashrate
                    if seconds < 3600:
                        estimated_time = f"{int(seconds / 60)} minutes"
                    elif seconds < 86400:
                        estimated_time = f"{int(seconds / 3600)} hours"
                    else:
                        estimated_time = f"{int(seconds / 86400)} days"
                
                # Calculate reject rate
                reject_rate = None
                if shares_valid is not None and shares_invalid is not None:
                    total_shares = shares_valid + shares_invalid
                    if total_shares > 0:
                        reject_rate = (shares_invalid / total_shares) * 100
                
                return DashboardTileData(
                    # Tile 1: Health
                    health_status=stats_resp.status == 200,
                    health_message=f"{active_workers} workers online" if stats_resp.status == 200 else f"HTTP {stats_resp.status}",
                    latency_ms=latency_ms,
                    
                    # Tile 2: Network Stats - YOUR hashrate
                    network_difficulty=network_diff,
                    pool_hashrate=format_hashrate(user_hashrate, "TH/s"),  # This is YOUR hashrate, not pool's
                    estimated_time_to_block=estimated_time,
                    pool_percentage=round(user_percentage, 4) if user_percentage else None,
                    active_workers=active_workers,  # Number of your active workers
                    
                    # Tile 3: Shares - YOUR shares
                    shares_valid=shares_valid,
                    shares_invalid=shares_invalid,
                    shares_stale=None,  # Solopool doesn't track stale shares separately
                    reject_rate=round(reject_rate, 2) if reject_rate is not None else None,
                    
                    # Tile 4: Blocks
                    blocks_found_24h=blocks_24h,
                    currency=coin.upper(),
                    balances=None,
                    
                    # Metadata
                    last_updated=datetime.utcnow(),
                    supports_earnings=False,
                    supports_balance=False
                )
        
        except Exception as e:
            logger.error(f"Failed to get Solopool dashboard data: {e}")
            return None
    
    def get_config_schema(self) -> Dict[str, Any]:
        """
        Solopool doesn't require additional config beyond URL/port.
        User can optionally provide username for worker-specific stats.
        """
        return {
            "type": "object",
            "properties": {
                "username": {
                    "type": "string",
                    "title": "Username (Optional)",
                    "description": "Your wallet address or username for worker-specific stats"
                }
            }
        }
    
    def _get_coin_from_port(self, port: int) -> Optional[str]:
        """Helper to determine coin from port number."""
        for coin, config in self.POOL_CONFIGS.items():
            if config["port"] == port:
                return coin
        return None


# Auto-register this plugin
# Pool driver loaded dynamically by PoolDriverLoader
