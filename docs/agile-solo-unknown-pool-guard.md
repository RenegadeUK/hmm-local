# Agile Solo Strategy: guard against unknown pool readings

Date: 2026-01-30

## Current Behavior
- Pool switching is triggered when the device-reported pool does not match the target.
- If telemetry returns no pool, it is treated as `None`, which forces a pool switch.

## Requirement
- Treat missing/empty pool values as an unknown signal and never trigger a pool switch based on it.

## Planned Change
- In Agile Solo Strategy, if `current_pool` is missing/empty, skip pool switching and log a warning.

## Implemented
- Skip pool switching when `current_pool` is missing/empty and record an action note.

## Tests
- `python -m pytest -q`
