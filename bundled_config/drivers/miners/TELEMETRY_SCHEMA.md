# Miner Telemetry Schema Contract

Schema Version: 1.0.0
Last Updated: 2026-02-13

## Purpose

This contract defines the canonical telemetry format all miner drivers should emit.
It enables:

- consistent analytics across miner types
- easier new driver onboarding
- safe preservation of vendor-specific fields
- stable mapping for API/UI consumers

## Canonical Top-Level Fields

These map directly to the `telemetry` table columns.

| Canonical key | DB column | Type | Unit | Required |
|---|---|---|---|---|
| `timestamp` | `timestamp` | datetime | UTC | Yes |
| `miner_id` | `miner_id` | int | - | Yes |
| `hashrate_ghs` | `hashrate` | float | GH/s | Yes |
| `hashrate_unit` | `hashrate_unit` | string | GH/s | Yes |
| `temperature_c` | `temperature` | float | °C | If available |
| `power_watts` | `power_watts` | float | W | If available |
| `shares_accepted` | `shares_accepted` | int | count | Yes |
| `shares_rejected` | `shares_rejected` | int | count | Yes |
| `pool_difficulty` | `pool_difficulty` | float | diff | If available |
| `pool_in_use` | `pool_in_use` | string | url[:port] | If available |
| `mode` | `mode` | string | enum | If available |
| `extra_data` | `data` | object | JSON | Yes |

## Required Standard Keys in `extra_data`

Drivers should emit these when source values exist:

- `uptime_seconds`
- `current_mode`
- `firmware_version`
- `raw_source` (e.g. `bitaxe_rest`, `cgminer`, `nmminer_udp`)

## Optional Standard Keys in `extra_data`

Use these exact names for cross-miner consistency:

- `best_share_diff`
- `best_session_diff`
- `network_difficulty`
- `pool_response_ms`
- `error_rate_pct`
- `fan_rpm`
- `fan_speed_pct`
- `voltage_mv`
- `core_voltage_mv`
- `core_voltage_actual_mv`
- `vr_temp_c`
- `frequency_mhz`
- `stratum_suggested_difficulty`
- `block_height`
- `hardware_errors`
- `device_rejected_pct`
- `pool_rejected_pct`
- `pool_stale_pct`
- `stale_shares`
- `work_utility`
- `utility`
- `wifi_rssi`
- `free_heap_bytes`

## Vendor Raw Preservation (Mandatory)

Always preserve unmodified source payloads under namespaced keys:

- `vendor.raw.system_info` (Bitaxe/NerdQaxe)
- `vendor.raw.summary` (Nano cgminer)
- `vendor.raw.pools` (Nano cgminer)
- `vendor.raw.devs` (Nano cgminer)
- `vendor.raw.estats` (Nano cgminer)
- `vendor.raw.mm_id0` (raw Nano MM string)
- `vendor.parsed.mm_id0` (parsed MM key/value object)

## Normalization Rules

- Hashrate must be normalized to **GH/s** in canonical field.
- Percent values should be numeric percentage (`12.3`), not strings with `%`.
- Difficulty should be numeric when possible; preserve raw in `vendor.raw.*` if parsing fails.
- Uptime should be integer seconds.

## Source Mapping Reference

### Bitaxe / NerdQaxe (`/api/system/info`)

- `hashRate` → `hashrate_ghs`
- `temp` → `temperature_c`
- `power` → `power_watts`
- `sharesAccepted` → `shares_accepted`
- `sharesRejected` → `shares_rejected`
- `poolDifficulty` → `pool_difficulty`
- `stratumURL` + `stratumPort` → `pool_in_use`
- `uptimeSeconds` → `uptime_seconds`
- `frequency` → `frequency_mhz`
- `bestDiff` → `best_share_diff`
- `bestSessionDiff` → `best_session_diff`

### Avalon Nano (cgminer API)

- `SUMMARY["MHS 5s"]` (MH/s) → `hashrate_ghs` (divide by 1000)
- `MM_ID0.TAvg` (fallback `DEVS.Temperature`) → `temperature_c`
- `MM_ID0.MPO` → `power_watts`
- `SUMMARY.Accepted` → `shares_accepted`
- `SUMMARY.Rejected` → `shares_rejected`
- `POOLS["Stratum Difficulty"]` (fallback `Work Difficulty`) → `pool_difficulty`
- active `POOLS.URL` (`Priority=0`) → `pool_in_use`
- `SUMMARY.Elapsed` → `uptime_seconds`
- `MM_ID0.WORKMODE` → `current_mode`
- `SUMMARY["Best Share"]` → `best_share_diff`

## Versioning and Update Flow

- Bundled canonical copy: `/app/bundled_config/drivers/miners/TELEMETRY_SCHEMA.md`
- Deployed user copy: `/config/drivers/miners/TELEMETRY_SCHEMA.md`
- Driver Management API endpoints:
  - `GET /api/drivers/miner-telemetry-schema/status`
  - `POST /api/drivers/miner-telemetry-schema/update`

This document is versioned using `Schema Version` and can be pulled to deployed config via API.
