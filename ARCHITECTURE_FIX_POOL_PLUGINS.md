# CRITICAL: Fix Pool Plugin Architecture Bypass

## Problem Statement

The application has a proper **plugin-based pool integration system** at `app/integrations/pools/` but critical parts of the codebase are **bypassing this architecture** by directly importing legacy services from `app/core/`.

This violates the plugin architecture and makes the system fragile, unmaintainable, and defeats the purpose of the plugin system.

---

## Current Architecture (CORRECT)

### Plugin System
```
app/integrations/
├── base_pool.py          # Abstract base class for all pool plugins
├── pool_registry.py      # Central registry for pool plugins
└── pools/
    ├── solopool_plugin.py   # Solopool.org implementation
    ├── braiins_plugin.py    # Braiins Pool implementation
    └── mmfp_plugin.py       # MMFP implementation
```

**Usage Pattern (CORRECT):**
```python
from integrations.pool_registry import PoolRegistry

# Get pool plugin
pool = PoolRegistry.get('solopool')
if pool:
    stats = await pool.get_stats(url, port, username)
```

---

## Current Architecture Violations (BROKEN)

### Legacy Services (SHOULD NOT EXIST)
```
app/core/
├── solopool.py    # ❌ Direct implementation - bypasses plugin system
└── braiins.py     # ❌ Direct implementation - bypasses plugin system
```

### Code Bypassing Plugin System

#### 1. `app/api/settings.py`
**Line 16:**
```python
from core.solopool import SolopoolService  # ❌ WRONG
```

**Lines 334-606:** Direct calls to `SolopoolService` methods:
- `SolopoolService.is_solopool_bch_pool()`
- `SolopoolService.get_bch_pool_stats()`
- `SolopoolService.get_bch_account_stats()`
- `SolopoolService.format_stats_summary()`
- `SolopoolService.calculate_ettb()`

**Should be:**
```python
from integrations.pool_registry import PoolRegistry

pool = PoolRegistry.get('solopool')
if pool:
    stats = await pool.get_account_stats(username, coin='BCH')
```

#### 2. `app/api/dashboard.py`
**Line 378:**
```python
from core.solopool import SolopoolService  # ❌ WRONG
```

**Lines 386-450:** Direct calls to `SolopoolService` for earnings calculations

#### 3. `app/api/miners.py`
**Line 385:**
```python
from core.solopool import SolopoolService  # ❌ WRONG
```

**Line 406:** Detection logic
```python
if SolopoolService.is_solopool_xmr_pool(pool.url, pool.port):  # ❌ WRONG
```

**Should be:**
```python
pool_type = await PoolRegistry.detect_pool_type(pool.url, pool.port)
if pool_type == 'solopool':
    # Handle solopool
```

#### 4. `app/api/strategy_pools.py`
**Line 12:**
```python
from core.solopool import SolopoolService  # ❌ WRONG
```

---

## Migration Plan

### Phase 1: Audit Pool Plugin Interfaces
- [ ] Read `app/integrations/base_pool.py` to understand the interface
- [ ] Check if `solopool_plugin.py` implements all required methods
- [ ] Check if `braiins_plugin.py` implements all required methods
- [ ] Identify any gaps between legacy services and plugin interface

### Phase 2: Enhance Pool Plugins (If Needed)
- [ ] Add missing methods to plugins that legacy services provide
- [ ] Ensure plugins return consistent data structures
- [ ] Add proper error handling and retries

### Phase 3: Refactor API Endpoints
- [ ] `app/api/settings.py` - Replace all `SolopoolService` calls with `PoolRegistry`
- [ ] `app/api/dashboard.py` - Replace all `SolopoolService` calls with `PoolRegistry`
- [ ] `app/api/miners.py` - Replace all `SolopoolService` calls with `PoolRegistry`
- [ ] `app/api/strategy_pools.py` - Replace all `SolopoolService` calls with `PoolRegistry`

### Phase 4: Deprecate Legacy Services
- [ ] Move `app/core/solopool.py` to `app/core/_deprecated/solopool.py`
- [ ] Move `app/core/braiins.py` to `app/core/_deprecated/braiins.py`
- [ ] Add deprecation warnings if anything still imports them
- [ ] Eventually delete after confirming no usage

### Phase 5: Test All Pool Functionality
- [ ] Dashboard pool tiles show correct data
- [ ] Settings → Pools page works
- [ ] Earnings calculations work
- [ ] Pool detection works
- [ ] All coins (BCH, DGB, BTC, BC2, XMR) work

---

## Benefits of Fixing This

1. **Maintainability**: All pool logic in one place (plugins)
2. **Extensibility**: Users can add custom pool plugins without modifying core
3. **Testability**: Plugins can be tested in isolation
4. **Consistency**: All pools use same interface and data structures
5. **Decoupling**: Core app doesn't know about specific pool implementations

---

## Impact Analysis

### Files That Need Changes
- `app/api/settings.py` (606 lines - major refactor)
- `app/api/dashboard.py` (1640 lines - medium refactor)
- `app/api/miners.py` (medium refactor)
- `app/api/strategy_pools.py` (minor refactor)

### Estimated Effort
- **Audit & Planning**: 2-3 hours
- **Plugin Enhancement**: 3-4 hours
- **API Refactoring**: 6-8 hours
- **Testing**: 3-4 hours
- **Total**: 14-19 hours

### Risk Level
🔴 **HIGH** - This touches critical dashboard and earnings functionality

### Dependencies
- Must be completed BEFORE hashrate units refactor
- Should be done in its own branch
- Requires comprehensive testing before merge

---

## After This Fix, THEN Fix Hashrate Units

Once the plugin architecture is properly used, the hashrate units fix becomes:
1. Update `format_hashrate()` utility in `app/core/utils.py`
2. Update pool plugin base class to return hashrate objects
3. Update all pool plugins to use the utility
4. Update miner adapters to use the utility
5. Update frontend to consume the new format

**Much cleaner and follows proper architecture!**

---

## Next Steps

1. **Stop hashrate units work** - Don't proceed with that refactor yet
2. **Audit pool plugins** - Understand what they implement
3. **Create branch**: `fix/pool-plugin-architecture`
4. **Fix architecture violations** - Refactor APIs to use PoolRegistry
5. **Test thoroughly** - Ensure all pool functionality works
6. **Merge to main** - Once stable
7. **THEN tackle hashrate units** - Within proper architecture

---

**Status:** 🔴 BLOCKING - Must be fixed before hashrate units refactor
**Priority:** P0 - Critical architectural flaw
**Created:** 7 February 2026
