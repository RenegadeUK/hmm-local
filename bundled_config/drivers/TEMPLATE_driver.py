"""
Template Pool Driver
Copy this file to create a new pool driver integration.

Steps:
1. Copy this file: cp TEMPLATE_driver.py mypool_driver.py
2. Replace "template" with your pool's name throughout
3. Update driver_type, display_name, and BASE_URL
4. Implement required methods (check_health, get_pool_stats, etc.)
5. Optionally implement get_dashboard_data() for dashboard tiles
6. Restart container to load the new driver
"""

__version__ = "1.0.2"

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

logger = logging.getLogger(__name__)


class TemplateIntegration(BasePoolIntegration):
    """Template pool integration - replace with your pool name."""
    
    # REQUIRED: Update these class attributes
    driver_version = __version__
    pool_type = "template"  # Must match driver filename (template_driver.py)
    display_name = "Template Pool"
    documentation_url = "https://your-pool.com/docs"
    supports_coins = ["BTC", "DGB", "BCH"]  # Coins this pool supports
    requires_api_key = False  # Set True if pool requires API authentication
    
    # Pool connection details
    BASE_URL = "https://api.your-pool.com"
    POOL_URL = "stratum.your-pool.com"
    POOL_PORT = 3333
    API_TIMEOUT = 10
    
    def get_pool_templates(self) -> List[PoolTemplate]:
        """
        Define pool configurations for UI pool selector.
        
        Each template appears in the "Add Pool" dialog.
        Users can select from these pre-configured options.
        """
        return [
            PoolTemplate(
                template_id="btc_global",
                display_name="Template Pool BTC (Global)",
                url=self.POOL_URL,
                port=self.POOL_PORT,
                coin="BTC",
                region="Global",
                mining_model=MiningModel.POOL,
                fee_percent=1.0,
                supports_shares=True,
                supports_earnings=True,
                supports_balance=True,
                requires_auth=self.requires_api_key,
                description="Template Pool's BTC mining pool"
            ),
            # Add more templates for other coins/regions
        ]
    
    async def check_health(
        self,
        url: str,
        port: int,
        coin: str,
        **kwargs
    ) -> PoolHealthStatus:
        """
        Check if pool is reachable and healthy.
        
        Args:
            url: Pool URL
            port: Pool port
            coin: Coin symbol
            **kwargs: Additional config from pool_config
        
        Returns:
            PoolHealthStatus with health info
        """
        try:
            start_time = datetime.utcnow()
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.BASE_URL}/health",  # Your pool's health endpoint
                    timeout=aiohttp.ClientTimeout(total=self.API_TIMEOUT)
                ) as response:
                    latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                    
                    if response.status == 200:
                        return PoolHealthStatus(
                            is_healthy=True,
                            response_time_ms=latency_ms,
                            error_message=None
                        )
                    else:
                        return PoolHealthStatus(
                            is_healthy=False,
                            response_time_ms=latency_ms,
                            error_message=f"HTTP {response.status}"
                        )
        except Exception as e:
            logger.error(f"Health check failed for {coin}: {e}")
            return PoolHealthStatus(
                is_healthy=False,
                response_time_ms=None,
                error_message=str(e)
            )
    
    async def get_pool_stats(
        self,
        url: str,
        coin: str,
        username: Optional[str] = None,
        **kwargs
    ) -> Optional[PoolStats]:
        """
        Get pool-wide statistics (total hashrate, miners, etc.).
        
        Args:
            url: Pool URL
            coin: Coin symbol
            username: Optional username (not used for pool-wide stats)
            **kwargs: Additional config
        
        Returns:
            PoolStats or None on error
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.BASE_URL}/stats",  # Your pool's stats endpoint
                    timeout=aiohttp.ClientTimeout(total=self.API_TIMEOUT)
                ) as response:
                    if response.status != 200:
                        return None
                    
                    data = await response.json()
                    
                    # Parse your pool's response format
                    return PoolStats(
                        hashrate=data.get("pool_hashrate", 0),
                        active_workers=data.get("active_miners", 0),
                        blocks_found=data.get("total_blocks", 0),
                        network_difficulty=data.get("difficulty"),
                        additional_stats={
                            "pool_fee": data.get("fee", 0),
                            "payout_threshold": data.get("min_payout")
                        }
                    )
        except Exception as e:
            logger.error(f"Failed to get pool stats for {coin}: {e}")
            return None
    
    async def get_dashboard_data(
        self,
        url: str,
        coin: str,
        username: Optional[str] = None,
        **kwargs
    ) -> Optional[DashboardTileData]:
        """
        Get USER-SPECIFIC data for dashboard tiles (OPTIONAL).
        
        IMPORTANT: This should return the USER's hashrate/shares,
        NOT pool-wide statistics!
        
        Args:
            url: Pool URL
            coin: Coin symbol
            username: User's wallet address or username
            **kwargs: Additional config
        
        Returns:
            DashboardTileData with user stats, or None on error
        """
        if not username:
            return None
        
        try:
            async with aiohttp.ClientSession() as session:
                # Fetch user's worker stats
                async with session.get(
                    f"{self.BASE_URL}/accounts/{username}",  # Your pool's user endpoint
                    timeout=aiohttp.ClientTimeout(total=self.API_TIMEOUT)
                ) as response:
                    if response.status != 200:
                        return DashboardTileData(
                            health_status=False,
                            health_message=f"API returned {response.status}",
                            currency=coin.upper()
                        )
                    
                    data = await response.json()
                    
                    # Parse USER's data from your pool's response format
                    # IMPORTANT: Convert hashrate to TH/s if API returns H/s
                    user_hashrate_hs = data.get("hashrate", 0)  # Assuming H/s
                    user_hashrate_ths = user_hashrate_hs / 1_000_000_000_000  # Convert to TH/s
                    
                    # Extract shares (check your API's field names - might be camelCase!)
                    workers = data.get("workers", {})
                    total_valid_shares = 0
                    total_invalid_shares = 0
                    
                    for worker in workers.values():
                        # Adjust field names based on your pool's API
                        total_valid_shares += worker.get("valid_shares", 0)
                        total_invalid_shares += worker.get("invalid_shares", 0)
                    
                    return DashboardTileData(
                        # Tile 1: Health
                        health_status=True,
                        health_message="OK",
                        
                        # Tile 2: Network Stats
                        pool_hashrate=user_hashrate_ths,  # USER's hashrate in TH/s!
                        active_workers=data.get("workers_online", 0),
                        network_difficulty=data.get("network_difficulty"),
                        
                        # Tile 3: Shares
                        shares_valid=total_valid_shares,
                        shares_invalid=total_invalid_shares,
                        
                        # Tile 4: Earnings/Balance
                        currency=coin.upper(),
                        confirmed_balance=data.get("balance"),
                        pending_balance=data.get("pending")
                    )
        except Exception as e:
            logger.error(f"Failed to get dashboard data for {coin}/{username}: {e}")
            return DashboardTileData(
                health_status=False,
                health_message=str(e),
                currency=coin.upper()
            )
    
    async def get_blocks(
        self,
        url: str,
        coin: str,
        limit: int = 10,
        **kwargs
    ) -> List[PoolBlock]:
        """
        Get recent blocks found by the pool.
        
        Args:
            url: Pool URL
            coin: Coin symbol
            limit: Maximum number of blocks to return
            **kwargs: Additional config
        
        Returns:
            List of PoolBlock objects
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.BASE_URL}/blocks?limit={limit}",
                    timeout=aiohttp.ClientTimeout(total=self.API_TIMEOUT)
                ) as response:
                    if response.status != 200:
                        return []
                    
                    data = await response.json()
                    
                    blocks = []
                    for block_data in data.get("blocks", [])[:limit]:
                        blocks.append(PoolBlock(
                            height=block_data.get("height"),
                            hash=block_data.get("hash"),
                            miner=block_data.get("miner", "Unknown"),
                            timestamp=block_data.get("timestamp"),
                            difficulty=block_data.get("difficulty"),
                            coin=coin.upper(),
                            reward=block_data.get("reward"),
                            confirmed=block_data.get("confirmed", False)
                        ))
                    
                    return blocks
        except Exception as e:
            logger.error(f"Failed to get blocks for {coin}: {e}")
            return []


# Register the driver (required)
def get_integration() -> BasePoolIntegration:
    """Factory function to create driver instance."""
    return TemplateIntegration()
