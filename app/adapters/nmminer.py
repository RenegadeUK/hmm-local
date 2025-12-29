"""
NMMiner ESP32 adapter (UDP telemetry + config)
"""
import asyncio
import socket
import json
from typing import Dict, List, Optional
from adapters.base import MinerAdapter, MinerTelemetry


class NMMinerAdapter(MinerAdapter):
    """
    Adapter for NMMiner ESP32 (lottery miner)
    - Telemetry via UDP broadcast on port 12345
    - Configuration via UDP on port 12347
    - No power metrics, no tuning, telemetry + pool control only
    """
    
    TELEMETRY_PORT = 12345
    CONFIG_PORT = 12347
    
    def __init__(self, miner_id: int, miner_name: str, ip_address: str, port: Optional[int] = None, config: Optional[Dict] = None):
        super().__init__(miner_id, miner_name, ip_address, port, config)
        self.last_telemetry: Optional[Dict] = None
    
    async def get_telemetry(self) -> Optional[MinerTelemetry]:
        """
        Get telemetry from last received UDP broadcast or database fallback.
        Note: Telemetry collection happens via UDP listener service,
        not direct polling.
        """
        # Try UDP broadcast data first
        if self.last_telemetry:
            try:
                data = self.last_telemetry
                
                return MinerTelemetry(
                    miner_id=self.miner_id,
                    hashrate=data.get("Hashrate", 0) / 1_000_000_000,  # Convert to GH/s
                    temperature=data.get("Temp", 0),
                    power_watts=None,  # No power metrics available
                    shares_accepted=data.get("Shares", 0),
                    shares_rejected=0,  # Not provided
                    pool_in_use=data.get("PoolInUse"),
                    extra_data={
                        "rssi": data.get("RSSI"),
                        "uptime": data.get("Uptime"),
                        "firmware": data.get("Firmware")
                    }
                )
            except Exception as e:
                print(f"❌ Failed to parse NMMiner telemetry: {e}")
        
        # Fallback to database if no UDP telemetry available
        try:
            from core.database import AsyncSessionLocal, Telemetry
            from sqlalchemy import select
            
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Telemetry)
                    .where(Telemetry.miner_id == self.miner_id)
                    .order_by(Telemetry.timestamp.desc())
                    .limit(1)
                )
                db_telemetry = result.scalar_one_or_none()
                
                if db_telemetry:
                    print(f"📊 Using database fallback telemetry for NMMiner {self.miner_id}")
                    return MinerTelemetry(
                        miner_id=self.miner_id,
                        hashrate=db_telemetry.hashrate,
                        temperature=db_telemetry.temperature,
                        power_watts=db_telemetry.power_watts,
                        shares_accepted=db_telemetry.shares_accepted,
                        shares_rejected=db_telemetry.shares_rejected,
                        pool_in_use=db_telemetry.pool_in_use,
                        extra_data=db_telemetry.data or {},
                        timestamp=db_telemetry.timestamp
                    )
        except Exception as e:
            print(f"⚠️ Failed to fetch database telemetry fallback: {e}")
        
        return None
    
    def update_telemetry(self, telemetry_data: Dict):
        """Update telemetry from UDP listener"""
        self.last_telemetry = telemetry_data
    
    async def get_mode(self) -> Optional[str]:
        """Get current operating mode - NMMiner doesn't support persistent modes"""
        return None
    
    async def set_mode(self, mode: str) -> bool:
        """NMMiner does not support mode tuning"""
        print("⚠️ NMMiner does not support mode changes")
        return False
    
    async def get_available_modes(self) -> List[str]:
        """NMMiner has no configurable modes"""
        return []
    
    async def switch_pool(self, pool_url: str, pool_port: int, pool_user: str, pool_password: str) -> bool:
        """
        Switch pool via UDP config message.
        Sends to specific IP or "0.0.0.0" for all devices.
        """
        try:
            # Construct username as pool_user.miner_name
            full_username = f"{pool_user}.{self.miner_name}"
            
            # Construct full pool URL with port
            full_pool_url = f"{pool_url}:{pool_port}"
            
            config = {
                "PrimaryPool": full_pool_url,
                "PrimaryAddress": full_username,
                "PrimaryPassword": pool_password
            }
            
            # Send UDP config
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(2)
            
            target_ip = self.ip_address if self.ip_address != "0.0.0.0" else "255.255.255.255"
            sock.sendto(json.dumps(config).encode(), (target_ip, self.CONFIG_PORT))
            sock.close()
            
            print(f"📤 Sent pool config to NMMiner at {target_ip}")
            return True
        except Exception as e:
            print(f"❌ Failed to switch pool on NMMiner: {e}")
            return False
    
    async def restart(self) -> bool:
        """NMMiner restart not supported via UDP"""
        print("⚠️ NMMiner restart not supported")
        return False
    
    async def is_online(self) -> bool:
        """Check if we've received recent telemetry"""
        if not self.last_telemetry:
            return False
        
        # Consider online if telemetry received in last 2 minutes
        from datetime import datetime, timedelta
        last_update = self.last_telemetry.get("_received_at")
        if last_update:
            return datetime.utcnow() - last_update < timedelta(minutes=2)
        
        return False


class NMMinerUDPListener:
    """
    UDP listener service for NMMiner telemetry broadcasts.
    Should be run as a background service in the scheduler.
    """
    
    def __init__(self, adapters: Dict[str, NMMinerAdapter]):
        self.adapters = adapters  # Map of IP -> adapter
        self.running = False
    
    async def start(self):
        """Start UDP listener"""
        self.running = True
        
        # Create UDP socket using asyncio protocol
        loop = asyncio.get_event_loop()
        
        # Create UDP endpoint
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: self._UDPProtocol(self),
            local_addr=("0.0.0.0", NMMinerAdapter.TELEMETRY_PORT)
        )
        
        print(f"📡 NMMiner UDP listener started on port {NMMinerAdapter.TELEMETRY_PORT}")
        
        # Keep running until stopped
        try:
            while self.running:
                await asyncio.sleep(1)
        finally:
            transport.close()
    
    class _UDPProtocol(asyncio.DatagramProtocol):
        """Internal UDP protocol handler"""
        
        def __init__(self, listener):
            self.listener = listener
            super().__init__()
        
        def datagram_received(self, data, addr):
            """Handle received UDP datagram"""
            try:
                # Parse JSON telemetry
                telemetry = json.loads(data.decode())
                source_ip = addr[0]
                
                # DEBUG: Log raw telemetry data
                print(f"📡 Received NMMiner telemetry from {source_ip}:")
                print(f"   Keys: {list(telemetry.keys())}")
                print(f"   Data: {json.dumps(telemetry, indent=2)}")
                
                # Add timestamp
                from datetime import datetime
                telemetry["_received_at"] = datetime.utcnow()
                
                # Update adapter if exists
                if source_ip in self.listener.adapters:
                    adapter = self.listener.adapters[source_ip]
                    adapter.update_telemetry(telemetry)
                    
                    # Schedule telemetry save (don't await in datagram_received)
                    asyncio.create_task(self.listener._save_telemetry(adapter, telemetry))
                else:
                    print(f"📡 Received NMMiner telemetry from unknown IP: {source_ip}")
            
            except Exception as e:
                print(f"⚠️ Error processing NMMiner telemetry: {e}")
                import traceback
                traceback.print_exc()
    
    async def _save_telemetry(self, adapter: NMMinerAdapter, data: Dict):
        """Save NMMiner telemetry to database"""
        try:
            from core.database import AsyncSessionLocal, Telemetry
            from core.mqtt import mqtt_client
            
            # Create telemetry object
            telemetry = adapter.last_telemetry
            if not telemetry:
                return
            
            # Convert to MinerTelemetry format
            miner_telemetry = await adapter.get_telemetry()
            if not miner_telemetry:
                return
            
            async with AsyncSessionLocal() as db:
                db_telemetry = Telemetry(
                    miner_id=adapter.miner_id,
                    timestamp=miner_telemetry.timestamp,
                    hashrate=miner_telemetry.hashrate,
                    temperature=miner_telemetry.temperature,
                    power_watts=miner_telemetry.power_watts,
                    shares_accepted=miner_telemetry.shares_accepted,
                    shares_rejected=miner_telemetry.shares_rejected,
                    pool_in_use=miner_telemetry.pool_in_use,
                    data=miner_telemetry.extra_data
                )
                db.add(db_telemetry)
                await db.commit()
            
            # Publish to MQTT
            mqtt_client.publish(
                f"telemetry/{adapter.miner_id}",
                miner_telemetry.to_dict()
            )
        
        except Exception as e:
            print(f"⚠️ Failed to save NMMiner telemetry: {e}")
    
    def stop(self):
        """Stop UDP listener"""
        self.running = False
