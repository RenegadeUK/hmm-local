"""
Bitaxe 601 adapter using REST API
"""
import aiohttp
from typing import Dict, List, Optional
from adapters.base import MinerAdapter, MinerTelemetry


class BitaxeAdapter(MinerAdapter):
    """Adapter for Bitaxe 601 miners"""
    
    MODES = ["eco", "standard", "turbo", "oc"]
    
    def __init__(self, miner_id: int, ip_address: str, port: Optional[int] = None, config: Optional[Dict] = None):
        super().__init__(miner_id, ip_address, port or 80, config)
        self.base_url = f"http://{ip_address}"
    
    async def get_telemetry(self) -> Optional[MinerTelemetry]:
        """Get telemetry from REST API"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/api/system/info", timeout=5) as response:
                    if response.status != 200:
                        return None
                    
                    data = await response.json()
                    
                    # Bitaxe returns hashRate already in GH/s
                    hashrate_ghs = data.get("hashRate", 0)
                    
                    # Build pool info from stratum settings
                    pool_url = data.get("stratumURL", "")
                    pool_port = data.get("stratumPort", "")
                    pool_info = f"{pool_url}:{pool_port}" if pool_url and pool_port else pool_url
                    
                    # Detect current mode based on frequency
                    frequency = data.get("frequency", 0)
                    current_mode = None
                    if frequency < 450:
                        current_mode = "eco"
                    elif frequency < 540:
                        current_mode = "standard"
                    elif frequency < 600:
                        current_mode = "turbo"
                    elif frequency > 0:
                        current_mode = "oc"
                    
                    return MinerTelemetry(
                        miner_id=self.miner_id,
                        hashrate=hashrate_ghs,
                        temperature=data.get("temp", 0),
                        power_watts=data.get("power", 0),
                        shares_accepted=data.get("sharesAccepted", 0),
                        shares_rejected=data.get("sharesRejected", 0),
                        pool_in_use=pool_info,
                        extra_data={
                            "frequency": data.get("frequency"),
                            "voltage": data.get("voltage"),
                            "uptime": data.get("uptimeSeconds"),
                            "asic_model": data.get("ASICModel"),
                            "version": data.get("version"),
                            "current_mode": current_mode
                        }
                    )
        except Exception as e:
            print(f"❌ Failed to get telemetry from Bitaxe {self.ip_address}: {e}")
            return None
    
    async def set_mode(self, mode: str) -> bool:
        """Set operating mode"""
        if mode not in self.MODES:
            print(f"❌ Invalid mode: {mode}. Valid modes: {self.MODES}")
            return False
        
        try:
            # Map mode to frequency/voltage presets
            mode_config = {
                "eco": {"frequency": 400, "voltage": 1100},
                "standard": {"frequency": 500, "voltage": 1150},
                "turbo": {"frequency": 575, "voltage": 1200},
                "oc": {"frequency": 625, "voltage": 1250}
            }
            
            config = mode_config.get(mode)
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/system/settings",
                    json=config,
                    timeout=5
                ) as response:
                    return response.status == 200
        except Exception as e:
            print(f"❌ Failed to set mode on Bitaxe: {e}")
            return False
    
    async def get_available_modes(self) -> List[str]:
        """Get available modes"""
        return self.MODES
    
    async def get_current_mode(self) -> Optional[str]:
        """Detect current mode based on frequency"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/api/system/info", timeout=5) as response:
                    if response.status != 200:
                        return None
                    
                    data = await response.json()
                    frequency = data.get("frequency", 0)
                    
                    # Map frequency ranges to modes (with tolerance)
                    if frequency < 450:
                        return "eco"  # ~400 MHz
                    elif frequency < 540:
                        return "standard"  # ~500 MHz
                    elif frequency < 600:
                        return "turbo"  # ~575 MHz
                    else:
                        return "oc"  # ~625 MHz
        except Exception as e:
            print(f"❌ Failed to detect mode on Bitaxe: {e}")
            return None
    
    async def switch_pool(self, pool_url: str, pool_user: str, pool_password: str) -> bool:
        """Switch mining pool"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/system/settings",
                    json={
                        "poolURL": pool_url,
                        "poolUser": pool_user,
                        "poolPassword": pool_password
                    },
                    timeout=5
                ) as response:
                    return response.status == 200
        except Exception as e:
            print(f"❌ Failed to switch pool on Bitaxe: {e}")
            return False
    
    async def restart(self) -> bool:
        """Restart miner"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.base_url}/api/system/restart", timeout=5) as response:
                    return response.status == 200
        except Exception as e:
            print(f"❌ Failed to restart Bitaxe: {e}")
            return False
    
    async def is_online(self) -> bool:
        """Check if miner is online"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/api/system/info", timeout=3) as response:
                    return response.status == 200
        except:
            return False
