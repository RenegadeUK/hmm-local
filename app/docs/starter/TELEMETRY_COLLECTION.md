# Telemetry Collection (Pre-change Notes)

## Current Implementation (as of 2026-01-30)
- Telemetry is collected by `SchedulerService._collect_telemetry()` in `app/core/scheduler.py`.
- PostgreSQL: uses `asyncio.gather()` to collect all miners in parallel.
- SQLite: sequential collection with a fixed 0.1s delay between miners.
- There is no concurrency limit or jitter for PostgreSQL.
- All enabled miners are polled on the same schedule.

## Requested Change
- Add a concurrency limit for parallel polling (default 5).
- Add jitter/stagger to avoid thundering‑herd spikes.
- Keep SQLite sequential behavior but add jittered delay.

## Scope
- Implement concurrency + jitter in `_collect_telemetry`.
- Add default config keys under `telemetry` in `/config/config.yaml`.

## Post-change Notes (2026-01-30)
- Added `telemetry.concurrency` (default 5) and `telemetry.jitter_max_ms` (default 500).
- PostgreSQL collection now uses a bounded semaphore with jittered starts.
- SQLite collection remains sequential with jittered delay between miners.
