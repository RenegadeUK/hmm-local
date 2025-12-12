"""
Avalon Nano 3 / 3S adapter using cgminer TCP API
"""
import socket
import json
import asyncio
from typing import Dict, List, Optional
from adapters.base import MinerAdapter, MinerTelemetry


class AvalonNanoAdapter(MinerAdapter):
    """Adapter for Avalon Nano 3 / 3S miners"""
    
    MODES = ["low", "med", "high"]
    DEFAULT_PORT = 4028
    
    def __init__(self, miner_id: int, miner_name: str, ip_address: str, port: Optional[int] = None, config: Optional[Dict] = None):
        super().__init__(miner_id, miner_name, ip_address, port or self.DEFAULT_PORT, config)
    
    async def get_telemetry(self) -> Optional[MinerTelemetry]:
        """Get telemetry from cgminer API"""
        try:
            # Get summary
            summary = await self._cgminer_command("summary")
            if not summary:
                return None
            
            # Get estats for power calculation
            estats = await self._cgminer_command("estats")
            
            # Get pool info
            pools = await self._cgminer_command("pools")
            
            # Parse telemetry
            summary_data = summary.get("SUMMARY", [{}])[0]
            
            # Hashrate is in MH/s, convert to GH/s
            hashrate = summary_data.get("MHS 5s", 0) / 1000.0  # GH/s
            shares_accepted = summary_data.get("Accepted", 0)
            shares_rejected = summary_data.get("Rejected", 0)
            
            # Get temperature, power, and current mode from estats
            temperature = self._get_temperature(estats)
            power_watts = self._calculate_power(estats)
            current_mode = self._detect_current_mode(estats)
            
            # Get active pool
            pool_in_use = None
            if pools and "POOLS" in pools:
                for pool in pools["POOLS"]:
                    if pool.get("Status") == "Alive" and pool.get("Priority") == 0:
                        pool_in_use = pool.get("URL")
                        break
            
            return MinerTelemetry(
                miner_id=self.miner_id,
                hashrate=hashrate,
                temperature=temperature,
                power_watts=power_watts,
                shares_accepted=shares_accepted,
                shares_rejected=shares_rejected,
                pool_in_use=pool_in_use,
                extra_data={"summary": summary_data, "current_mode": current_mode}
            )
        except Exception as e:
            print(f"❌ Failed to get telemetry from Avalon Nano {self.ip_address}: {e}")
            return None
    
    def _detect_current_mode(self, estats: Optional[Dict]) -> Optional[str]:
        """Detect current mode from WORKMODE field"""
        if not estats or "STATS" not in estats:
            return None
        
        try:
            stats_data = estats["STATS"][0]
            mm_id = stats_data.get("MM ID0", "")
            
            # Parse WORKMODE from MM ID0 string (e.g., WORKMODE[2])
            # WORKMODE values: 0=low, 1=med, 2=high (most common mapping)
            if "WORKMODE[" in mm_id:
                start = mm_id.index("WORKMODE[") + 9
                end = mm_id.index("]", start)
                workmode = int(mm_id[start:end])
                
                # Map workmode to mode name
                mode_map = {
                    0: "low",
                    1: "med", 
                    2: "high"
                }
                return mode_map.get(workmode)
            
            return None
        except Exception as e:
            print(f"⚠️ Failed to detect mode: {e}")
            return None
    
    def _get_temperature(self, estats: Optional[Dict]) -> Optional[float]:
        """Get temperature from estats MM ID string"""
        if not estats or "STATS" not in estats:
            return None
        
        try:
            stats_data = estats["STATS"][0]
            mm_id = stats_data.get("MM ID0", "")
            
            # Parse TAvg from MM ID0 string (e.g., TAvg[89])
            if "TAvg[" in mm_id:
                start = mm_id.index("TAvg[") + 5
                end = mm_id.index("]", start)
                return float(mm_id[start:end])
            
            return None
        except Exception as e:
            print(f"⚠️ Failed to get temperature: {e}")
            return None
    
    def _calculate_power(self, estats: Optional[Dict]) -> Optional[float]:
        """Calculate power from PS[] fields in MM ID string"""
        if not estats or "STATS" not in estats:
            return None
        
        try:
            stats_data = estats["STATS"][0]
            mm_id = stats_data.get("MM ID0", "")
            
            # Parse PS array from MM ID0 string (e.g., PS[0 0 27445 4 0 3782 133])
            if "PS[" in mm_id:
                start = mm_id.index("PS[") + 3
                end = mm_id.index("]", start)
                ps_str = mm_id[start:end]
                ps_values = [int(x) for x in ps_str.split()]
                
                if len(ps_values) >= 7:
                    raw_power_code = ps_values[5]  # 6th value (index 5) = 3782
                    millivolts = ps_values[2]      # 3rd value (index 2) = 27445
                    
                    if millivolts > 0:
                        watts = raw_power_code / (millivolts / 1000.0)
                        print(f"⚡ Power calculation: raw={raw_power_code}, mV={millivolts}, watts={watts:.2f}W")
                        return watts
            
            return None
        except Exception as e:
            print(f"⚠️ Failed to calculate power: {e}")
            return None
    
    async def set_mode(self, mode: str) -> bool:
        """Set operating mode"""
        if mode not in self.MODES:
            print(f"❌ Invalid mode: {mode}. Valid modes: {self.MODES}")
            return False
        
        try:
            # Map mode to frequency preset (MHz values for Avalon Nano)
            # Low ~200MHz (~60W), Med ~250MHz (~120W), High ~300MHz (~180W)
            freq_map = {
                "low": 200,
                "med": 250,
                "high": 300
            }
            
            freq = freq_map.get(mode, 250)
            print(f"📝 Setting Avalon Nano frequency to {freq} MHz for mode '{mode}'")
            result = await self._cgminer_command(f"ascset|0,freq,{freq}")
            print(f"✅ Frequency set result: {result}")
            
            return result is not None
        except Exception as e:
            print(f"❌ Failed to set mode on Avalon Nano: {e}")
            return False
    
    async def get_available_modes(self) -> List[str]:
        """Get available modes"""
        return self.MODES
    
    async def switch_pool(self, pool_url: str, pool_port: int, pool_user: str, pool_password: str) -> bool:
        """Switch mining pool - Avalon Nano has 3 fixed pool slots (0, 1, 2)
        
        Strategy: Since cgminer doesn't support removepool, we must work within the 3-slot constraint.
        We'll check if the desired pool exists in any slot, and if not, we'll reconfigure one of the
        3 slots by manually updating it via the web interface or accepting the limitation.
        
        For now, we check existing pools and only switch if the pool already exists.
        """
        try:
            # Construct username as pool_user.miner_name
            full_username = f"{pool_user}.{self.miner_name}"
            
            # Construct full pool URL with stratum protocol and port
            full_pool_url = f"stratum+tcp://{pool_url}:{pool_port}"
            
            print(f"🔄 Switching to pool: {full_pool_url} with user: {full_username}")
            
            # Get current pools
            pools_result = await self._cgminer_command("pools")
            if not pools_result or "POOLS" not in pools_result:
                print("❌ Failed to get current pools")
                return False
            
            print(f"📋 Found {len(pools_result['POOLS'])} pool slots:")
            for pool in pools_result["POOLS"]:
                active = "✅ ACTIVE" if pool.get("Stratum Active") else "⚪"
                print(f"  {active} [{pool['POOL']}] {pool['URL']} - {pool['User']}")
            
            # Check if the desired pool exists in any slot (match by URL only, not user)
            existing_slot = None
            for pool in pools_result["POOLS"]:
                pool_url_normalized = pool["URL"].lower().replace("stratum+tcp://", "")
                target_url_normalized = full_pool_url.lower().replace("stratum+tcp://", "")
                
                if pool_url_normalized == target_url_normalized:
                    existing_slot = pool["POOL"]
                    print(f"✨ Pool found at slot {existing_slot}")
                    break
            
            if existing_slot is not None:
                # Pool exists, switch to it
                print(f"🔀 Switching to pool slot {existing_slot}")
                switch_result = await self._cgminer_command(f"switchpool|{existing_slot}")
                if not switch_result:
                    print(f"❌ Failed to switch to pool {existing_slot}")
                    return False
                
                # Enable the pool
                await self._cgminer_command(f"enablepool|{existing_slot}")
                await asyncio.sleep(1.5)
                
                # Verify
                verify_result = await self._cgminer_command("pools")
                if verify_result and "POOLS" in verify_result:
                    for pool in verify_result["POOLS"]:
                        if pool["POOL"] == existing_slot and pool.get("Stratum Active"):
                            print(f"✅ Successfully switched to slot {existing_slot}: {pool['URL']}")
                            return True
                
                print(f"⚠️ Switch command sent but verification unclear")
                return True
            else:
                # Pool doesn't exist in the 3 slots
                print(f"❌ Pool {full_pool_url} not found in any of the 3 available slots")
                print(f"⚠️  Avalon Nano has 3 fixed pool slots that must be manually configured")
                print(f"⚠️  Please configure this pool via the miner's web interface first")
                print(f"📝 Current pools on device:")
                for pool in pools_result["POOLS"]:
                    print(f"    [{pool['POOL']}] {pool['URL']}")
                return False
            
        except Exception as e:
            print(f"❌ Failed to switch pool: {e}")
            return False
    
    async def restart(self) -> bool:
        """Restart miner"""
        try:
            result = await self._cgminer_command("restart")
            return result is not None
        except Exception as e:
            print(f"❌ Failed to restart Avalon Nano: {e}")
            return False
    
    async def is_online(self) -> bool:
        """Check if miner is online"""
        try:
            result = await self._cgminer_command("summary")
            return result is not None
        except:
            return False
    
    async def _cgminer_command(self, command: str) -> Optional[Dict]:
        """Send command to cgminer API"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((self.ip_address, self.port))
            
            # Send command
            cmd = {"command": command.split("|")[0], "parameter": command.split("|")[1] if "|" in command else ""}
            sock.sendall(json.dumps(cmd).encode())
            
            # Receive response
            response = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response += chunk
            
            sock.close()
            
            # Parse JSON response - cgminer returns multiple JSON objects separated by null bytes
            # Split on null byte and take the first valid JSON
            decoded = response.decode('utf-8', errors='ignore')
            
            # Remove null bytes and extra characters
            decoded = decoded.strip('\x00').strip()
            
            # Try to find the first complete JSON object
            if decoded:
                # cgminer often returns JSON with trailing null bytes or extra data
                # Find the end of the first JSON object
                brace_count = 0
                json_end = -1
                for i, char in enumerate(decoded):
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            json_end = i + 1
                            break
                
                if json_end > 0:
                    json_str = decoded[:json_end]
                    return json.loads(json_str)
            
            return json.loads(decoded)
        except Exception as e:
            print(f"⚠️ cgminer command failed: {e}")
            return None
