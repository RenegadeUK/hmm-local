# Operations Dashboard (Pre-change Notes)

## Current Navigation (as of 2026-01-30)
- Dashboard is a top-level nav item pointing to `/`.
- No Operations dashboard exists.

## Requested Change
- Make Dashboard a top-level category with sub-items:
  - Overview (existing Dashboard page)
  - Operations (new page)
- Operations panels:
  - What is it doing right now? (active automation, strategy per miner, last decision)
  - Ramp/Storm indicators (ramp-up, throttling writes, HA unstable)
  - High-water mark tiles (DB connections, miner concurrency, telemetry backlog)

## Scope
- Add Operations page and new `/api/operations/status` endpoint.
- Reuse existing DB high-water metrics and telemetry metrics.
- Update navigation + routing.

## Post-change Notes (2026-01-30)
- Added Operations dashboard at `/dashboard/operations`.
- Dashboard is now a nav category with Overview (`/`) and Operations sub-items.
- New endpoint: `GET /api/operations/status` aggregates automation, strategy, HA, telemetry, and DB pool metrics.
- Operations page shows:
  - Active automation rules
  - Agile strategy status + enrolled miners
  - Last decision snapshot
  - Mode indicators (ramp-up, throttling writes, HA unstable)
  - High-water mark tiles (DB connections, miner concurrency, telemetry backlog)
