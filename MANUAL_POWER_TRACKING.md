# Manual Power Tracking Implementation

**Feature:** Allow users to manually specify power consumption for miners without auto-detection (XMRig, NMMiner)

**Status:** Planning Complete - Implementation Pending

**Started:** 2026-01-02

---

## Problem Statement

XMRig and NMMiner miners don't provide power consumption via their APIs, making accurate cost tracking impossible. Users know their approximate power usage but have no way to input it.

## Solution Overview

Add optional `manual_power_watts` field to Miner model with fallback logic:
1. **Priority 1:** Use `telemetry.power_watts` (auto-detected)
2. **Priority 2:** Use `miner.manual_power_watts` (user estimate)
3. **Priority 3:** Default to 0 (unknown)

This ensures:
- ✅ No impact on miners with auto-detection (Avalon Nano, Bitaxe, NerdQaxe)
- ✅ Manual power only applied when miner is running (telemetry exists)
- ✅ Shut down miners = 0W (no telemetry = no cost)
- ✅ More accurate profitability and cost tracking

---

## Implementation Plan

### Phase 1: Database Layer

#### Task 1: Add field to Miner model ⏳
- **File:** `app/core/database.py`
- **Change:** Add `manual_power_watts: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)` to Miner class
- **Location:** After `firmware_version` field (line ~28)
- **Outcome:** ORM model has new field
- **Verification:** Model compiles without errors
- **Status:** Not Started

#### Task 2: Create database migration ⏳
- **File:** `app/core/migrations.py`
- **Change:** Add column to miners table: `ALTER TABLE miners ADD COLUMN manual_power_watts INTEGER NULL`
- **Outcome:** Database schema updated on app startup
- **Verification:** SQLite schema shows new column: `.schema miners`
- **Status:** Not Started

---

### Phase 2: UI Layer

#### Task 3: Update miner edit form ⏳
- **File:** `app/ui/templates/miners/edit.html`
- **Changes:**
  - Add form group with label "Estimated Power Usage (W)"
  - Input type="number", min=1, max=5000, placeholder="e.g., 75"
  - Help text: "Optional: For miners without auto-detection (XMRig, NMMiner). Leave blank if power is auto-detected."
  - Add `manual_power_watts` to form data
- **Outcome:** Users can input manual power estimate
- **Verification:** Visit `/miners/{xmrig_id}/edit`, see new field
- **Status:** Not Started

#### Task 4: Update miner detail page ⏳
- **File:** `app/ui/templates/miners/detail.html`
- **Changes:**
  - Add power display logic:
    - If `latest_telemetry.power_watts`: "Power: 75W (auto-detected)"
    - Elif `miner.manual_power_watts`: "Power: ~75W (manual estimate)"
    - Else: "Power: Unknown"
  - Color code: green for auto, blue for manual, gray for unknown
- **Outcome:** Clear indication of power source
- **Verification:** Visit XMRig detail, see "~75W (manual estimate)"
- **Status:** Not Started

---

### Phase 3: API Layer

#### Task 5: Update API endpoints ⏳
- **File:** `app/api/miners.py`
- **Functions to update:**
  1. `create_miner()` - Accept `manual_power_watts` in request body
  2. `update_miner()` - Accept `manual_power_watts` in request body
  3. `get_miner()` - Include `manual_power_watts` in response
  4. `list_miners()` - Include `manual_power_watts` in response
- **Validation:** 1 ≤ manual_power_watts ≤ 5000 (or None)
- **Outcome:** API handles manual power field
- **Verification:** 
  - POST `/api/miners` with `manual_power_watts: 75` → saves to DB
  - GET `/api/miners/{id}` → returns `manual_power_watts`
- **Status:** Not Started

---

### Phase 4: Cost Calculations

#### Task 6: Update daily-cost widget ⏳
- **File:** `app/api/widgets.py`
- **Function:** `get_daily_cost_widget()` (lines 238-320)
- **Change:** Modify power lookup logic (lines 306-309):
  ```python
  # Current:
  if t.power_watts:
      miner_power[t.miner_id] = (t.power_watts, t.timestamp)
  
  # New:
  power = t.power_watts
  if not power:
      # Fallback to manual power if available
      miner = next((m for m in miners if m.id == t.miner_id), None)
      if miner and miner.manual_power_watts:
          power = miner.manual_power_watts
  
  if power:
      if t.miner_id not in miner_power or t.timestamp > miner_power[t.miner_id][1]:
          miner_power[t.miner_id] = (power, t.timestamp)
  ```
- **Outcome:** Manual power used when `telemetry.power_watts` is None
- **Verification:** XMRig with `manual_power_watts=75` shows in daily cost widget
- **Status:** Not Started

#### Task 7: Update other cost calculations ⏳
- **Files to update:**
  1. `app/api/dashboard.py` - Main dashboard 24h cost (lines 670-733)
  2. `app/api/miners.py` - `get_miner_24h_cost()` function
  3. `app/api/widgets.py` - `get_profitability_widget()` (lines 475-520)
  4. Any other cost/profitability calculations
- **Change:** Apply same fallback logic in all locations
- **Outcome:** Consistent power lookup across all calculations
- **Verification:** Check each endpoint with XMRig miner
- **Status:** Not Started

---

### Phase 5: Testing & Verification

#### Task 8: Test XMRig manual power ⏳
- **Setup:**
  1. Edit XMRig miner
  2. Set `manual_power_watts = 75`
  3. Save
- **Verification Steps:**
  1. Check database: `SELECT manual_power_watts FROM miners WHERE miner_type = 'xmrig'` → should return 75
  2. GET `/api/miners/{xmrig_id}` → response includes `"manual_power_watts": 75`
  3. Visit detail page → shows "~75W (manual estimate)"
- **Expected Outcome:** Manual power persists and displays correctly
- **Status:** Not Started

#### Task 9: Test Avalon Nano auto-power ⏳
- **Setup:**
  1. Avalon Nano with working telemetry (power_watts > 0)
  2. Set `manual_power_watts = 999` on same miner
  3. Check 24h cost calculation
- **Verification Steps:**
  1. GET `/api/widgets/daily-cost` → verify cost uses telemetry.power_watts, NOT 999W
  2. Check detail page → shows "75W (auto-detected)", not "~999W (manual)"
  3. Telemetry priority confirmed
- **Expected Outcome:** Auto-detected power takes priority over manual field
- **Status:** Not Started

#### Task 10: Test 24h cost with manual power ⏳
- **Setup:**
  1. XMRig with `manual_power_watts = 75`
  2. Running for exactly 6 hours
  3. Current energy price: 20 p/kWh
- **Verification Steps:**
  1. GET `/api/widgets/daily-cost`
  2. Calculate expected: 75W × 6h × 20p/kWh = 0.075kW × 6h × 20p = 9 pence = £0.09
  3. Compare API result with manual calculation
  4. Check XMRig shut down → cost stops accumulating
- **Expected Outcome:** Cost calculated accurately, only when telemetry exists
- **Status:** Not Started

---

## Success Criteria

### Functional Requirements
- ✅ XMRig with `manual_power_watts=75` appears in cost calculations
- ✅ Avalon Nano ignores manual field, uses `telemetry.power_watts`
- ✅ Shut down XMRig = 0W (no telemetry = no cost)
- ✅ UI clearly distinguishes "~75W (estimate)" vs "75W (auto)"
- ✅ All cost endpoints use consistent fallback logic
- ✅ Field validation: 1-5000W range
- ✅ Optional field: can be left blank

### Non-Breaking Changes
- ✅ Existing miners continue working unchanged
- ✅ Miners with auto-detection unaffected
- ✅ No changes to adapter code required
- ✅ Database migration runs automatically
- ✅ Backward compatible (NULL values allowed)

### Code Quality
- ✅ DRY: Fallback logic in helper function (if needed)
- ✅ Consistent naming: `manual_power_watts` everywhere
- ✅ Clear UI messaging about auto vs manual
- ✅ Input validation on frontend and backend

---

## Files Modified

### Database Layer
- `app/core/database.py` - Add field to Miner model
- `app/core/migrations.py` - Add column migration

### UI Layer
- `app/ui/templates/miners/edit.html` - Add input field
- `app/ui/templates/miners/detail.html` - Display power source

### API Layer
- `app/api/miners.py` - CRUD endpoints
- `app/api/widgets.py` - daily-cost, profitability widgets
- `app/api/dashboard.py` - 24h cost calculations

---

## Testing Checklist

### Unit Tests
- [ ] Manual power saves to database
- [ ] Manual power returns in API responses
- [ ] Validation rejects < 1W or > 5000W
- [ ] NULL values accepted (optional field)

### Integration Tests
- [ ] XMRig cost calculation uses manual power
- [ ] Avalon cost calculation ignores manual power
- [ ] Cost stops when miner shuts down
- [ ] UI displays correct power source indicator

### Manual Testing
- [ ] Edit XMRig, set 75W, verify saves
- [ ] Check detail page shows "~75W (manual estimate)"
- [ ] Verify 24h cost includes XMRig power
- [ ] Shut down XMRig, verify cost stops
- [ ] Edit Avalon, set 999W, verify ignored

---

## Rollout Plan

1. **Development:** Implement all tasks 1-7
2. **Local Testing:** Validate tasks 8-10
3. **Commit:** Git commit with detailed message
4. **Deploy:** Push to production (miners.danvic.co.uk)
5. **Validation:** Test with live XMRig/NMMiner miners
6. **Documentation:** Update user guide (if exists)

---

## Notes

- Manual power is stored as INTEGER (watts) for simplicity
- No fractional watts needed for user estimates
- Field optional to maintain flexibility
- Future: Could add "last updated" timestamp for manual values
- Future: Could suggest power values based on miner type/model

---

## Completion Status

- **Phase 1 (Database):** ⏳ Not Started
- **Phase 2 (UI):** ⏳ Not Started  
- **Phase 3 (API):** ⏳ Not Started
- **Phase 4 (Calculations):** ⏳ Not Started
- **Phase 5 (Testing):** ⏳ Not Started

**Overall Progress:** 0/10 tasks complete

---

**Last Updated:** 2026-01-02  
**Implementation Status:** Planning Complete - Ready to Begin
