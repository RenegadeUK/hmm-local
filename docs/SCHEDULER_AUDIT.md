# Scheduler Audit (13 Feb 2026)

## Status Update (14 Feb 2026)

Post-audit hardening and cleanup have materially improved scheduler safety:

- `start()` is now guarded and idempotent (already-running short-circuit).
- Stale jobs are cleared before fresh registration when scheduler is stopped.
- Critical job registration is validated before scheduler start.
- `shutdown()` is now resilient:
   - attempts listener stop even if scheduler is already stopped,
   - handles sync/async listener stop methods,
   - clears listener references to avoid stale lifecycle state,
   - catches scheduler shutdown exceptions without crashing.
- Logging hygiene is now consistent in scheduler core paths:
   - bare `except:` removed,
   - duplicate exception logs consolidated,
   - no `print()`/`traceback.print_exc()` usage remains in scheduler.
- Current scheduler diagnostics are clean (no file-level errors).
- Guardrail tests now cover startup/validation/shutdown/listener/discovery paths.

## Scope

File audited: `app/core/scheduler.py`

## Executive Summary

The scheduler is currently a **monolithic orchestration + business logic file** with high coupling across telemetry, automation, strategy, Home Assistant, cloud push, analytics aggregation, and database maintenance.

Current condition is functional but carries elevated risk for regressions and slow feature velocity.

## Key Metrics

- File length: **4918 lines**
- Methods in `SchedulerService`: **70** (after duplicate cleanup)
- Job registrations in `start()`: **51**
- `print()` calls: **174**
- `logger.*` calls: **137**
- `start()` method length: **388 lines**

## Critical Findings

1. **Monolithic startup registration**
   - `start()` registers most jobs, starts scheduler, then continues adding jobs.
   - Hard to reason about startup order and side-effects.

2. **Mixed concerns in one class**
   - Telemetry collection, cloud push, price band strategy, pool strategy, HA control, analytics, discovery, backups all co-located.

3. **Inconsistent logging approach**
   - Heavy mix of `print()` and structured logger calls.
   - Reduces observability consistency.

4. **Large high-risk methods**
   - `_collect_miner_telemetry`, `_collect_telemetry`, `_reconcile_automation_rules`, `_aggregate_*` contain dense branching and DB writes.

## Change Applied During Audit

To remove an active hazard, duplicate method name was cleaned up:

- Removed obsolete duplicate `_push_to_cloud()` implementation.
- Remaining canonical implementation is the one near the end of the class.

## Refactor Map (No Functional Changes)

### Phase 1 — Stabilize Entry and Ownership

- Keep `SchedulerService` as orchestration shell only.
- Split `start()` registration into private helpers:
  - `_register_telemetry_jobs()`
  - `_register_automation_jobs()`
  - `_register_strategy_jobs()`
  - `_register_ha_jobs()`
  - `_register_maintenance_jobs()`
  - `_register_immediate_startup_jobs()`
- Move `self.scheduler.start()` to end of registration consistently.

### Phase 2 — Extract Domain Modules

Suggested module layout under `app/core/scheduler_jobs/`:

- `telemetry.py`
- `automation.py`
- `agile_strategy.py`
- `home_assistant.py`
- `cloud.py`
- `pools.py`
- `maintenance.py`
- `analytics.py`
- `discovery.py`

Each module should expose focused async functions and receive dependencies explicitly (`db`, `app_config`, adapters/services).

### Phase 3 — Normalize Logging and Error Handling

- Replace `print()` calls with `logger.info/warning/error` + structured context.
- Keep event-log writes for user-facing history, but do not rely on prints.

### Phase 4 — Guardrails

- Add smoke tests for:
  - job registration count and job IDs
  - startup sequence
  - critical job execution contracts (`_collect_telemetry`, strategy reconciliation, cloud push)

## Method Heatmap (Largest Methods)

- `start()` (~388 lines)
- `_collect_miner_telemetry()` (~333 lines)
- `_aggregate_telemetry()` (~230 lines)
- `_aggregate_miner_analytics()` (~230 lines)
- `_reconcile_automation_rules()` (~205 lines)

## Recommended Next Implementation Slice

First safe slice:

1. Refactor only `start()` into `_register_*` helpers (no logic changes).
2. Convert only startup logging in this area to `logger`.
3. Validate jobs present with same IDs and triggers.

This gives immediate readability improvement with minimal behavior risk.
