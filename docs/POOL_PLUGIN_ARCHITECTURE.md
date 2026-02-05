# Pool Plugin Architecture

**Version:** 1.0.0  
**Date:** 5 February 2026  
**Feature Branch:** feature/pool-plugin-dashboard

## Overview

The Pool Plugin Architecture provides a unified, extensible system for integrating multiple mining pool services into HMM-Local. This replaces the previous hardcoded pool implementations with a plugin-based registry system that automatically discovers and manages pool integrations.

## Architecture Components

### 1. Base Pool Integration (`app/integrations/base_pool.py`)

The foundation of the plugin system. All pool integrations extend `BasePoolIntegration`.

**Key Classes:**
- `BasePoolIntegration` - Abstract base class for pool plugins
- `DashboardTileData` - Standardized data structure for dashboard tiles
- `PoolHealthStatus` - Health check response format
- `PoolBlock` - Block data structure
- `PoolStats` - Pool statistics structure

**Required Plugin Properties:**
```python
@property
@abstractmethod
def pool_type(self) -> str:
    """Unique identifier (e.g., 'solopool', 'braiins', 'mmfp')"""

@property
@abstractmethod
def display_name(self) -> str:
    """Human-readable name (e.g., 'Braiins Pool')"""

@property
@abstractmethod
def documentation_url(self) -> str:
    """Link to pool documentation"""

@property
@abstractmethod
def supports_coins(self) -> List[str]:
    """List of supported coins (e.g., ['BTC', 'BCH', 'DGB'])"""

@property
@abstractmethod
def requires_api_key(self) -> bool:
    """Whether pool requires API authentication"""
```

**Required Plugin Methods:**
```python
async def detect(self, url: str, port: int, **kwargs) -> bool:
    """Auto-detect if URL/port points to this pool type"""

async def health_check(self, url: str, port: int, **kwargs) -> PoolHealthStatus:
    """Check pool connectivity and health"""

async def get_dashboard_data(self, url: str, port: int, **kwargs) -> DashboardTileData:
    """Fetch data for 4 dashboard tiles"""
```

### 2. Pool Registry (`app/integrations/pools/__init__.py`)

Central registry that discovers and manages all pool plugins.

**Features:**
- Automatic plugin discovery via `PoolRegistry.register()`
- Pool detection by URL/port
- Health monitoring
- Dashboard data aggregation

**Usage:**
```python
from integrations.pools import PoolRegistry

# Auto-detect pool type
pool_plugin = await PoolRegistry.detect_pool(url, port)

# Get health status
health = await PoolRegistry.check_pool_health(url, port, pool_type)

# Fetch dashboard data
data = await PoolRegistry.get_pool_dashboard_data(url, port, pool_type, **config)
```

### 3. Dashboard Service Layer (`app/core/dashboard_pool_service.py`)

Orchestrates pool data fetching with caching and aggregation.

**Key Features:**
- 30-second cache TTL for all pool data
- Platform tile aggregation across all pools
- Per-pool tile generation
- Parallel data fetching from multiple pools

**API Endpoints:**
- `GET /api/dashboard/pools/platform-tiles` - Consolidated 4-tile summary across all pools
- `GET /api/dashboard/pools` - Per-pool 4-tile breakdown
- `GET /api/dashboard/pools?pool_id={id}` - Specific pool tiles

**Platform Tiles Structure:**
```json
{
  "tile_1_health": {
    "total_pools": 3,
    "healthy_pools": 2,
    "unhealthy_pools": 1,
    "avg_latency_ms": 150.5,
    "status": "healthy"
  },
  "tile_2_network": {
    "total_pool_hashrate": 1234567890.0,
    "total_network_difficulty": 98765432109876.0,
    "avg_pool_percentage": 0.0125,
    "estimated_time_to_block": "7 days"
  },
  "tile_3_shares": {
    "total_valid": 50000,
    "total_invalid": 25,
    "total_stale": 5,
    "avg_reject_rate": 0.06
  },
  "tile_4_blocks": {
    "total_blocks_24h": 3,
    "total_earnings_24h": 0.00012345,
    "currencies": ["BTC", "BCH", "DGB"]
  }
}
```

**Per-Pool Tiles Structure:**
```json
{
  "pool_uuid": {
    "pool_id": "pool_uuid",
    "pool_type": "solopool",
    "display_name": "Solopool.org",
    "supports_coins": ["BTC", "BCH", "DGB", "BC2"],
    "tile_1_health": { ... },
    "tile_2_network": { ... },
    "tile_3_shares": { ... },
    "tile_4_blocks": { ... },
    "last_updated": "2026-02-05T12:00:00Z",
    "supports_earnings": false,
    "supports_balance": false
  }
}
```

## Implemented Pool Plugins

### 1. MMFP Pool Integration (`app/integrations/pools/mmfp_plugin.py`)

**Pool Type:** `mmfp`  
**Display Name:** MMFP Pool  
**Supported Coins:** BTC, BCH, DGB  
**Requires API Key:** No  
**Detection:** HTTP GET to `/stats` returns 200

**API Endpoints:**
- `GET /stats` - Pool statistics (hashrate, network difficulty, workers)
- `GET /blocks/recent` - Recent blocks found (24h)

**Dashboard Data:**
- Tile 1: Pool health status, latency
- Tile 2: Pool hashrate, network difficulty, pool %, ETTB
- Tile 3: Not available (no shares data)
- Tile 4: Blocks found in last 24h

### 2. Solopool Integration (`app/integrations/pools/solopool_plugin.py`)

**Pool Type:** `solopool`  
**Display Name:** Solopool.org  
**Supported Coins:** BTC, BCH, DGB, BC2  
**Requires API Key:** No  
**Detection:** Port-based (3333=DGB, 3334=BTC, 3335=BCH, 3336=BC2)

**API Endpoints:**
- `GET /api/stats` - Pool stats per coin
- `GET /api/blocks` - Block history per coin
- `GET /api/accounts/{username}` - Account stats (shares, paid)

**Pool Configurations:**
```python
POOL_CONFIGS = {
    "DGB": {"url": "dgb-sha.solopool.org", "ports": [3333, 8033]},
    "BCH": {"url": "bch.solopool.org", "ports": [3335, 8035]},
    "BTC": {"url": "btc.solopool.org", "ports": [3334, 8034]},
    "BC2": {"url": "bc2.solopool.org", "ports": [3336, 8036]}
}
```

**Dashboard Data:**
- Tile 1: Pool connectivity, worker count
- Tile 2: Pool hashrate, network difficulty, ETTB calculation
- Tile 3: Valid shares (from account data)
- Tile 4: Blocks found 24h, time to last block

**Special Features:**
- Parallel API calls to `/api/stats` and `/api/blocks`
- Auto-detects coin by port number
- Calculates estimated time to block based on pool hashrate vs network difficulty

### 3. Braiins Pool Integration (`app/integrations/pools/braiins_plugin.py`)

**Pool Type:** `braiins`  
**Display Name:** Braiins Pool  
**Supported Coins:** BTC  
**Requires API Key:** Yes (SlushPool-Auth-Token)  
**Detection:** URL contains "braiins" or "slushpool"

**API Endpoints:**
- `GET /accounts/workers/json/btc` - Worker status, hashrate
- `GET /accounts/profile/json/btc/` - Balance (pending/confirmed)
- `GET /accounts/rewards/json/btc/` - Daily earnings

**Authentication:**
```python
headers = {
    "SlushPool-Auth-Token": api_token
}
```

**Dashboard Data:**
- Tile 1: Worker status (online/offline count)
- Tile 2: Pool hashrate (5m average from workers)
- Tile 3: Worker count as proxy for shares
- Tile 4: Today's earnings, confirmed/pending balance

**Special Features:**
- Converts satoshis to BTC for all balance/earnings displays
- Tracks worker online/offline status
- Calculates today's earnings from rewards API

**Data Conversions:**
```python
btc_value = satoshis / 100000000
```

## Frontend Integration

### API Client (`ui-react/src/lib/api.ts`)

**New Functions:**
```typescript
poolsAPI.getPlatformTiles() // GET /api/dashboard/pools/platform-tiles
poolsAPI.getPoolTiles(poolId?: string) // GET /api/dashboard/pools
```

**TypeScript Interfaces:**
- `PlatformTilesResponse` - 4 consolidated tiles
- `PoolTilesResponse` - Dictionary of pool IDs to tile sets
- `PoolTileSet` - 4 tiles per pool

### Dashboard Component (`ui-react/src/pages/Dashboard.tsx`)

**React Query Hooks:**
```typescript
// Platform tiles (30s refresh)
const { data: platformTiles } = useQuery<PlatformTilesResponse>({
  queryKey: ["pools", "platform-tiles"],
  queryFn: () => poolsAPI.getPlatformTiles(),
  refetchInterval: 30000
});

// Per-pool tiles (30s refresh)
const { data: poolTiles } = useQuery<PoolTilesResponse>({
  queryKey: ["pools", "tiles"],
  queryFn: () => poolsAPI.getPoolTiles(),
  refetchInterval: 30000
});
```

**Dashboard Sections:**
1. **Original Stats** - Workers, Power, Cost, Best Share (unchanged)
2. **Pool Platform Summary** - 4 consolidated tiles across all pools
3. **Per-Pool Sections** - Each pool gets its own 4-tile breakdown
4. **Legacy Tiles** - Temporarily preserved for comparison

## Creating a New Pool Plugin

### Step 1: Create Plugin File

Create `app/integrations/pools/yourpool_plugin.py`:

```python
from integrations.base_pool import BasePoolIntegration, DashboardTileData, PoolHealthStatus
from typing import Optional
import aiohttp
import logging

logger = logging.getLogger(__name__)

class YourPoolIntegration(BasePoolIntegration):
    pool_type = "yourpool"
    display_name = "Your Pool Name"
    documentation_url = "https://yourpool.example.com/docs"
    supports_coins = ["BTC", "BCH"]
    requires_api_key = False  # or True if needed
    
    async def detect(self, url: str, port: int, **kwargs) -> bool:
        """Auto-detect if this is your pool"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://{url}:{port}/your-api-endpoint", timeout=5) as resp:
                    return resp.status == 200
        except:
            return False
    
    async def health_check(self, url: str, port: int, **kwargs) -> PoolHealthStatus:
        """Check pool health"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://{url}:{port}/health", timeout=5) as resp:
                    if resp.status == 200:
                        return PoolHealthStatus(is_healthy=True)
                    return PoolHealthStatus(is_healthy=False, error_message="Unhealthy")
        except Exception as e:
            return PoolHealthStatus(is_healthy=False, error_message=str(e))
    
    async def get_dashboard_data(self, url: str, port: int, **kwargs) -> DashboardTileData:
        """Fetch data for dashboard tiles"""
        try:
            # Fetch your pool's API data
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://{url}:{port}/stats") as resp:
                    data = await resp.json()
            
            # Map to DashboardTileData
            return DashboardTileData(
                # Tile 1: Health
                health_status=True,
                health_message=f"{data['workers']} workers online",
                latency_ms=123.45,
                
                # Tile 2: Network
                network_difficulty=data['network_difficulty'],
                pool_hashrate=data['pool_hashrate'],
                estimated_time_to_block="5 days",
                pool_percentage=0.01,
                
                # Tile 3: Shares
                shares_valid=data['valid_shares'],
                shares_invalid=data['invalid_shares'],
                shares_stale=0,
                reject_rate=0.05,
                
                # Tile 4: Blocks/Earnings
                blocks_found_24h=data['blocks_24h'],
                estimated_earnings_24h=None,  # For solo pools
                currency="BTC",
                confirmed_balance=None,  # For managed pools
                pending_balance=None,
                
                # Metadata
                supports_earnings=False,  # True if pool tracks earnings
                supports_balance=False   # True if pool shows balances
            )
        except Exception as e:
            logger.error(f"Failed to get dashboard data: {e}")
            return DashboardTileData(
                health_status=False,
                health_message=f"Error: {str(e)}"
            )
```

### Step 2: Register Plugin

Add to `app/integrations/pools/__init__.py`:

```python
from .yourpool_plugin import YourPoolIntegration

# Register with the pool registry
PoolRegistry.register(YourPoolIntegration())
```

### Step 3: Test

The plugin will automatically:
- Appear in pool detection
- Show up in health checks
- Render on the dashboard with 4 tiles
- Aggregate into platform tiles

No Dashboard component changes needed!

## Database Schema

Pools are stored in the `pools` table:

```sql
CREATE TABLE pools (
    id UUID PRIMARY KEY,
    pool_type VARCHAR(50),  -- 'solopool', 'braiins', 'mmfp', etc.
    name VARCHAR(255),
    url VARCHAR(255),
    port INTEGER,
    username VARCHAR(255),
    config JSON,  -- Pool-specific config (api_key, etc.)
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

## Performance Considerations

### Caching Strategy
- **Platform tiles**: Cached for 30 seconds
- **Per-pool tiles**: Cached for 30 seconds
- **Pool health checks**: Cached for 60 seconds

### Parallel Execution
All pool data fetches execute in parallel using `asyncio.gather()`:
```python
pool_data = await asyncio.gather(
    *[plugin.get_dashboard_data(...) for plugin in plugins],
    return_exceptions=True
)
```

### Error Handling
- Failed pool fetches return exceptions, don't crash aggregation
- Unhealthy pools still show in tiles (with error state)
- Retries with exponential backoff (via aiohttp timeout)

## Migration Guide

### From Legacy System

**Old Pattern (Hardcoded):**
```python
# app/core/solopool.py
class SolopoolIntegration:
    # Hardcoded implementation
    pass

# app/api/settings.py
@router.get("/settings/solopool/stats")
async def get_solopool_stats():
    # Custom endpoint
    pass
```

**New Pattern (Plugin-Based):**
```python
# app/integrations/pools/solopool_plugin.py
class SolopoolIntegration(BasePoolIntegration):
    # Extends base class
    pass

# Automatic via registry
pool_data = await PoolRegistry.get_pool_dashboard_data(...)
```

### Breaking Changes
- Old endpoints `/settings/solopool`, `/settings/braiins` deprecated
- Custom pool tile components replaced with unified rendering
- Pool data now flows through `DashboardPoolService`

## Testing Checklist

- [ ] Pool auto-detection works for each plugin
- [ ] Health checks return accurate status
- [ ] Dashboard tiles show correct data
- [ ] Platform tiles aggregate properly
- [ ] Caching works (30s TTL)
- [ ] Parallel fetching doesn't cause race conditions
- [ ] Error handling shows appropriate messages
- [ ] WebSocket updates trigger re-fetch
- [ ] New plugins appear automatically

## Future Enhancements

### Planned Features
- [ ] NerdMiners plugin migration
- [ ] Plugin marketplace/community plugins
- [ ] Per-pool notification rules
- [ ] Historical pool performance analytics
- [ ] Pool comparison view
- [ ] Automatic pool failover based on health

### API Extensions
- [ ] `POST /pools` - Add pool via UI
- [ ] `PUT /pools/{id}` - Update pool config
- [ ] `DELETE /pools/{id}` - Remove pool
- [ ] `GET /pools/discover` - Network scan for pools

## Support

**Documentation:** `/docs/POOL_PLUGIN_ARCHITECTURE.md`  
**Example Plugins:** `app/integrations/pools/`  
**Issues:** GitHub Issues on hmm-local repository

---

**Last Updated:** 5 February 2026  
**Authors:** DANVIC.dev  
**License:** See project LICENSE
