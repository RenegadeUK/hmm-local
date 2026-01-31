"""
NerdMiners Pool Service
Handles pool stats API integration for pool.nerdminers.org
"""
import httpx
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class NerdMinersService:
    """Service for interacting with NerdMiners Pool API"""
    
    BASE_URL = "https://pool.nerdminers.org"
    TIMEOUT = 10.0
    
    @staticmethod
    def is_nerdminers_pool(url: str, port: int) -> bool:
        """Check if a pool is NerdMiners pool"""
        return "pool.nerdminers.org" in url.lower() and port == 3333
    
    @staticmethod
    async def get_pool_status() -> Optional[Dict[str, Any]]:
        """
        Get pool status from API
        GET https://pool.nerdminers.org/pool/pool.status
        """
        try:
            async with httpx.AsyncClient(timeout=NerdMinersService.TIMEOUT) as client:
                response = await client.get(f"{NerdMinersService.BASE_URL}/pool/pool.status")
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch NerdMiners pool status: {e}")
            return None
    
    @staticmethod
    async def get_user_stats(wallet_address: str) -> Optional[Dict[str, Any]]:
        """
        Get user stats from API
        GET https://pool.nerdminers.org/users/<Wallet_Address>
        """
        try:
            async with httpx.AsyncClient(timeout=NerdMinersService.TIMEOUT) as client:
                response = await client.get(f"{NerdMinersService.BASE_URL}/users/{wallet_address}")
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch NerdMiners user stats for {wallet_address}: {e}")
            return None
    
    @staticmethod
    def format_stats_summary(raw_stats: Optional[Dict], pool_stats: Optional[Dict] = None) -> Optional[Dict]:
        """
        Format NerdMiners stats for display in NerdMinersTile
        User data: workers, hashrate1m, shares, lastshare, bestshare, bestever
        Pool data: Workers (total), diff
        
        Pool status returns array of objects, first one has Workers count
        """
        if not raw_stats:
            return None
        
        try:
            # Extract pool stats if available (pool_stats is an array)
            pool_workers = 0
            pool_diff = 0
            if pool_stats and isinstance(pool_stats, list) and len(pool_stats) > 0:
                pool_workers = pool_stats[0].get("Workers", 0)
            if pool_stats and isinstance(pool_stats, list) and len(pool_stats) > 2:
                pool_diff = pool_stats[2].get("diff", 0)
            
            return {
                "workers": raw_stats.get("workers", 0),
                "hashrate": raw_stats.get("hashrate1m", "0 H/s"),
                "shares": int(raw_stats.get("shares", 0)),
                "lastShare": raw_stats.get("lastshare"),
                "bestShare": raw_stats.get("bestshare", 0),
                "bestEver": raw_stats.get("bestever", 0),
                "poolTotalWorkers": pool_workers,
                "poolDifficulty": pool_diff
            }
        except Exception as e:
            logger.error(f"Error formatting NerdMiners stats: {e}")
            return None
