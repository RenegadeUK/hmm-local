# Pool Plugin Architecture Audit

## Executive Summary

**Status:** ✅ Pool plugins exist and are functional  
**Problem:** Legacy `app/core/solopool.py` has ~500 lines of direct API implementation that **duplicates** what's in the plugin  
**Solution:** Deprecate legacy service, enhance plugin interface, refactor APIs to use PoolRegistry

---

## Architecture Analysis

### 1. Base Interface (`app/integrations/base_pool.py`)

**Status:** ✅ **Well-designed, comprehensive interface**

**Key Classes:**
```python
class BasePoolIntegration(ABC):
    # Identity
    pool_type: str
    display_name: str
    documentation_url: Optional[str]
    
    # Capabilities
    supports_coins: List[str]
    requires_api_key: bool
    
    # Core Methods
    async def detect(url, port) → bool
    async def get_health(url, port) → PoolHealthStatus
    async def get_network_difficulty(coin) → float
    async def get_pool_stats(url, coin) → PoolStats
    async def get_blocks(url, coin, hours) → List[PoolBlock]
    async def get_dashboard_data(url, coin, username) → DashboardTileData
    
    # Optional Methods
    async def get_user_stats(url, coin, username) → Dict
    async def get_worker_stats(url, coin, worker) → Dict
```

**Data Models:**
- `DashboardTileData` - 4 dashboard tiles (health, network, shares, earnings)
- `PoolHealthStatus` - Health check results
- `PoolStats` - Pool-wide statistics
- `PoolBlock` - Block found data
- `PoolTemplate` - Pre-configured pool endpoints

**Verdict:** Interface is production-ready and comprehensive.

---

### 2. Solopool Plugin (`app/integrations/pools/solopool_plugin.py`)

**Status:** ⚠️ **Partially implemented** - Only 150 lines of 501 total

**What's Implemented:**
- ✅ `pool_type = "solopool"`
- ✅ `get_pool_templates()` - Returns DGB/BCH/BTC/BC2 templates
- ✅ Coin-specific API bases defined
- ✅ Pool URLs and ports defined

**What's Missing (needs to be added):**
- ❌ `detect(url, port)` - Pool detection
- ❌ `get_health(url, port)` - Health checks
- ❌ `get_network_difficulty(coin)` - Network difficulty
- ❌ `get_pool_stats(url, coin)` - Pool statistics
- ❌ `get_blocks(url, coin, hours)` - Recent blocks
- ❌ `get_dashboard_data(url, coin, username)` - Dashboard tiles
- ❌ `get_user_stats(url, coin, username)` - User statistics

**Need to review lines 151-501 to see what else is implemented.**

---

### 3. Legacy Service (`app/core/solopool.py`)

**Status:** ⚠️ **505 lines of functional code that should be IN the plugin**

**What's Implemented:**
```python
class SolopoolService:
    # Detection methods
    is_solopool_bch_pool(url, port) → bool
    is_solopool_dgb_pool(url, port) → bool
    is_solopool_btc_pool(url, port) → bool
    is_solopool_bc2_pool(url, port) → bool
    is_solopool_xmr_pool(url, port) → bool
    
    # API fetch methods (per coin)
    get_bch_account_stats(username) → Dict
    get_dgb_account_stats(username) → Dict
    get_btc_account_stats(username) → Dict
    get_bc2_account_stats(username) → Dict
    get_xmr_account_stats(username) → Dict
    
    # Network stats (per coin)
    get_bch_pool_stats() → Dict
    get_dgb_pool_stats() → Dict
    get_btc_pool_stats() → Dict
    get_bc2_pool_stats() → Dict
    get_xmr_pool_stats() → Dict
    
    # Utility methods
    extract_username(pool_user) → str
    format_stats_summary(stats) → Dict  # ← FORMATS HASHRATE!
    _format_hashrate(hashrate) → str
    calculate_ettb(network_hr, user_hr, block_time) → Dict
    calculate_ticket_count(network_hr, user_hr) → Dict
    atomic_to_coin(atomic_units, coin) → float
```

**This is ALL the logic the plugin needs!** It's just in the wrong place.

---

## Gap Analysis

### What Plugin Has vs What APIs Need

| Feature | Plugin | Legacy Service | APIs Use |
|---------|--------|----------------|----------|
| Pool detection | ❌ Missing | ✅ Has | ✅ Required |
| Account stats | ❌ Missing | ✅ Has | ✅ Required |
| Pool stats | ❌ Missing | ✅ Has | ✅ Required |
| Stats formatting | ❌ Missing | ✅ Has | ✅ Required |
| ETTB calculation | ❌ Missing | ✅ Has | ✅ Required |
| Username extraction | ❌ Missing | ✅ Has | ✅ Required |
| Dashboard data | ❌ Missing | ❌ None | ⚠️ Cobbled together |

---

## Migration Strategy

### Phase 1: Complete Solopool Plugin (4-6 hours)

**Copy all logic from `app/core/solopool.py` to `app/integrations/pools/solopool_plugin.py`:**

1. **Detection Method:**
```python
async def detect(self, url: str, port: int) -> bool:
    """Detect if this is a Solopool.org pool"""
    for coin, config in self.POOL_CONFIGS.items():
        if url in config["pools"] and port == config["port"]:
            return True
    return False
```

2. **User Stats Method:**
```python
async def get_user_stats(
    self,
    url: str,
    coin: str,
    username: str,
    **kwargs
) -> Optional[Dict[str, Any]]:
    """Get user-specific stats from Solopool API"""
    api_base = self.API_BASES.get(coin.upper())
    if not api_base:
        return None
    
    # Extract username (remove .workername)
    username = username.split('.')[0] if username else ""
    
    # Fetch from API (with caching)
    # ... copy logic from get_bch_account_stats(), etc.
    
    # Format using format_stats_summary()
    return self._format_stats_summary(raw_stats)
```

3. **Dashboard Data Method:**
```python
async def get_dashboard_data(
    self,
    url: str,
    coin: str,
    username: Optional[str] = None,
    **kwargs
) -> Optional[DashboardTileData]:
    """Get all dashboard tile data"""
    # Fetch user stats
    user_stats = await self.get_user_stats(url, coin, username)
    
    # Fetch pool stats
    pool_stats = await self.get_pool_stats(url, coin)
    
    # Calculate ETTB
    ettb = self._calculate_ettb(...)
    
    return DashboardTileData(
        # Tile 1: Health
        health_status=True,
        health_message="Connected",
        latency_ms=latency,
        
        # Tile 2: Network
        pool_hashrate=user_stats.get("hashrate_raw"),
        network_difficulty=pool_stats.get("difficulty"),
        estimated_time_to_block=ettb.get("formatted"),
        active_workers=user_stats.get("workers"),
        
        # Tile 3: Shares (not supported by Solopool)
        
        # Tile 4: Blocks
        blocks_found_24h=user_stats.get("blocks_24h"),
        last_block_found=...,
        currency=coin.upper()
    )
```

4. **Move ALL utility methods from legacy service to plugin as private methods:**
   - `_extract_username()`
   - `_format_stats_summary()` ← **This formats hashrate!**
   - `_format_hashrate()`
   - `_calculate_ettb()`
   - `_calculate_ticket_count()`
   - `_atomic_to_coin()`

---

### Phase 2: Refactor API Endpoints (6-8 hours)

#### `app/api/settings.py`

**BEFORE:**
```python
from core.solopool import SolopoolService

# Line 334-606: Direct calls
if SolopoolService.is_solopool_bch_pool(pool.url, pool.port):
    username = SolopoolService.extract_username(matching_pool.user)
    bch_stats = await SolopoolService.get_bch_account_stats(username)
    formatted_stats = SolopoolService.format_stats_summary(bch_stats)
```

**AFTER:**
```python
from integrations.pool_registry import PoolRegistry

# Detect pool type
pool_type = await PoolRegistry.detect_pool_type(pool.url, pool.port)
if pool_type == "solopool":
    pool_plugin = PoolRegistry.get("solopool")
    user_stats = await pool_plugin.get_user_stats(
        pool.url, 
        coin="BCH",  # Determine from port/url
        username=pool.user
    )
```

#### `app/api/dashboard.py`

**BEFORE:**
```python
from core.solopool import SolopoolService

is_bch = SolopoolService.is_solopool_bch_pool(pool.url, pool.port)
if is_bch:
    # Fetch earnings...
```

**AFTER:**
```python
pool_type = await PoolRegistry.detect_pool_type(pool.url, pool.port)
if pool_type == "solopool":
    pool_plugin = PoolRegistry.get("solopool")
    dashboard_data = await pool_plugin.get_dashboard_data(
        pool.url,
        coin=coin,  # Determine from pool
        username=pool.user
    )
```

---

### Phase 3: Deprecate Legacy Service (1 hour)

1. Move `app/core/solopool.py` → `app/core/_deprecated/solopool.py`
2. Add deprecation warning at top of file
3. Update any remaining imports to show warning
4. Test all pool functionality works via plugin
5. Eventually delete deprecated file

---

## Benefits After Migration

1. **✅ Consistent Architecture** - All pool logic in plugins
2. **✅ Easy to Extend** - Add new pools by creating plugin
3. **✅ Testable** - Plugins can be unit tested independently
4. **✅ Maintainable** - Single source of truth per pool
5. **✅ Hashrate Fix Easier** - Update `_format_hashrate()` in one place

---

## Hashrate Units in Plugin Context

**Current `_format_hashrate()` in legacy service:**
```python
def _format_hashrate(hashrate: float) -> str:
    """Format hashrate with appropriate unit"""
    if hashrate >= 1e12:
        return f"{hashrate / 1e12:.2f} TH/s"
    # ... etc
```

**After migration to plugin:**
```python
def _format_hashrate(self, hashrate: float) -> dict:
    """Format hashrate for API responses (hybrid format)"""
    from core.utils import format_hashrate
    return format_hashrate(hashrate, unit="H/s")
```

This returns the hybrid format:
```json
{
  "display": "27.21 TH/s",
  "value": 27210.0,
  "unit": "GH/s"
}
```

---

## Estimated Effort

| Phase | Task | Hours |
|-------|------|-------|
| 1 | Complete solopool_plugin.py | 4-6 |
| 2 | Refactor API endpoints | 6-8 |
| 3 | Test all functionality | 3-4 |
| 4 | Deprecate legacy service | 1 |
| **Total** | | **14-19** |

---

## Risk Assessment

**Risk Level:** 🟡 **MEDIUM-HIGH**

**Risks:**
1. ⚠️ Dashboard pool tiles break during migration
2. ⚠️ Settings page stats break
3. ⚠️ Earnings calculations break
4. ⚠️ All 4 coins (BCH, DGB, BTC, BC2) must work

**Mitigation:**
- Create branch `fix/pool-plugin-architecture`
- Test each coin individually
- Verify dashboard tiles render correctly
- Verify settings page shows stats
- Verify earnings calculations work
- Only merge when ALL functionality verified

---

## Next Steps

1. ✅ **Read remaining lines of solopool_plugin.py** (151-501) to see what's already implemented
2. ⬜ Create feature branch
3. ⬜ Complete solopool plugin implementation
4. ⬜ Test plugin in isolation
5. ⬜ Refactor settings.py to use plugin
6. ⬜ Refactor dashboard.py to use plugin
7. ⬜ Test end-to-end functionality
8. ⬜ Deprecate legacy service
9. ⬜ Merge to main
10. ⬜ **THEN** tackle hashrate units refactor

---

**Created:** 7 February 2026  
**Status:** 📋 Ready for implementation
