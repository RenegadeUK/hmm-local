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
        Format NerdMiners stats for display
        Adapts the API response to match the format expected by PoolTile
        """
        if not raw_stats:
            return None
        
        try:
            # Extract relevant stats from API response
            # Adjust these field names based on actual API response structure
            return {
                "workers": raw_stats.get("workers", 0),
                "hashrate": raw_stats.get("hashrate", "0 H/s"),
                "shares": raw_stats.get("shares", 0),
                "lastShare": raw_stats.get("lastShare"),
                "paid": raw_stats.get("paid", 0),
                "balance": raw_stats.get("balance", 0),
                "blocks_24h": raw_stats.get("blocks_24h", 0),
                "blocks_7d": raw_stats.get("blocks_7d", 0),
                "blocks_30d": raw_stats.get("blocks_30d", 0),
                "current_luck": raw_stats.get("luck"),
                "ettb": {
                    "formatted": raw_stats.get("ettb", "Unknown")
                } if raw_stats.get("ettb") else None,
                "lastBlockTimestamp": raw_stats.get("lastBlockTime")
            }
        except Exception as e:
            logger.error(f"Error formatting NerdMiners stats: {e}")
            return None
