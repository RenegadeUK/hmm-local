# Hashrate Units Implementation Checklist

## Phase 1: Backend Utility (MUST DO FIRST)

### 1. Create `app/core/utils.py` - Add format_hashrate()
```python
def format_hashrate(value: float, unit: str = "GH/s") -> dict:
    """
    Format hashrate for API responses.
    Returns both formatted string AND normalized numeric value.
    All numeric values normalized to GH/s for consistency.
    """
```
**Status:** ⬜ Not Started

---

## Phase 2: Backend API Endpoints (80 changes)

### 2.1 Pool Integration Services
- [ ] `app/integrations/solopool.py` - Format pool stats
- [ ] `app/integrations/braiins.py` - Format pool stats

### 2.2 Miner Adapters (Return telemetry with formatted hashrate)
- [ ] `app/adapters/avalon_nano.py` - Lines 43-116 (hashrate in GH/s)
- [ ] `app/adapters/bitaxe.py` - Format hashrate response
- [ ] `app/adapters/nerdqaxe.py` - Format hashrate response
- [ ] `app/adapters/nmminer.py` - Lines 39-308 (MH/s → format)
- [ ] `app/adapters/xmrig.py` - Format hashrate response

### 2.3 API Endpoints (Major Changes)

#### `app/api/dashboard.py`
- [ ] Line 121: `total_hashrate` aggregation
- [ ] Pool stats response structure
- [ ] Summary stats response structure
**Estimated Lines:** 50+

#### `app/api/miners.py`
- [ ] Line 301-302: Return formatted hashrate in telemetry
- [ ] Line 365: Return formatted hashrate in history
**Estimated Lines:** 20

#### `app/api/analytics.py`
- [ ] Line 25: `hashrate_score` calculation
- [ ] Lines 32-35: `avg_hashrate`, `min_hashrate`, `max_hashrate`, `hashrate_unit`
- [ ] Lines 114-135: Statistics aggregation
- [ ] Line 151: Metric parameter handling
- [ ] Lines 230-242: Export CSV formatting
- [ ] Lines 270-302: Overview statistics
**Estimated Lines:** 80

#### `app/api/overview.py`
- [ ] Lines 25-26: `avg_hashrate`, `hashrate_unit` in monthly stats
- [ ] Lines 81-108: Monthly data aggregation and formatting
- [ ] Lines 194-214: ASIC statistics formatting
**Estimated Lines:** 60

#### `app/api/settings.py`
- [ ] Lines 179, 216: `hashrate_5m` formatting
- [ ] Lines 396-606: All pool stats with `network_hashrate` and `user_hashrate`
  - BCH pool stats (lines 396-400)
  - DGB pool stats (lines 429-433)
  - BTC pool stats (lines 462-466)
  - BC2 pool stats (lines 495-499)
  - Multi-coin pool stats (lines 524-606)
**Estimated Lines:** 100+

### 2.4 Database Models
**NO CHANGES NEEDED** - Keep current structure (hashrate + unit), format on read

---

## Phase 3: Frontend Changes (60 changes)

### 3.1 DELETE formatHashrate() Functions
- [ ] `ui-react/src/lib/utils.ts` - DELETE entire formatHashrate function
- [ ] `ui-react/src/components/miners/MinerTable.tsx` - DELETE lines 16-24
- [ ] `ui-react/src/components/miners/MinerTile.tsx` - DELETE lines 16-24

### 3.2 Update Component Imports
- [ ] `ui-react/src/pages/Dashboard.tsx` - REMOVE line 5: `import { formatHashrate } from "@/lib/utils"`

### 3.3 Update Display Logic (Use .display property)

#### `ui-react/src/pages/Dashboard.tsx`
- [ ] Line 180: Pool hashrate tile - Change to `pool.tile_2_network.pool_hashrate.display`
- [ ] Lines 425-429: Summary stats - Change to `stats.total_pool_hashrate.display`
- [ ] Remove all `* 1e12`, `/ 1000` conversions
**Estimated Lines:** 15

#### `ui-react/src/pages/Analytics.tsx`
- [ ] Lines 11-12, 59-60: Update TypeScript interfaces to use hashrate object
- [ ] Line 163: Efficiency calculation - Use `m.avg_hashrate.value / 1000` (GH/s → TH/s)
- [ ] Line 256: Display - Use `miner.avg_hashrate.display`
**Estimated Lines:** 10

#### `ui-react/src/pages/MinerDetail.tsx`
- [ ] Lines 345-346: Display - Use `telemetry.hashrate.display`
**Estimated Lines:** 2

#### `ui-react/src/pages/Leaderboard.tsx`
- [ ] Lines 21-22, 243-247: Update to use hashrate object
**Estimated Lines:** 5

#### `ui-react/src/pages/EnergyOptimization.tsx`
- [ ] Line 66: `avg_hashrate_ghs` - Use hashrate object
**Estimated Lines:** 2

#### `ui-react/src/components/miners/MinerTable.tsx`
- [ ] Line 58: Column header (keep as-is)
- [ ] Line 137: Display - Change to `miner.hashrate.display`
**Estimated Lines:** 2

#### `ui-react/src/components/miners/MinerTile.tsx`
- [ ] Lines 89-95: Display - Change to `miner.hashrate.display`
**Estimated Lines:** 2

#### `ui-react/src/components/widgets/BraiinsTile.tsx`
- [ ] Lines 6-7, 19, 54-55: Use hashrate object
**Estimated Lines:** 4

#### `ui-react/src/components/widgets/NerdMinersTile.tsx`
- [ ] Lines 7, 22, 44, 54: Use hashrate object
**Estimated Lines:** 4

#### `ui-react/src/components/widgets/PoolTile.tsx`
- [ ] Lines 9, 39, 208-209: Use hashrate object
**Estimated Lines:** 4

### 3.4 Update TypeScript Interfaces

#### `ui-react/src/types/miner.ts`
```typescript
export interface Miner {
  hashrate: {
    display: string;
    value: number;  // Always in GH/s
    unit: string;   // Always "GH/s"
  };
  // ... other fields
}
```
**Estimated Lines:** 5

#### `ui-react/src/types/telemetry.ts`
```typescript
export interface Telemetry {
  hashrate: {
    display: string;
    value: number;  // Always in GH/s
    unit: string;   // Always "GH/s"
  };
  // ... other fields
}
```
**Estimated Lines:** 5

### 3.5 Chart Data (Use .value property)
- [ ] `ui-react/src/pages/Dashboard.tsx` - Lines 271-289: Pool hashrate history
- [ ] `ui-react/src/pages/Analytics.tsx` - Chart data processing
**Estimated Lines:** 10

---

## Phase 4: Testing Checklist

### Visual Testing (Manual)
- [ ] Dashboard pool tiles show correct hashrate (e.g., "27.21 TH/s")
- [ ] Dashboard summary stats show correct pool hashrate
- [ ] Miners page table shows correct hashrate
- [ ] Miners page tiles show correct hashrate
- [ ] Miner detail page shows correct hashrate
- [ ] Analytics page shows correct hashrate
- [ ] Analytics page efficiency calculations correct
- [ ] Leaderboard shows correct hashrate
- [ ] Pool tiles show correct hashrate
- [ ] Braiins tile shows correct hashrate
- [ ] NerdMiners tile shows correct hashrate

### Functional Testing
- [ ] Table sorting works correctly (uses .value)
- [ ] Charts render correctly (uses .value)
- [ ] Efficiency calculations correct (W/TH uses .value / 1000)
- [ ] CSV export shows correct units
- [ ] API responses match new structure

### Regression Testing
- [ ] All existing functionality still works
- [ ] No console errors in browser
- [ ] No backend errors in logs
- [ ] Database queries still performant

---

## Phase 5: Deployment

### Pre-Deployment
- [ ] Backend changes committed and tagged
- [ ] Frontend changes committed and tagged
- [ ] React build completed (`npm run build`)
- [ ] Docker image built with new version

### Deployment Steps
1. [ ] Deploy backend + frontend together (atomic deploy)
2. [ ] Monitor logs for errors
3. [ ] Verify dashboard displays correctly
4. [ ] Check all pages for correct units

### Rollback Plan
If issues found:
1. [ ] Revert to previous Docker image
2. [ ] Restart container
3. [ ] Verify old version working

---

## Summary

**Total Files to Modify:**
- Backend: ~15 files
- Frontend: ~20 files

**Total Line Changes:**
- Backend: ~350 lines
- Frontend: ~80 lines

**Estimated Time:**
- Backend implementation: 4-6 hours
- Frontend implementation: 2-3 hours
- Testing: 2-3 hours
- **Total: 8-12 hours**

**Risk Level:** 🟡 MEDIUM
- High file count but low complexity
- Changes are mechanical (find/replace pattern)
- Must deploy atomically (backend + frontend together)
- Comprehensive testing required

**Dependencies:**
- MUST complete Phase 1 first (backend utility)
- MUST complete Phase 2 before Phase 3 (backend before frontend)
- MUST deploy Phase 2 + Phase 3 together (atomic)

---

## Current Status
- ⬜ Not Started
- 🔄 In Progress
- ✅ Complete
- ⚠️ Blocked

**Last Updated:** 7 February 2026
