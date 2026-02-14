# Energy Provider Plugin Contract (v1)

Date: 2026-02-13

## Goal

Extract energy pricing into a provider plugin model, with Octopus Agile as the reference implementation.

This mirrors the miner/pool driver model and separates:

- core scheduling/orchestration
- provider-specific API logic
- normalized price slot contract

## Plugin Location

- Bundled providers: `bundled_config/providers/energy/`
- Deployed providers: `/config/providers/energy/`
- File naming convention: `*_provider.py`

## Core Contract

Defined in [app/providers/energy/base.py](app/providers/energy/base.py):

- `EnergyPriceProvider`
- `EnergyPriceSlot`
- `EnergyProviderMetadata`

Required methods:

- `get_metadata()`
- `validate_config(config)`
- `fetch_prices(region, start_utc, end_utc, config)`

Optional methods:

- `get_current_price(...)` (default provided)
- `health_check(...)` (default provided)

## Loader

Defined in [app/providers/energy/loader.py](app/providers/energy/loader.py):

- `EnergyProviderLoader`
- `init_energy_provider_loader()`
- `get_energy_provider_loader()`

## Reference Provider

`octopus_agile_provider.py` in [bundled_config/providers/energy](bundled_config/providers/energy)

Provider ID: `octopus_agile`

## Runtime Deployment

Startup deployment now includes energy providers:

- [entrypoint.sh](entrypoint.sh) deploys bundled provider files to `/config/providers/energy/` when empty.

## Runtime Integration (Implemented)

- Startup initialization in [app/main.py](app/main.py):
	- `init_energy_provider_loader("/config")`
- Scheduler integration in [app/core/scheduler.py](app/core/scheduler.py):
	- `_update_energy_prices()` now uses provider selection + `fetch_prices(...)`
	- Preserves existing `EnergyPrice` table upsert behavior

## Management API (Implemented)

Endpoints in [app/api/driver_management.py](app/api/driver_management.py):

- `GET /api/drivers/energy-providers/status`
- `POST /api/drivers/energy-providers/update/{provider_name}`
- `POST /api/drivers/energy-providers/update-all`

These mirror miner/pool driver management semantics and write audit records.

## Next Integration Slice

1. Add UI page section for energy provider status/update actions.
2. Add provider selection/config (`energy.provider_id`, `energy.providers.*`) in Settings UI/API.
3. Add provider health/status endpoint for operator visibility.
