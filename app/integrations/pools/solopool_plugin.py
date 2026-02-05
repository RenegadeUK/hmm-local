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
    DashboardTileData
)
from integrations.pool_registry import PoolRegistry

logger = logging.getLogger(__name__)


class SolopoolIntegration(BasePoolIntegration):
    """Integration for Solopool.org solo mining pools."""
    
    # Class attributes
    pool_type = "solopool"
    display_name = "Solopool.org"
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
                        return data.get("networkDifficulty")
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
                    
                    return PoolStats(
                        hashrate=data.get("poolHashrate", 0),
                        active_workers=data.get("poolMiners", 0),
                        blocks_found=data.get("poolBlocks", 0),
                        network_difficulty=data.get("networkDifficulty"),
                        additional_stats={
                            "pool_fee": data.get("poolFee", 0),
                            "network_hashrate": data.get("networkHashrate")
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
        - Pool stats (/api/stats)
        - Recent blocks (/api/blocks)
        - Worker stats (/api/accounts/{username}) if username provided
        """
        api_base = self.API_BASES.get(coin.upper())
        if not api_base:
            logger.warning(f"No Solopool API for {coin}")
            return None
        
        try:
            async with aiohttp.ClientSession() as session:
                # Fetch stats and blocks in parallel
                stats_task = session.get(
                    f"{api_base}/stats",
                    timeout=aiohttp.ClientTimeout(total=self.API_TIMEOUT)
                )
                blocks_task = session.get(
                    f"{api_base}/blocks",
                    timeout=aiohttp.ClientTimeout(total=self.API_TIMEOUT)
                )
                
                # Execute parallel requests
                start_time = datetime.utcnow()
                stats_resp, blocks_resp = await asyncio.gather(
                    stats_task, blocks_task, return_exceptions=True
                )
                
                latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                
                # Check if requests succeeded
                if isinstance(stats_resp, Exception) or isinstance(blocks_resp, Exception):
                    return DashboardTileData(
                        health_status=False,
                        health_message="API request failed",
                        currency=coin.upper()
                    )
                
                # Parse stats
                stats_data = await stats_resp.json() if stats_resp.status == 200 else {}
                blocks_data = await blocks_resp.json() if blocks_resp.status == 200 else {}
                
                # Count recent blocks (last 24h)
                all_blocks = []
                if blocks_data and isinstance(blocks_data, dict):
                    if 'immature' in blocks_data and blocks_data['immature']:
                        all_blocks.extend(blocks_data['immature'])
                    if 'matured' in blocks_data and blocks_data['matured']:
                        all_blocks.extend(blocks_data['matured'])
                
                cutoff = datetime.utcnow().timestamp() - (24 * 3600)
                blocks_24h = len([b for b in all_blocks if b.get('timestamp', 0) >= cutoff])
                
                # Calculate pool percentage of network
                pool_hashrate = stats_data.get("poolHashrate", 0)
                network_hashrate = stats_data.get("networkHashrate", 0)
                pool_percentage = None
                if network_hashrate and network_hashrate > 0:
                    pool_percentage = (pool_hashrate / network_hashrate) * 100
                
                # Estimate time to block (very rough)
                network_diff = stats_data.get("networkDifficulty", 0)
                estimated_time = None
                if pool_hashrate and pool_hashrate > 0 and network_diff:
                    seconds = network_diff * (2**32) / pool_hashrate
                    if seconds < 3600:
                        estimated_time = f"{int(seconds / 60)} minutes"
                    elif seconds < 86400:
                        estimated_time = f"{int(seconds / 3600)} hours"
                    else:
                        estimated_time = f"{int(seconds / 86400)} days"
                
                return DashboardTileData(
                    # Tile 1: Health
                    health_status=stats_resp.status == 200,
                    health_message="Connected" if stats_resp.status == 200 else f"HTTP {stats_resp.status}",
                    latency_ms=latency_ms,
                    
                    # Tile 2: Network Stats
                    network_difficulty=stats_data.get("networkDifficulty"),
                    pool_hashrate=pool_hashrate,
                    estimated_time_to_block=estimated_time,
                    pool_percentage=round(pool_percentage, 4) if pool_percentage else None,
                    
                    # Tile 3: Shares
                    # Note: Solopool doesn't provide share stats in public API
                    shares_valid=None,
                    shares_invalid=None,
                    shares_stale=None,
                    reject_rate=None,
                    
                    # Tile 4: Blocks
                    blocks_found_24h=blocks_24h,
                    estimated_earnings_24h=None,  # Solo pool - no earnings estimate
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
PoolRegistry.register(SolopoolIntegration())
