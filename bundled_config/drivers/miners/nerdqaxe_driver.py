"""
NerdQaxe++ adapter using REST API
"""
import aiohttp
import logging
from typing import Dict, List, Optional
from adapters.base import MinerAdapter, MinerTelemetry
from core.utils import format_hashrate

logger = logging.getLogger(__name__)

__version__ = "1.1.1"


class NerdQaxeAdapter(MinerAdapter):
    """Adapter for NerdQaxe++ miners"""
    
    miner_type = "nerdqaxe"  # Required for driver loader
    STRATEGY_MODE_FIELD = "nerdqaxe_mode"
    CHAMPION_LOWEST_MODE = "eco"
    MODES = ["eco", "standard", "turbo", "oc"]
    
    def __init__(self, miner_id: int, miner_name: str, ip_address: str, port: Optional[int] = None, config: Optional[Dict] = None):
        super().__init__(miner_id, miner_name, ip_address, port or 80, config)
        self.base_url = f"http://{ip_address}"
    
    async def get_telemetry(self) -> Optional[MinerTelemetry]:
        """Get telemetry from REST API"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/api/system/info", timeout=5) as response:
                    if response.status != 200:
                        return None
                    
                    data = await response.json()
                    
                    # NerdQaxe returns hashRate in GH/s
                    hashrate_ghs = data.get("hashRate", 0)
                    hashrate_formatted = format_hashrate(hashrate_ghs, "GH/s")
                    
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
                        hashrate=hashrate_formatted["value"],  # Normalized to GH/s
                        temperature=data.get("temp", 0),
                        power_watts=data.get("power", 0),
                        shares_accepted=data.get("sharesAccepted", 0),
                        shares_rejected=data.get("sharesRejected", 0),
                        pool_difficulty=data.get("poolDifficulty"),
                        pool_in_use=pool_info,
                        extra_data={
                            "hashrate_unit": "GH/s",
                            "hashrate_display": hashrate_formatted["display"],
                            "raw_source": "nerdqaxe_rest",
                            "frequency_mhz": data.get("frequency"),
                            "voltage_mv": data.get("voltage"),
                            "uptime_seconds": data.get("uptimeSeconds"),
                            "asic_model": data.get("ASICModel"),
                            "firmware_version": data.get("version"),
                            "current_mode": current_mode,
                            "best_share_diff": data.get("bestDiff"),
                            "best_session_diff": data.get("bestSessionDiff"),
                            "free_heap_bytes": data.get("freeHeap"),
                            "core_voltage_mv": data.get("coreVoltage"),
                            "core_voltage_actual_mv": data.get("coreVoltageActual"),
                            "wifi_rssi": data.get("wifiStatus"),
                            "fan_speed_pct": data.get("fanSpeed"),
                            "fan_rpm": data.get("fanRpm"),
                            "vr_temp_c": data.get("vrTemp"),
                            "small_core_count": data.get("smallCoreCount"),
                            "pool_difficulty": data.get("poolDifficulty"),
                            "difficulty": data.get("poolDifficulty"),
                            "network_difficulty": data.get("networkDifficulty"),
                            "stratum_suggested_difficulty": data.get("stratumSuggestedDifficulty"),
                            "pool_response_ms": data.get("responseTime"),
                            "error_rate_pct": data.get("errorPercentage"),
                            "block_height": data.get("blockHeight"),
                            "vendor": {
                                "raw": {
                                    "system_info": dict(data)
                                }
                            },
                            # Legacy aliases (temporary compatibility during migration)
                            "frequency": data.get("frequency"),
                            "voltage": data.get("voltage"),
                            "uptime": data.get("uptimeSeconds"),
                            "version": data.get("version"),
                            "best_diff": data.get("bestDiff"),
                            "free_heap": data.get("freeHeap"),
                            "core_voltage": data.get("coreVoltage"),
                            "core_voltage_actual": data.get("coreVoltageActual"),
                            "fan_speed": data.get("fanSpeed"),
                            "vr_temp": data.get("vrTemp"),
                            "response_time": data.get("responseTime"),
                            "error_percentage": data.get("errorPercentage")
                        }
                    )
        except Exception as e:
            print(f"❌ Failed to get telemetry from NerdQaxe {self.ip_address}: {e}")
            return None
    
    async def get_mode(self) -> Optional[str]:
        """Get current operating mode"""
        return await self.get_current_mode()
    
    async def set_mode(self, mode: str) -> bool:
        """Set operating mode"""
        # Accept 'std' as alias for 'standard' (backward compatibility)
        if mode == "std":
            mode = "standard"
        
        if mode not in self.MODES:
            logger.error(f"Invalid mode for {self.miner_name}: {mode}. Valid modes: {self.MODES}")
            return False
        
        try:
            # Map mode to frequency/voltage presets
            mode_config = {
                "eco": {"frequency": 400, "voltage": 1100},
                "standard": {"frequency": 525, "voltage": 1150},
                "turbo": {"frequency": 575, "voltage": 1200},
                "oc": {"frequency": 625, "voltage": 1250}
            }
            
            config = mode_config.get(mode)
            
            async with aiohttp.ClientSession() as session:
                async with session.patch(
                    f"{self.base_url}/api/system",
                    json=config,
                    timeout=5
                ) as response:
                    if response.status in [200, 204]:
                        logger.info(f"Successfully set {self.miner_name} to mode {mode}")
                        return True
                    else:
                        response_text = await response.text()
                        logger.error(f"Failed to set mode on {self.miner_name}: HTTP {response.status} - {response_text}")
                        return False
        except Exception as e:
            logger.error(f"Exception setting mode on {self.miner_name}: {type(e).__name__}: {str(e)}")
            logger.exception(e)  # Log full traceback
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
                    elif frequency < 550:
                        return "standard"  # ~525 MHz
                    elif frequency < 600:
                        return "turbo"  # ~575 MHz
                    else:
                        return "oc"  # ~625 MHz
        except Exception as e:
            print(f"❌ Failed to detect mode on NerdQaxe: {e}")
            return None
    
    async def switch_pool(self, pool_url: str, pool_port: int, pool_user: str, pool_password: str) -> bool:
        """Switch mining pool and restart miner"""
        try:
            # Construct username as pool_user.miner_name
            full_username = f"{pool_user}.{self.miner_name}"
            
            print(f"🔄 NerdQaxe: Updating pool configuration...")
            async with aiohttp.ClientSession() as session:
                async with session.patch(
                    f"{self.base_url}/api/system",
                    json={
                        "stratumURL": pool_url,
                        "stratumPort": pool_port,
                        "stratumUser": full_username,
                        "stratumPassword": pool_password
                    },
                    timeout=5
                ) as response:
                    if response.status not in [200, 204]:
                        print(f"❌ Failed to update pool configuration")
                        return False
            
            # Restart miner to apply pool changes
            print(f"🔄 NerdQaxe: Restarting to apply pool changes...")
            restart_success = await self.restart()
            
            if restart_success:
                print(f"✅ NerdQaxe: Pool switched and miner restarted")
            else:
                print(f"⚠️ NerdQaxe: Pool updated but restart failed")
            
            return restart_success
        except Exception as e:
            print(f"❌ Failed to switch pool on NerdQaxe: {e}")
            return False
    
    async def restart(self) -> bool:
        """Restart miner"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.base_url}/api/system/restart", timeout=5) as response:
                    return response.status == 200
        except Exception as e:
            print(f"❌ Failed to restart NerdQaxe: {e}")
            return False
    
    async def is_online(self) -> bool:
        """Check if miner is online"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/api/system/info", timeout=3) as response:
                    return response.status == 200
        except:
            return False
    
    async def _apply_custom_settings(self, settings: Dict) -> bool:
        """Apply custom tuning settings (frequency, voltage)"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.patch(
                    f"{self.base_url}/api/system",
                    json=settings,
                    timeout=5
                ) as response:
                    return response.status in [200, 204]
        except Exception as e:
            print(f"❌ Failed to apply custom settings on NerdQaxe: {e}")
            return False
