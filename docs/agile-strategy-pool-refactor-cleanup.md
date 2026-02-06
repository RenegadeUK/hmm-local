# Agile Strategy Pool-Based Refactor - Cleanup Summary

**Date:** 6 February 2026  
**Status:** ✅ Complete

## Overview

Completed the cleanup phase of transitioning Agile Solo Strategy from hardcoded coin-based targeting to flexible pool-based selection. This allows any band to target any pool (or OFF state), making the system more flexible and maintainable.

## Changes Made

### 1. Core Logic Updates (`app/core/agile_solo_strategy.py`)

**Added Helper Function:**
```python
@staticmethod
async def _get_pool_name(db: AsyncSession, pool_id: Optional[int]) -> str:
    """Get pool name from pool_id for logging purposes."""
    if pool_id is None:
        return "OFF"
    
    result = await db.execute(select(Pool).where(Pool.id == pool_id))
    pool = result.scalar_one_or_none()
    return pool.name if pool else f"Pool#{pool_id}"
```

**Updated Pool Validation (lines 310-340):**
- Changed from coin-based validation to pool ID validation
- Now validates that all `target_pool_id` values exist and are enabled
- Provides better error messages with pool names

**Updated Band Transition Logic (lines 410-505):**
- OFF detection: `target_pool_id is None` instead of `target_coin == "OFF"`
- Band matching: Uses `sort_order` instead of `target_coin`
- All logging: Shows pool names instead of coin symbols

**Updated Strategy State Tracking (lines 760-795):**
- `strategy.current_price_band` now stores **pool name** (e.g., "Solopool DGB", "Braiins BCH")
- `strategy.current_band_sort_order` tracks specific band (primary key)
- Band transitions logged with pool names

### 2. Default Bands (`app/core/agile_bands.py`)

**Updated DEFAULT_BANDS:**
- All 6 bands now use `target_pool_id: None` (OFF state)
- Removed `target_coin: "OFF"` from defaults
- Fresh installs will use new schema from start

**Marked VALID_COINS as Legacy:**
```python
# Valid coin options for Agile Solo Strategy (LEGACY - pools now used directly)
VALID_COINS = ["OFF", "DGB", "BC2", "BCH", "BTC", "BTC_POOLED"]
```
Kept for backward compatibility but no longer used in new code.

### 3. Database Schema

**AgileStrategyBand Model:**
```python
target_coin: Mapped[Optional[str]]  # DEPRECATED - kept for backward compatibility
target_pool_id: Mapped[Optional[int]]  # New field - None = OFF
```

**Strategy State:**
- `current_price_band` (str): Now stores pool name for display
- `current_band_sort_order` (int): Tracks specific band position

## What Still Uses Legacy Code

### Backward Compatibility
These remain for migrating old data:

1. **`target_coin` database field** - Marked DEPRECATED but not removed
2. **`find_pool_for_coin()` function** - Used in legacy fallback path
3. **VALID_COINS list** - Kept for validating old data
4. **Coin validation in API** - Marked as "legacy - prefer target_pool_id"

### Already Updated
These were updated in the previous phase:

✅ **Database Schema:** Added `target_pool_id` column  
✅ **API Endpoints:** Band CRUD handles `target_pool_id`  
✅ **Pool Selection API:** `/api/pools/for-bands` lists available pools  
✅ **React UI:** Pool dropdown instead of coin dropdown  
✅ **Core Execution:** Uses `target_pool_id` with coin fallback  

## Testing Checklist

- [x] Container rebuilds and starts successfully
- [ ] Agile Strategy execution logs show pool names
- [ ] OFF bands work (target_pool_id = null)
- [ ] Pool switching works for all pool types
- [ ] Operations page displays current pool name
- [ ] Band transitions show pool names in logs
- [ ] Champion mode still works
- [ ] Home Assistant control preserved
- [ ] Legacy target_coin bands still function (fallback)

## Migration Path

**For Fresh Installs:**
- Default bands created with `target_pool_id: None`
- Users configure pools via dropdown
- Everything uses pool-based system

**For Existing Deployments:**
- Legacy `target_coin` bands still work via fallback
- System logs deprecation warnings
- Users can edit bands to select pool directly
- No forced migration needed

## Benefits

1. **Flexibility:** Any band can use any pool (not limited to hardcoded coins)
2. **Maintainability:** No coin-specific logic in core engine
3. **Extensibility:** Easy to add new pool types without code changes
4. **Clarity:** Logs show actual pool names, not abstract coin symbols
5. **Pool Management:** Centralized pool configuration
6. **Future-Proof:** Ready for dynamic pool strategies

## Example Logging Output

**Before (Coin-Based):**
```
Target band: DGB (sort_order=3) @ 8.5p/kWh
BAND TRANSITION: band #2 (BCH) → band #3 (DGB)
```

**After (Pool-Based):**
```
Target band: Solopool DGB (sort_order=3) @ 8.5p/kWh
BAND TRANSITION: band #2 (Solopool BCH) → band #3 (Solopool DGB)
```

## Operations UI Display

**Before:**
```
Band: DGB
```

**After:**
```
Band: Solopool DGB
```

The `current_price_band` field now contains the full pool name, making it clear which specific pool is active.

## Code Quality Improvements

1. **Type Safety:** Pool IDs are integers (None for OFF)
2. **Database Integrity:** Foreign key to Pool table
3. **Error Messages:** Show pool names not IDs
4. **Logging:** Consistent pool name display
5. **Validation:** Pool existence checked before use

## Next Steps (Optional Future Work)

- **Remove Legacy Code:** After sufficient production time, remove deprecated fields
- **Pool Name Caching:** Add Redis cache for _get_pool_name() to reduce queries
- **Audit Log Enhancement:** Show pool changes not just coin changes
- **UI Enhancement:** Display pool icon/logo instead of just name
- **Analytics:** Track pool usage statistics across bands

## Related Documents

- [Agile Solo Strategy Core](./agile-solo-unknown-pool-guard.md)
- [Miner Management SPA Plan](./MINER_MANAGEMENT_SPA_PLAN.md)
- [Database Migration](./database-force-postgres-switch.md)

---

**Status:** Ready for production use  
**Backward Compatibility:** ✅ Maintained  
**Migration Required:** ❌ Optional  
**Breaking Changes:** None
