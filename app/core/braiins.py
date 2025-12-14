"""
Braiins Pool API Integration Service
"""
import aiohttp
from typing import Optional, Dict, Any


class BraiinsPoolService:
    """Service for interacting with Braiins Pool API"""
    
    BASE_URL = "https://pool.braiins.com/accounts"
    POOL_URL = "stratum.braiins.com"
    POOL_PORT = 3333
    
    @staticmethod
    def is_braiins_pool(url: str, port: int) -> bool:
        """Check if a pool URL/port combination is Braiins Pool"""
        return "braiins.com" in url.lower() and port == BraiinsPoolService.POOL_PORT
    
    @staticmethod
    async def get_workers(api_token: str) -> Optional[Dict[str, Any]]:
        """
        Get workers information from Braiins Pool API
        
        Args:
            api_token: SlushPool-Auth-Token for authentication
            
        Returns:
            Dict with workers data or None if request fails
        """
        headers = {
            "SlushPool-Auth-Token": api_token,
            "Accept": "application/json"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{BraiinsPoolService.BASE_URL}/workers/json/btc",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        print(f"Braiins API error (workers): {response.status}")
                        return None
        except Exception as e:
            print(f"Failed to fetch Braiins workers: {e}")
            return None
    
    @staticmethod
    async def get_profile(api_token: str) -> Optional[Dict[str, Any]]:
        """
        Get profile/balance information from Braiins Pool API
        
        Args:
            api_token: SlushPool-Auth-Token for authentication
            
        Returns:
            Dict with profile data or None if request fails
        """
        headers = {
            "SlushPool-Auth-Token": api_token,
            "Accept": "application/json"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{BraiinsPoolService.BASE_URL}/profile/json/btc/",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        print(f"Braiins API error (profile): {response.status}")
                        return None
        except Exception as e:
            print(f"Failed to fetch Braiins profile: {e}")
            return None
    
    @staticmethod
    async def get_rewards(api_token: str) -> Optional[Dict[str, Any]]:
        """
        Get daily rewards from Braiins Pool API
        
        Args:
            api_token: SlushPool-Auth-Token for authentication
            
        Returns:
            Dict with rewards data or None if request fails
        """
        headers = {
            "SlushPool-Auth-Token": api_token,
            "Accept": "application/json"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{BraiinsPoolService.BASE_URL}/rewards/json/btc/",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        print(f"Braiins API error (rewards): {response.status}")
                        return None
        except Exception as e:
            print(f"Failed to fetch Braiins rewards: {e}")
            return None
    
    @staticmethod
    def format_stats_summary(workers_data: Optional[Dict], profile_data: Optional[Dict], 
                            rewards_data: Optional[Dict]) -> Dict[str, Any]:
        """
        Format Braiins Pool data into a summary
        
        Args:
            workers_data: Workers API response
            profile_data: Profile API response
            rewards_data: Rewards API response
            
        Returns:
            Formatted statistics dictionary
        """
        summary = {
            "workers_online": 0,
            "workers_offline": 0,
            "total_hashrate": 0,
            "current_balance": 0,
            "today_reward": 0,
            "all_time_reward": 0
        }
        
        # Parse workers data for hashrate
        if workers_data and "btc" in workers_data:
            workers_btc = workers_data["btc"]
            # Calculate total hashrate from individual workers
            total_hashrate_5m = 0
            total_hashrate_24h = 0
            workers_online = 0
            workers_offline = 0
            
            for worker_name, worker_data in workers_btc.items():
                if isinstance(worker_data, dict):
                    state = worker_data.get("state", "")
                    if state == "active":
                        workers_online += 1
                    else:
                        workers_offline += 1
                    
                    # Sum up hashrate from all workers
                    total_hashrate_5m += worker_data.get("hash_rate_5m", 0)
                    total_hashrate_24h += worker_data.get("hash_rate_24h", 0)
            
            summary["workers_online"] = workers_online
            summary["workers_offline"] = workers_offline
            summary["total_hashrate"] = total_hashrate_24h
            summary["hashrate_5m"] = BraiinsPoolService._format_hashrate(total_hashrate_5m)
            summary["hashrate_24h"] = BraiinsPoolService._format_hashrate(total_hashrate_24h)
        
        # Parse profile data (has balance and reward info)
        if profile_data and "btc" in profile_data:
            btc_data = profile_data["btc"]
            
            # Convert BTC strings to satoshis (multiply by 100000000)
            try:
                summary["current_balance"] = int(float(btc_data.get("current_balance", "0")) * 100000000)
                summary["today_reward"] = int(float(btc_data.get("today_reward", "0")) * 100000000)
                summary["all_time_reward"] = int(float(btc_data.get("all_time_reward", "0")) * 100000000)
            except (ValueError, TypeError):
                pass
        
        # Could parse rewards_data for more detailed daily history if needed
        
        return summary
    
    @staticmethod
    def _format_hashrate(hashrate: float) -> str:
        """Format hashrate with appropriate unit (Braiins returns TH/s)"""
        if hashrate == 0:
            return "0 TH/s"
        elif hashrate >= 1000:
            return f"{hashrate / 1000:.2f} PH/s"
        elif hashrate >= 1:
            return f"{hashrate:.2f} TH/s"
        elif hashrate >= 0.001:
            return f"{hashrate * 1000:.2f} GH/s"
        else:
            return f"{hashrate * 1000000:.2f} MH/s"
