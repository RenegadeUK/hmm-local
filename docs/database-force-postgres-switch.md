# Database settings: force switch to PostgreSQL

Date: 2026-01-30

## Current Behavior
- The Database Settings page only allows switching to PostgreSQL after a successful migration and validation.
- The `/api/settings/database/switch` endpoint blocks switching to PostgreSQL unless migration succeeded.

## Requirement
- Allow enabling PostgreSQL from the Database page even if the migration check fails.

## Planned Change
- Add a `force=true` option to the switch endpoint to bypass migration success checks.
- Expose a clearly labeled “Force switch” action in the Database page with a warning.

## Implemented
- Added `force` flag to `/api/settings/database/switch` to bypass migration success check.
- Added a “Force switch to PostgreSQL” panel in the Database page.

## Tests
- `python -m pytest -q`
