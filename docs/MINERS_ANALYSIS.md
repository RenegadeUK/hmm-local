# Miners Page - Old Implementation Analysis

## Overview
The old miners list page (`/miners`) provides a comprehensive view of all configured miners with two view modes: **Tiles** (default) and **Table**. It includes bulk operations, health indicators, and detailed per-miner stats.

## Key Features

### 1. View Modes
- **Tiles View**: Grid layout (3 columns on desktop, responsive)
- **Table View**: Compact table with sortable columns
- View preference saved in localStorage (`minersView`)
- Toggle buttons in top-right corner

### 2. Miner Card/Row Components

Each miner displays:

| Field | Description | Source | Notes |
|-------|-------------|--------|-------|
| **Name** | Miner name | `m.name` | User-defined |
| **Type** | Miner type badge | `m.miner_type` | Color-coded pill (same as leaderboards) |
| **Status** | Enabled/Disabled + Online/Offline | `m.enabled`, `m.is_offline` | Offline = no telemetry in 5 minutes |
| **Hashrate** | Current hashrate | `m.hashrate` + `m.hashrate_unit` | GH/s for ASIC, KH/s for CPU |
| **Power** | Current power consumption | `m.power` | Watts (W) |
| **Pool** | Current pool name | `m.pool` | Mapped from pool URL via `pools_dict` |
| **24h Cost** | Energy cost last 24 hours | `m.cost_24h` | £ (GBP) - calculated from telemetry + pricing |
| **Mode** | Operating mode | `m.current_mode` | low/med/high, eco/standard/turbo, etc. |
| **Best Diff** | Context-dependent metric | `m.best_diff`, `m.firmware_version` | See below |

#### Best Diff Column Logic
- **XMRig**: Shows firmware version (not difficulty)
- **Avalon Nano**: "Best Share"
- **NMMiner**: "Best Diff"
- **Bitaxe/NerdQaxe**: "Best Session"
- Format: K/M/B suffixes for large numbers

### 3. Health Indicators

**Visual Cues:**
- **Red border**: Health score < 50 (critical)
- **Offline badge**: Orange "Offline" badge if `is_offline = true`
- **Grayed out**: Offline miners have reduced opacity + gray background
- **Health score**: Not displayed on card, but used for border

### 4. Bulk Operations

**Bulk Actions Bar** (shows when miners selected):
- **Enable** - Enable selected miners
- **Disable** - Disable selected miners  
- **Set Mode** - Change operating mode (low/med/high/eco/standard/turbo)
- **Switch Pool** - Change pool for all selected
- **Restart** - Restart selected miners
- **Clear** - Clear selection

**Selection:**
- Checkbox in top-right of each tile
- "Select All" checkbox in table header
- Selected count displays in bulk actions bar

**Modals:**
- Mode selection dropdown
- Pool selection dropdown (populated from pools API)

### 5. Add Miner Tile

- Displayed as last tile in grid
- Dashed border with "+" icon
- Links to `/miners/add` wizard
- Shown even when miners exist

### 6. Empty State

When no miners configured:
- Centered message
- Link to Network Discovery (`/settings/discovery`)
- "Add Miner" button

### 7. Sorting

Default sort order:
1. ASIC miners first (avalon_nano, bitaxe, nerdqaxe, nmminer)
2. CPU miners last (xmrig)
3. Within each group: alphabetical by name

### 8. Color-Coded Badges

Miner type badges (10% opacity + colored text):
- **Bitaxe**: Blue (`rgba(59, 130, 246, 0.2)`, `#3b82f6`)
- **NerdQaxe**: Purple (`rgba(139, 92, 246, 0.2)`, `#8b5cf6`)
- **Avalon Nano**: Green (`rgba(16, 185, 129, 0.2)`, `#10b981`)
- **NMMiner**: Orange (`rgba(245, 158, 11, 0.2)`, `#f59e0b`)
- **XMRig**: Red (`rgba(239, 68, 68, 0.2)`, `#ef4444`)

### 9. Actions per Miner

**Tile View Actions:**
- **View** - Navigate to `/miners/{id}` (detail page)
- **Edit** - Navigate to `/miners/{id}/edit`
- **Delete** - Confirmation + API call to delete

**Table View Actions:**
- Same as tiles (inline buttons)

## API Endpoint

**URL**: `/api/dashboard/all?dashboard_type={type}`

**Parameters:**
- `dashboard_type`: "asic" (ASIC only) or "all" (all miners)

**Response Structure:**
```json
{
  "miners": [
    {
      "id": 1,
      "name": "Bitaxe-Hex",
      "miner_type": "bitaxe",
      "enabled": true,
      "is_offline": false,
      "hashrate": 650.5,
      "hashrate_unit": "GH/s",
      "power": 15.2,
      "pool": "Solo CK",
      "cost_24h": 0.42,
      "current_mode": "turbo",
      "best_diff": 12500000000,
      "firmware_version": null,
      "health_score": 87
    },
    ...
  ],
  "stats": {
    "online_miners": 5,
    "total_hashrate": 2750.3,
    "total_power": 75.4,
    "total_cost_24h": 1.85,
    "current_price": 10.5
  },
  "events": [...],
  "energy_prices": [...]
}
```

**Key Fields:**
- `is_offline`: Determined by no telemetry in last 5 minutes
- `cost_24h`: Calculated from historical telemetry + energy pricing
- `pool`: Mapped from pool URL to pool name via `pools_dict`
- `health_score`: Latest health score (can be `null`)
- `best_diff`: Highest difficulty share (0 if none)

**Calculations:**
- **24h Cost**: Iterate telemetry records, calculate kWh per period, multiply by energy price at that timestamp
- **Is Offline**: Check if latest telemetry timestamp > 5 minutes ago
- **Total Hashrate**: Sum of all enabled miners' hashrates (GH/s)
- **Total Power**: Sum of all enabled miners' power consumption

## JavaScript Functions

### View Management
- `setView(view)` - Switch between tiles/table view
- `toggleAllMinersTable(checked)` - Select/deselect all miners (table)

### Data Formatting
- `getMinerIcon(type)` - Returns emoji icon per miner type
- `getMinerTypeBadge(minerType)` - Returns colored badge HTML
- `getBestDiffLabel(minerType)` - Returns context-appropriate label
- `formatBestDiff(bestDiff, minerType, firmwareVersion)` - Format with K/M/B suffix
- `formatHashrate(hashrate, unit)` - Format hashrate display

### Selection & Bulk Operations
- `toggleMinerSelection(minerId, checked)` - Add/remove from selection
- `bulkEnable()` - Enable all selected miners
- `bulkDisable()` - Disable all selected miners
- `bulkRestart()` - Restart all selected miners
- `showBulkModeModal()` - Open mode selection modal
- `executeBulkMode()` - Apply mode to selected miners
- `showBulkPoolModal()` - Open pool selection modal
- `executeBulkPool()` - Apply pool to selected miners
- `clearSelection()` - Clear all selections

### Miner Actions
- `viewMiner(id)` - Navigate to detail page
- `editMiner(id)` - Navigate to edit page
- `deleteMiner(id, name)` - Confirm + delete miner

## React Implementation Requirements

### 1. Core Components
```
Miners.tsx (main page)
├── ViewToggle.tsx (tiles/table switcher)
├── BulkActionsBar.tsx (bulk operations toolbar)
├── MinerTile.tsx (tile view card)
├── MinerTableRow.tsx (table view row)
├── AddMinerTile.tsx (+ tile)
├── BulkModeModal.tsx
└── BulkPoolModal.tsx
```

### 2. State Management
- Selected miners (Set<number>)
- View mode (tiles/table) - persist to localStorage
- Bulk modal visibility
- Miners data (from API)

### 3. Data Fetching
- Use React Query: `useQuery(['miners'], fetchMiners)`
- Poll every 30 seconds (optional)
- Handle loading/error states

### 4. Design Consistency
- Use established minimal design (left border accents for health issues)
- Color-coded pills for miner types (same as leaderboards)
- Subtle red left border (4px) for health score < 50
- Gray out offline miners with reduced opacity
- No excessive backgrounds/gradients

### 5. Bulk Operations API
Need to implement:
- `POST /api/bulk/enable` - Body: `{miner_ids: [1, 2, 3]}`
- `POST /api/bulk/disable`
- `POST /api/bulk/restart`
- `POST /api/bulk/set-mode` - Body: `{miner_ids: [...], mode: "high"}`
- `POST /api/bulk/switch-pool` - Body: `{miner_ids: [...], pool_id: 5}`

### 6. Missing Features to Consider
- Pagination (if many miners)
- Search/filter miners by name/type
- Sort options (by name, hashrate, cost, etc.)
- Export miners list (CSV)
- Miner groups/tags
- Quick actions (turn on/off without navigating away)

### 7. Accessibility
- Keyboard navigation for selection
- ARIA labels for checkboxes
- Focus management in modals
- Escape key to close modals

## Next Steps

1. ✅ **Complete this analysis document**
2. **Design React component hierarchy**
3. **Implement data fetching with React Query**
4. **Build MinerTile component** (start with tiles view)
5. **Implement selection state management**
6. **Build BulkActionsBar component**
7. **Add MinerTableRow component** (table view)
8. **Implement bulk operation modals**
9. **Add bulk operation API endpoints** (backend)
10. **Test with real miners data**
11. **Polish responsive design**
12. **Add animations/transitions**

## Key Differences from Old Implementation

**React Advantages:**
- Component reusability (MinerTile, MinerTableRow)
- State management with hooks
- Type safety with TypeScript
- React Query for caching/polling
- Better performance (virtual scrolling if needed)

**Design Improvements:**
- Minimal aesthetic (no excessive borders/backgrounds)
- Better health indicators (left border accent only)
- Improved color-coded pills (consistent with leaderboards)
- Smoother animations/transitions
- Better responsive design

**Technical Improvements:**
- TypeScript interfaces for type safety
- React Query for automatic refetching
- Better error handling
- Loading skeletons
- Optimistic updates for bulk operations

---

**Status**: Analysis complete, ready to implement React version
**Last Updated**: January 25, 2026
