"""
MMFP Solutions Pool Integration

MMFP (https://www.mmfpsolutions.io/) is a local solo mining pool software
that supports multiple coins (BTC, BCH, DGB, BC2) with a REST API for monitoring.
"""
import aiohttp
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from integrations.base_pool import (
    BasePoolIntegration,
    PoolHealthStatus,
    PoolBlock,
    PoolStats,
    DashboardTileData
)
from integrations.pool_registry import PoolRegistry

logger = logging.getLogger(__name__)


class MMFPIntegration(BasePoolIntegration):
    """
    MMFP Solutions local solo pool integration.
    
    API Documentation: https://www.mmfpsolutions.io/index.html
    Default API Port: 4004
    """
    
    pool_type = "mmfp"
    display_name = "MMFP Solutions (Local Solo Pool)"
    documentation_url = "https://www.mmfpsolutions.io/index.html"
    supports_coins = ["BTC", "BCH", "DGB", "BC2"]
    requires_api_key = False
    
    API_PORT = 4004
    API_TIMEOUT = 5.0
    
    def _get_api_url(self, url: str) -> str:
        """Build API base URL from stratum URL"""
        # Remove any protocol
        clean_url = url.replace("http://", "").replace("https://", "")
        # Remove any port from URL
        clean_url = clean_url.split(":")[0]
        return f"http://{clean_url}:{self.API_PORT}"
    
    async def detect(self, url: str, port: int) -> bool:
        """
        Detect MMFP pool by checking health endpoint.
        """
        try:
            api_url = self._get_api_url(url)
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{api_url}/api/v1/health",
                    timeout=aiohttp.ClientTimeout(total=self.API_TIMEOUT)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        # MMFP health endpoint returns {"status": "ok", "version": "...", "uptime": ...}
                        return data.get("status") == "ok"
        except Exception as e:
            logger.debug(f"MMFP detection failed for {url}: {e}")
        
        return False
    
    async def get_health(self, url: str, port: int, **kwargs) -> PoolHealthStatus:
        """
        Check MMFP pool health via API.
        """
        try:
            api_url = self._get_api_url(url)
            
            import time
            start_time = time.time()
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{api_url}/api/v1/health",
                    timeout=aiohttp.ClientTimeout(total=self.API_TIMEOUT)
                ) as response:
                    latency_ms = (time.time() - start_time) * 1000
                    
                    if response.status == 200:
                        data = await response.json()
                        
                        return PoolHealthStatus(
                            is_healthy=True,
                            latency_ms=latency_ms,
                            additional_info={
                                "version": data.get("version"),
                                "uptime_seconds": data.get("uptime")
                            }
                        )
                    else:
                        return PoolHealthStatus(
                            is_healthy=False,
                            latency_ms=latency_ms,
                            error_message=f"HTTP {response.status}"
                        )
        
        except Exception as e:
            return PoolHealthStatus(
                is_healthy=False,
                error_message=str(e)
            )
    
    async def get_network_difficulty(self, coin: str, **kwargs) -> Optional[float]:
        """
        Get network difficulty from MMFP pool metrics.
        """
        try:
            # Extract URL from kwargs
            url = kwargs.get("url")
            if not url:
                logger.warning("No URL provided to get_network_difficulty")
                return None
            
            api_url = self._get_api_url(url)
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{api_url}/api/v1/{coin.upper()}/metrics/pool",
                    timeout=aiohttp.ClientTimeout(total=self.API_TIMEOUT)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("network_comparison", {}).get("network_difficulty")
        
        except Exception as e:
            logger.error(f"Failed to get network difficulty from MMFP: {e}")
        
        return None
    
    async def get_pool_stats(self, url: str, coin: str, **kwargs) -> Optional[PoolStats]:
        """
        Get pool statistics from MMFP API.
        """
        try:
            api_url = self._get_api_url(url)
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{api_url}/api/v1/{coin.upper()}/metrics/pool",
                    timeout=aiohttp.ClientTimeout(total=self.API_TIMEOUT)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Extract hashrate (prefer 5m average)
                        hashrate_data = data.get("hashrate", {})
                        hashrate = hashrate_data.get("5m") or hashrate_data.get("1m") or 0
                        
                        return PoolStats(
                            hashrate=hashrate,
                            active_workers=data.get("active_miners"),
                            blocks_found=data.get("blocks_found"),
                            network_difficulty=data.get("network_comparison", {}).get("network_difficulty"),
                            additional_stats={
                                "pool_percentage": data.get("network_comparison", {}).get("pool_percentage"),
                                "estimated_time_to_block": data.get("network_comparison", {}).get("estimated_time_to_block"),
                                "shares_1m": data.get("shares", {}).get("1m", {}),
                                "shares_5m": data.get("shares", {}).get("5m", {}),
                                "shares_15m": data.get("shares", {}).get("15m", {})
                            }
                        )
        
        except Exception as e:
            logger.error(f"Failed to get pool stats from MMFP: {e}")
        
        return None
    
    async def get_blocks(
        self, 
        url: str, 
        coin: str, 
        hours: int = 24,
        **kwargs
    ) -> List[PoolBlock]:
        """
        Get recent blocks from MMFP.
        Note: As of current API, MMFP doesn't have a blocks endpoint.
        This method returns empty list but is here for future support.
        """
        # TODO: When MMFP adds /api/v1/{coin}/blocks endpoint, implement here
        logger.debug("MMFP blocks endpoint not yet implemented")
        return []
    
    async def get_worker_stats(
        self,
        url: str,
        coin: str,
        worker_name: str,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """
        Get worker-specific statistics from MMFP.
        """
        try:
            api_url = self._get_api_url(url)
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{api_url}/api/v1/{coin.upper()}/metrics/miners",
                    timeout=aiohttp.ClientTimeout(total=self.API_TIMEOUT)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        workers = data.get("workers", [])
                        
                        # Find matching worker
                        for worker in workers:
                            worker_full_name = worker.get("worker_name", "")
                            # Match by worker name (format: address.WorkerName)
                            if worker_name.lower() in worker_full_name.lower():
                                return {
                                    "worker_name": worker_full_name,
                                    "is_active": worker.get("is_active"),
                                    "user_agent": worker.get("current_user_agent"),
                                    "hashrate": worker.get("current_hashrate"),
                                    "valid_shares": worker.get("current_valid_shares"),
                                    "invalid_shares": worker.get("current_invalid_shares"),
                                    "best_share_difficulty": worker.get("best_share_difficulty"),
                                    "best_share_network_difficulty": worker.get("best_share_network_difficulty"),
                                    "best_share_block_height": worker.get("best_share_block_height"),
                                    "last_seen_at": worker.get("last_seen_at")
                                }
        
        except Exception as e:
            logger.error(f"Failed to get worker stats from MMFP: {e}")
        
        return None
    
    def get_config_schema(self) -> Dict[str, Any]:
        """
        MMFP doesn't require additional config beyond URL/port.
        """
        return {
            "type": "object",
            "properties": {
                "info": {
                    "type": "string",
                    "title": "Setup Information",
                    "description": f"MMFP Solutions is a local solo pool. Install from: {self.documentation_url}"
                }
            }
        }
    
    async def get_dashboard_data(
        self,
        url: str,
        coin: str,
        username: Optional[str] = None,
        **kwargs
    ) -> Optional[DashboardTileData]:
        """
        Get all dashboard tile data in one optimized call.
        MMFP provides comprehensive metrics in a single API call.
        """
        try:
            api_url = self._get_api_url(url)
            
            async with aiohttp.ClientSession() as session:
                # Single API call for all data
                async with session.get(
                    f"{api_url}/api/v1/{coin.upper()}/metrics/pool",
                    timeout=aiohttp.ClientTimeout(total=self.API_TIMEOUT)
                ) as response:
                    if response.status != 200:
                        return None
                    
                    data = await response.json()
                    
                    # Extract network comparison data
                    network_comp = data.get("network_comparison", {})
                    hashrate_data = data.get("hashrate", {})
                    shares_data = data.get("shares", {})
                    
                    # Calculate shares for last 24h (use 15m window as proxy)
                    shares_15m = shares_data.get("15m", {})
                    shares_valid = shares_15m.get("valid", 0)
                    shares_invalid = shares_15m.get("invalid", 0)
                    shares_stale = shares_15m.get("stale", 0)
                    shares_total = shares_15m.get("total", 1)
                    
                    # Calculate reject rate
                    reject_rate = 0.0
                    if shares_total > 0:
                        reject_rate = ((shares_invalid + shares_stale) / shares_total) * 100
                    
                    # Pool hashrate (prefer 5m average)
                    pool_hashrate = hashrate_data.get("5m") or hashrate_data.get("1m") or 0
                    
                    return DashboardTileData(
                        # Tile 1: Health (assume healthy if we got data)
                        health_status=True,
                        health_message="Connected",
                        latency_ms=None,  # Would need separate timing
                        
                        # Tile 2: Network Stats
                        network_difficulty=network_comp.get("network_difficulty"),
                        pool_hashrate=pool_hashrate,
                        estimated_time_to_block=network_comp.get("estimated_time_to_block"),
                        pool_percentage=network_comp.get("pool_percentage"),
                        
                        # Tile 3: Shares (last 15m as proxy)
                        shares_valid=shares_valid,
                        shares_invalid=shares_invalid,
                        shares_stale=shares_stale,
                        reject_rate=round(reject_rate, 2),
                        
                        # Tile 4: Blocks
                        blocks_found_24h=data.get("blocks_found", 0),
                        currency=coin.upper(),
                        
                        # Metadata
                        last_updated=datetime.utcnow(),
                        supports_earnings=False,  # Solo pool - no earnings API
                        supports_balance=False
                    )
        
        except Exception as e:
            logger.error(f"Failed to get dashboard data from MMFP: {e}")
            return None


# Auto-register this plugin
PoolRegistry.register(MMFPIntegration())
