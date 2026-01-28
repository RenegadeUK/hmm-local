# Audit Logs Legacy View Notes

Source: `app/ui/templates/audit_logs.html`

## Features
- Summary tiles showing total events and success rate for the selected time range.
- Filter controls:
  - `resource_type`: miner, pool, strategy, automation, discovery, profile.
  - `action`: create, update, delete, execute, enable, disable.
  - `days`: 1, 7, 30, 90 (defaults to 7).
- Data table columns: timestamp (local), action badge, resource (type + optional name), user, IP address, status badge, and a "View" button when `changes` JSON exists.
- Modal viewer surfaces `changes` payloads formatted via `JSON.stringify` with indentation.
- Auto-refresh behavior tied to the `days` select: changing the range reloads logs and stats immediately.

## API Usage
- Logs: `GET /api/audit/logs?resource_type=&action=&days=7&limit=100`
- Stats: `GET /api/audit/stats?days=7`

## Target Parity for React Migration
1. Preserve filtering + stats behavior and defaults.
2. Provide a responsive table/card layout and JSON change viewer.
3. Include manual refresh affordance and ensure TanStack Query keys include filters.
