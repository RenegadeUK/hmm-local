# Miner Management React Migration Plan

_Last updated: 2026-01-28_

## Overview

We are replacing the legacy Jinja2 Miner Management hub and its downstream pages with dedicated React routes inside the new SPA. Goals:

- Reduce navigation depth (direct sidebar access via accordion)
- Eliminate long-scroll templates by breaking content into concise cards or collapsible panels
- Reuse shadcn-inspired components (cards, tables, forms, dialogs) for a cohesive aesthetic
- Mirror existing FastAPI endpoints—no backend changes required
- Provide responsive layouts and accessible controls for desktop + mobile

## Navigation Updates

- Sidebar accordion **Miner Management** (collapsed by default)
  - `/settings/agile-solo-strategy` → **Agile Strategy** React page
  - `/settings/optimization` → **Energy Optimization** React page
  - `/automation` → **Automation Rules** React page
  - `/pools/strategies` → **Pool Strategies** React page
  - `/settings/energy` → **Energy Pricing** React page
  - `/settings/integrations/homeassistant` → **Home Assistant** React page
- Each link renders within the SPA (no full page reloads). Breadcrumb + page title appear at top for context.

## Shared UI Conventions

- Page layout: header section (title, subtitle, quick actions) followed by stacked cards.
- Cards limited to ~500px height when possible; tables get internal scroll (`max-h-[400px] overflow-y-auto`).
- Toggles + status chips use shared components (primary accent for enabled, muted for disabled).
- Toasts for mutation outcomes, skeleton loaders for async content.
- Use TanStack Query for all data fetching with appropriate caching + refetch intervals.

## Feature Design Details

### 1. Agile Strategy

**Sections**
1. **Strategy Overview** card
   - Badge showing enabled/disabled
   - Toggle switch, enrolled miner count, last execution timestamp
   - Info accordions ("What is Agile Strategy?", "Solo vs Pooled", "OFF Band Behavior", "Automation Conflicts")
2. **Enroll Miners** card
   - Collapsible groups per miner type (Bitaxe, NerdQaxe++, Avalon Nano, NMMiner)
   - Checkbox list with search/filter + "Select all" per group
3. **Price Band Strategy** card
   - Table with editable price ranges, dropdowns for coin + mode per hardware type
   - Sticky header, inline `Reset to defaults` button
4. **Hysteresis & Notes** info banner

**Data / APIs**
- `GET /api/settings/agile-solo-strategy` → strategy state + miners grouped by type
- `POST /api/settings/agile-solo-strategy` → enable flag + miner IDs
- `GET /api/settings/agile-solo-strategy/bands` → band list
- `PATCH /api/settings/agile-solo-strategy/bands/{id}` → updates per field
- `POST /api/settings/agile-solo-strategy/bands/reset` → reset defaults

**UX Notes**
- Mutations optimistically update badges/toggles.
- Table edits debounce on blur; invalid numbers revert with inline error.

### 2. Energy Optimization

**Sections**
1. **Auto Optimization** card (toggle, current status, "Run now" button)
2. **KPIs** grid (24h cost, net profit, current price, recommendation)
3. **Price Forecast** card with chart + legend
4. **Smart Schedule** card (target hours input, generate button, results list)
5. **Per-Miner Profitability** table (sticky header, color-coded profits)

**Data / APIs**
- `/api/energy/should-mine-now`
- `/api/energy/overview`
- `/api/energy/price-forecast?hours=24`
- `/api/energy/auto-optimization/status|trigger|toggle`
- `/api/miners`
- `/api/energy/miners/{id}/schedule-recommendation`

**UX Notes**
- Charts via Tremor/Recharts or minimal Chart.js wrapper.
- Auto-refresh KPIs every 60s (TanStack refetch interval).

### 3. Automation Rules

**Sections**
1. **Toolbar** with Add Rule button, filters (Enabled/Paused), search input.
2. **Rules Table**
   - Columns: Name, Trigger, Action, Priority, Status, Updated, Actions
   - Expand row or drawer to show JSON trigger/action payloads.
3. **Empty State** with CTA when no rules exist.

**Data / APIs**
- `GET /api/automation/` (existing list route)
- `PUT /api/automation/{id}` for enable/disable edits
- `DELETE /api/automation/{id}`
- `POST /api/automation/{id}/duplicate`

**UX Notes**
- Confirm dialogs before destructive actions.
- Inline badges for trigger/action categories.

### 4. Pool Strategies

**Sections**
1. **Header Toolbar** (Add Strategy, Strategy Guide button)
2. **Strategies Table**
   - Columns: Name, Type, Status, Pools/Miners, Last Switch, Actions
   - Action menu: Execute now, Edit, Delete
3. **Strategy Guide** panel (slide-over or modal) summarizing Round Robin vs Load Balance content.
4. **Empty State** message + CTA when no strategies exist.

**Data / APIs**
- `GET /api/pools/strategies`
- `POST /api/pools/strategies/{id}/execute`
- `DELETE /api/pools/strategies/{id}`

**UX Notes**
- Use colored chips for type (info = round robin, primary = load balance).

### 5. Energy Pricing

**Sections**
1. **Configuration** card (region select, enable toggle, status pill)
2. **Current Price** card
3. **Next Price** card
4. **Timeline** accordion with Today/Tomorrow tabs showing colored slot grid.

**Data / APIs**
- `/api/dashboard/energy/config`
- `/api/dashboard/energy/{current|next|timeline}`
- `/api/dashboard/energy/region`
- `/api/dashboard/energy/toggle`

**UX Notes**
- Region select saves immediately with success toast.
- Timeline tiles use gradient backgrounds mapped to price ranges.

### 6. Home Assistant Integration

**Sections**
1. **Configuration** form card (name, base URL, token, enable/keepalive toggles, action buttons)
2. **Help / Use Cases** collapsible info card
3. **Device Table**
   - Filters: Enrolled only toggle, search
   - Columns: Device, Entity ID, State, Linked Miner, Controls, Enrolled flag
   - Controls menu with On/Off/Refresh/Link actions
4. **Link Device Dialog** with miner dropdown

**Data / APIs**
- `/api/integrations/homeassistant/config` (GET/POST/DELETE)
- `/api/integrations/homeassistant/test`
- `/api/integrations/homeassistant/discover`
- `/api/miners/`
- `/api/integrations/homeassistant/devices[?enrolled_only=true]`
- `/devices/{id}/link`, `/control`, `/state`, `/enroll`

**UX Notes**
- Device rows highlight when enrolled.
- Control buttons become disabled when integration disabled.

## Implementation Order

1. **Agile Strategy** (foundational + most complex)
2. Energy Optimization
3. Automation Rules
4. Pool Strategies
5. Energy Pricing
6. Home Assistant

Each page will:
- Live under `ui-react/src/pages/{Feature}.tsx`
- Use shared hooks/components from `/ui-react/src/components`
- Include route additions + sidebar link updates (already wired)
- Ship with `npm run build` validation + doc updates as needed

This document will evolve as we implement and iterate.
