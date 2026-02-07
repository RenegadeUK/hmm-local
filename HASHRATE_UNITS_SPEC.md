# Hashrate Units Specification

## PROBLEM
The codebase has inconsistent hashrate units across backend and frontend, causing display bugs.

## ROOT CAUSES
1. **No standard unit convention** - Some APIs return H/s, some return TH/s, some return GH/s
2. **Multiple format functions** - formatHashrate() exists in 3 different files with different assumptions
3. **Unit field inconsistency** - Some places include unit field, some don't
4. **Backend inconsistency** - Different endpoints return different units for the same concept

## CURRENT STATE (BROKEN)

### Backend Returns:
- **Miner hashrate**: GH/s (with `hashrate_unit` field)
- **Pool hashrate** (`pool_hashrate`): TH/s (NO unit field)
- **Total pool hashrate** (`total_pool_hashrate_ghs`): GH/s (unit in field name)
- **Network hashrate**: Varies by coin
- **Analytics**: GH/s (with `hashrate_unit` field)

### Frontend formatHashrate():
- **src/lib/utils.ts**: Expects H/s (base unit), auto-scales
- **src/components/miners/MinerTable.tsx**: Local function, expects value + unit
- **src/components/miners/MinerTile.tsx**: Local function, expects value + unit

## SOLUTION

### STANDARD: HYBRID APPROACH - BACKEND PROVIDES BOTH FORMATTED + RAW VALUES

**Design Principle:**
- **Backend**: Returns BOTH pre-formatted strings AND numeric values
- **Frontend**: Uses strings for display, numbers for sorting/charts
- **NO conversion logic in frontend** - Backend normalizes all units

**Why Hybrid?**
- ✅ Pre-formatted strings for display (no frontend formatting)
- ✅ Numeric values for sorting tables
- ✅ Numeric values for chart rendering
- ✅ Unit consistency (all numeric values in same unit: GH/s)
- ✅ Frontend can't mess up conversions (no conversion code exists)

### Implementation Plan:

#### Phase 1: Backend Formatting Utility
1. Add formatting utility in `app/core/utils.py`:
```python
def format_hashrate(value: float, unit: str = "GH/s") -> dict:
    """
    Format hashrate for API responses.
    Returns both formatted string AND normalized numeric value.
    All numeric values normalized to GH/s for consistency.
    
    Returns:
        {
            "display": "25.36 TH/s",  // Pre-formatted string
            "value": 25360.0,         // Numeric in GH/s
            "unit": "GH/s"            // Unit of numeric value
        }
    """
    # Convert input to H/s first
    if unit.upper() == "TH/S":
        hs = value * 1e12
    elif unit.upper() == "GH/S":
        hs = value * 1e9
    elif unit.upper() == "MH/S":
        hs = value * 1e6
    elif unit.upper() == "KH/S":
        hs = value * 1e3
    else:
        hs = value
    
    # Determine best display unit
    if hs >= 1e12:
        display = f"{hs / 1e12:.2f} TH/s"
    elif hs >= 1e9:
        display = f"{hs / 1e9:.2f} GH/s"
    elif hs >= 1e6:
        display = f"{hs / 1e6:.2f} MH/s"
    elif hs >= 1e3:
        display = f"{hs / 1e3:.2f} KH/s"
    else:
        display = f"{hs:.2f} H/s"
    
    return {
        "display": display,
        "value": hs / 1e9,  # Always return GH/s for consistency
        "unit": "GH/s"
    }
```

2. Update ALL API responses to return structured hashrate objects:
```json
{
  "hashrate": {
    "display": "25.36 TH/s",
    "value": 25360.0,
    "unit": "GH/s"
  },
  "pool_hashrate": {
    "display": "27.21 TH/s",
    "value": 27210.0,
    "unit": "GH/s"
  }
}
```

#### Phase 2: Frontend Simplification
1. **REMOVE ALL** formatHashrate functions:
   - `src/lib/utils.ts` - DELETE formatHashrate()
   - `src/components/miners/MinerTable.tsx` - DELETE formatHashrate()
   - `src/components/miners/MinerTile.tsx` - DELETE formatHashrate()

2. **REMOVE ALL** conversion logic (`* 1e12`, `/ 1000`, etc.)

3. **Frontend usage patterns**:
```typescript
// Display (use pre-formatted string)
<span>{miner.hashrate.display}</span>

// Sorting (use numeric value - all in GH/s)
miners.sort((a, b) => b.hashrate.value - a.hashrate.value)

// Charts (use numeric value - all in GH/s)
chartData = miners.map(m => ({
  name: m.name,
  hashrate: m.hashrate.value  // Already in GH/s, no conversion
}))
```

#### Phase 3: Database Schema (Optional)
- Keep current database structure (hashrate as numeric + unit)
- Backend converts on read for API responses
- No database migration required

## FILES TO MODIFY

### Backend (Python) - Add format_hashrate() utility:
- `app/core/utils.py` - Add format_hashrate() function
- `app/api/dashboard.py` - Return pre-formatted hashrate strings
- `app/api/analytics.py` - Return pre-formatted hashrate strings
- `app/api/overview.py` - Return pre-formatted hashrate strings
- `app/api/settings.py` - Return pre-formatted pool hashrate strings
- `app/api/miners.py` - Return pre-formatted miner hashrate strings
- `app/integrations/solopool.py` - Format before returning
- `app/integrations/braiins.py` - Format before returning

### Frontend (TypeScript) - Remove ALL formatting logic:
- `ui-react/src/lib/utils.ts` - **DELETE formatHashrate() function**
- `ui-react/src/components/miners/MinerTable.tsx` - **DELETE formatHashrate(), display strings directly**
- `ui-react/src/components/miners/MinerTile.tsx` - **DELETE formatHashrate(), display strings directly**
- `ui-react/src/pages/Dashboard.tsx` - **REMOVE all * 1e12 conversions, display strings directly**
- `ui-react/src/pages/Analytics.tsx` - **REMOVE all conversions, display strings directly**
- `ui-react/src/pages/MinerDetail.tsx` - **REMOVE all conversions, display strings directly**
- `ui-react/src/pages/Leaderboard.tsx` - **REMOVE all conversions, display strings directly**

## MIGRATION NOTES

### Breaking Changes:
- ALL API responses change from numeric values to formatted strings
- Frontend components simplified to remove ALL formatting logic
- Backend becomes single source of truth for display formatting

### Testing Checklist:
- [ ] Miner tiles show correct hashrate (backend formatted)
- [ ] Pool tiles show correct hashrate (backend formatted)
- [ ] Analytics charts display correctly (backend formatted)
- [ ] Leaderboard shows correct values (backend formatted)
- [ ] Efficiency (W/TH) calculations done in backend
- [ ] No formatHashrate() calls remain in frontend
- [ ] No conversion math (* 1e12, / 1000) remains in frontend

### Example API Response Changes:

**BEFORE (BROKEN):**
```json
{
  "hashrate": 25.36,
  "hashrate_unit": "GH/s",
  "pool_hashrate": 27.21,  // Unit unknown!
  "total_pool_hashrate_ghs": 50000
}
```

**AFTER (CORRECT - HYBRID):**
```json
{
  "hashrate": {
    "display": "25.36 GH/s",
    "value": 25.36,
    "unit": "GH/s"
  },
  "pool_hashrate": {
    "display": "27.21 TH/s",
    "value": 27210.0,
    "unit": "GH/s"
  },
  "total_pool_hashrate": {
    "display": "50.00 TH/s",
    "value": 50000.0,
    "unit": "GH/s"
  }
}
```

**Frontend Component Changes:**

**BEFORE (WRONG - Frontend does conversion):**
```typescript
// Display
<span>{formatHashrate(miner.hashrate * 1e9)}</span>

// Sorting
miners.sort((a, b) => {
  const aValue = a.hashrate_unit === "TH/s" ? a.hashrate * 1000 : a.hashrate
  const bValue = b.hashrate_unit === "TH/s" ? b.hashrate * 1000 : b.hashrate
  return bValue - aValue
})

// Charts
chartData = miners.map(m => ({
  hashrate: m.hashrate_unit === "TH/s" ? m.hashrate * 1000 : m.hashrate
}))
```

**AFTER (CORRECT - Frontend uses provided values):**
```typescript
// Display (use pre-formatted string)
<span>{miner.hashrate.display}</span>

// Sorting (use numeric value - all in GH/s)
miners.sort((a, b) => b.hashrate.value - a.hashrate.value)

// Charts (use numeric value - all in GH/s)
chartData = miners.map(m => ({
  name: m.name,
  hashrate: m.hashrate.value  // Already normalized to GH/s
}))
```

---

## IMPLEMENTATION ORDER

1. **Create backend utility** - `app/core/utils.py` format_hashrate()
2. **Update backend APIs** - All endpoints return formatted strings
3. **Remove frontend formatting** - Delete all formatHashrate() and conversions
4. **Deploy together** - Backend + Frontend must be deployed atomically
5. **Verify all displays** - Run through testing checklist

**Estimated Changes:** ~80 backend modifications, ~60 frontend modifications

---

**Status:** ✅ Specification complete - Ready for implementation
**User Decision Required:** Approve to proceed with implementation
