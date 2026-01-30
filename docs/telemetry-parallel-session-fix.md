# Telemetry: parallel DB session fix

Date: 2026-01-30

## Current Behavior
- Parallel telemetry collection shares a single async SQLAlchemy session across concurrent tasks.
- asyncpg raises: "This session is provisioning a new connection; concurrent operations are not permitted".

## Requirement
- Keep parallel telemetry collection but avoid concurrent use of a single session.

## Planned Change
- Create a fresh AsyncSession per miner task during parallel collection.
- Keep sequential mode unchanged for SQLite.

## Implemented
- Parallel telemetry tasks now open their own AsyncSession to avoid concurrent use conflicts.

## Tests
- `python -m pytest -q`
