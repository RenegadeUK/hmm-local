# Energy Provider Plugins

Drop `*_provider.py` files in this directory to add energy price providers.

## Included

- `octopus_agile_provider.py` — reference implementation for Octopus Agile UK tariff.

## Deployment

Bundled providers are copied to `/config/providers/energy/` on first run (or when empty).
