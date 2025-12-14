"""
Solopool.org integration service
"""
import aiohttp
from typing import Optional, Dict, Any
from datetime import datetime


class SolopoolService:
    """Service for interacting with Solopool.org API"""
    
    BCH_API_BASE = "https://bch.solopool.org/api"
    BCH_POOLS = ["eu2.solopool.org", "us1.solopool.org"]
    BCH_PORT = 8002
    
    DGB_API_BASE = "https://dgb-sha.solopool.org/api"
    DGB_POOLS = ["eu1.solopool.org", "us1.solopool.org"]
    DGB_PORT = 8004
    
    BTC_API_BASE = "https://btc.solopool.org/api"
    BTC_POOLS = ["eu3.solopool.org"]
    BTC_PORT = 8005
    
    @staticmethod
    def is_solopool_bch_pool(pool_url: str, pool_port: int) -> bool:
        """Check if pool is a Solopool BCH pool"""
        return pool_url in SolopoolService.BCH_POOLS and pool_port == SolopoolService.BCH_PORT
    
    @staticmethod
    def is_solopool_dgb_pool(pool_url: str, pool_port: int) -> bool:
        """Check if pool is a Solopool DGB pool"""
        return pool_url in SolopoolService.DGB_POOLS and pool_port == SolopoolService.DGB_PORT
    
    @staticmethod
    def is_solopool_btc_pool(pool_url: str, pool_port: int) -> bool:
        """Check if pool is a Solopool BTC pool"""
        return pool_url in SolopoolService.BTC_POOLS and pool_port == SolopoolService.BTC_PORT
    
    @staticmethod
    def extract_username(pool_user: str) -> str:
        """Extract username from pool user (remove .workername if present)"""
        # Pool user format is usually "username" or "username.workername"
        return pool_user.split('.')[0] if pool_user else ""
    
    @staticmethod
    async def get_bch_account_stats(username: str) -> Optional[Dict[str, Any]]:
        """Fetch BCH account stats from Solopool API"""
        if not username:
            return None
        
        try:
            url = f"{SolopoolService.BCH_API_BASE}/accounts/{username}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data
                    else:
                        print(f"⚠️ Solopool BCH API returned status {response.status} for user {username}")
                        return None
        except Exception as e:
            print(f"❌ Failed to fetch Solopool BCH stats for {username}: {e}")
            return None
    
    @staticmethod
    async def get_dgb_account_stats(username: str) -> Optional[Dict[str, Any]]:
        """Fetch DGB account stats from Solopool API"""
        if not username:
            return None
        
        try:
            url = f"{SolopoolService.DGB_API_BASE}/accounts/{username}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data
                    else:
                        print(f"⚠️ Solopool DGB API returned status {response.status} for user {username}")
                        return None
        except Exception as e:
            print(f"❌ Failed to fetch Solopool DGB stats for {username}: {e}")
            return None
    
    @staticmethod
    async def get_btc_account_stats(username: str) -> Optional[Dict[str, Any]]:
        """Fetch BTC account stats from Solopool API"""
        if not username:
            return None
        
        try:
            url = f"{SolopoolService.BTC_API_BASE}/accounts/{username}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data
                    else:
                        print(f"⚠️ Solopool BTC API returned status {response.status} for user {username}")
                        return None
        except Exception as e:
            print(f"❌ Failed to fetch Solopool BTC stats for {username}: {e}")
            return None
    
    @staticmethod
    def format_stats_summary(stats: Dict[str, Any]) -> Dict[str, Any]:
        """Format stats for display"""
        if not stats:
            return {}
        
        # API returns: hashrate, currentHashrate, workersOnline, workersTotal, 
        # paymentsTotal (in satoshis), stats.lastShare, stats.roundShares
        # earnings array has: period (seconds), blocks, amount, luck
        # Note: earnings[].luck is average luck for blocks FOUND in that period
        # Current round luck is in stats.currentLuck or stats.luck
        earnings = stats.get("earnings", [])
        
        # Get different time period stats
        earnings_map = {}
        for e in earnings:
            period = e.get("period")
            if period == 86400:  # 24 hours
                earnings_map["24h"] = e
            elif period == 604800:  # 7 days
                earnings_map["7d"] = e
            elif period == 2592000:  # 30 days
                earnings_map["30d"] = e
        
        # Extract current round luck - this is what users see on the website
        # Try multiple possible field locations
        stats_obj = stats.get("stats", {})
        current_luck = (
            stats_obj.get("currentLuck") or 
            stats_obj.get("luck") or
            stats.get("currentLuck") or
            stats.get("luck") or
            0
        )
        
        # Format hashrate for display
        hashrate = stats.get("currentHashrate") or stats.get("hashrate", 0)
        hashrate_formatted = SolopoolService._format_hashrate(hashrate)
        
        return {
            "hashrate": hashrate_formatted,
            "hashrate_raw": hashrate,
            "currentHashrate": stats.get("currentHashrate", 0),
            "workers": stats.get("workersOnline", 0),
            "workersTotal": stats.get("workersTotal", 0),
            "shares": stats_obj.get("roundShares", 0),
            "paid": stats.get("paymentsTotal", 0),  # In satoshis
            "lastShare": stats_obj.get("lastShare"),
            "current_luck": current_luck,  # Current round luck (what UI shows)
            "blocks_24h": earnings_map.get("24h", {}).get("blocks", 0),
            "luck_24h": earnings_map.get("24h", {}).get("luck", 0),
            "blocks_7d": earnings_map.get("7d", {}).get("blocks", 0),
            "luck_7d": earnings_map.get("7d", {}).get("luck", 0),
            "blocks_30d": earnings_map.get("30d", {}).get("blocks", 0),
            "luck_30d": earnings_map.get("30d", {}).get("luck", 0),
            "workers_detail": stats.get("workers", {}),  # Individual worker stats
            "raw": stats  # Keep full response for detailed view
        }
    
    @staticmethod
    def _format_hashrate(hashrate: float) -> str:
        """Format hashrate with appropriate unit"""
        if hashrate == 0:
            return "0 H/s"
        elif hashrate >= 1e15:
            return f"{hashrate / 1e15:.2f} PH/s"
        elif hashrate >= 1e12:
            return f"{hashrate / 1e12:.2f} TH/s"
        elif hashrate >= 1e9:
            return f"{hashrate / 1e9:.2f} GH/s"
        elif hashrate >= 1e6:
            return f"{hashrate / 1e6:.2f} MH/s"
        elif hashrate >= 1e3:
            return f"{hashrate / 1e3:.2f} KH/s"
        else:
            return f"{hashrate:.2f} H/s"
