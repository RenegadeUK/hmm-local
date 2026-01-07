"""
XMRig CPU Miner Adapter

XMRig API Documentation: https://xmrig.com/docs/miner/api

To enable the API in XMRig, add to your config.json:

{
    "api": {
        "id": null,
        "worker-id": null
    },
    "http": {
        "enabled": true,
        "host": "0.0.0.0",
        "port": 8080,
        "access-token": null,
        "restricted": true
    }
}

Or use command line arguments:
xmrig --http-enabled --http-host=0.0.0.0 --http-port=8080 --http-access-token=YOUR_TOKEN

Notes:
- If access-token is set, include it in the miner configuration
- Restricted mode (recommended) limits available API endpoints
- Default port is 8080 but can be changed
"""
import aiohttp
from typing import Dict, List, Optional
from adapters.base import MinerAdapter, MinerTelemetry


class XMRigAdapter(MinerAdapter):
    """Adapter for XMRig CPU miners"""
    
    def __init__(self, miner_id: int, miner_name: str, ip_address: str, port: int = 8080, config: Optional[Dict] = None):
        super().__init__(miner_id, miner_name, ip_address, port, config)
        self.access_token = config.get("access_token") if config else None
        self.base_url = f"http://{ip_address}:{port}"
    
    def _get_headers(self) -> Dict[str, str]:
        """Get HTTP headers with optional authorization"""
        headers = {"Content-Type": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers
    
    async def get_telemetry(self) -> Optional[MinerTelemetry]:
        """
        Get telemetry from XMRig API
        
        API endpoints:
        - GET /1/summary - Basic stats (hashrate, shares, uptime)
        - GET /2/summary - Detailed stats (includes temperature if available)
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/2/summary",
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status != 200:
                        return None
                    
                    data = await response.json()
                    
                    # Extract data from response
                    # XMRig returns hashrate in H/s, convert to KH/s
                    hashrate_hs = data.get("hashrate", {}).get("total", [0, 0, 0])[0]  # 10s average in H/s
                    hashrate_khs = (hashrate_hs / 1000.0) if hashrate_hs else 0
                    
                    # Keep in KH/s - CPU miners work in kilohash range, not gigahash
                    # (10 KH/s would show as 0.00001 GH/s which is confusing)
                    hashrate = hashrate_khs
                    
                    # Get shares
                    results = data.get("results", {})
                    shares_good = results.get("shares_good", 0)
                    shares_total = results.get("shares_total", 0)
                    shares_rejected = shares_total - shares_good if shares_total else 0
                    
                    # Get pool info
                    pool = data.get("connection", {}).get("pool", "")
                    
                    # Get temperature (if available - some systems report CPU temp)
                    temp = None
                    if "cpu" in data and "temp" in data["cpu"]:
                        temp = data["cpu"]["temp"]
                    
                    # CPU-specific mining data
                    cpu_data = data.get("cpu", {})
                    threads_enabled = cpu_data.get("enabled", 0)
                    threads_total = cpu_data.get("threads", 0)
                    
                    # Hugepages info (critical for RandomX performance)
                    hugepages = data.get("hugepages", [0, 0])  # [allocated, total]
                    hugepages_str = f"{hugepages[0]}/{hugepages[1]}" if len(hugepages) >= 2 else "Unknown"
                    
                    # Backend optimization (AVX2, AVX, SSE, etc.)
                    backend = cpu_data.get("backend", "Unknown")
                    
                    # Pool latency
                    connection = data.get("connection", {})
                    pool_ping = connection.get("ping", 0)
                    
                    # Get hashrate values with None checks for division
                    hashrate_totals = data.get("hashrate", {}).get("total", [0, 0, 0])
                    hashrate_1m_hs = hashrate_totals[1] if len(hashrate_totals) > 1 else 0
                    hashrate_15m_hs = hashrate_totals[2] if len(hashrate_totals) > 2 else 0
                    
                    extra_data = {
                        "hashrate_1m": (hashrate_1m_hs / 1000.0) if hashrate_1m_hs else 0,  # Convert H/s to KH/s
                        "hashrate_15m": (hashrate_15m_hs / 1000.0) if hashrate_15m_hs else 0,  # Convert H/s to KH/s
                        "hashrate_unit": "KH/s",
                        "threads_enabled": threads_enabled,
                        "threads_total": threads_total,
                        "cpu_brand": cpu_data.get("brand", "Unknown"),
                        "backend": backend,
                        "hugepages": hugepages_str,
                        "pool_ping": pool_ping,
                        "uptime": data.get("uptime", 0),
                        "version": data.get("version", "Unknown"),
                        "algo": data.get("algo", "Unknown"),
                        "difficulty": connection.get("diff", 0)
                    }
                    
                    return MinerTelemetry(
                        miner_id=self.miner_id,
                        hashrate=hashrate,
                        temperature=temp,
                        power_watts=None,  # XMRig doesn't report power
                        shares_accepted=shares_good,
                        shares_rejected=shares_rejected,
                        pool_in_use=pool,
                        extra_data=extra_data
                    )
        
        except Exception as e:
            print(f"XMRig telemetry error: {e}")
            return None
    
    async def get_mode(self) -> Optional[str]:
        """Get current operating mode - XMRig doesn't support persistent modes"""
        return None
    
    async def set_mode(self, mode: str) -> bool:
        """
        XMRig doesn't have preset modes like ASICs
        Could potentially adjust thread count, but not implemented
        """
        return False
    
    async def get_available_modes(self) -> List[str]:
        """XMRig doesn't have preset modes"""
        return []
    
    async def switch_pool(self, pool_url: str, pool_port: int, pool_user: str, pool_password: str) -> bool:
        """
        Switch pool using XMRig API
        Requires non-restricted API mode
        
        Note: This may not work if API is in restricted mode
        """
        try:
            # XMRig expects pool in format: pool_url:pool_port
            pool_address = f"{pool_url}:{pool_port}"
            
            payload = {
                "url": pool_address,
                "user": pool_user,
                "pass": pool_password,
                "keepalive": True
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.POST(
                    f"{self.base_url}/1/config",
                    headers=self._get_headers(),
                    json={"pools": [payload]},
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    return response.status == 204
        
        except Exception as e:
            print(f"XMRig pool switch error: {e}")
            return False
    
    async def restart(self) -> bool:
        """
        Restart XMRig
        Requires non-restricted API mode
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/1/restart",
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    return response.status in [200, 204]
        
        except Exception as e:
            print(f"XMRig restart error: {e}")
            return False
    
    async def is_online(self) -> bool:
        """Check if XMRig API is reachable"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/1/summary",
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=2)
                ) as response:
                    return response.status == 200
        except:
            return False
    
    async def pause(self) -> bool:
        """
        Pause mining
        Requires non-restricted API mode
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/1/pause",
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    return response.status in [200, 204]
        except Exception as e:
            print(f"XMRig pause error: {e}")
            return False
    
    async def resume(self) -> bool:
        """
        Resume mining after pause
        Requires non-restricted API mode
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/1/resume",
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    return response.status in [200, 204]
        except Exception as e:
            print(f"XMRig resume error: {e}")
            return False
