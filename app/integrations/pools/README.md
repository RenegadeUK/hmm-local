# Pool Integration Plugin System

## Overview

HMM's pool plugin system allows third-party developers to add support for new mining pools without modifying core code. Plugins are automatically discovered and registered at startup.

## Creating a New Pool Plugin

### 1. Create Your Plugin File

Create a new file in `app/integrations/pools/` named `{yourpool}_plugin.py`:

```python
"""
Your Pool Name Integration
"""
from integrations.base_pool import (
    BasePoolIntegration,
    PoolHealthStatus,
    PoolBlock,
    PoolStats
)
from integrations.pool_registry import PoolRegistry

class YourPoolIntegration(BasePoolIntegration):
    pool_type = "yourpool"  # Unique identifier
    display_name = "Your Pool Name"
    documentation_url = "https://yourpool.example.com"
    supports_coins = ["BTC", "LTC"]  # Empty list = all coins
    requires_api_key = False  # Set True if API key needed
    
    async def detect(self, url: str, port: int) -> bool:
        """Auto-detect if URL belongs to your pool"""
        return "yourpool.com" in url.lower()
    
    async def get_health(self, url: str, port: int, **kwargs) -> PoolHealthStatus:
        """Check pool connectivity"""
        # Implement your health check
        return PoolHealthStatus(is_healthy=True)
    
    async def get_network_difficulty(self, coin: str, **kwargs) -> Optional[float]:
        """Get current network difficulty"""
        # Fetch from your pool's API
        return 1234567.89
    
    async def get_pool_stats(self, url: str, coin: str, **kwargs) -> Optional[PoolStats]:
        """Get pool statistics"""
        return PoolStats(
            hashrate=1234567890,
            active_workers=42,
            blocks_found=10
        )
    
    async def get_blocks(self, url: str, coin: str, hours: int = 24, **kwargs) -> List[PoolBlock]:
        """Get recent blocks"""
        return []
    
    def get_config_schema(self) -> Dict:
        """Define custom config fields"""
        return {
            "type": "object",
            "properties": {
                "api_key": {
                    "type": "string",
                    "title": "API Key",
                    "description": "Your pool API key"
                }
            }
        }

# Auto-register
PoolRegistry.register(YourPoolIntegration())
```

### 2. That's It!

Your plugin is automatically discovered and registered when HMM starts. No other code changes needed!

## Example: MMFP Solutions Plugin

See `app/integrations/pools/mmfp_plugin.py` for a complete working example.

## API Reference

### BasePoolIntegration Methods

#### Required Methods

- `detect(url, port) -> bool` - Auto-detect pool type
- `get_health(url, port) -> PoolHealthStatus` - Check connectivity
- `get_network_difficulty(coin) -> float` - Get network difficulty
- `get_pool_stats(url, coin) -> PoolStats` - Get pool stats
- `get_blocks(url, coin, hours) -> List[PoolBlock]` - Get recent blocks

#### Optional Methods

- `get_config_schema() -> Dict` - Define custom config fields
- `validate_config(config) -> bool` - Validate config
- `get_user_stats(url, coin, username) -> Dict` - User-specific stats
- `get_worker_stats(url, coin, worker_name) -> Dict` - Worker-specific stats

#### Dashboard Integration (CRITICAL)

**`get_dashboard_data(url, coin, username) -> DashboardTileData`**

This is the most important method for UI integration. It provides data for dashboard tiles.

**Dashboard Architecture:**

HMM has two types of dashboard tiles:

1. **PLATFORM TILES (4 tiles)** - Top of dashboard
   - Consolidated view across ALL pools
   - Automatically aggregated by HMM
   - Your plugin doesn't need to worry about this

2. **POOL TILES (4 tiles per pool)** - Below platform tiles
   - Individual breakdown for your specific pool
   - Your plugin provides this data via `get_dashboard_data()`

**Your Plugin's Responsibility:**

Provide accurate data for YOUR pool's 4 tiles. HMM will handle aggregation.

**Tile Structure:**

**Tile 1: Pool Health**
- `health_status` (bool) - Is pool reachable?
- `health_message` (str) - Status message ("Connected", "Error: timeout", etc.)
- `latency_ms` (float, optional) - API response time in milliseconds

**Tile 2: Network Stats**
- `network_difficulty` (float, optional) - Current network difficulty
- `pool_hashrate` (float, optional) - Pool's total hashrate in H/s
- `estimated_time_to_block` (str, optional) - Human readable estimate ("2 hours", "3 days")
- `pool_percentage` (float, optional) - Pool % of network hashrate (0-100)

**Tile 3: Shares (24h preferred)**
- `shares_valid` (int, optional) - Valid shares submitted
- `shares_invalid` (int, optional) - Invalid shares rejected
- `shares_stale` (int, optional) - Stale shares
- `reject_rate` (float, optional) - Percentage rejected (0-100)

**Tile 4: Earnings/Blocks (24h preferred)**
- `blocks_found_24h` (int, optional) - Blocks found in last 24 hours
- `estimated_earnings_24h` (float, optional) - Estimated earnings in native coin
- `currency` (str) - Coin ticker (BTC, DGB, BCH, etc.)
- `balances` (dict, optional) - `{"pending": 0.5, "confirmed": 1.2}`

**Implementation Example:**
```python
async def get_dashboard_data(self, url: str, coin: str, username: Optional[str] = None, **kwargs) -> Optional[DashboardTileData]:
    """Fetch all dashboard data in one optimized call."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{url}/api/stats") as response:
                data = await response.json()
                
                return DashboardTileData(
                    # Tile 1: Health
                    health_status=True,
                    health_message="Connected",
                    latency_ms=response.elapsed.total_seconds() * 1000,
                    
                    # Tile 2: Network
                    network_difficulty=data.get("network_difficulty"),
                    pool_hashrate=data.get("pool_hashrate"),
                    estimated_time_to_block="2 hours",
                    pool_percentage=0.01,
                    
                    # Tile 3: Shares
                    shares_valid=data.get("shares_valid_24h", 0),
                    shares_invalid=data.get("shares_invalid_24h", 0),
                    shares_stale=data.get("shares_stale_24h", 0),
                    reject_rate=2.5,
                    
                    # Tile 4: Earnings
                    blocks_found_24h=data.get("blocks_24h", 0),
                    estimated_earnings_24h=None,  # Solo pool - no estimate
                    currency=coin.upper(),
                    balances=None,  # Solo pool - no balance API
                    
                    # Metadata
                    last_updated=datetime.utcnow(),
                    supports_earnings=False,  # Set True if pool has earnings API
                    supports_balance=False    # Set True if pool has balance API
                )
    except Exception as e:
        logger.error(f"Dashboard data fetch failed: {e}")
        return None
```

**Notes:**
- Not all pools support all metrics - use `None` for unsupported fields
- HMM UI gracefully handles missing data (shows "N/A" or hides field)
- Optimize by fetching all data in one API call if possible
- Use `supports_earnings` and `supports_balance` flags to tell UI what's available

### Data Structures

#### PoolHealthStatus
```python
PoolHealthStatus(
    is_healthy=True,
    latency_ms=42.5,
    error_message=None,
    additional_info={}
)
```

#### PoolStats
```python
PoolStats(
    hashrate=1234567890,
    active_workers=42,
    blocks_found=10,
    network_difficulty=9876543.21,
    additional_stats={}
)
```

#### PoolBlock
```python
PoolBlock(
    height=123456,
    hash="abc123...",
    miner="worker_name",
    timestamp=1234567890,
    difficulty=1234567.89,
    network_difficulty=9876543.21,
    coin="BTC",
    reward=6.25,
    confirmed=True
)
```

## Testing Your Plugin

1. Place your plugin file in `app/integrations/pools/`
2. Restart HMM container
3. Check logs for "Registered pool integration: Your Pool Name"
4. Test pool detection:
   ```python
   from integrations.pool_registry import PoolRegistry
   
   pool_type = await PoolRegistry.detect_pool_type("yourpool.com", 3333)
   print(pool_type)  # Should print "yourpool"
   ```

## Plugin Distribution

To share your plugin:
1. Create a GitHub repository with your plugin file
2. Include README with installation instructions
3. Submit PR to HMM repository or distribute independently

Users can install by:
```bash
# Download plugin
wget https://raw.githubusercontent.com/you/yourpool-hmm/main/yourpool_plugin.py \
  -O /path/to/hmm/app/integrations/pools/yourpool_plugin.py

# Restart HMM
docker-compose restart
```

## Best Practices

1. **Error Handling**: Always catch exceptions and return appropriate error states
2. **Timeouts**: Use reasonable API timeouts (5-10 seconds)
3. **Logging**: Use `logger.info()`, `logger.warning()`, `logger.error()`
4. **Async**: All methods are async - use `aiohttp` for HTTP requests
5. **Documentation**: Add docstrings explaining your pool's specific requirements

## Need Help?

- Check existing plugins for examples
- Review `BasePoolIntegration` docstrings
- Open an issue on GitHub

---

**Pool Plugin System Version:** 1.0.0  
**Last Updated:** 5 February 2026
