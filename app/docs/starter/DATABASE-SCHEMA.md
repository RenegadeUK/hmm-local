# HMM Database Schema Reference

**Generated**: January 24, 2026  
**Source**: `app/core/database.py`

This is the **authoritative** schema reference. All code MUST use these exact field names.

---

## Core Tables

### Miner
Miner configuration and state

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `id` | int | No | Primary key |
| `name` | str(100) | No | Miner display name |
| `miner_type` | str(50) | No | avalon_nano, bitaxe, nerdqaxe, nmminer |
| `ip_address` | str(45) | No | IPv4/IPv6 address |
| `port` | int | Yes | Custom port (optional) |
| `current_mode` | str(20) | Yes | eco/standard/turbo or low/med/high |
| `firmware_version` | str(100) | Yes | Firmware version string |
| `manual_power_watts` | int | Yes | User-provided power estimate |
| `enabled` | bool | No | Is miner active? (default: True) |
| `config` | JSON | Yes | Miner-specific config data |
| `last_mode_change` | datetime | Yes | When mode was last changed |
| `created_at` | datetime | No | When miner was added |
| `updated_at` | datetime | No | Last update timestamp |

**NO** `current_pool` field - pool info comes from Telemetry!

---

### Telemetry
Miner telemetry snapshots

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `id` | int | No | Primary key |
| `miner_id` | int | No | FK to Miner.id (indexed) |
| `timestamp` | datetime | No | When telemetry captured (indexed) |
| `hashrate` | float | Yes | Hashrate value |
| `hashrate_unit` | str(10) | Yes | KH/s, MH/s, GH/s, TH/s |
| `temperature` | float | Yes | Temperature in °C |
| `power_watts` | float | Yes | Power consumption in watts |
| `shares_accepted` | int | Yes | Accepted shares count |
| `shares_rejected` | int | Yes | Rejected shares count |
| `pool_in_use` | str(255) | Yes | Current pool URL/name |
| `data` | JSON | Yes | Additional miner-specific data |

**IMPORTANT**: Field is `power_watts`, NOT `power`!  
**NO** `uptime` field - not tracked in telemetry!

**Index**: Composite on (`miner_id`, `timestamp`) for fast queries

---

### Pool
Mining pool configuration

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `id` | int | No | Primary key |
| `name` | str(100) | No | Pool display name |
| `url` | str(255) | No | Pool hostname/IP |
| `port` | int | No | Pool port |
| `user` | str(255) | No | Pool username/worker |
| `password` | str(255) | No | Pool password |
| `enabled` | bool | No | Is pool active? |
| `priority` | int | No | Load balancing weight (default: 0) |
| `network_difficulty` | float | Yes | DGB network difficulty |
| `network_difficulty_updated_at` | datetime | Yes | When difficulty last updated |
| `best_share` | float | Yes | Current best share in round |
| `best_share_updated_at` | datetime | Yes | When best share last improved |
| `created_at` | datetime | No | When pool was added |

**SECURITY**: Never expose `password` field to Sam or logs!

---

### BlockFound
Blocks solved by miners

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `id` | int | No | Primary key |
| `miner_id` | int | No | FK to Miner.id (indexed) |
| `miner_name` | str(100) | No | Snapshot (in case renamed) |
| `miner_type` | str(50) | No | avalon_nano, bitaxe, nerdqaxe |
| `coin` | str(10) | No | BTC, BCH, BC2, DGB (indexed) |
| `pool_name` | str(100) | No | Pool where block found |
| `difficulty` | float | No | Share difficulty |
| `network_difficulty` | float | No | Network difficulty at time |
| `block_height` | int | Yes | Block height (if available) |
| `block_reward` | float | Yes | Block reward (if available) |
| `hashrate` | float | Yes | Miner hashrate at time |
| `hashrate_unit` | str(10) | No | GH/s, TH/s |
| `miner_mode` | str(20) | Yes | Mode at time of block |
| `timestamp` | datetime | No | When block found (indexed) |

**Index**: Composite on (`miner_id`, `coin`)

---

### HighDiffShare
High difficulty shares leaderboard

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `id` | int | No | Primary key |
| `miner_id` | int | No | FK to Miner.id (indexed) |
| `miner_name` | str(100) | No | Snapshot (in case renamed) |
| `miner_type` | str(50) | No | avalon_nano, bitaxe, nerdqaxe |
| `coin` | str(10) | No | BTC, BCH, BC2, DGB |
| `pool_name` | str(100) | No | Pool where share submitted |
| `difficulty` | float | No | Share difficulty (indexed) |
| `network_difficulty` | float | Yes | Network difficulty at time |
| `was_block_solve` | bool | No | True if diff >= network_diff |
| `hashrate` | float | Yes | Miner hashrate at time |
| `hashrate_unit` | str(10) | No | GH/s, TH/s |
| `miner_mode` | str(20) | Yes | Mode at time of share |
| `timestamp` | datetime | No | When share submitted (indexed) |

**Index**: Composite on (`difficulty`, `timestamp`)

---

## Pricing & Energy

### EnergyPrice
Octopus Agile pricing data

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `id` | int | No | Primary key |
| `region` | str(1) | No | A-P (Agile region, indexed) |
| `valid_from` | datetime | No | Slot start time (indexed) |
| `valid_to` | datetime | No | Slot end time |
| `price_pence` | float | No | Price in pence per kWh |
| `created_at` | datetime | No | When price was fetched |

### CryptoPrice
Cached cryptocurrency prices

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `id` | int | No | Primary key |
| `coin_id` | str(50) | No | bitcoin, bitcoin-cash, digibyte, bellscoin, monero (unique) |
| `price_gbp` | float | No | Price in GBP |
| `source` | str(50) | No | coingecko, coincap, binance |
| `updated_at` | datetime | No | When price last updated |

---

## Automation

### AutomationRule
User-defined automation rules

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `id` | int | No | Primary key |
| `name` | str(100) | No | Rule display name |
| `enabled` | bool | No | Is rule active? |
| `trigger_type` | str(50) | No | price_threshold, time_window, etc |
| `trigger_config` | JSON | No | Trigger conditions |
| `action_type` | str(50) | No | apply_mode, switch_pool, alert |
| `action_config` | JSON | No | Action parameters |
| `priority` | int | No | Execution priority |
| `last_executed_at` | datetime | Yes | When rule last ran |
| `last_execution_context` | JSON | Yes | Last execution details |
| `created_at` | datetime | No | When rule created |

### AgileStrategy
Agile Solo Strategy state

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `id` | int | No | Primary key |
| `enabled` | bool | No | Is strategy active? |
| `current_price_band` | str(20) | Yes | off, dgb_high, dgb_med, etc |
| `hysteresis_counter` | int | No | 2-slot delay counter |
| `last_action_time` | datetime | Yes | When strategy last acted |
| `last_price_checked` | float | Yes | Last price checked (p/kWh) |
| `state_data` | JSON | Yes | Additional state tracking |
| `created_at` | datetime | No | When strategy created |
| `updated_at` | datetime | No | Last update timestamp |

### AgileStrategyBand
Price band definitions

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `id` | int | No | Primary key |
| `strategy_id` | int | No | FK to AgileStrategy |
| `min_price` | float | Yes | Min price (p/kWh), None=lowest |
| `max_price` | float | Yes | Max price (p/kWh), None=highest |
| `target_coin` | str(10) | No | OFF, DGB, BCH, BTC |
| `bitaxe_mode` | str(20) | No | managed_externally, eco, std, turbo, oc |
| `nerdqaxe_mode` | str(20) | No | managed_externally, eco, std, turbo, oc |
| `avalon_nano_mode` | str(20) | No | managed_externally, low, med, high |
| `sort_order` | int | No | Display order (0-based) |
| `created_at` | datetime | No | When band created |
| `updated_at` | datetime | No | Last update timestamp |

### MinerStrategy
Miner enrollment in Agile Solo

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `id` | int | No | Primary key |
| `miner_id` | int | No | FK to Miner.id (indexed, unique) |
| `strategy_enabled` | bool | No | Is miner enrolled? |
| `created_at` | datetime | No | When enrolled |

---

## Health & Monitoring

### HealthScore
Miner health scores over time

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `id` | int | No | Primary key |
| `miner_id` | int | No | FK to Miner.id (indexed) |
| `timestamp` | datetime | No | Score timestamp (indexed) |
| `overall_score` | float | No | Overall health 0-100 |
| `uptime_score` | float | No | Uptime component 0-100 |
| `temperature_score` | float | Yes | Temp component 0-100 (nullable for no sensor) |
| `hashrate_score` | float | No | Hashrate component 0-100 |
| `reject_rate_score` | float | No | Reject rate component 0-100 |
| `details` | JSON | Yes | Detailed breakdown |

### PoolHealth
Pool health monitoring

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `id` | int | No | Primary key |
| `pool_id` | int | No | FK to Pool.id (indexed) |
| `timestamp` | datetime | No | Check timestamp (indexed) |
| `response_time_ms` | float | Yes | Response time in ms |
| `is_reachable` | bool | No | Is pool reachable? |
| `reject_rate` | float | Yes | Reject rate percentage |
| `shares_accepted` | int | Yes | Shares accepted count |
| `shares_rejected` | int | Yes | Shares rejected count |
| `health_score` | float | Yes | Overall health 0-100 |
| `luck_percentage` | float | Yes | Pool luck % |
| `error_message` | str(500) | Yes | Error details if unreachable |

---

## Logging & Events

### Event
System events and alerts

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `id` | int | No | Primary key |
| `timestamp` | datetime | No | Event timestamp (indexed) |
| `event_type` | str(50) | No | info, warning, error, alert |
| `source` | str(100) | No | miner_id, automation_rule_id, system |
| `message` | text | No | Event message |
| `data` | JSON | Yes | Additional event data |

### AuditLog
Configuration change tracking

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `id` | int | No | Primary key |
| `timestamp` | datetime | No | Action timestamp (indexed) |
| `user` | str(100) | No | Username (default: system) |
| `action` | str(50) | No | create, update, delete, execute (indexed) |
| `resource_type` | str(50) | No | miner, pool, strategy, etc (indexed) |
| `resource_id` | int | Yes | Resource ID |
| `resource_name` | str(255) | Yes | Resource name |
| `changes` | JSON | Yes | before/after values |
| `ip_address` | str(45) | Yes | Client IP |
| `user_agent` | str(255) | Yes | Client user agent |
| `status` | str(20) | No | success, failure |
| `error_message` | str(500) | Yes | Error details if failed |

---

## Notifications

### NotificationConfig
Notification channel configuration

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `id` | int | No | Primary key |
| `channel_type` | str(20) | No | telegram, discord |
| `enabled` | bool | No | Is channel active? |
| `config` | JSON | No | bot_token, chat_id, webhook_url |
| `created_at` | datetime | No | When configured |
| `updated_at` | datetime | No | Last update timestamp |

### AlertConfig
Alert type configuration

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `id` | int | No | Primary key |
| `alert_type` | str(50) | No | miner_offline, high_temp, etc (unique) |
| `enabled` | bool | No | Is alert active? |
| `config` | JSON | Yes | thresholds, timeouts |
| `created_at` | datetime | No | When configured |
| `updated_at` | datetime | No | Last update timestamp |

### NotificationLog
Sent notifications log

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `id` | int | No | Primary key |
| `timestamp` | datetime | No | When sent (indexed) |
| `channel_type` | str(20) | No | telegram, discord |
| `alert_type` | str(50) | No | Alert type |
| `message` | str(1000) | No | Message sent |
| `success` | bool | No | Was send successful? |
| `error` | str(500) | Yes | Error message if failed |

---

## Common Pitfalls

### ❌ WRONG:
```python
miner.current_pool  # DOES NOT EXIST
miner.pool          # DOES NOT EXIST
telemetry.power     # DOES NOT EXIST
telemetry.uptime    # DOES NOT EXIST
```

### ✅ CORRECT:
```python
miner.current_mode          # ✓ Exists
telemetry.pool_in_use       # ✓ Pool from telemetry
telemetry.power_watts       # ✓ Correct field name
# No uptime field available!
```

---

**Last Updated**: January 24, 2026  
**Verified Against**: `app/core/database.py` (SQLAlchemy models)
