"""
Base Pool Integration Interface

This module provides the abstract base class for all pool integrations.
Third-party developers can create new pool plugins by extending BasePoolIntegration.
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel


class PoolHealthStatus(BaseModel):
    """Health status returned by pool integrations"""
    is_healthy: bool
    latency_ms: Optional[float] = None
    error_message: Optional[str] = None
    additional_info: Dict[str, Any] = {}


class PoolBlock(BaseModel):
    """Block data structure returned by pool integrations"""
    height: int
    hash: Optional[str] = None
    miner: str  # Miner name/worker
    timestamp: int  # Unix timestamp
    difficulty: float
    network_difficulty: float
    coin: str
    reward: Optional[float] = None
    confirmed: bool = False


class PoolStats(BaseModel):
    """Pool statistics structure"""
    hashrate: Optional[float] = None
    active_workers: Optional[int] = None
    blocks_found: Optional[int] = None
    network_difficulty: Optional[float] = None
    additional_stats: Dict[str, Any] = {}


class BasePoolIntegration(ABC):
    """
    Abstract base class for pool integrations.
    
    To create a new pool integration:
    1. Create a new file in app/integrations/pools/
    2. Extend this class
    3. Implement all abstract methods
    4. Register in __init__.py
    
    Example:
        class MyCustomPool(BasePoolIntegration):
            pool_type = "mycustom"
            display_name = "My Custom Pool"
            documentation_url = "https://example.com"
            
            async def detect(self, url: str, port: int) -> bool:
                # Detection logic
                return True
    """
    
    @property
    @abstractmethod
    def pool_type(self) -> str:
        """
        Unique identifier for this pool type.
        Must be lowercase, alphanumeric + underscore only.
        Examples: 'solopool', 'braiins', 'mmfp'
        """
        pass
    
    @property
    @abstractmethod
    def display_name(self) -> str:
        """
        Human-readable name shown in UI.
        Example: "MMFP Solutions (Local Solo Pool)"
        """
        pass
    
    @property
    def documentation_url(self) -> Optional[str]:
        """
        Link to pool documentation/website.
        Optional but recommended.
        """
        return None
    
    @property
    def supports_coins(self) -> List[str]:
        """
        List of supported coin symbols.
        Return empty list for all coins.
        Example: ['BTC', 'BCH', 'DGB', 'BC2']
        """
        return []
    
    @property
    def requires_api_key(self) -> bool:
        """Whether this pool requires an API key for statistics"""
        return False
    
    @abstractmethod
    async def detect(self, url: str, port: int) -> bool:
        """
        Detect if this integration can handle the given URL/port.
        
        Args:
            url: Pool URL or IP address
            port: Stratum port
            
        Returns:
            True if this integration recognizes the pool
            
        Example:
            async def detect(self, url: str, port: int) -> bool:
                if "mypool.com" in url:
                    return True
                # Try API ping
                try:
                    response = await http.get(f"http://{url}:8080/api/health")
                    return response.status == 200
                except:
                    return False
        """
        pass
    
    @abstractmethod
    async def get_health(self, url: str, port: int, **kwargs) -> PoolHealthStatus:
        """
        Check pool health/connectivity.
        
        Args:
            url: Pool URL or IP address
            port: Stratum port
            **kwargs: Additional pool-specific config (api_key, etc.)
            
        Returns:
            PoolHealthStatus with health information
        """
        pass
    
    @abstractmethod
    async def get_network_difficulty(self, coin: str, **kwargs) -> Optional[float]:
        """
        Get current network difficulty for a coin.
        
        Args:
            coin: Coin symbol (BTC, BCH, DGB, etc.)
            **kwargs: Pool-specific config
            
        Returns:
            Network difficulty as float, or None if unavailable
        """
        pass
    
    @abstractmethod
    async def get_pool_stats(self, url: str, coin: str, **kwargs) -> Optional[PoolStats]:
        """
        Get pool-wide statistics.
        
        Args:
            url: Pool URL or IP address
            coin: Coin symbol
            **kwargs: Pool-specific config (user, api_key, etc.)
            
        Returns:
            PoolStats object or None if unavailable
        """
        pass
    
    @abstractmethod
    async def get_blocks(
        self, 
        url: str, 
        coin: str, 
        hours: int = 24,
        **kwargs
    ) -> List[PoolBlock]:
        """
        Get recent blocks found by this pool.
        
        Args:
            url: Pool URL or IP address
            coin: Coin symbol
            hours: How many hours back to fetch
            **kwargs: Pool-specific config
            
        Returns:
            List of PoolBlock objects
        """
        pass
    
    def get_config_schema(self) -> Dict[str, Any]:
        """
        JSON schema for pool-specific configuration fields.
        Used to generate UI forms dynamically.
        
        Returns:
            JSON Schema dict
            
        Example:
            return {
                "type": "object",
                "properties": {
                    "api_key": {
                        "type": "string",
                        "title": "API Key",
                        "description": "Your pool API key"
                    }
                },
                "required": ["api_key"]
            }
        """
        return {
            "type": "object",
            "properties": {}
        }
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """
        Validate pool-specific configuration.
        
        Args:
            config: Configuration dictionary
            
        Returns:
            True if valid, False otherwise
        """
        return True
    
    async def get_user_stats(
        self,
        url: str,
        coin: str,
        username: str,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """
        Get user-specific statistics (optional).
        
        Args:
            url: Pool URL
            coin: Coin symbol
            username: Pool username
            **kwargs: Pool-specific config
            
        Returns:
            User stats dict or None if not supported
        """
        return None
    
    async def get_worker_stats(
        self,
        url: str,
        coin: str,
        worker_name: str,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """
        Get worker-specific statistics (optional).
        Useful for matching HMM miners to pool workers.
        
        Args:
            url: Pool URL
            coin: Coin symbol
            worker_name: Worker name
            **kwargs: Pool-specific config
            
        Returns:
            Worker stats dict or None if not supported
        """
        return None
