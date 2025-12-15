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
    
    XMR_API_BASE = "https://xmr.solopool.org/api"
    XMR_POOLS = ["eu1.solopool.org"]
    XMR_PORT = 8010
    
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
    def is_solopool_xmr_pool(pool_url: str, pool_port: int) -> bool:
        """Check if pool is a Solopool XMR pool"""
        return pool_url in SolopoolService.XMR_POOLS and pool_port == SolopoolService.XMR_PORT
    
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
    async def get_xmr_account_stats(username: str) -> Optional[Dict[str, Any]]:
        """Fetch XMR account stats from Solopool API"""
        if not username:
            return None
        
        try:
            url = f"{SolopoolService.XMR_API_BASE}/accounts/{username}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data
                    else:
                        print(f"⚠️ Solopool XMR API returned status {response.status} for user {username}")
                        return None
        except Exception as e:
            print(f"❌ Failed to fetch Solopool XMR stats for {username}: {e}")
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
        
        # Sum up sharesValid from all workers
        workers = stats.get("workers", {})
        total_shares = sum(worker.get("sharesValid", 0) for worker in workers.values() if isinstance(worker, dict))
        
        # Get last block timestamp from payments array
        last_block_timestamp = None
        payments = stats.get("payments", [])
        if payments and len(payments) > 0:
            # Payments are ordered newest first
            last_block_timestamp = payments[0].get("timestamp")
        
        return {
            "hashrate": hashrate_formatted,
            "hashrate_raw": hashrate,
            "currentHashrate": stats.get("currentHashrate", 0),
            "workers": stats.get("workersOnline", 0),
            "workersTotal": stats.get("workersTotal", 0),
            "shares": total_shares,
            "paid": stats.get("paymentsTotal", 0),  # In satoshis
            "lastShare": stats_obj.get("lastShare"),
            "lastBlockTimestamp": last_block_timestamp,  # Timestamp of last block found
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
    
    @staticmethod
    async def get_bch_pool_stats() -> Optional[Dict[str, Any]]:
        """Fetch BCH pool/network stats from Solopool API"""
        try:
            url = f"{SolopoolService.BCH_API_BASE}/stats"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data
                    else:
                        print(f"⚠️ Solopool BCH pool stats API returned status {response.status}")
                        return None
        except Exception as e:
            print(f"❌ Failed to fetch Solopool BCH pool stats: {e}")
            return None
    
    @staticmethod
    async def get_dgb_pool_stats() -> Optional[Dict[str, Any]]:
        """Fetch DGB pool/network stats from Solopool API"""
        try:
            url = f"{SolopoolService.DGB_API_BASE}/stats"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data
                    else:
                        print(f"⚠️ Solopool DGB pool stats API returned status {response.status}")
                        return None
        except Exception as e:
            print(f"❌ Failed to fetch Solopool DGB pool stats: {e}")
            return None
    
    @staticmethod
    async def get_btc_pool_stats() -> Optional[Dict[str, Any]]:
        """Fetch BTC pool/network stats from Solopool API"""
        try:
            url = f"{SolopoolService.BTC_API_BASE}/stats"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data
                    else:
                        print(f"⚠️ Solopool BTC pool stats API returned status {response.status}")
                        return None
        except Exception as e:
            print(f"❌ Failed to fetch Solopool BTC pool stats: {e}")
            return None
    
    @staticmethod
    async def get_xmr_pool_stats() -> Optional[Dict[str, Any]]:
        """Fetch XMR pool/network stats from Solopool API"""
        try:
            url = f"{SolopoolService.XMR_API_BASE}/stats"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data
                    else:
                        print(f"⚠️ Solopool XMR pool stats API returned status {response.status}")
                        return None
        except Exception as e:
            print(f"❌ Failed to fetch Solopool XMR pool stats: {e}")
            return None
    
    @staticmethod    def calculate_ettb(network_hashrate: float, user_hashrate: float, block_time_seconds: int) -> Optional[Dict[str, Any]]:
        """
        Calculate Expected Time To Block (ETTB)
        
        Args:
            network_hashrate: Network hashrate in H/s
            user_hashrate: User's hashrate in H/s
            block_time_seconds: Average block time in seconds (600 for BTC, 600 for BCH, 15 for DGB)
        
        Returns:
            Dict with formatted ETTB or None if calculation not possible
        """
        if not network_hashrate or not user_hashrate or user_hashrate <= 0:
            return None
        
        # ETTB = (Network Hashrate / Your Hashrate) × Block Time
        ettb_seconds = (network_hashrate / user_hashrate) * block_time_seconds
        
        # Format into human-readable units
        if ettb_seconds < 60:
            return {"value": int(ettb_seconds), "unit": "seconds", "formatted": f"{int(ettb_seconds)}s"}
        elif ettb_seconds < 3600:
            minutes = ettb_seconds / 60
            return {"value": round(minutes, 1), "unit": "minutes", "formatted": f"{round(minutes, 1)}m"}
        elif ettb_seconds < 86400:
            hours = ettb_seconds / 3600
            return {"value": round(hours, 1), "unit": "hours", "formatted": f"{round(hours, 1)}h"}
        elif ettb_seconds < 31536000:  # Less than a year
            days = ettb_seconds / 86400
            return {"value": round(days, 1), "unit": "days", "formatted": f"{round(days, 1)}d"}
        else:
            years = ettb_seconds / 31536000
            return {"value": round(years, 1), "unit": "years", "formatted": f"{round(years, 1)}y"}
    
    @staticmethod
    def calculate_ticket_count(network_hashrate: float, user_hashrate: float) -> Optional[Dict[str, Any]]:
        """
        Calculate Ticket Count (TC) - your percentage of network hashrate
        
        Args:
            network_hashrate: Network hashrate in H/s
            user_hashrate: User's hashrate in H/s
        
        Returns:
            Dict with percentage and formatted string or None if calculation not possible
        """
        if not network_hashrate or not user_hashrate or network_hashrate <= 0:
            return None
        
        # TC = (Your Hashrate / Network Hashrate) × 100
        percentage = (user_hashrate / network_hashrate) * 100
        
        # Format based on magnitude
        if percentage >= 1:
            return {"percentage": percentage, "formatted": f"{percentage:.2f}%"}
        elif percentage >= 0.01:
            return {"percentage": percentage, "formatted": f"{percentage:.4f}%"}
        elif percentage >= 0.0001:
            return {"percentage": percentage, "formatted": f"{percentage:.6f}%"}
        else:
            # For very small percentages, use scientific notation
            return {"percentage": percentage, "formatted": f"{percentage:.2e}%"}

