# System logs: capture tracebacks in events

Date: 2026-01-30

## Current Behavior
- System Logs page shows Event records with short messages.
- Runtime exceptions are logged to stdout but not stored in Event data.

## Requirement
- Surface full error details in System Logs without relying on Docker logs.
- Keep storage bounded to avoid huge entries.

## Planned Change
- Add a global exception handler that stores a truncated traceback in Event.data.
- Update System Logs UI to display the traceback block when present.

## Implemented
- Added a global exception handler that records truncated tracebacks in Event data for 5xx errors.
- System Logs UI now renders a dedicated traceback disclosure panel.

## Tests
- `python -m pytest -q`
