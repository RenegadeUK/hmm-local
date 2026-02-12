"""
Base MinerAdapter interface
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from datetime import datetime


class MinerTelemetry:
    """Standardized telemetry data structure"""
    
    def __init__(
        self,
        miner_id: int,
        hashrate: Optional[float] = None,
        temperature: Optional[float] = None,
        power_watts: Optional[float] = None,
        shares_accepted: Optional[int] = None,
        shares_rejected: Optional[int] = None,
        pool_difficulty: Optional[float] = None,
        pool_in_use: Optional[str] = None,
        extra_data: Optional[Dict] = None
    ):
        self.miner_id = miner_id
        self.timestamp = datetime.utcnow()
        self.hashrate = hashrate
        self.temperature = temperature
        self.power_watts = power_watts
        self.shares_accepted = shares_accepted
        self.shares_rejected = shares_rejected
        self.pool_difficulty = pool_difficulty
        self.pool_in_use = pool_in_use
        self.extra_data = extra_data or {}
    
    def to_dict(self) -> Dict:
        """Convert to dictionary with structured hashrate format"""
        # Extract hashrate formatting from extra_data
        hashrate_unit = self.extra_data.get("hashrate_unit", "GH/s") if self.extra_data else "GH/s"
        hashrate_display = self.extra_data.get("hashrate_display", f"{self.hashrate:.2f} {hashrate_unit}") if self.extra_data else f"{self.hashrate:.2f} {hashrate_unit}"
        
        return {
            "miner_id": self.miner_id,
            "timestamp": self.timestamp.isoformat(),
            "hashrate": {
                "display": hashrate_display,
                "value": self.hashrate,  # Always in GH/s (normalized)
                "unit": hashrate_unit     # Always "GH/s"
            },
            "temperature": self.temperature,
            "power_watts": self.power_watts,
            "shares_accepted": self.shares_accepted,
            "shares_rejected": self.shares_rejected,
            "pool_in_use": self.pool_in_use,
            "extra_data": self.extra_data
        }


class MinerAdapter(ABC):
    """Base adapter interface for all miner types"""
    
    def __init__(self, miner_id: int, miner_name: str, ip_address: str, port: Optional[int] = None, config: Optional[Dict] = None):
        self.miner_id = miner_id
        self.miner_name = miner_name
        self.ip_address = ip_address
        self.port = port
        self.config = config or {}
    
    @abstractmethod
    async def get_telemetry(self) -> Optional[MinerTelemetry]:
        """Get current telemetry data from miner"""
        pass
    
    @abstractmethod
    async def get_mode(self) -> Optional[str]:
        """Get current operating mode"""
        pass
    
    @abstractmethod
    async def set_mode(self, mode: str) -> bool:
        """Set miner operating mode"""
        pass
    
    @abstractmethod
    async def get_available_modes(self) -> List[str]:
        """Get list of available operating modes"""
        pass
    
    @abstractmethod
    async def switch_pool(self, pool_url: str, pool_port: int, pool_user: str, pool_password: str) -> bool:
        """Switch to a different mining pool"""
        pass
    
    @abstractmethod
    async def restart(self) -> bool:
        """Restart the miner"""
        pass
    
    @abstractmethod
    async def is_online(self) -> bool:
        """Check if miner is reachable"""
        pass
