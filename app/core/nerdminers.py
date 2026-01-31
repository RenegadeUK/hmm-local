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
        Returns 3 separate JSON objects separated by newlines:
        1. {runtime, lastupdate, Users, Workers, Idle, Disconnected}
        2. {hashrate1m, hashrate5m, ...}
        3. {diff, accepted, rejected, bestshare, SPS1m, ...}
        """
        try:
            async with httpx.AsyncClient(timeout=NerdMinersService.TIMEOUT) as client:
                response = await client.get(f"{NerdMinersService.BASE_URL}/pool/pool.status")
                response.raise_for_status()
                
                # Parse multiple JSON objects separated by newlines
                import json
                text = response.text.strip()
                json_objects = []
                for line in text.split('\n'):
                    if line.strip():
                        json_objects.append(json.loads(line))
                
                return json_objects
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
            # Log pool_stats structure for debugging
            logger.info(f"Pool stats received: {pool_stats}")
            logger.info(f"Pool stats type: {type(pool_stats)}")
            
            # Extract pool stats if available (pool_stats is an array)
            pool_workers = 0
            pool_diff = 0
            if pool_stats and isinstance(pool_stats, list) and len(pool_stats) > 0:
                logger.info(f"Pool stats[0]: {pool_stats[0]}")
                pool_workers = pool_stats[0].get("Workers", 0)
            if pool_stats and isinstance(pool_stats, list) and len(pool_stats) > 2:
                logger.info(f"Pool stats[2]: {pool_stats[2]}")
                pool_diff = pool_stats[2].get("diff", 0)
            
            # Format hashrate - NerdMiners API returns values like "941K" (941 KH/s) or "4.19" (4.19 GH/s)
            hashrate_raw = raw_stats.get("hashrate1m", "0")
            hashrate_formatted = NerdMinersService._format_hashrate(hashrate_raw)
            
            return {
                "workers": raw_stats.get("workers", 0),
                "hashrate": hashrate_formatted,
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
    
    @staticmethod
    def _format_hashrate(hashrate_str: str) -> str:
        """
        Format hashrate from NerdMiners API format to proper units
        API returns: "941K" = 941 KH/s, "4.19" = 4.19 GH/s, "9.68265G" = 9.68 GH/s
        """
        if not hashrate_str or hashrate_str == "0":
            return "0 H/s"
        
        try:
            # Check if it ends with a unit letter
            if hashrate_str[-1].isalpha():
                value = float(hashrate_str[:-1])
                unit = hashrate_str[-1].upper()
                
                if unit == 'K':
                    # Convert KH/s to proper format
                    if value >= 1000:
                        return f"{value / 1000:.2f} MH/s"
                    return f"{value:.2f} KH/s"
                elif unit == 'M':
                    # Convert MH/s to proper format
                    if value >= 1000:
                        return f"{value / 1000:.2f} GH/s"
                    return f"{value:.2f} MH/s"
                elif unit == 'G':
                    # Convert GH/s to proper format
                    if value >= 1000:
                        return f"{value / 1000:.2f} TH/s"
                    return f"{value:.2f} GH/s"
                elif unit == 'T':
                    return f"{value:.2f} TH/s"
            else:
                # No unit letter means it's in GH/s (default for pool)
                value = float(hashrate_str)
                if value >= 1000:
                    return f"{value / 1000:.2f} TH/s"
                elif value < 1:
                    return f"{value * 1000:.2f} MH/s"
                return f"{value:.2f} GH/s"
        except ValueError:
            logger.warning(f"Could not parse hashrate: {hashrate_str}")
            return hashrate_str
        
        return "0 H/s"
