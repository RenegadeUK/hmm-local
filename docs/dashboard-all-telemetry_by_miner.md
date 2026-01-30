# Dashboard /api/dashboard/all NameError Fix

Date: 2026-01-30

## Current Behavior
- The `/api/dashboard/all` endpoint aggregates dashboard data for all miners.
- It expects a `telemetry_by_miner` map to be available when iterating miners.
- Recent deployments throw a `NameError` because `telemetry_by_miner` is not defined within `get_dashboard_all`.

## Requirement
- Ensure `telemetry_by_miner` is initialized and populated in `get_dashboard_all` to avoid runtime errors.

## Planned Change
- Add `telemetry_by_miner` initialization in `get_dashboard_all` using the existing 24h telemetry query pattern.
- Keep behavior consistent with other dashboard endpoints and limit scope to this missing variable.

## Implemented
- Initialized and populated `telemetry_by_miner` inside `get_dashboard_all`.

## Tests
- `python -m pytest -q`
