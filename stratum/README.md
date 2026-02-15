# HMM-Local Stratum Gateway (Scaffold)

Companion service for local solo mining against local pruned nodes.

## Scope (current scaffold)

- Multi-coin TCP listeners:
  - BTC: `3333`
  - BCH: `3334`
  - DGB (SHA256d only): `3335`
- HTTP API on `8082`:
  - `GET /` (basic config/stats UI)
  - `GET /health`
  - `GET /config`
  - `POST /config`
  - `GET /stats`
  - `GET /stats/{coin}`
- Basic Stratum v1 method handling scaffold:
  - `mining.subscribe`
  - `mining.authorize`
  - `mining.submit`

## Notes

This is scaffolding only. Share validation, `getblocktemplate` integration, template distribution, and block submission are intentionally deferred to incremental implementation.

## Environment Variables

- `STRATUM_BIND_HOST` (default `0.0.0.0`)
- `BTC_STRATUM_PORT` (default `3333`)
- `BCH_STRATUM_PORT` (default `3334`)
- `DGB_STRATUM_PORT` (default `3335`)
- `DGB_ALGO` (default `sha256d`, enforced)
- `BTC_RPC_URL`, `BCH_RPC_URL`, `DGB_RPC_URL`
- `BTC_RPC_USER`, `BCH_RPC_USER`, `DGB_RPC_USER`
- `BTC_RPC_PASSWORD`, `BCH_RPC_PASSWORD`, `DGB_RPC_PASSWORD`
