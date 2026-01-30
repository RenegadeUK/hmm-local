# Database Pool Monitoring (Pre-change Notes)

## Current Implementation (as of 2026-01-30)
- Database pool health is checked in `SchedulerService._monitor_database_health()` in `app/core/scheduler.py`.
- The database health API endpoint is `GET /api/health/database` in `app/api/health.py`.
- Pool utilization is derived from SQLAlchemy pool fields: `size()`, `checkedout()`, `overflow()` and returned as `checked_out/total_capacity`.
- Alerts are emitted when utilization exceeds 80% (warning) and 90% (critical).
- No persistent high-water marks are tracked (daily or since boot).
- No explicit pool timeout is configured for PostgreSQL engine (`pool_timeout` not set).
- No centralized logging for pool timeout context (endpoint/task name, request id).

## Requested Enhancements
1. Add high-water marks (daily + since boot):
   - `db_pool_in_use_peak_24h`
   - `db_pool_wait_count_24h`
   - `db_pool_wait_seconds_sum_24h`
   - `active_queries_peak_24h`
   - `slow_query_count_24h`
2. Fail fast when pool is exhausted:
   - set `pool_timeout=3–5s`
   - log endpoint/task name and wait duration when timeouts occur
3. HA flapping guardrails (not in scope for this change)

## Scope for This Change
- Implement #1 and #2 only.
- Persist high-water marks in `/config`.
- Expose high-water marks via `GET /api/health/database` for UI/inspection.
- Add PostgreSQL pool timeout.
- Add request context logging for pool timeouts.

## Post-change Notes (2026-01-30)
- Added persistent high-water marks stored in `/config/db_pool_metrics.json`.
- High-water marks are updated by scheduled database health checks and by `GET /api/health/database`.
- Added PostgreSQL `pool_timeout=5` to fail fast on exhaustion.
- Added request ID middleware and SQLAlchemy pool timeout handler that logs endpoint context and records wait counts.
- `GET /api/health/database` now returns `high_water_marks` for `last_24h` and `since_boot`.
