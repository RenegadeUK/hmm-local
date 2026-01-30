# HA datetime normalization fix

Date: 2026-01-30

## Current Behavior
- `AgileSoloStrategy.control_ha_device_for_miner()` and reconcile logic store HA `state.last_updated` directly in `homeassistant_devices.last_state_change`.
- HA `last_updated` values can be timezone-aware, but the DB columns are `TIMESTAMP WITHOUT TIME ZONE`.
- This causes asyncpg to raise `can't subtract offset-naive and offset-aware datetimes` during autoflush.

## Requirement
- Store only naive UTC datetimes in `homeassistant_devices.last_state_change` and `last_off_command_timestamp`.

## Planned Change
- Normalize HA datetimes to naive UTC before assignment.
- Reuse a single helper to avoid missed conversions.

## Implemented
- Added `_to_naive_utc()` and normalized HA `last_updated` before storing.

## Tests
- `python -m pytest -q`
