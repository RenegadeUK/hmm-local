"""
Base Pool Integration Interface

This module provides the abstract base class for all pool integrations.
Third-party developers can create new pool plugins by extending BasePoolIntegration.
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel
from enum import Enum


class MiningModel(str, Enum):
    """Mining model type"""
    SOLO = "solo"      # Solo mining - you get 100% of block reward when you find it
    POOL = "pool"      # Pool mining - shares earnings with other miners


class PoolTemplate(BaseModel):
    """
    Template defining a pre-configured pool endpoint.
    Plugins provide these templates to ensure compliance and prevent misconfiguration.
    """
    # Identity
    template_id: str                    # Unique ID: "dgb_eu1", "btc_braiins"
    display_name: str                   # UI display: "Solopool.org DGB (EU1)"
    
    # Connection
    url: str                            # Pool URL without protocol: "eu1.solopool.org"
    port: int                           # Stratum port: 8004
    
    # Mining Info
    coin: str                           # Coin symbol: "DGB", "BTC"
    mining_model: MiningModel           # "solo" or "pool"
    region: Optional[str] = None        # Geographic region: "EU", "US", "ASIA"
    
    # Capabilities (what data this pool provides)
    requires_auth: bool = False         # Requires API key/username for stats?
    supports_shares: bool = False       # Can show share statistics? (Tile 3)
    supports_earnings: bool = False     # Can show earnings estimates? (Tile 4)
    supports_balance: bool = False      # Can show account balance? (Tile 4)
    
    # Metadata
    description: Optional[str] = None   # Help text for users
    fee_percent: Optional[float] = None # Pool fee percentage (if disclosed)


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
    hashrate: Optional[Union[float, dict]] = None  # Accepts float or {display, value, unit} dict
    active_workers: Optional[int] = None
    blocks_found: Optional[int] = None
    network_difficulty: Optional[float] = None
    additional_stats: Dict[str, Any] = {}


class DashboardTileData(BaseModel):
    """
    Dashboard widget data for pool tiles.
    Plugins provide this data to populate the 4 standard dashboard tiles.
    
    ⚠️ MANDATORY REQUIREMENTS:
    Tile 1 fields (health_status, health_message, latency_ms) are REQUIRED.
    ALL plugins MUST populate these fields. Failure to do so will result in
    rejection during plugin registration.
    
    Tiles 2-4 are optional and depend on pool capabilities:
    - Tile 2: Network stats (optional but recommended)
    - Tile 3: Shares (FPPS/PPS pools only)
    - Tile 4: Earnings/Blocks (varies by pool type)
    """
    # ============================================================================
    # Tile 1: Pool Health — MANDATORY FOR ALL PLUGINS
    # ============================================================================
    health_status: bool = True          # REQUIRED: Is pool reachable?
    health_message: Optional[str] = None  # REQUIRED: Status message
    latency_ms: Optional[float] = None    # REQUIRED: Response time in ms
    
    # ============================================================================
    # Tile 2: Network Stats — OPTIONAL (public data, recommended)
    # ============================================================================
    network_difficulty: Optional[float] = None
    pool_hashrate: Optional[Union[float, dict]] = None  # Accepts float or {display, value, unit} dict
    estimated_time_to_block: Optional[str] = None
    pool_percentage: Optional[float] = None
    active_workers: Optional[int] = None  # Number of active workers for this user
    
    # ============================================================================
    # Tile 3: Shares — OPTIONAL (FPPS/PPS pools only, requires auth)
    # ============================================================================
    shares_valid: Optional[int] = None
    shares_invalid: Optional[int] = None
    shares_stale: Optional[int] = None
    reject_rate: Optional[float] = None
    
    # ============================================================================
    # Tile 4: Earnings/Blocks — OPTIONAL (varies by pool type)
    # ============================================================================
    blocks_found_24h: Optional[int] = None
    last_block_found: Optional[datetime] = None  # Timestamp of most recent block
    estimated_earnings_24h: Optional[float] = None
    currency: Optional[str] = None  # BTC, BCH, DGB, etc.
    confirmed_balance: Optional[float] = None
    pending_balance: Optional[float] = None
    
    # ============================================================================
    # Additional metadata
    # ============================================================================
    last_updated: Optional[datetime] = None
    supports_earnings: bool = False  # Does pool track earnings?
    supports_balance: bool = False  # Does pool show balance?


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
    def get_pool_templates(self) -> List[PoolTemplate]:
        """
        Return all available pool configuration templates.
        
        ⚠️ MANDATORY: Every plugin MUST provide at least one template.
        Templates define pre-validated pool endpoints that meet platform requirements.
        
        Returns:
            List of PoolTemplate objects
            
        Example:
            def get_pool_templates(self):
                return [
                    PoolTemplate(
                        template_id="dgb_eu1",
                        display_name="Solopool.org DGB (EU1)",
                        url="eu1.solopool.org",
                        port=8004,
                        coin="DGB",
                        mining_model=MiningModel.SOLO,
                        region="EU",
                        requires_auth=False,
                        supports_shares=False,
                        supports_earnings=False,
                        supports_balance=False,
                        description="European solo mining for DigiByte"
                    ),
                    # ... more templates
                ]
        """
        pass
    
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
    
    async def get_dashboard_data(
        self,
        url: str,
        coin: str,
        username: Optional[str] = None,
        **kwargs
    ) -> Optional[DashboardTileData]:
        """
        Get data for all 4 dashboard tiles in one call.
        This is the primary method HMM calls to populate dashboard widgets.
        
        ⚠️ MANDATORY TILE 1 REQUIREMENTS:
        ALL plugins MUST populate these fields in the returned DashboardTileData:
        - health_status (bool): True if pool is reachable, False otherwise
        - health_message (str): Status message ("Connected", "HTTP 500", etc.)
        - latency_ms (float): Response time in milliseconds
        
        Failure to populate Tile 1 fields will result in plugin rejection.
        
        Tiles 2-4 are optional and depend on pool capabilities.
        
        Args:
            url: Pool URL
            coin: Coin symbol  
            username: Pool username (if applicable)
            **kwargs: Pool-specific config (api_key, workers, etc.)
            
        Returns:
            DashboardTileData with all tile information, or None if unavailable
            
        Example Implementation:
            async def get_dashboard_data(self, url, coin, username, **kwargs):
                start_time = datetime.utcnow()
                
                try:
                    response = await http.get(f"{url}/api/stats")
                    latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                    
                    return DashboardTileData(
                        # MANDATORY: Tile 1
                        health_status=response.status == 200,
                        health_message="Connected" if response.ok else f"HTTP {response.status}",
                        latency_ms=latency_ms,
                        
                        # OPTIONAL: Tiles 2-4
                        pool_hashrate=data.get("hashrate"),
                        currency=coin.upper(),
                        ...
                    )
                except Exception as e:
                    return DashboardTileData(
                        health_status=False,
                        health_message=f"Error: {str(e)}",
                        latency_ms=None,
                        currency=coin.upper()
                    )
```
            
        Note:
            Plugins should implement this to provide efficient dashboard updates.
            Default implementation calls individual methods, but plugins can
            optimize by making a single API call.
        """
        # Default implementation: aggregate from individual methods
        try:
            health = await self.get_health(url, 0, **kwargs)
            stats = await self.get_pool_stats(url, coin, **kwargs)
            
            return DashboardTileData(
                health_status=health.is_healthy,
                health_message=health.error_message,
                latency_ms=health.latency_ms,
                network_difficulty=stats.network_difficulty if stats else None,
                pool_hashrate=stats.hashrate if stats else None,
                blocks_found_24h=stats.blocks_found if stats else None,
                last_updated=datetime.utcnow()
            )
        except Exception:
            return None
