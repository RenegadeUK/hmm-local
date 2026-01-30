# Telemetry parallel collection: commit fix

Date: 2026-01-30

## Current Behavior
- Parallel telemetry uses a dedicated session per miner task.
- Telemetry rows are added to each task session but never committed.
- Result: telemetry does not persist, UI shows miners offline.

## Requirement
- Ensure each per-task session commits telemetry rows.

## Planned Change
- Commit at the end of `_collect_miner_telemetry` when using a task session.

## Implemented
- `_collect_miner_telemetry` now returns a write flag so task sessions can commit.
- Parallel telemetry tasks commit or rollback per miner.

## Tests
- `python -m pytest -q`
